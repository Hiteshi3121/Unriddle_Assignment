"""
agent.py — The core agent loop (full-context version for Groq Developer Plan).

HOW IT WORKS:
1. list_documents → see what PDFs exist
2. read_pdf → get the COMPLETE text of each document (all pages, no chunking)
3. check_drug_interactions → safety check on all medications found
4. flag_for_review → escalate each issue found
5. Produce the final structured JSON summary


NO-FABRICATION GUARDRAIL:
System prompt explicitly bans guessing. Every missing field must be marked
[MISSING — requires clinician review], never filled with a plausible value.
"""

import json
import time
import datetime
from groq import Groq
from tools import (
    list_documents, read_pdf, check_drug_interactions, flag_for_review,
    TOOL_SCHEMAS
)

MAX_STEPS = 20
MODEL = "llama-3.3-70b-versatile"


# ---------------------------------------------------------------------------
# SYSTEM PROMPT
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a clinical documentation assistant preparing a discharge summary DRAFT from hospital source documents.

You will receive the COMPLETE text of patient records. Read everything carefully before producing the summary.

## CRITICAL RULES

### Rule 1: NEVER FABRICATE
Never invent, guess, or infer clinical facts not explicitly in the source documents.
- Field not found anywhere → [MISSING — requires clinician review]
- Lab result not yet returned → [PENDING — result not yet available]
- Never fill in plausible values. Either it is documented or it is not.

### Rule 2: FLAG CONFLICTS, NEVER RESOLVE THEM
If two parts of the document disagree (different diagnoses, different doses):
- Show BOTH values
- Mark: [CONFLICTING — clinician must resolve]

### Rule 3: FLAG MEDICATION CHANGES
If a medication was added, stopped, or dose-changed with no documented reason:
- Note the change + flag: [REASON NOT DOCUMENTED — reconciliation required]

### Rule 4: DETECT MIXED PATIENT DATA
This PDF may contain records for more than one patient. Look for:
- Different patient names or MRN numbers
- Sudden diagnosis switch (e.g. gastroenteritis on page 1, DKA on page 3)
- Gender inconsistency
- Drastically different demographics (weight 48kg vs 71kg)
- Different admission dates with no link
If detected → call flag_for_review with field_name="mixed_patient_data"
Then produce SEPARATE summaries for each patient in a "patients" array.

### Rule 5: FLAG ALL SAFETY CONCERNS
Always flag:
- DAMA (discharged against medical advice)
- Vasopressor use without documented reason
- Hb drop without documented cause
- Pending cultures or imaging at time of discharge
- Medications with no documented indication
- Critical lab values outside normal range
- Incomplete discharge prescription

### Rule 6: WORKFLOW
1. Call list_documents
2. Call read_pdf for each document — you will receive the FULL text
3. Call check_drug_interactions with all medications identified
4. Call flag_for_review for EACH issue found
5. Produce the final JSON summary

### Rule 7: THIS IS ALWAYS A DRAFT
Mark is_draft: true and review_required: true always.

### Rule 8: OUTPUT FORMAT IS STRICT
Your FINAL response MUST be pure JSON only — starting with { and ending with }.
No explanation, no prose, no markdown. Just the JSON object.
If you found data in the document, USE IT — do not mark it MISSING.
Only mark MISSING if you genuinely could not find it anywhere in the full text.

### Rule 9: ASSIGN DATA TO THE CORRECT PATIENT
When you detect multiple patients, identify each patient by their unique markers —
different diagnoses, different names/MRNs, different demographics, different document types.
Then extract each field ONLY from sections that clearly belong to that patient:
- A medication list belongs to the patient whose treatment context it appears in
- A lab result belongs to the patient whose chart it was recorded in
- A hospital course belongs to the patient whose admission it describes
- If you cannot confidently attribute a piece of data to a specific patient, mark it [MISSING]
- Never fill a patient's field with data from another patient's record

## REQUIRED OUTPUT FORMAT
ALWAYS use the patients array structure below. Never use a flat single-patient structure.
All 10 sections are MANDATORY. Extract real values from the document for every field.

