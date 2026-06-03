"""
run.py — Entry point. Run this to process a patient folder.

USAGE:
    python run.py --patient_dir ./patient_data/patient_2

OUTPUT:
    ./patient_data/patient_2/summary.json   <- the discharge summary draft
    ./patient_data/patient_2/trace.json     <- step-by-step agent reasoning
"""

import os
import json
import argparse
from dotenv import load_dotenv
from groq import Groq

from agent import run_agent


def main():
    parser = argparse.ArgumentParser(
        description="Discharge Summary Agent — generates a structured summary from patient PDFs"
    )
    parser.add_argument(
        "--patient_dir",
        type=str,
        required=True,
        help="Path to the folder containing the patient's PDF files"
    )
    args = parser.parse_args()
    patient_dir = args.patient_dir

    # --- Load API key ---
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("ERROR: GROQ_API_KEY not found.")
        print("Create a .env file with: GROQ_API_KEY=your_key_here")
        print("Get a free key at: https://console.groq.com")
        return

    # --- Validate patient directory ---
    if not os.path.isdir(patient_dir):
        print(f"ERROR: Directory not found: {patient_dir}")
        return

    pdfs = [f for f in os.listdir(patient_dir) if f.lower().endswith(".pdf")]
    if not pdfs:
        print(f"ERROR: No PDF files found in: {patient_dir}")
        return

    print(f"Found {len(pdfs)} PDF(s) in {patient_dir}: {pdfs}")

    # --- Create Groq client ---
    client = Groq(api_key=api_key)

    # --- Run the agent ---
    print("\nStarting agent...\n")
    result = run_agent(patient_dir=patient_dir, client=client)

    # --- Save outputs ---
    summary_path = os.path.join(patient_dir, "summary.json")
    trace_path = os.path.join(patient_dir, "trace.json")

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(result["summary"], f, indent=2, ensure_ascii=False)

    with open(trace_path, "w", encoding="utf-8") as f:
        json.dump(result["trace"], f, indent=2, ensure_ascii=False)

    # --- Print results ---
    print("\n" + "="*60)
    print("RESULTS")
    print("="*60)
    print(f"Steps taken    : {result['steps_taken']}")
    print(f"Flags raised   : {len(result['escalation_flags'])}")
    print(f"Summary saved  : {summary_path}")
    print(f"Trace saved    : {trace_path}")

    if result["escalation_flags"]:
        print("\nFLAGS RAISED FOR CLINICIAN REVIEW:")
        for flag in result["escalation_flags"]:
            print(f"  !  {flag}")

    print("\nDone. Both files saved — open them in VS Code to review.")


if __name__ == "__main__":
    main()
