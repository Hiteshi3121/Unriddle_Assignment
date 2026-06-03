"""
generate_report.py — Converts summary.json into a visual HTML report.

USAGE:
    python generate_report.py --patient_dir ./patient_data/patient_2

OUTPUT:
    ./patient_data/patient_2/summary_report.html

Opens in any browser. No internet required — all CSS is inline.
"""

import json
import argparse
import os
from datetime import datetime


def badge(text: str) -> str:
    """Color-code special status values."""
    if not isinstance(text, str):
        return str(text)
    t = text.strip()
    if "[MISSING" in t:
        return f'<span class="badge missing">{t}</span>'
    if "[PENDING" in t:
        return f'<span class="badge pending">{t}</span>'
    if "[CONFLICTING" in t:
        return f'<span class="badge conflict">{t}</span>'
    if "[REVIEW REQUIRED]" in t:
        return f'<span class="badge flag">{t}</span>'
    if "[REASON NOT DOCUMENTED" in t:
        return f'<span class="badge flag">{t}</span>'
    if "[PARSE ERROR" in t:
        return f'<span class="badge missing">{t}</span>'
    return t


def val(v) -> str:
    """Render any value as HTML."""
    if isinstance(v, list):
        if not v:
            return '<span class="empty">—</span>'
        return "<ul>" + "".join(f"<li>{badge(str(i))}</li>" for i in v) + "</ul>"
    if isinstance(v, dict):
        rows = "".join(
            f"<tr><td class='key'>{k}</td><td>{val(v2)}</td></tr>"
            for k, v2 in v.items()
        )
        return f"<table class='inner'>{rows}</table>"
    return badge(str(v)) if v is not None else '<span class="empty">—</span>'


def render_medications(meds) -> str:
    if not meds or not isinstance(meds, list):
        return '<p class="missing-text">[MISSING — requires clinician review]</p>'
    rows = ""
    for m in meds:
        if not isinstance(m, dict):
            rows += f"<tr><td colspan='5'>{badge(str(m))}</td></tr>"
            continue
        change = m.get("change_from_admission", "unknown")
        change_class = ""
        if "new" in str(change).lower():
            change_class = "new-med"
        elif "stopped" in str(change).lower():
            change_class = "stopped-med"
        elif "changed" in str(change).lower():
            change_class = "changed-med"

        rows += f"""<tr>
            <td><strong>{badge(m.get('medication','—'))}</strong></td>
            <td>{badge(m.get('dose','—'))}</td>
            <td>{badge(m.get('frequency','—'))}</td>
            <td>{badge(m.get('duration','—'))}</td>
            <td class="{change_class}">{badge(str(change))}</td>
        </tr>"""

    return f"""<table class="med-table">
        <thead>
            <tr>
                <th>Medication</th>
                <th>Dose</th>
                <th>Frequency</th>
                <th>Duration</th>
                <th>Change from Admission</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>"""


def render_flags(flags) -> str:
    if not flags:
        return '<p class="ok-text">✓ No flags raised</p>'
    items = ""
    for f in flags:
        items += f'<div class="flag-item">{badge(str(f))}</div>'
    return items


