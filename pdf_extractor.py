"""
pdf_extractor.py — Extracts full text from a PDF file.

Strategy:
1. Try pdfplumber first (fast, no API, works for digital PDFs)
2. If empty → use Groq vision OCR page by page (for scanned/handwritten PDFs)
3. Returns the COMPLETE text of the document — no truncation, no chunking.

"""

import os
import time
import base64
import warnings
import pdfplumber
import fitz  # pymupdf


def _extract_with_pdfplumber(pdf_path: str) -> str:
    text_parts = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
    except Exception as e:
        warnings.warn(f"pdfplumber failed on {pdf_path}: {e}")
    return "\n".join(text_parts)


def _extract_with_vision(pdf_path: str, client) -> str:
    """
    Page-by-page vision OCR using llama-4-scout (supports images).
    300K TPM on dev tier — safe to process 71 pages with 0.5s sleep.
    """
    text_parts = []

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        warnings.warn(f"pymupdf could not open {pdf_path}: {e}")
        return ""

    total = len(doc)
    print(f"    [Vision OCR] {total} pages — processing with Groq llama-4-scout...")

    for page_num in range(total):
        try:
            page = doc[page_num]
            mat = fitz.Matrix(100 / 72, 100 / 72)
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")

            # Re-render at lower DPI if too large
            if len(img_bytes) > 3.5 * 1024 * 1024:
                mat = fitz.Matrix(72 / 72, 72 / 72)
                pix = page.get_pixmap(matrix=mat)
                img_bytes = pix.tobytes("png")

            img_b64 = base64.standard_b64encode(img_bytes).decode("utf-8")

            response = client.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                max_tokens=2000,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{img_b64}"}
                        },
                        {
                            "type": "text",
                            "text": (
                                "Transcribe all text from this medical document page exactly as written. "
                                "Do not summarize or interpret. If unclear, write [ILLEGIBLE]. "
                                "Preserve all labels, values, dates, medication names, dosages, and table data."
                            )
                        }
                    ]
                }]
            )

            page_text = response.choices[0].message.content
            text_parts.append(f"[Page {page_num + 1}]\n{page_text}")

            if (page_num + 1) % 10 == 0:
                print(f"    [Vision OCR] {page_num + 1}/{total} pages done...")

            # 0.5s sleep — safe with 300K TPM dev tier
            time.sleep(0.5)

        except Exception as e:
            warnings.warn(f"Vision OCR failed on page {page_num + 1}: {e}")
            text_parts.append(f"[Page {page_num + 1}]\n[EXTRACTION FAILED]")
            time.sleep(1.0)  # longer pause on error

    doc.close()
    print(f"    [Vision OCR] Complete. {len(text_parts)} pages extracted.")
    return "\n\n".join(text_parts)


def extract_pdf_text(pdf_path: str, client) -> str:
    """
    Returns the COMPLETE text of a PDF — all pages, no truncation.
    Tries pdfplumber first, falls back to Groq vision OCR for scanned docs.
    """
    if not os.path.exists(pdf_path):
        warnings.warn(f"PDF not found: {pdf_path}")
        return ""

    text = _extract_with_pdfplumber(pdf_path)
    if text.strip():
        return text

    warnings.warn(f"No text via pdfplumber — using vision OCR: {pdf_path}")
    return _extract_with_vision(pdf_path, client)
