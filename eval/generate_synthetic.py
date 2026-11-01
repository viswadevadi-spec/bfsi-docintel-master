import csv
import random
from pathlib import Path

from docx import Document
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


ROOT_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT_DIR / "data" / "apps"
CSV_PATH = ROOT_DIR / "eval" / "answers.csv"

FIRST_NAMES = [
    "Aarav",
    "Vivaan",
    "Aditya",
    "Vihaan",
    "Arjun",
    "Sai",
    "Riya",
    "Aadhya",
    "Diya",
    "Ananya",
]
LAST_NAMES = [
    "Sharma",
    "Verma",
    "Reddy",
    "Nair",
    "Patel",
    "Iyer",
    "Rao",
    "Gupta",
    "Singh",
    "Joshi",
]
EMP_TYPES = ["salaried", "self_employed"]


def compute_ground_truth_risk(income, loan_amt, tenure, credit, existing_emi):
    rate = 0.105 / 12.0
    emi = loan_amt * (rate * (1 + rate) ** tenure) / ((1 + rate) ** tenure - 1)
    dti = (existing_emi + emi) / income
    if dti > 0.50 or credit < 650:
        return "high"
    if dti > 0.35 or credit < 720:
        return "medium"
    return "low"


def make_docx(app_id: str, row: dict, messy: bool):
    doc = Document()
    doc.add_heading(f"Retail Loan Application - {app_id}", level=1)
    doc.add_paragraph("Confidential Financial Disclosure Document - Page 1")

    if messy:
        doc.add_page_break()
        doc.add_heading("Section B: Structured Applicant Schedule", level=2)
        table = doc.add_table(rows=4, cols=4)
        header = table.rows[0].cells
        header[0].text = "Field"
        header[1].text = "Primary Value"
        header[2].text = "Secondary Field"
        header[3].text = "Secondary Value"

        row1 = table.rows[1].cells
        row1[0].text = "Applicant Full Name"
        row1[1].text = row["applicant_name"]
        row1[2].text = "Employment Category"
        row1[3].text = row["employment_type"]

        row2 = table.rows[2].cells
        row2[0].text = "Monthly Net Income (INR)"
        row2[1].text = str(row["monthly_income_inr"])
        row2[2].text = "Existing Monthly EMIs (INR)"
        row2[3].text = str(row["existing_monthly_emi_inr"])

        row3 = table.rows[3].cells
        row3[0].text = "Requested Loan Amount (INR)"
        row3[1].text = str(row["loan_amount_inr"])
        row3[2].text = "Tenure (Months) / CIBIL"
        row3[3].text = (
            f"{row['tenure_months']} months | Score: {row['credit_score']}"
        )
    else:
        doc.add_paragraph(f"Applicant Name: {row['applicant_name']}")
        doc.add_paragraph(f"Employment Type: {row['employment_type']}")
        doc.add_paragraph(f"Monthly Income (INR): {row['monthly_income_inr']}")
        doc.add_paragraph(
            f"Existing Monthly EMIs (INR): {row['existing_monthly_emi_inr']}"
        )
        doc.add_page_break()
        doc.add_heading("Loan Terms & Bureau Summary (Page 2)", level=2)
        doc.add_paragraph(f"Requested Loan Amount (INR): {row['loan_amount_inr']}")
        doc.add_paragraph(f"Repayment Tenure (Months): {row['tenure_months']}")
        doc.add_paragraph(f"Bureau Credit Score: {row['credit_score']}")

    file_path = OUT_DIR / f"{app_id}.docx"
    doc.save(file_path)
    return file_path.name


def make_pdf(app_id: str, row: dict, two_column: bool):
    file_path = OUT_DIR / f"{app_id}.pdf"
    pdf = canvas.Canvas(str(file_path), pagesize=letter)
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(50, 750, f"BFSI Retail Credit Application: {app_id}")
    pdf.setFont("Helvetica", 11)

    if two_column:
        pdf.drawString(50, 700, f"Applicant Name: {row['applicant_name']}")
        pdf.drawString(50, 675, f"Employment Type: {row['employment_type']}")
        pdf.drawString(50, 650, f"Monthly Income (INR): {row['monthly_income_inr']}")
        pdf.drawString(
            320, 700, f"Existing Monthly EMIs (INR): {row['existing_monthly_emi_inr']}"
        )
        pdf.drawString(320, 675, f"Requested Loan Amount (INR): {row['loan_amount_inr']}")
        pdf.drawString(320, 650, f"Tenure (Months): {row['tenure_months']}")
        pdf.drawString(320, 625, f"Credit Score: {row['credit_score']}")
    else:
        pdf.drawString(50, 700, f"Applicant Name: {row['applicant_name']}")
        pdf.drawString(50, 675, f"Employment Type: {row['employment_type']}")
        pdf.drawString(50, 650, f"Monthly Income (INR): {row['monthly_income_inr']}")
        pdf.drawString(
            50, 625, f"Existing Monthly EMIs (INR): {row['existing_monthly_emi_inr']}"
        )
        pdf.showPage()
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(50, 750, "Facility Request & Credit Bureau Data")
        pdf.setFont("Helvetica", 11)
        pdf.drawString(50, 710, f"Requested Loan Amount (INR): {row['loan_amount_inr']}")
        pdf.drawString(50, 685, f"Tenure (Months): {row['tenure_months']}")
        pdf.drawString(50, 660, f"Credit Score: {row['credit_score']}")

    pdf.save()
    return file_path.name


def main():
    random.seed(42)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []

    for i in range(1, 31):
        app_id = f"LOAN_{i:03d}"
        income = float(random.choice([35000, 50000, 75000, 120000, 180000, 250000]))
        loan_amt = float(random.choice([200000, 500000, 1200000, 2500000, 4000000]))
        tenure = random.choice([12, 24, 36, 60, 120])
        credit = random.choice([580, 640, 690, 715, 760, 810])
        existing_emi = float(random.choice([0, 5000, 12000, 25000, 40000]))
        employment_type = random.choice(EMP_TYPES)
        applicant_name = (
            f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        )
        expected_risk = compute_ground_truth_risk(
            income, loan_amt, tenure, credit, existing_emi
        )

        row = {
            "app_id": app_id,
            "applicant_name": applicant_name,
            "monthly_income_inr": income,
            "loan_amount_inr": loan_amt,
            "tenure_months": tenure,
            "credit_score": credit,
            "existing_monthly_emi_inr": existing_emi,
            "employment_type": employment_type,
            "expected_risk": expected_risk,
        }
        if i <= 15:
            row["filename"] = make_docx(app_id, row, messy=(i % 3 == 0))
        else:
            row["filename"] = make_pdf(app_id, row, two_column=(i % 3 == 0))
        rows.append(row)

    with CSV_PATH.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Generated 30 files in {OUT_DIR} and ground-truth labels in {CSV_PATH}")


if __name__ == "__main__":
    main()