def render_patient(p: dict, number: int) -> str:
    d = p.get("patient_demographics", {})
    investigations = p.get("investigations", {})

    demo_rows = ""
    for k, v2 in d.items():
        demo_rows += f"<tr><td class='key'>{k.replace('_',' ').title()}</td><td>{badge(str(v2))}</td></tr>"

    return f"""
    <div class="patient-card">
        <div class="patient-header">Patient {number}</div>

        <div class="section-grid">

            <div class="section">
                <div class="section-title">Demographics</div>
                <table class="inner">{demo_rows}</table>
            </div>

            <div class="section">
                <div class="section-title">Dates</div>
                <table class="inner">
                    <tr><td class="key">Admission</td><td>{badge(str(p.get('admission_date','—')))}</td></tr>
                    <tr><td class="key">Discharge</td><td>{badge(str(p.get('discharge_date','—')))}</td></tr>
                    <tr><td class="key">Discharge Condition</td><td>{badge(str(p.get('discharge_condition','—')))}</td></tr>
                </table>
            </div>

            <div class="section">
                <div class="section-title">Diagnosis</div>
                <table class="inner">
                    <tr><td class="key">Principal</td><td>{badge(str(p.get('principal_diagnosis','—')))}</td></tr>
                    <tr><td class="key">Secondary</td><td>{val(p.get('secondary_diagnoses',[]))}</td></tr>
                    <tr><td class="key">Allergies</td><td>{badge(str(p.get('allergies','—')))}</td></tr>
                </table>
            </div>

        </div>

        <div class="section full-width">
            <div class="section-title">Hospital Course</div>
            <p class="narrative">{badge(str(p.get('hospital_course','—')))}</p>
        </div>

        <div class="section full-width">
            <div class="section-title">Discharge Medications <span class="subtitle">(changes from admission noted)</span></div>
            {render_medications(p.get('discharge_medications'))}
        </div>

        <div class="section-grid">

            <div class="section">
                <div class="section-title">Procedures</div>
                {val(p.get('procedures', []))}
            </div>

            <div class="section">
                <div class="section-title">Pending Results</div>
                {val(p.get('pending_results', []))}
            </div>

            <div class="section">
                <div class="section-title">Follow-up Instructions</div>
                <p>{badge(str(p.get('follow_up_instructions','—')))}</p>
            </div>

        </div>

        <div class="section full-width">
            <div class="section-title">Investigations</div>
            <div class="section-grid">
                <div>
                    <div class="sub-title">Labs</div>
                    {val(investigations.get('labs', []))}
                </div>
                <div>
                    <div class="sub-title">Imaging</div>
                    {val(investigations.get('imaging', []))}
                </div>
                <div>
                    <div class="sub-title">Other</div>
                    {val(investigations.get('other', []))}
                </div>
            </div>
        </div>

        <div class="section full-width">
            <div class="section-title flags-title">Escalation Flags for This Patient</div>
            {render_flags(p.get('escalation_flags', []))}
        </div>

    </div>
    """


