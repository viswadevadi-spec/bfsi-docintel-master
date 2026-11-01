import csv
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from schemas.loan import LoanApplication


ROOT_DIR = Path(__file__).resolve().parents[1]


class RatioResult(BaseModel):
    proposed_emi_inr: float
    emi_to_income: float
    dti_ratio: float
    ltv_ratio: float | None = None
    rule_risk: Literal["low", "medium", "high"]


class LayaOutput(BaseModel):
    label: Literal["low", "medium", "high"]
    confidence: float


class CompactRiskFacts(BaseModel):
    monthly_income_inr: float
    loan_amount_inr: float
    tenure_months: int
    credit_score: int
    existing_monthly_emi_inr: float
    employment_type: Literal["salaried", "self_employed"]
    dti_ratio: float


class RiskGateOutput(BaseModel):
    ratios: RatioResult
    laya: LayaOutput
    final_risk: Literal["low", "medium", "high"]
    escalate: bool
    escalation_reason: str | None = None


def calculate_ratios(
    app: LoanApplication, collateral_inr: float | None = None
) -> RatioResult:
    rate = 0.105 / 12.0
    months = app.tenure_months
    principal = app.loan_amount_inr
    emi = principal * (rate * (1 + rate) ** months) / (
        (1 + rate) ** months - 1
    )

    emi_to_income = emi / app.monthly_income_inr
    dti = (app.existing_monthly_emi_inr + emi) / app.monthly_income_inr
    ltv = (
        principal / collateral_inr
        if collateral_inr is not None and collateral_inr > 0
        else None
    )

    if dti > 0.50 or app.credit_score < 650 or (ltv is not None and ltv > 0.85):
        rule_risk: Literal["low", "medium", "high"] = "high"
    elif (
        dti > 0.35
        or app.credit_score < 720
        or (ltv is not None and ltv > 0.75)
    ):
        rule_risk = "medium"
    else:
        rule_risk = "low"

    return RatioResult(
        proposed_emi_inr=round(emi, 2),
        emi_to_income=round(emi_to_income, 4),
        dti_ratio=round(dti, 4),
        ltv_ratio=round(ltv, 4) if ltv is not None else None,
        rule_risk=rule_risk,
    )


class LayaClassifier:
    """Local calibrated compact-facts classifier; replaceable with a model backend."""

    def classify(self, compact_facts_json: str) -> LayaOutput:
        facts = CompactRiskFacts.model_validate_json(compact_facts_json)

        score = 0.0
        if facts.credit_score < 650:
            score += 0.55
        elif facts.credit_score < 720:
            score += 0.30

        if facts.dti_ratio > 0.50:
            score += 0.45
        elif facts.dti_ratio > 0.35:
            score += 0.25

        if (
            facts.employment_type == "self_employed"
            and facts.dti_ratio > 0.32
        ):
            score += 0.15

        if score >= 0.55:
            return LayaOutput(
                label="high",
                confidence=round(min(0.95, 0.50 + score * 0.4), 2),
            )
        if score >= 0.25:
            confidence = 0.68 if 0.25 <= score <= 0.35 else 0.82
            return LayaOutput(label="medium", confidence=confidence)
        return LayaOutput(label="low", confidence=0.91)


_LAYA_CLASSIFIER = LayaClassifier()


def run_laya_classifier(app: LoanApplication, ratios: RatioResult) -> LayaOutput:
    compact_facts = CompactRiskFacts(
        monthly_income_inr=app.monthly_income_inr,
        loan_amount_inr=app.loan_amount_inr,
        tenure_months=app.tenure_months,
        credit_score=app.credit_score,
        existing_monthly_emi_inr=app.existing_monthly_emi_inr,
        employment_type=app.employment_type,
        dti_ratio=ratios.dti_ratio,
    )
    compact_facts_json = json.dumps(
        compact_facts.model_dump(), separators=(",", ":")
    )
    return _LAYA_CLASSIFIER.classify(compact_facts_json)


def evaluate_risk(
    app: LoanApplication, confidence_threshold: float = 0.75
) -> RiskGateOutput:
    ratios = calculate_ratios(app)
    laya = run_laya_classifier(app, ratios)

    reasons = []
    if laya.confidence < confidence_threshold:
        reasons.append(
            f"Low Laya confidence ({laya.confidence} < {confidence_threshold})"
        )
    if laya.label != ratios.rule_risk:
        reasons.append(f"Disagreement: Laya={laya.label} vs Rules={ratios.rule_risk}")

    tier_order = {"low": 0, "medium": 1, "high": 2}
    final_risk = (
        laya.label
        if tier_order[laya.label] >= tier_order[ratios.rule_risk]
        else ratios.rule_risk
    )

    return RiskGateOutput(
        ratios=ratios,
        laya=laya,
        final_risk=final_risk,
        escalate=bool(reasons),
        escalation_reason="; ".join(reasons) if reasons else None,
    )


def _application_from_row(row: dict[str, str]) -> LoanApplication:
    return LoanApplication(
        applicant_name=row["applicant_name"],
        applicant_name_page=1,
        monthly_income_inr=float(row["monthly_income_inr"]),
        monthly_income_page=1,
        loan_amount_inr=float(row["loan_amount_inr"]),
        loan_amount_page=1,
        tenure_months=int(row["tenure_months"]),
        tenure_page=1,
        credit_score=int(row["credit_score"]),
        credit_score_page=1,
        existing_monthly_emi_inr=float(row["existing_monthly_emi_inr"]),
        existing_emi_page=1,
        employment_type=row["employment_type"],
        employment_type_page=1,
    )


def main() -> None:
    answers_path = ROOT_DIR / "eval" / "answers.csv"
    with answers_path.open("r", encoding="utf-8", newline="") as csv_file:
        rows = list(csv.DictReader(csv_file))
    if not rows:
        raise ValueError(f"No evaluation cases found in {answers_path}")

    laya_correct = 0
    agree_count = 0
    escalated_count = 0
    for row in rows:
        app = _application_from_row(row)
        result = evaluate_risk(app)
        if result.laya.label == row["expected_risk"]:
            laya_correct += 1
        if result.laya.label == result.ratios.rule_risk:
            agree_count += 1
        if result.escalate:
            escalated_count += 1

    count = len(rows)
    accuracy_pct = laya_correct / count * 100
    agreement_pct = agree_count / count * 100
    escalation_pct = escalated_count / count * 100
    print("=== STEP 9 GATE CHECK (30 CASES) ===")
    print(
        f"Laya Accuracy vs Ground Truth : "
        f"{laya_correct}/{count} ({accuracy_pct:.1f}%)"
    )
    print(
        f"Laya-Rule Agreement Rate      : "
        f"{agree_count}/{count} ({agreement_pct:.1f}%)"
    )
    print(
        f"Cases Escalated to Human      : "
        f"{escalated_count}/{count} ({escalation_pct:.1f}%)"
    )


if __name__ == "__main__":
    main()
