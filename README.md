# Discharge Summary Agent

An agentic AI system that reads messy, scanned patient PDFs and produces a structured, clinically safe discharge summary draft for clinician review.

Built for the Dscribe / Unriddle Technologies AI Engineer take-home assignment.

---

<img width="1886" height="822" alt="image" src="https://github.com/user-attachments/assets/9389cbe7-dd46-482b-bdd8-c41a8472e4ad" />

DEMO VID LINK - https://drive.google.com/file/d/1Ek_tMqilnH9BpX5y50bbf_Rhlyq0pOKj/view?usp=sharing


## How to Run

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Add your Groq API key
cp .env.example .env
# Edit .env and add: GROQ_API_KEY=gsk_your_key_here

# 3. Place patient PDFs in a folder
mkdir -p patient_data/patient_

# 4. Run the agent
python run.py --patient_dir ./patient_data/patient_

# 5. Generate visual HTML report (opens in browser automatically) //just for better visual
python generate_report.py --patient_dir ./patient_data/patient_1

# Output files saved inside the patient folder:
#   summary.json        — structured discharge summary draft
#   trace.json          — full step-by-step reasoning audit trail
#   summary_report.html — visual HTML report (open in any browser)
```

---

## Project Structure

```
├── agent.py           Core agent loop (Plan → Act → Observe → Repeat)
├── tools.py           4 tools the agent can call
├── pdf_extractor.py   PDF text extraction (text-based + vision OCR fallback)
├── run.py             CLI entry point
├── generate_report.py Converts summary.json to visual HTML report
├── schema.py          Discharge summary data structure
└── patient_data/      Place patient PDF folders here
```

---

**Architecture:**
```
list_documents
→ read_pdf                 [all 71 pages, ~70-80K+ chars]
→ check_drug_interactions
→ flag_for_review(s)
→ generate summary         [model sees ENTIRE document at once]
```

---

## Agent Loop Design

The agent follows a **Plan → Act → Observe → Repeat** loop built from scratch — no LangChain, LangGraph, or CrewAI.

**Each iteration:**
1. Model receives full conversation history + available tools
2. Model decides which tool to call (or produces final summary if done)
3. Tool runs and returns a result
4. Result is appended to conversation history
5. Loop repeats

**Tools available:**
| Tool | Purpose |
|---|---|
| `list_documents` | See all PDFs in the patient folder with page counts |
| `read_pdf` | Extract complete text from a document (vision OCR for scanned PDFs) |
| `check_drug_interactions` | Mock safety check against known dangerous drug pairs |
| `flag_for_review` | Escalate a conflict, missing field, or safety concern |

**Loop exits when:**
- Model produces the final summary (`finish_reason == "stop"`)
- Hard step cap of 20 is reached (safety limit)

---

## No-Fabrication Guardrail

The most critical design decision. Enforced at two levels:

**Level 1 — System prompt rules:**
- Never invent, guess, or infer clinical facts
- Field not found → `[MISSING — requires clinician review]`
- Result not returned → `[PENDING — result not yet available]`
- Conflicting sources → show BOTH values + `[CONFLICTING — clinician must resolve]`
- Medication change with no documented reason → `[REASON NOT DOCUMENTED]`

**Level 2 — Output always marked as draft:**
Every summary is stamped `is_draft: true` and `review_required: true`. It is never presented as a finalized clinical document.

**What the agent flags instead of guessing:**
- Mixed patient data in one file
- DAMA (discharged against medical advice)
- Pending cultures or imaging at discharge
- Medications with no documented indication
- Critical lab values outside normal range
- Hb drop without documented cause

---

## Mixed Patient Detection

The agent detects when a single PDF contains records for multiple patients by looking for:
- Different diagnoses appearing in the same file (e.g. gastroenteritis on page 1, DKA on page 3)
- Drastically different demographics (weight 48kg vs 71kg)
- Gender inconsistency across pages
- Different MRN numbers or patient identifiers

When detected, the agent produces **separate summaries per patient** in a `patients` array and flags the issue for clinician verification.

---

## Failure and Conflict Handling

| Situation | Behaviour |
|---|---|
| Scanned PDF (no text layer) | Falls back to Groq vision OCR (llama-4-scout, page by page) |
| API call fails | Caught with try/except, error recorded in trace, agent continues |
| Step cap reached | Stops gracefully, adds cap-reached flag to escalation list |
| Conflicting information | Both values shown, field marked conflicting, flag raised |
| Missing field | Marked `[MISSING — requires clinician review]`, never guessed |
| Medication change, no reason | Flagged: `[REASON NOT DOCUMENTED — reconciliation required]` |
| Drug interaction found | Surfaced via `flag_for_review`, added to escalation list |
| Model produces prose not JSON | Recall nudge fires: model re-extracts key fields explicitly |
| Mixed patient data | Separate summaries produced, mixed_patient_data flag raised |

---

## Required Output Sections

Per assignment specification, every summary includes all 10 required sections:

1. **Patient demographics** — name, age, gender, patient ID, weight
2. **Admission & discharge dates**
3. **Principal and secondary diagnoses**
4. **Hospital course** — full narrative of the stay
5. **Procedures** — with dates where documented
6. **Discharge medications** — with dose, frequency, duration, and change from admission noted
7. **Allergies**
8. **Follow-up instructions**
9. **Pending results**
10. **Discharge condition**

---

## Trace Format

Every agent step is recorded for full auditability:

```json
{
  "step": 3,
  "reasoning": "(no text)",
  "action": "flag_for_review",
  "input": {
    "field_name": "mixed_patient_data",
    "reason": "Sudden diagnosis switch from gastroenteritis to DKA detected"
  },
  "result": {
    "success": true,
    "flag": "[REVIEW REQUIRED] mixed_patient_data: ..."
  },
  "next_decision": "(continuing)"
}
```
---
## What I'd Do With More Time

1. **Part 2 — Feedback loop:** Build a simulated reviewer (LLM acting as strict doctor) that edits drafts, measure edit distance before/after, inject correction examples into future prompts to reduce edit burden over iterations.
2. **Real drug interaction API:** Integrate DrugBank or OpenFDA for comprehensive safety checking.
3. **Pre-segmentation pass:** A lightweight dedicated pass to detect patient boundaries before the main agent runs, improving attribution accuracy for mixed-patient files.
4. **Evaluation harness:** Use the clean typed discharge summary (pages 1-2 of the provided PDF) as ground truth, measure field-level extraction accuracy against it automatically.
5. **Streaming output:** Use the streaming API so clinicians see the summary being generated in real time rather than waiting for the full run.
6. **Structured conflict resolution UI:** Surface conflicts in a simple web UI where a clinician can click to resolve each one, with the resolution logged back into the system.
