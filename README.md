# BFSI DocIntel

**BFSI DocIntel** is an AI-assisted document review prototype for loan and contract workflows. It extracts information from PDF and DOCX files, retrieves relevant RBI guidance, and produces evidence-based explanations with source citations and a human-review step.

> **Important:** This is a demonstration project, not a lending decision system or legal advice. Its included regulatory material is a retrieval-oriented summary, not a complete or authoritative source of current regulations. Verify applicable RBI directions and lender policies before making real decisions.

## Features

- Parse PDF and DOCX files into page-aware text with Docling.
- Retrieve relevant passages from the included regulatory corpus using ChromaDB.
- Calculate loan affordability and risk indicators locally using deterministic rules.
- Use **Laya**, a local, rule-based classifier over compact loan facts, alongside the lending rules. Laya is not a separately trained machine-learning model.
- Generate concise, evidence-based explanations with Groq; validate citations and retry once if citations fail validation.
- Pause the workflow for human review and export an executive memo as a DOCX file.

## How it works

1. Upload a loan or contract document in the Streamlit app.
2. The app extracts text and preserves page numbers for citations.
3. For loan reviews, enter the applicant and loan details, including the source page for each field. Laya and deterministic rules calculate risk locally.
4. ChromaDB retrieves relevant passages from the local RBI-guidance corpus.
5. Groq generates an explanation from the extracted document, risk results, and retrieved passages. The app checks cited pages and regulation IDs against the available evidence.
6. Review the result in the human-review step and download the generated memo.

## Technology

Python · Streamlit · Docling · ChromaDB · LangGraph · Groq API · Pydantic · SQLite

## Requirements

- Python 3.10 or later
- A Groq API key for generating explanations

## Setup

Run these commands from the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Create a `.env` file in the project root:

```dotenv
GROQ_API_KEY=your_groq_api_key
# Optional; defaults to qwen/qwen3.8-27b
GROQ_MODEL=qwen/qwen3.8-27b
```

Keep the API key private. `.env` is excluded by `.gitignore`; do not commit or share it.

The app automatically builds the local ChromaDB collections from the included
regulatory material the first time retrieval is needed. To build them manually:

```powershell
python -m retrieval.ingest
```

Optionally check the Groq connection:

```powershell
python check_llm.py
```

Start the app:

```powershell
streamlit run app/main.py
```

Streamlit prints a local URL in the terminal, usually `http://localhost:8501`.

## Evaluation

The repository includes 30 **synthetic** loan scenarios in `eval/answers.csv`. Run the local risk gate check with:

```powershell
python -m agents.risk
```

It reports Laya's agreement with the synthetic labels, agreement with the deterministic rule assessment, and the number of cases escalated. These figures are a small, synthetic demonstration—not evidence of production accuracy or performance on real loan applications.

## Project layout

```text
agents/       Risk, explanation, compliance, and citation-validation logic
app/          Streamlit user interface
data/         Included regulatory retrieval corpus
eval/         Synthetic loan scenarios and RAG questions
graph/        LangGraph workflow and checkpoint configuration
parsers/      PDF/DOCX parsing
report/       Executive memo generation
retrieval/    ChromaDB ingestion and search
schemas/      Loan application data model
```

## Data and privacy

Uploaded documents, parsed files, local databases, generated reports, virtual environments, and `.env` files are excluded from Git. Document contents and selected evidence are sent to Groq when an explanation is requested. Do not upload sensitive or personally identifiable information unless you have approval and have reviewed the provider's data-handling terms.

## License

This project is distributed under the MIT License. See [LICENSE](LICENSE).
