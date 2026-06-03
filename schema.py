"""
schema.py — Defines the structure of a discharge summary.

WHY THIS FILE EXISTS:
Every discharge summary must have specific sections (diagnoses, medications, etc.).
By defining this structure up front, the agent always knows what it needs to fill in.
The 'status' field on every section is the core safety guardrail:
  - "sourced"     → found in documents, value is trustworthy
  - "missing"     → not found anywhere, must be reviewed by clinician
  - "pending"     → documented as pending in the source notes (e.g., lab awaiting result)
  - "conflicting" → two documents disagree, clinician must resolve
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class SummaryField:
    """
    A single field in the discharge summary.
    'value' holds what we found; 'status' tells us how confident we are.
    'flags' holds any warnings the agent wants to surface (e.g., drug interaction).
    """
    value: str = "[MISSING — requires clinician review]"
    status: str = "missing"   # one of: sourced, missing, pending, conflicting
    flags: List[str] = field(default_factory=list)  # list of warnings/notes


@dataclass
class MedicationEntry:
    """
    Represents one medication line in the discharge summary.
    'change' tells us if it's new, stopped, dose-changed, or unchanged vs admission.
    'reason' is the documented reason — if blank and there's a change, agent must flag it.
    """
    name: str = ""
    dose: str = ""
    frequency: str = ""
    change: str = "unchanged"  # new | stopped | dose-changed | unchanged
    reason: str = ""           # if change != unchanged and reason is empty → flag it
    flag: str = ""             # any reconciliation warning


@dataclass
class DischargeSummary:
    """
    The full discharge summary. One instance per patient.

    The agent fills in each SummaryField as it reads through the source PDFs.
    Fields it cannot find stay as "[MISSING — requires clinician review]".
    This document is always a DRAFT — never auto-finalized.
    """

    # --- Patient Identity ---
    patient_name:       SummaryField = field(default_factory=SummaryField)
    patient_age:        SummaryField = field(default_factory=SummaryField)
    patient_gender:     SummaryField = field(default_factory=SummaryField)
    patient_id:         SummaryField = field(default_factory=SummaryField)

    # --- Dates ---
    admission_date:     SummaryField = field(default_factory=SummaryField)
    discharge_date:     SummaryField = field(default_factory=SummaryField)

    # --- Diagnoses ---
    principal_diagnosis:   SummaryField = field(default_factory=SummaryField)
    secondary_diagnoses:   SummaryField = field(default_factory=SummaryField)

    # --- Clinical Details ---
    hospital_course:    SummaryField = field(default_factory=SummaryField)
    procedures:         SummaryField = field(default_factory=SummaryField)
    allergies:          SummaryField = field(default_factory=SummaryField)
    discharge_condition: SummaryField = field(default_factory=SummaryField)

    # --- Medications ---
    # This is a list instead of a SummaryField because there are multiple medications
    discharge_medications: List[MedicationEntry] = field(default_factory=list)
    medication_flags: List[str] = field(default_factory=list)  # reconciliation warnings

    # --- Follow-up & Pending ---
    follow_up_instructions: SummaryField = field(default_factory=SummaryField)
    pending_results:        SummaryField = field(default_factory=SummaryField)

    # --- Meta ---
    # These are filled by the agent automatically, not from the PDFs
    generated_at: str = ""
    is_draft: bool = True       # Always True — this document is never auto-finalized
    review_required: bool = True  # Always True for clinician sign-off
    escalation_flags: List[str] = field(default_factory=list)  # critical issues surfaced
