from __future__ import annotations

import argparse
import json
from html import escape
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
RESULTS_DIR = ROOT / "results"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _badge_class(value: str) -> str:
    normalized = (value or "").lower()
    if normalized in {"completed", "true", "correct_answer"}:
        return "ok"
    if normalized in {"unknown_error", "missing", "none", ""}:
        return "neutral"
    if normalized in {"problem_formalization", "reference_build", "student_formalization", "evidence", "diagnosis", "hint"}:
        return "bad"
    if "error" in normalized or "mismatch" in normalized or "fail" in normalized:
        return "warn"
    return "neutral"


def _metric_cards(summary: dict[str, Any]) -> str:
    cards = [
        ("Samples", summary.get("sample_count", 0)),
        ("Hint Verification Failures", summary.get("hint_verification_failures", 0)),
        ("Final Correctness Agreement", summary.get("final_correctness_agreement", 0)),
        ("Completed", summary.get("stage_counts", {}).get("completed", 0)),
    ]
    return "".join(
        f'<div class="metric-card"><div class="metric-label">{escape(str(label))}</div><div class="metric-value">{escape(str(value))}</div></div>'
        for label, value in cards
    )


def _dict_panel(title: str, payload: dict[str, Any]) -> str:
    items = "".join(
        f'<tr><td>{escape(str(key))}</td><td>{escape(str(value))}</td></tr>'
        for key, value in payload.items()
    )
    return (
        f'<section class="panel"><h2>{escape(title)}</h2>'
        f'<table class="summary-table"><thead><tr><th>Key</th><th>Value</th></tr></thead><tbody>{items}</tbody></table></section>'
    )


def render_html(summary: dict[str, Any], rows: list[dict[str, Any]], title: str) -> str:
    summary_json = json.dumps(summary, ensure_ascii=False)
    rows_json = json.dumps(rows, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title)}</title>
  <style>
    :root {{
      --bg: #f4f7fb;
      --panel: #ffffff;
      --line: #d8e1ee;
      --ink: #17324d;
      --muted: #5d7288;
      --ok: #dff6e8;
      --ok-ink: #1f7a47;
      --warn: #fff2d8;
      --warn-ink: #9a5b00;
      --bad: #fde3e3;
      --bad-ink: #a02828;
      --neutral: #ebf1f7;
      --neutral-ink: #49627b;
      --accent: #2671d9;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: "Segoe UI", Arial, sans-serif;
    }}
    .container {{
      max-width: 1500px;
      margin: 0 auto;
      padding: 24px;
    }}
    h1 {{ margin: 0 0 8px; font-size: 28px; }}
    .subtle {{ color: var(--muted); margin-bottom: 20px; }}
    .metric-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-bottom: 20px;
    }}
    .metric-card, .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 16px;
      box-shadow: 0 8px 24px rgba(17, 40, 75, 0.06);
    }}
    .metric-label {{ color: var(--muted); font-size: 13px; margin-bottom: 8px; }}
    .metric-value {{ font-size: 26px; font-weight: 700; }}
    .panel-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 16px;
      margin-bottom: 20px;
    }}
    .summary-table, .results-table {{
      width: 100%;
      border-collapse: collapse;
    }}
    .summary-table th, .summary-table td,
    .results-table th, .results-table td {{
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      padding: 10px 8px;
      font-size: 13px;
    }}
    .controls {{
      display: grid;
      grid-template-columns: 2fr 1fr 1fr 1fr;
      gap: 12px;
      margin-bottom: 16px;
    }}
    input, select {{
      width: 100%;
      padding: 10px 12px;
      border-radius: 10px;
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
    }}
    .badge {{
      display: inline-block;
      border-radius: 999px;
      padding: 4px 9px;
      font-size: 12px;
      font-weight: 600;
      white-space: nowrap;
    }}
    .ok {{ background: var(--ok); color: var(--ok-ink); }}
    .warn {{ background: var(--warn); color: var(--warn-ink); }}
    .bad {{ background: var(--bad); color: var(--bad-ink); }}
    .neutral {{ background: var(--neutral); color: var(--neutral-ink); }}
    .results-wrap {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 16px;
      box-shadow: 0 8px 24px rgba(17, 40, 75, 0.06);
      overflow: auto;
    }}
    .hint-text {{
      max-width: 320px;
      white-space: normal;
      line-height: 1.4;
    }}
    .mono {{
      font-family: Consolas, "Courier New", monospace;
      font-size: 12px;
    }}
    .footer-note {{
      color: var(--muted);
      font-size: 13px;
      margin-top: 12px;
    }}
  </style>
