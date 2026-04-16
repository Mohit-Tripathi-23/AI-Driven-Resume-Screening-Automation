#!/usr/bin/env python3
"""
Step 1: Parse resumes (PDF or DOCX) into structured JSON.

Usage:
    python tools/parse_resumes.py --input resumes/
    python tools/parse_resumes.py --input resumes/candidate.pdf

Output: .tmp/resumes/<stem>.json for each resume
"""
import argparse
import json
import re
import sys
from pathlib import Path

import pdfplumber
from docx import Document

TMP_DIR = Path(".tmp/resumes")

# ── text extraction ──────────────────────────────────────────────────────────

def extract_text_pdf(path: Path) -> str:
    pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n".join(pages)


def extract_text_docx(path: Path) -> str:
    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


# ── lightweight field extraction ─────────────────────────────────────────────

def _find_email(text: str) -> str | None:
    m = re.search(r"[\w.+\-]+@[\w\-]+\.[a-zA-Z]{2,}", text)
    return m.group(0) if m else None


def _find_phone(text: str) -> str | None:
    m = re.search(r"(\+?[\d][\d\s\-().]{7,}\d)", text)
    return m.group(0).strip() if m else None


def _find_name(text: str) -> str | None:
    """Heuristic: first non-empty line is usually the candidate's name."""
    for line in text.splitlines():
        line = line.strip()
        if line and len(line.split()) <= 5 and not re.search(r"[@\d/\\]", line):
            return line
    return None


# ── main parse ───────────────────────────────────────────────────────────────

def parse_resume(path: Path) -> dict:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        raw_text = extract_text_pdf(path)
    elif suffix in (".docx", ".doc"):
        raw_text = extract_text_docx(path)
    else:
        raise ValueError(f"Unsupported file type: {suffix!r}. Use PDF or DOCX.")

    if not raw_text.strip():
        raise ValueError(f"No text could be extracted from {path.name}. "
                         "The file may be scanned/image-only.")

    return {
        "filename": path.name,
        "path": str(path.resolve()),
        "candidate_name": _find_name(raw_text),
        "email": _find_email(raw_text),
        "phone": _find_phone(raw_text),
        "raw_text": raw_text,
        "char_count": len(raw_text),
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse resumes (PDF/DOCX) into JSON for the scoring step."
    )
    parser.add_argument(
        "--input", required=True,
        help="Path to a single resume file or a directory of resumes."
    )
    parser.add_argument(
        "--output", default=str(TMP_DIR),
        help=f"Output directory (default: {TMP_DIR})"
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if input_path.is_file():
        files = [input_path]
    elif input_path.is_dir():
        files = (
            list(input_path.glob("*.pdf"))
            + list(input_path.glob("*.docx"))
            + list(input_path.glob("*.doc"))
        )
    else:
        print(f"ERROR: {input_path} does not exist.", file=sys.stderr)
        sys.exit(1)

    if not files:
        print(f"No PDF or DOCX files found in {input_path}", file=sys.stderr)
        sys.exit(1)

    ok, failed = 0, 0
    for f in files:
        print(f"Parsing {f.name} ...", end=" ")
        try:
            data = parse_resume(f)
            out = output_dir / f"{f.stem}.json"
            out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"OK  ->  {out}")
            ok += 1
        except Exception as exc:
            print(f"FAILED  ({exc})", file=sys.stderr)
            failed += 1

    print(f"\nDone: {ok} parsed, {failed} failed.  Output in {output_dir}/")


if __name__ == "__main__":
    main()
