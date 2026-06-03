"""
tools.py — The 4 tools the agent can use.

THE 4 TOOLS:
  1. list_documents          → see all PDFs with page counts
  2. read_pdf                → extract FULL text of a document (no page limits)
  3. check_drug_interactions → mock safety check on medications
  4. flag_for_review         → escalate a conflict/missing/safety issue
"""

import os
from pdf_extractor import extract_pdf_text


# ---------------------------------------------------------------------------
# TOOL IMPLEMENTATIONS
# ---------------------------------------------------------------------------

def list_documents(patient_dir: str) -> dict:
    """Returns all PDFs in the patient folder with page counts."""
    try:
        import fitz
        files = [f for f in os.listdir(patient_dir) if f.lower().endswith(".pdf")]
        if not files:
            return {"success": False, "files": [], "message": "No PDF files found."}

        file_info = []
        for f in files:
            try:
                doc = fitz.open(os.path.join(patient_dir, f))
                pages = len(doc)
                doc.close()
            except Exception:
                pages = "unknown"
            file_info.append({"filename": f, "pages": pages})

        return {
            "success": True,
            "files": file_info,
            "message": f"Found {len(files)} document(s). Call read_pdf to get the full text of each."
        }
    except Exception as e:
        return {"success": False, "files": [], "message": str(e)}


def read_pdf(filename: str, patient_dir: str, client) -> dict:
    """
    Extracts and returns the COMPLETE text of a PDF — all pages, no truncation.
    With 300K TPM on Groq dev tier, the full text (~17K tokens for 71 pages)
    fits comfortably in one API call.
    """
    pdf_path = os.path.join(patient_dir, filename)

    if not os.path.exists(pdf_path):
        return {"success": False, "filename": filename, "text": "",
                "message": f"File not found: {filename}"}

    try:
        import fitz
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        doc.close()
    except Exception:
        total_pages = "unknown"

    try:
        text = extract_pdf_text(pdf_path, client)

        if not text.strip():
            return {"success": False, "filename": filename, "text": "",
                    "total_pages": total_pages,
                    "message": f"Could not extract text from {filename}."}

        return {
            "success": True,
            "filename": filename,
            "text": text,
            "total_pages": total_pages,
            "char_count": len(text),
            "message": f"Full text extracted from {filename} ({total_pages} pages, {len(text):,} chars). Analyze the complete text now."
        }
    except Exception as e:
        return {"success": False, "filename": filename, "text": "",
                "total_pages": total_pages, "message": str(e)}


def check_drug_interactions(medications: list) -> dict:
    """Mock drug interaction checker with hardcoded known dangerous pairs."""
    KNOWN_INTERACTIONS = {
        ("warfarin", "aspirin"):      "HIGH RISK: Warfarin + Aspirin — major bleeding risk.",
        ("warfarin", "ibuprofen"):    "HIGH RISK: Warfarin + Ibuprofen — major bleeding risk.",
        ("metformin", "contrast"):    "CAUTION: Metformin should be held before contrast procedures.",
        ("lisinopril", "potassium"):  "CAUTION: Lisinopril + Potassium — risk of hyperkalemia.",
        ("ssri", "tramadol"):         "HIGH RISK: SSRI + Tramadol — serotonin syndrome risk.",
        ("digoxin", "amiodarone"):    "HIGH RISK: Digoxin + Amiodarone — toxicity risk.",
        ("noradrenaline", "tramadol"):"CAUTION: Noradrenaline + Tramadol — cardiovascular monitoring needed.",
        ("insulin", "alcohol"):       "CAUTION: Insulin + Alcohol — hypoglycaemia risk.",
    }

    found = []
    meds_lower = [m.lower() for m in medications]
    for (a, b), warning in KNOWN_INTERACTIONS.items():
        if any(a in m for m in meds_lower) and any(b in m for m in meds_lower):
            found.append(warning)

    if found:
        return {"success": True, "interactions_found": True, "warnings": found,
                "message": f"{len(found)} interaction(s) detected — must be reviewed."}
    return {"success": True, "interactions_found": False, "warnings": [],
            "message": "No interactions detected. Note: mock database only."}


def flag_for_review(field_name: str, reason: str, escalation_list: list) -> dict:
    """Adds a flag to the escalation list for mandatory clinician review."""
    flag = f"[REVIEW REQUIRED] {field_name}: {reason}"
    escalation_list.append(flag)
    return {"success": True, "flag": flag,
            "message": f"Flagged '{field_name}' for clinician review."}


# ---------------------------------------------------------------------------
# TOOL SCHEMAS — OpenAI / Groq format
# ---------------------------------------------------------------------------

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_documents",
            "description": "List all available PDF documents with page counts. Call this first.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_pdf",
            "description": (
                "Extract the COMPLETE text of a PDF document — all pages, no truncation. "
                "This returns the full document content so you can analyze everything at once. "
                "After reading, identify all patients, extract all clinical data, "
                "detect mixed patient records, and prepare for the final summary."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Exact filename from list_documents (e.g. 'patient.pdf')"
                    }
                },
                "required": ["filename"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_drug_interactions",
            "description": (
                "Check a list of medications for dangerous interactions. "
                "Call this after identifying all discharge medications. "
                "Include medications from ALL patients found in the document."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "medications": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Full medication list with doses where available"
                    }
                },
                "required": ["medications"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "flag_for_review",
            "description": (
                "Flag an issue for mandatory clinician review. Use for: "
                "missing fields, conflicting data, medication changes without reasons, "
                "pending results, drug interactions, DAMA, mixed patient records, "
                "critical lab values, undocumented medications, safety concerns."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "field_name": {"type": "string",
                                   "description": "Field or issue name (e.g. 'mixed_patient_data', 'discharge_medications')"},
                    "reason": {"type": "string",
                               "description": "Specific reason why clinician review is needed"}
                },
                "required": ["field_name", "reason"]
            }
        }
    }
]