</head>
<body>
  <div class="container">
    <h1>{escape(title)}</h1>
    <div class="subtle">Bản HTML trực quan hóa kết quả benchmark diagnosis + hint.</div>

    <div class="metric-grid">
      {_metric_cards(summary)}
    </div>

    <div class="panel-grid">
      {_dict_panel("Stage Counts", summary.get("stage_counts", {}))}
      {_dict_panel("Category Counts", summary.get("category_counts", {}))}
      {_dict_panel("Diagnosis Counts", summary.get("diagnosis_counts", {}))}
    </div>

    <section class="results-wrap">
      <div class="controls">
        <input id="searchBox" type="text" placeholder="Tìm theo sample_id / problem_id / hint / diagnosis..." />
        <select id="categoryFilter"><option value="">Tất cả category</option></select>
        <select id="stageFilter"><option value="">Tất cả stage</option></select>
        <select id="diagnosisFilter"><option value="">Tất cả diagnosis</option></select>
      </div>
      <table class="results-table">
        <thead>
          <tr>
            <th>Sample</th>
            <th>Category</th>
            <th>Variant</th>
            <th>Stage</th>
            <th>Diagnosis</th>
            <th>Expected</th>
            <th>Detected</th>
            <th>Hint</th>
          </tr>
        </thead>
        <tbody id="resultsBody"></tbody>
      </table>
      <div class="footer-note" id="rowCount"></div>
    </section>
  </div>

  <script>
    const summary = {summary_json};
    const rows = {rows_json};

    const searchBox = document.getElementById("searchBox");
    const categoryFilter = document.getElementById("categoryFilter");
    const stageFilter = document.getElementById("stageFilter");
    const diagnosisFilter = document.getElementById("diagnosisFilter");
    const resultsBody = document.getElementById("resultsBody");
    const rowCount = document.getElementById("rowCount");

    function badge(value) {{
      const text = value ?? "none";
      const normalized = String(text).toLowerCase();
      let cls = "neutral";
      if (normalized === "completed" || normalized === "correct_answer" || normalized === "true") cls = "ok";
      else if (normalized.includes("error") || normalized.includes("fail") || normalized.includes("mismatch")) cls = "warn";
      else if (["problem_formalization", "reference_build", "student_formalization", "evidence", "diagnosis", "hint"].includes(normalized)) cls = "bad";
      return `<span class="badge ${{cls}}">${{escapeHtml(String(text))}}</span>`;
    }}

    function escapeHtml(value) {{
      return value
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }}

    function fillSelect(select, values) {{
      const unique = [...new Set(values.filter(Boolean))].sort();
      for (const value of unique) {{
        const option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        select.appendChild(option);
      }}
    }}

    function render() {{
      const search = searchBox.value.trim().toLowerCase();
      const category = categoryFilter.value;
      const stage = stageFilter.value;
      const diagnosis = diagnosisFilter.value;

      const filtered = rows.filter((row) => {{
        const blob = JSON.stringify(row).toLowerCase();
        if (search && !blob.includes(search)) return false;
        if (category && row.category !== category) return false;
        if (stage) {{
          const rowStage = row.failing_stage || "completed";
          if (rowStage !== stage) return false;
        }}
        if (diagnosis) {{
          const rowDiagnosis = row.diagnosis_label || "missing";
          if (rowDiagnosis !== diagnosis) return false;
        }}
        return true;
      }});

      resultsBody.innerHTML = filtered.map((row) => {{
        const stage = row.failing_stage || "completed";
        const diagnosis = row.diagnosis_label || "missing";
        return `
          <tr>
            <td class="mono">${{escapeHtml(row.sample_id)}}</td>
            <td>${{escapeHtml(row.category)}}</td>
            <td>${{escapeHtml(row.variant_type || "")}}</td>
            <td>${{badge(stage)}}</td>
            <td>${{badge(diagnosis)}}<div class="mono">${{escapeHtml(String(row.diagnosis_confidence ?? ""))}}</div></td>
            <td>${{badge(String(Boolean(row.expected_correctness)))}}</td>
            <td>${{badge(String(Boolean(row.pipeline_detected_final_correct)))}}</td>
            <td class="hint-text">${{escapeHtml(row.hint_text || row.error_message || "")}}</td>
          </tr>
        `;
      }}).join("");

      rowCount.textContent = `Hiển thị ${{filtered.length}} / ${{rows.length}} sample`;
    }}

    fillSelect(categoryFilter, rows.map((row) => row.category));
    fillSelect(stageFilter, rows.map((row) => row.failing_stage || "completed"));
    fillSelect(diagnosisFilter, rows.map((row) => row.diagnosis_label || "missing"));

    searchBox.addEventListener("input", render);
    categoryFilter.addEventListener("change", render);
    stageFilter.addEventListener("change", render);
    diagnosisFilter.addEventListener("change", render);
    render();
  </script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, default=RESULTS_DIR / "hint_diagnosis_benchmark_summary.json")
    parser.add_argument("--results", type=Path, default=RESULTS_DIR / "hint_diagnosis_benchmark_results.jsonl")
    parser.add_argument("--output", type=Path, default=RESULTS_DIR / "hint_diagnosis_benchmark_report.html")
    parser.add_argument("--title", default="Hint Diagnosis Benchmark Report")
    args = parser.parse_args()

    summary = _load_json(args.summary)
    rows = _load_jsonl(args.results)
    html = render_html(summary, rows, args.title)
    args.output.write_text(html, encoding="utf-8")
    print("HTML report generated.")
    print(f"Rows: {len(rows)}")


if __name__ == "__main__":
    main()
