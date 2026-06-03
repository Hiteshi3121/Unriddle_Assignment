# Discharge Summary Agent

An agentic AI system that reads messy patient source PDFs and produces a structured, clinically safe discharge summary draft for clinician review.

Built for the Dscribe / Unriddle Technologies AI Engineer take-home assignment.

---

## How to Run

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Add your API key
cp .env.example .env
# Edit .env and paste your API_KEY

# 3. Place patient PDFs in a folder
mkdir -p patient_data/patient_1

# 4. Run the agent
python run.py --patient_dir ./patient_data/patient_1

# 5. generate_report
python generate_report.py --patient_dir ./patient_data/patient_2

# Output files are saved inside the patient folder:
#   patient_data/patient_1/summary.json  ← discharge summary draft
#   patient_data/patient_1/trace.json    ← full step-by-step reasoning
```

---

## Project Structure

```
├── schema.py          Shape of the discharge summary output
├── pdf_extractor.py   PDF text extraction (text-based + scanned fallback)
├── tools.py           4 tools the agent can call
├── agent.py           Core agent loop
├── run.py             CLI entry point
└── patient_data/      Place patient PDF folders here
```

---

## Agent Loop Design

The agent follows a Plan → Act → Observe → Repeat loop built from scratch.

**Each iteration:**
1. Claude receives the conversation history + available tools
2. Claude decides which tool to call (or finishes if done)
3. The tool runs and returns a result
4. The result is appended to conversation history
5. Loop repeats

**Loop exits when:**
- Claude produces the final summary (`end_turn`)
- The hard step cap of 25 is reached (safety limit)

The agent always starts by calling `list_documents` to see what source material exists, then reads each document, reconciles medications, checks for drug interactions, and flags any conflicts or missing data before generating the summary.

---

## No-Fabrication Guardrail

This is the most important design decision. It is enforced at two levels:

**Level 1 — System prompt:** Claude is explicitly told never to guess, infer, or fill in plausible values. Every section it cannot source from documents must be marked `[MISSING — requires clinician review]`. Conflicts must be shown as both values + flagged, not resolved.

**Level 2 — Output schema:** Every field in the discharge summary has a `status` attribute: `sourced`, `missing`, `pending`, or `conflicting`. This forces the agent to categorize what it found for every single field — there is no way to silently leave a gap.

The output is always marked `is_draft: true` and `review_required: true`. It is never presented as a finalized clinical document.

---

## Failure and Conflict Handling

| Situation | Behaviour |
|---|---|
| PDF not found | Returns empty result, agent flags document as unreadable |
| Scanned PDF (no text layer) | Falls back to Claude vision OCR (page-by-page) |
| API call fails | Caught with try/except, error recorded in trace, agent continues |
| Step cap reached | Stops gracefully, adds cap-reached flag to escalation list |
| Conflicting information | Both values shown, field marked `conflicting`, flag raised |
| Missing field | Marked `[MISSING — requires clinician review]`, never filled |
| Medication change, no reason | Change noted + `[REASON NOT DOCUMENTED — reconciliation required]` flag |
| Drug interaction found | Surfaced immediately via `flag_for_review`, added to escalation list |

---

## Trace Format

Every step is recorded:
```json
{
  "step": 3,
  "reasoning": "Found admission medications. Need discharge medications to compare.",
  "action": "read_pdf",
  "input": { "filename": "medications.pdf" },
  "result": { "success": true, "text": "..." },
  "next_decision": "Lisinopril added with no documented reason — will flag."
}
```

This makes the agent's decisions fully auditable — a clinician or engineer can trace exactly why the summary says what it says.

---

## Limitations

- **Mock drug interaction database:** The interaction checker uses a small hardcoded table. A production system would call a real clinical API (e.g., DrugBank, First Databank).
- **Vision OCR quality:** For very low-quality scans, Claude vision may miss or misread text. A production system would use a dedicated medical OCR service.
- **No memory across patients:** Each run is stateless. The agent has no knowledge of other patients or prior runs.
- **Single-agent:** Complex cases with many conflicting documents could benefit from a multi-agent design (one agent per document type, one orchestrator).
- **No fine-tuning:** The no-fabrication guardrail relies entirely on prompt engineering. A production system would want fine-tuning or RLHF to reinforce this behaviour.

---

## What I'd Do With More Time

1. **Part 2 — Feedback loop:** Build a simulated reviewer (LLM acting as strict doctor) that edits drafts, measure edit distance before/after, inject correction examples into future prompts to reduce edit burden over iterations.
2. **Real drug interaction API:** Integrate DrugBank or OpenFDA for comprehensive safety checking.
3. **Structured conflict resolution UI:** Instead of just flagging conflicts in JSON, surface them in a simple web UI where a clinician can click to resolve each one.
4. **Evaluation harness:** Create a test set of synthetic patients with known ground-truth summaries to measure extraction accuracy.
5. **Streaming output:** Use Claude's streaming API so doctors see the summary being generated in real time rather than waiting for the full run.