ALWAYS output this exact JSON structure:
{
  "mixed_patient_data_warning": "only include this field if multiple patients were detected",
  "patients": [
    {
      "patient_number": 1,
      "patient_demographics": {
        "name": "[MISSING — requires clinician review]",
        "age": "[MISSING — requires clinician review]",
        "gender": "[MISSING — requires clinician review]",
        "patient_id": "[MISSING — requires clinician review]",
        "weight": "[MISSING — requires clinician review]"
      },
      "admission_date": "[MISSING — requires clinician review]",
      "discharge_date": "[MISSING — requires clinician review]",
      "principal_diagnosis": "[MISSING — requires clinician review]",
      "secondary_diagnoses": [],
      "allergies": "[MISSING — requires clinician review]",
      "hospital_course": "[MISSING — requires clinician review]",
      "procedures": [],
      "investigations": {"labs": [], "imaging": [], "other": []},
      "discharge_condition": "[MISSING — requires clinician review]",
      "discharge_medications": [],
      "follow_up_instructions": "[MISSING — requires clinician review]",
      "pending_results": [],
      "escalation_flags": []
    }
  ],
  "is_draft": true,
  "review_required": true
}

This is the DEFAULT structure with all fields as MISSING.
Your job is to REPLACE each [MISSING] with the ACTUAL value found in the document.
IMPORTANT RULES:
- NEVER invent names like John Doe or Jane Smith — name is [MISSING] unless explicitly in the document
- NEVER invent dates like 2022-01-01 — dates are [MISSING] unless explicitly in the document
- NEVER invent diagnoses — only use diagnoses explicitly written in the document
- hospital_course: write a real paragraph from the clinical notes — only [MISSING] if zero clinical info exists
- discharge_medications: list EVERY medication from the discharge advice with dose, frequency, duration
- Replace [] arrays with actual data found — keep [] only if genuinely nothing found
- [PENDING] for results sent but not received, [CONFLICTING] when sources disagree
"""


# ---------------------------------------------------------------------------
# TOOL ROUTER
# ---------------------------------------------------------------------------

def execute_tool(tool_name: str, tool_input: dict, patient_dir: str,
                 client: Groq, escalation_list: list) -> str:
    if tool_name == "list_documents":
        result = list_documents(patient_dir)

    elif tool_name == "read_pdf":
        filename = tool_input.get("filename", "")
        result = read_pdf(filename, patient_dir, client)

    elif tool_name == "check_drug_interactions":
        medications = tool_input.get("medications", [])
        result = check_drug_interactions(medications)

    elif tool_name == "flag_for_review":
        field_name = tool_input.get("field_name", "unknown")
        reason = tool_input.get("reason", "no reason given")
        result = flag_for_review(field_name, reason, escalation_list)

    else:
        result = {"success": False, "message": f"Unknown tool: {tool_name}"}

    return json.dumps(result)


# ---------------------------------------------------------------------------
# MAIN AGENT FUNCTION
# ---------------------------------------------------------------------------

def run_agent(patient_dir: str, client: Groq) -> dict:
    """
    Runs the full agent loop for one patient folder.
    Returns: {summary, trace, escalation_flags, steps_taken}
    """
    trace = []
    escalation_list = []
    step_count = 0

    summary = {
        "error": "Agent did not complete successfully.",
        "escalation_flags": escalation_list,
        "is_draft": True,
        "review_required": True
    }

    print(f"\n{'='*60}")
    print(f"AGENT START — {patient_dir}")
    print(f"Model: {MODEL} | Max steps: {MAX_STEPS}")
    print(f"{'='*60}\n")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    while step_count < MAX_STEPS:
        step_count += 1
        print(f"[Step {step_count}] Calling Groq...")

        # Compress old read_pdf results to save tokens
        # (keeps history small while preserving the latest full document text)
        messages = _compress_old_read_pdf(messages)

        # --- Call the model (with one retry on tool_use_failed) ---
        response = None
        for attempt in range(2):
            try:
                response = client.chat.completions.create(
                    model=MODEL,
                    max_tokens=16000,
                    tools=TOOL_SCHEMAS,
                    tool_choice="auto",
                    messages=messages
                )
                break
            except Exception as e:
                err = str(e)
                if "tool_use_failed" in err and attempt == 0:
                    print(f"  WARNING: tool_use_failed — retrying...")
                    time.sleep(2)
                    continue
                trace.append({"step": step_count, "reasoning": "API error",
                               "action": "error", "input": {}, "result": err,
                               "next_decision": "Stopping."})
                print(f"  ERROR: {e}")
                response = None
                break

        if response is None:
            break

        choice = response.choices[0]
        stop_reason = choice.finish_reason
        message = choice.message
        reasoning_text = message.content or ""

        # --- Tool calls ---
        if stop_reason == "tool_calls" and message.tool_calls:
            messages.append({
                "role": "assistant",
                "content": reasoning_text,
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name,
                                  "arguments": tc.function.arguments}}
                    for tc in message.tool_calls
                ]
            })

            for tc in message.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_input = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tool_input = {}

                print(f"  -> Tool: {tool_name}")
                if tool_name != "read_pdf":  # don't spam full PDF text
                    print(f"     Input: {json.dumps(tool_input)[:200]}")

                try:
                    result_str = execute_tool(
                        tool_name, tool_input, patient_dir, client, escalation_list
                    )
                    result_data = json.loads(result_str)
                except Exception as e:
                    result_str = json.dumps({"success": False, "message": str(e)})
                    result_data = {"success": False, "message": str(e)}

                # For read_pdf, only print summary not full text
                if tool_name == "read_pdf":
                    chars = result_data.get("char_count", "?")
                    pages = result_data.get("total_pages", "?")
                    print(f"     Result: {pages} pages, {chars:,} chars extracted")
                else:
                    print(f"     Result: {result_str[:200]}")

                trace.append({
                    "step": step_count,
                    "reasoning": reasoning_text or "(no text)",
                    "action": tool_name,
                    "input": tool_input if tool_name != "read_pdf" else {"filename": tool_input.get("filename")},
                    "result": result_data if tool_name != "read_pdf" else {
                        "success": result_data.get("success"),
                        "pages": result_data.get("total_pages"),
                        "chars": result_data.get("char_count"),
                        "message": result_data.get("message")
                    },
                    "next_decision": "(continuing)"
                })

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_str
                })

        # --- Final response ---
        elif stop_reason == "stop":
            # Before accepting the final response, check if key fields are missing.
            # If so, send a recall nudge to force the model to extract them.
            raw = reasoning_text.strip()
            needs_recall = False
            try:
                test = json.loads(raw) if raw.startswith("{") else {}
                patients_list = test.get("patients", [test])
                for pt in patients_list:
                    if "[MISSING" in str(pt.get("principal_diagnosis", "MISSING")):
                        needs_recall = True
                        break
                    if "[MISSING" in str(pt.get("hospital_course", "MISSING")):
                        needs_recall = True
                        break
            except Exception:
                needs_recall = True

            if needs_recall:
                print(f"  -> Key fields MISSING. Sending extraction recall...")
                recall_messages = messages + [{
                    "role": "user",
                    "content": (
                        "You have the full document text above (82,000+ chars). "
                        "Before producing JSON, answer these questions from the text:\n"
                        "1. What is the principal diagnosis for each patient? (look for DIAGNOSIS: sections)\n"
                        "2. What are the follow-up instructions? (look for FOLLOW-UP or ADVICE ON DISCHARGE)\n"
                        "3. What allergies are documented? (look for Known Drug Allergies)\n"
                        "4. What is the discharge condition? (look for CONDITION AT DISCHARGE)\n"
                        "5. What procedures were done? (look for IV cannulation, Foley, Echo, CT)\n"
                        "Now produce the complete JSON summary with ALL these fields filled in from the document."
                    )
                }]
                try:
                    recall = client.chat.completions.create(
                        model=MODEL, max_tokens=16000, messages=recall_messages
                    )
                    reasoning_text = recall.choices[0].message.content or reasoning_text
                    print(f"  -> Recall complete.")
                except Exception as e:
                    print(f"  WARNING: Recall failed: {e}")

            print(f"  -> Agent finished after {step_count} steps.")

            # If model wrote prose instead of JSON, nudge it
            # IMPORTANT: Do NOT append the prose to messages — it would
            # poison the nudge by telling the model "I couldn't find things".
            cleaned = reasoning_text.strip()
            if cleaned and not cleaned.startswith("{") and not cleaned.startswith("```"):
                print(f"  -> Prose response detected. Sending JSON nudge...")
                # Send nudge WITHOUT the prose response in context
                # The full OCR text is already in messages from the read_pdf step
                nudge_messages = messages + [{
                    "role": "user",
                    "content": (
                        "You have already read the full document text above. "
                        "Now produce ONLY the discharge summary as a JSON object — "
                        "pure JSON starting with { and ending with }. "
                        "Extract all data you found in the document text. "
                        "Only use [MISSING — requires clinician review] for fields "
                        "that are genuinely not anywhere in the document. "
                        "DO NOT write any explanation — just the JSON."
                    )
                }]
                try:
                    nudge = client.chat.completions.create(
                        model=MODEL, max_tokens=16000, messages=nudge_messages
                    )
                    reasoning_text = nudge.choices[0].message.content or reasoning_text
                except Exception as e:
                    print(f"  WARNING: JSON nudge failed: {e}")

            trace.append({
                "step": step_count,
                "reasoning": "Produced final summary.",
                "action": "generate_summary",
                "input": {},
                "result": reasoning_text[:500] + "..." if len(reasoning_text) > 500 else reasoning_text,
                "next_decision": "Done."
            })

            summary = _parse_summary(reasoning_text, escalation_list)
            break

        else:
            print(f"  Unexpected stop_reason: {stop_reason}")
            trace.append({"step": step_count, "action": "unexpected_stop",
                           "result": stop_reason, "next_decision": "Stopping."})
            break

    else:
        print(f"\n! Step cap ({MAX_STEPS}) reached.")
        escalation_list.append(f"[STEP CAP] Agent stopped at {MAX_STEPS} steps — summary may be incomplete.")
        summary = {"error": "Step cap reached", "escalation_flags": escalation_list}

    print(f"\n{'='*60}")
    print(f"AGENT DONE — {step_count} steps, {len(escalation_list)} flags")
    print(f"{'='*60}\n")

    return {
        "summary": summary,
        "trace": trace,
        "escalation_flags": escalation_list,
        "steps_taken": step_count
    }


def _compress_old_read_pdf(messages: list) -> list:
    """
    After the model has processed a read_pdf result, compress the stored
    raw text to save tokens. Keeps only the most recent read_pdf full text.
    This is still needed because with multiple documents, each full text
    stays in history and grows the context.
    """
    pdf_indices = []
    for i, msg in enumerate(messages):
        if msg.get("role") == "tool":
            try:
                content = json.loads(msg["content"])
                if "total_pages" in content and "text" in content:
                    pdf_indices.append(i)
            except Exception:
                pass

    # Compress all except the most recent read_pdf result
    for idx in pdf_indices[:-1]:
        try:
            content = json.loads(messages[idx]["content"])
            filename = content.get("filename", "?")
            pages = content.get("total_pages", "?")
            messages[idx]["content"] = json.dumps({
                "success": True,
                "filename": filename,
                "total_pages": pages,
                "text": f"[Full text of {filename} ({pages} pages) — already processed by agent]",
                "message": "Document already read and analyzed."
            })
        except Exception:
            pass

    return messages


def _parse_summary(text: str, escalation_list: list) -> dict:
    """
    Parse JSON summary from model response. Tries multiple strategies. Never crashes.

    Strategy 1: Direct parse after stripping markdown fences
    Strategy 2: Extract largest JSON object (find outermost { ... })
    Strategy 3: If text is a JSON string containing JSON (double-encoded), decode twice
    """
    def _attach_metadata(s: dict) -> dict:
        if "escalation_flags" not in s:
            s["escalation_flags"] = []
        s["escalation_flags"].extend(escalation_list)
        s["generated_at"] = datetime.datetime.now().isoformat()
        s["is_draft"] = True
        s["review_required"] = True
        return s

    cleaned = text.strip()

    # Strip markdown code fences
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
        cleaned = cleaned.strip()

    # Strategy 1: direct parse
    try:
        return _attach_metadata(json.loads(cleaned))
    except json.JSONDecodeError:
        pass

    # Strategy 2: find outermost { ... } and parse that
    try:
        start = cleaned.index("{")
        end = cleaned.rindex("}") + 1
        return _attach_metadata(json.loads(cleaned[start:end]))
    except (ValueError, json.JSONDecodeError):
        pass

    # Strategy 3: double-encoded — text is a JSON string containing JSON
    try:
        inner = json.loads(cleaned)  # parse as string
        if isinstance(inner, str):
            return _attach_metadata(json.loads(inner))
    except (json.JSONDecodeError, TypeError):
        pass

    # All strategies failed — preserve raw output
    return {
        "raw_output": text,
        "parse_error": "Could not parse JSON from model response. Raw output preserved.",
        "escalation_flags": escalation_list + ["[PARSE ERROR] Summary could not be structured."],
        "generated_at": datetime.datetime.now().isoformat(),
        "is_draft": True,
        "review_required": True
    }
