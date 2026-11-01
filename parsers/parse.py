import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.document import TableItem, TextItem
from docling.datamodel.pipeline_options import (
    AcceleratorDevice,
    AcceleratorOptions,
    PdfPipelineOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption
from pydantic import BaseModel


_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _build_converter(do_ocr: bool = False) -> DocumentConverter:
    pdf_options = PdfPipelineOptions()
    pdf_options.do_ocr = do_ocr
    pdf_options.generate_page_images = False
    pdf_options.generate_picture_images = False
    pdf_options.accelerator_options = AcceleratorOptions(
        num_threads=min(4, os.cpu_count() or 4),
        device=AcceleratorDevice.AUTO,
    )
    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_options),
        }
    )


_CONVERTER = _build_converter(do_ocr=False)


class ParsedDocument(BaseModel):
    filename: str
    total_pages: int
    pages: dict[int, str]
    full_tagged_text: str


def parse_file(file_path: str | Path) -> ParsedDocument:
    path = Path(file_path)
    if not path.is_absolute():
        path = _PROJECT_ROOT / path
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    result = _CONVERTER.convert(str(path))
    doc = result.document

    pages_dict: dict[int, list[str]] = {}
    for item, _level in doc.iterate_items():
        page_no = (
            item.prov[0].page_no
            if hasattr(item, "prov") and item.prov
            else 1
        )
        pages_dict.setdefault(page_no, [])

        if isinstance(item, TableItem):
            pages_dict[page_no].append(item.export_to_markdown(doc=doc))
        elif isinstance(item, TextItem):
            pages_dict[page_no].append(item.text)

    consolidated = {
        page: "\n\n".join(blocks) for page, blocks in sorted(pages_dict.items())
    }
    tagged_blocks = [
        f"=== [PAGE {page}] ===\n{text}\n=== [END PAGE {page}] ==="
        for page, text in consolidated.items()
    ]

    return ParsedDocument(
        filename=path.name,
        total_pages=max(len(consolidated), 1),
        pages=consolidated,
        full_tagged_text="\n\n".join(tagged_blocks),
    )


def _process_and_save(filename: str, apps_dir: Path, out_dir: Path) -> str:
    parsed = parse_file(apps_dir / filename)
    out_file = out_dir / f"{filename}.json"
    out_file.write_text(parsed.model_dump_json(indent=2), encoding="utf-8")
    return f"Parsed {filename} -> {parsed.total_pages} pages saved to {out_file}"


if __name__ == "__main__":
    sample_files = [
        "LOAN_001.docx",
        "LOAN_003.docx",
        "LOAN_016.pdf",
        "LOAN_018.pdf",
        "LOAN_020.pdf",
    ]
    apps_dir = _PROJECT_ROOT / "data" / "apps"
    out_dir = _PROJECT_ROOT / "data" / "parsed"
    out_dir.mkdir(parents=True, exist_ok=True)
    max_workers = min(len(sample_files), os.cpu_count() or 1)
    failures = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_process_and_save, filename, apps_dir, out_dir): filename
            for filename in sample_files
        }
        for future in as_completed(futures):
            try:
                print(future.result())
            except Exception as error:
                filename = futures[future]
                failures.append(filename)
                print(f"Failed processing {filename}: {error}")

    if failures:
        failed_files = ", ".join(sorted(failures))
        raise RuntimeError(f"Failed to parse sample documents: {failed_files}")
