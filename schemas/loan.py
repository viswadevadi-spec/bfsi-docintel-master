from typing import Literal

from pydantic import BaseModel, Field


class LoanApplication(BaseModel):
    applicant_name: str
    applicant_name_page: int | None = None
    monthly_income_inr: float = Field(gt=0)
    monthly_income_page: int | None = None
    loan_amount_inr: float = Field(gt=0)
    loan_amount_page: int | None = None
    tenure_months: int = Field(gt=0)
    tenure_page: int | None = None
    credit_score: int = Field(ge=0, le=900)
    credit_score_page: int | None = None
    existing_monthly_emi_inr: float = Field(ge=0)
    existing_emi_page: int | None = None
    employment_type: Literal["salaried", "self_employed"]
    employment_type_page: int | None = None