def generate_html(summary: dict, output_path: str):
    generated_at = summary.get("generated_at", datetime.now().isoformat())
    try:
        dt = datetime.fromisoformat(generated_at)
        generated_str = dt.strftime("%d %b %Y, %I:%M %p")
    except Exception:
        generated_str = generated_at

    # Handle both single patient and multi-patient formats
    patients = summary.get("patients", [])
    if not patients and "principal_diagnosis" in summary:
        patients = [summary]  # single patient without array

    mixed_warning = summary.get("mixed_patient_data_warning", "")
    all_flags = summary.get("escalation_flags", [])

    patients_html = ""
    for i, p in enumerate(patients):
        num = p.get("patient_number", i + 1)
        patients_html += render_patient(p, num)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Discharge Summary Report</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f0f2f5; color: #222; font-size: 14px; }}

        .draft-banner {{
            background: #d32f2f; color: white; text-align: center;
            padding: 10px; font-weight: bold; font-size: 15px; letter-spacing: 1px;
        }}

        .header {{
            background: #1a237e; color: white; padding: 20px 30px;
        }}
        .header h1 {{ font-size: 22px; margin-bottom: 4px; }}
        .header .meta {{ font-size: 12px; opacity: 0.8; }}

        .mixed-warning {{
            background: #fff3cd; border-left: 4px solid #ffc107;
            margin: 16px 30px; padding: 12px 16px; border-radius: 4px;
            font-weight: 500;
        }}

        .global-flags {{
            margin: 16px 30px; background: #fff;
            border-radius: 8px; border: 1px solid #e0e0e0;
            padding: 16px;
        }}
        .global-flags h3 {{ color: #c62828; margin-bottom: 10px; font-size: 14px; }}

        .container {{ padding: 0 30px 30px; }}

        .patient-card {{
            background: white; border-radius: 10px; margin-bottom: 24px;
            border: 1px solid #e0e0e0; overflow: hidden;
            box-shadow: 0 2px 6px rgba(0,0,0,0.06);
        }}
        .patient-header {{
            background: #283593; color: white; padding: 12px 20px;
            font-size: 16px; font-weight: bold;
        }}

        .section {{ padding: 16px 20px; }}
        .full-width {{ border-top: 1px solid #f0f0f0; }}
        .section-grid {{
            display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 0; border-top: 1px solid #f0f0f0;
        }}
        .section-grid .section {{ border-right: 1px solid #f0f0f0; }}
        .section-grid .section:last-child {{ border-right: none; }}

        .section-title {{
            font-weight: 600; color: #1a237e; font-size: 12px;
            text-transform: uppercase; letter-spacing: 0.5px;
            margin-bottom: 10px; padding-bottom: 6px;
            border-bottom: 2px solid #e8eaf6;
        }}
        .flags-title {{ border-bottom-color: #ffcdd2; color: #c62828; }}
        .sub-title {{ font-weight: 600; color: #555; font-size: 12px; margin-bottom: 6px; }}
        .subtitle {{ font-weight: normal; color: #666; text-transform: none; letter-spacing: 0; }}

        table.inner {{ width: 100%; border-collapse: collapse; }}
        table.inner td {{ padding: 4px 8px 4px 0; vertical-align: top; }}
        table.inner td.key {{ color: #666; font-size: 12px; width: 38%; white-space: nowrap; }}

        table.med-table {{
            width: 100%; border-collapse: collapse; font-size: 13px;
        }}
        table.med-table th {{
            background: #e8eaf6; color: #1a237e; padding: 8px 10px;
            text-align: left; font-size: 12px;
        }}
        table.med-table td {{ padding: 7px 10px; border-bottom: 1px solid #f5f5f5; }}
        table.med-table tr:hover td {{ background: #fafafa; }}
        .new-med {{ color: #2e7d32; font-weight: 500; }}
        .stopped-med {{ color: #c62828; text-decoration: line-through; }}
        .changed-med {{ color: #e65100; font-weight: 500; }}

        ul {{ padding-left: 18px; }}
        ul li {{ padding: 2px 0; }}

        .badge {{
            display: inline-block; padding: 2px 8px; border-radius: 12px;
            font-size: 12px; font-weight: 500;
        }}
        .badge.missing {{ background: #ffebee; color: #c62828; }}
        .badge.pending {{ background: #fff8e1; color: #e65100; }}
        .badge.conflict {{ background: #fff3e0; color: #bf360c; }}
        .badge.flag {{ background: #fce4ec; color: #880e4f; }}

        .flag-item {{
            background: #fff8e1; border-left: 3px solid #ffc107;
            padding: 8px 12px; margin-bottom: 6px; border-radius: 0 4px 4px 0;
            font-size: 13px;
        }}

        .ok-text {{ color: #2e7d32; font-style: italic; }}
        .missing-text {{ color: #c62828; font-style: italic; }}
        .empty {{ color: #bbb; }}

        .narrative {{
            line-height: 1.7; color: #333; font-size: 13px;
            background: #fafafa; padding: 12px; border-radius: 4px;
            border-left: 3px solid #3f51b5;
        }}

        .footer {{
            text-align: center; padding: 20px; color: #999; font-size: 12px;
        }}
    </style>
</head>
<body>

<div class="draft-banner">
    ⚠ DRAFT — FOR CLINICIAN REVIEW ONLY — NOT A FINALIZED CLINICAL DOCUMENT ⚠
</div>

<div class="header">
    <h1>Discharge Summary Report</h1>
    <div class="meta">Generated: {generated_str} &nbsp;|&nbsp; Agent model: llama-3.3-70b-versatile &nbsp;|&nbsp; is_draft: true &nbsp;|&nbsp; review_required: true</div>
</div>

{'<div class="mixed-warning">⚠ ' + mixed_warning + '</div>' if mixed_warning else ''}

{f'''<div class="global-flags">
    <h3>Global Escalation Flags</h3>
    {render_flags(all_flags)}
</div>''' if all_flags else ''}

<div class="container">
    {patients_html}
</div>

<div class="footer">
    Generated by Discharge Summary Agent &nbsp;|&nbsp; Dscribe / Unriddle Technologies Assignment &nbsp;|&nbsp; Always requires clinician verification before use
</div>

</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Report saved: {output_path}")
    print(f"Open in browser: file:///{output_path.replace(chr(92), '/')}")


def main():
    parser = argparse.ArgumentParser(description="Convert summary.json to HTML report")
    parser.add_argument("--patient_dir", required=True)
    args = parser.parse_args()

    summary_path = os.path.join(args.patient_dir, "summary.json")
    output_path = os.path.join(args.patient_dir, "summary_report.html")

    if not os.path.exists(summary_path):
        print(f"ERROR: summary.json not found in {args.patient_dir}")
        print("Run the agent first: python run.py --patient_dir <dir>")
        return

    with open(summary_path, encoding="utf-8") as f:
        summary = json.load(f)

    generate_html(summary, output_path)

    # Auto-open in default browser
    import webbrowser
    webbrowser.open(f"file:///{os.path.abspath(output_path)}")


if __name__ == "__main__":
    main()
