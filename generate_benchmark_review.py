"""Generate a self-contained HTML review page for benchmark draft data."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


HTML_TEMPLATE = """<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Benchmark Review</title>
  <style>
    :root {{
      --bg: #f5efe4;
      --panel: #fffaf3;
      --panel-strong: #fff;
      --ink: #1f1f1f;
      --muted: #6b665d;
      --line: #dbcdb6;
      --accent: #c75c2a;
      --accent-soft: #f4d7c8;
      --good: #2f7d4d;
      --warn: #a36700;
      --bad: #9f2d2d;
      --shadow: 0 14px 36px rgba(84, 66, 38, 0.12);
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      font-family: "Segoe UI", "Helvetica Neue", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(199, 92, 42, 0.08), transparent 28%),
        radial-gradient(circle at top right, rgba(47, 125, 77, 0.08), transparent 24%),
        linear-gradient(180deg, #f8f2e9 0%, var(--bg) 100%);
      min-height: 100vh;
    }}

    .page {{
      max-width: 1520px;
      margin: 0 auto;
      padding: 24px;
    }}

    .hero {{
      background: linear-gradient(135deg, rgba(199, 92, 42, 0.12), rgba(255, 255, 255, 0.9));
      border: 1px solid rgba(199, 92, 42, 0.18);
      border-radius: 22px;
      padding: 24px;
      box-shadow: var(--shadow);
    }}

    .hero h1 {{
      margin: 0 0 8px;
      font-size: 32px;
      line-height: 1.1;
    }}

    .hero p {{
      margin: 0;
      color: var(--muted);
      max-width: 900px;
      line-height: 1.6;
    }}

    .stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 12px;
      margin-top: 18px;
    }}

    .stat {{
      background: rgba(255, 255, 255, 0.78);
      border: 1px solid rgba(219, 205, 182, 0.9);
      border-radius: 16px;
      padding: 14px 16px;
    }}

    .stat .label {{
      display: block;
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 4px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}

    .stat .value {{
      font-size: 30px;
      font-weight: 700;
    }}

    .layout {{
      display: grid;
      grid-template-columns: 360px minmax(0, 1fr);
      gap: 18px;
      margin-top: 18px;
    }}

    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 20px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }}

    .panel h2 {{
      margin: 0;
      font-size: 18px;
    }}

    .panel-header {{
      padding: 16px 18px;
      border-bottom: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.7);
    }}

    .panel-body {{
      padding: 16px 18px;
    }}

    .filters {{
      display: grid;
      gap: 10px;
      margin-bottom: 14px;
    }}

    .filters label {{
      display: grid;
      gap: 6px;
      font-size: 13px;
      color: var(--muted);
    }}

    input, select {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 11px 12px;
      font-size: 14px;
      color: var(--ink);
      background: var(--panel-strong);
    }}

    .list-meta {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;
      color: var(--muted);
      font-size: 13px;
    }}

    .sample-list {{
      display: grid;
      gap: 10px;
      max-height: calc(100vh - 330px);
      overflow: auto;
      padding-right: 4px;
    }}

    .sample-card {{
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px;
      background: var(--panel-strong);
      cursor: pointer;
      transition: transform 0.14s ease, border-color 0.14s ease, box-shadow 0.14s ease;
    }}

    .sample-card:hover {{
      transform: translateY(-1px);
      border-color: rgba(199, 92, 42, 0.45);
      box-shadow: 0 10px 28px rgba(84, 66, 38, 0.1);
    }}

    .sample-card.active {{
      border-color: var(--accent);
      box-shadow: 0 0 0 2px rgba(199, 92, 42, 0.14);
    }}

    .sample-card h3 {{
      margin: 0 0 8px;
      font-size: 15px;
      line-height: 1.4;
    }}

    .sample-card p {{
      margin: 0;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
      display: -webkit-box;
      -webkit-line-clamp: 3;
      line-clamp: 3;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}

    .badges {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 10px;
    }}

    .badge {{
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 5px 9px;
      font-size: 12px;
      font-weight: 600;
      background: #f2ede4;
      color: #4f4a42;
    }}

    .badge.label-correct_answer {{
      background: rgba(47, 125, 77, 0.15);
      color: var(--good);
    }}

    .badge.label-arithmetic_error {{
      background: rgba(163, 103, 0, 0.16);
      color: var(--warn);
    }}

    .badge.label-quantity_relation_error,
    .badge.label-target_misunderstanding,
    .badge.label-unknown_error {{
      background: rgba(159, 45, 45, 0.12);
      color: var(--bad);
    }}

    .content-grid {{
      display: grid;
      gap: 16px;
    }}

    .section {{
      background: rgba(255, 255, 255, 0.72);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 16px;
    }}

    .section h3 {{
      margin: 0 0 12px;
      font-size: 15px;
      letter-spacing: 0.01em;
    }}

    .section p, .section li {{
      color: #33302a;
      line-height: 1.58;
    }}

    .kv {{
      display: grid;
      grid-template-columns: 180px minmax(0, 1fr);
      gap: 10px 14px;
      font-size: 14px;
    }}

    .kv .k {{
      color: var(--muted);
      font-weight: 600;
    }}

    .code-block {{
      white-space: pre-wrap;
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px;
      font-family: "Cascadia Code", Consolas, monospace;
      font-size: 13px;
      line-height: 1.55;
      max-height: 280px;
      overflow: auto;
    }}

    .table-wrap {{
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: rgba(255, 255, 255, 0.8);
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}

    th, td {{
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }}

    th {{
      background: rgba(255, 255, 255, 0.9);
      position: sticky;
      top: 0;
      z-index: 1;
    }}

    .score-bar {{
      height: 8px;
      border-radius: 999px;
      background: rgba(219, 205, 182, 0.9);
      overflow: hidden;
      margin-top: 6px;
    }}

    .score-fill {{
      height: 100%;
      background: linear-gradient(90deg, #e9b18d, var(--accent));
    }}

    .muted {{
      color: var(--muted);
    }}

    .empty {{
      padding: 26px;
      text-align: center;
      color: var(--muted);
      border: 1px dashed var(--line);
      border-radius: 16px;
      background: rgba(255,255,255,0.6);
    }}

    @media (max-width: 1180px) {{
      .layout {{
        grid-template-columns: 1fr;
      }}

      .sample-list {{
        max-height: 420px;
      }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <h1>Benchmark Draft Review</h1>
      <p>
        Trang này dùng để rà soát <strong>benchmark_draft.jsonl</strong> và
        <strong>benchmark_selection_scores.json</strong> theo dạng dễ đọc hơn.
        Bạn có thể lọc theo nhãn lỗi (diagnosis label), split, độ khó và xem chi tiết từng sample.
      </p>
      <div class="stats" id="stats"></div>
    </section>

    <div class="layout">
      <aside class="panel">
        <div class="panel-header">
          <h2>Bộ lọc benchmark</h2>
        </div>
        <div class="panel-body">
          <div class="filters">
            <label>
              Tìm theo từ khóa
              <input id="searchBox" type="search" placeholder="Tìm problem text, sample id, rationale...">
            </label>
            <label>
              Split
              <select id="splitFilter"></select>
            </label>
            <label>
              Nhãn lỗi chính
              <select id="labelFilter"></select>
            </label>
            <label>
              Độ khó
              <select id="difficultyFilter"></select>
            </label>
            <label>
              Review status
              <select id="reviewFilter"></select>
            </label>
          </div>

          <div class="list-meta">
            <span id="resultCount"></span>
            <span class="muted">Chọn một sample để xem chi tiết</span>
          </div>

          <div class="sample-list" id="sampleList"></div>
        </div>
      </aside>

      <main class="panel">
        <div class="panel-header">
          <h2>Chi tiết sample</h2>
        </div>
        <div class="panel-body">
          <div class="content-grid" id="detailPanel"></div>
        </div>
      </main>
    </div>

    <section class="panel" style="margin-top: 18px;">
      <div class="panel-header">
        <h2>Selection scores cho base problems</h2>
      </div>
      <div class="panel-body">
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Problem ID</th>
                <th>Score</th>
                <th>Lý do chấm điểm</th>
              </tr>
            </thead>
            <tbody id="scoreTableBody"></tbody>
          </table>
        </div>
      </div>
    </section>
  </div>

  <script id="benchmark-data" type="application/json">__BENCHMARK_JSON__</script>
  <script id="selection-data" type="application/json">__SELECTION_JSON__</script>
  <script>
    const benchmarkSamples = JSON.parse(document.getElementById("benchmark-data").textContent);
    const selectionScores = JSON.parse(document.getElementById("selection-data").textContent);

    const elements = {{
      stats: document.getElementById("stats"),
      sampleList: document.getElementById("sampleList"),
      detailPanel: document.getElementById("detailPanel"),
      resultCount: document.getElementById("resultCount"),
      searchBox: document.getElementById("searchBox"),
      splitFilter: document.getElementById("splitFilter"),
      labelFilter: document.getElementById("labelFilter"),
      difficultyFilter: document.getElementById("difficultyFilter"),
      reviewFilter: document.getElementById("reviewFilter"),
      scoreTableBody: document.getElementById("scoreTableBody"),
    }};

    const state = {{
      search: "",
      split: "all",
      label: "all",
      difficulty: "all",
      review: "all",
      selectedSampleId: benchmarkSamples.length ? benchmarkSamples[0].sample_id : null,
    }};

    function escapeHtml(value) {{
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }}

    function prettyJson(value) {{
      return JSON.stringify(value, null, 2);
    }}

    function uniqueValues(items, getter) {{
      return [...new Set(items.map(getter).filter(Boolean))].sort();
    }}

    function buildSelect(select, values, placeholder) {{
      select.innerHTML = "";
      const allOption = document.createElement("option");
      allOption.value = "all";
      allOption.textContent = placeholder;
      select.appendChild(allOption);
      values.forEach((value) => {{
        const option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        select.appendChild(option);
      }});
    }}

    function computeStats() {{
      const labelCounts = countBy(benchmarkSamples, (sample) => sample.gold_diagnosis.primary_label);
      const splitCounts = countBy(benchmarkSamples, (sample) => sample.split);
      const baseProblems = new Set(benchmarkSamples.map((sample) => sample.source_problem_id)).size;

      elements.stats.innerHTML = `
        <div class="stat">
          <span class="label">Tổng samples</span>
          <span class="value">${benchmarkSamples.length}</span>
        </div>
        <div class="stat">
          <span class="label">Base problems</span>
          <span class="value">${baseProblems}</span>
        </div>
        <div class="stat">
          <span class="label">Số nhãn lỗi</span>
          <span class="value">${Object.keys(labelCounts).length}</span>
        </div>
        <div class="stat">
          <span class="label">Split nhiều nhất</span>
          <span class="value">${topKey(splitCounts) || "-"}</span>
        </div>
        <div class="stat">
          <span class="label">Nhãn nhiều nhất</span>
          <span class="value">${topKey(labelCounts) || "-"}</span>
        </div>
      `;
    }}

    function countBy(items, getter) {{
      return items.reduce((acc, item) => {{
        const key = getter(item);
        acc[key] = (acc[key] || 0) + 1;
        return acc;
      }}, {{}});
    }}

    function topKey(counter) {{
      return Object.entries(counter).sort((a, b) => b[1] - a[1])[0]?.[0] || null;
    }}

    function matchesFilters(sample) {{
      const haystack = [
        sample.sample_id,
        sample.source_problem_id,
        sample.problem.text,
        sample.student_case.student_answer_raw,
        sample.gold_diagnosis.primary_label,
        sample.gold_diagnosis.localization,
        sample.gold_diagnosis.rationale,
      ].join(" ").toLowerCase();

      if (state.search && !haystack.includes(state.search)) return false;
      if (state.split !== "all" && sample.split !== state.split) return false;
      if (state.label !== "all" && sample.gold_diagnosis.primary_label !== state.label) return false;
      if (state.difficulty !== "all" && sample.problem.difficulty !== state.difficulty) return false;
      if (state.review !== "all" && sample.metadata.review_status !== state.review) return false;
      return true;
    }}

    function renderSampleList() {{
      const filtered = benchmarkSamples.filter(matchesFilters);
      elements.resultCount.textContent = `${filtered.length} sample đang hiển thị`;

      if (!filtered.length) {{
        elements.sampleList.innerHTML = `<div class="empty">Không có sample nào khớp bộ lọc hiện tại.</div>`;
        elements.detailPanel.innerHTML = `<div class="empty">Chưa có sample để hiển thị.</div>`;
        return;
      }}

      if (!filtered.some((sample) => sample.sample_id === state.selectedSampleId)) {{
        state.selectedSampleId = filtered[0].sample_id;
      }}

      elements.sampleList.innerHTML = filtered.map((sample) => `
        <article class="sample-card ${sample.sample_id === state.selectedSampleId ? "active" : ""}" data-sample-id="${sample.sample_id}">
          <h3>${escapeHtml(sample.sample_id)}</h3>
          <p>${escapeHtml(sample.problem.text)}</p>
          <div class="badges">
            <span class="badge label-${sample.gold_diagnosis.primary_label}">${escapeHtml(sample.gold_diagnosis.primary_label)}</span>
            <span class="badge">${escapeHtml(sample.split)}</span>
            <span class="badge">${escapeHtml(sample.problem.difficulty)}</span>
          </div>
        </article>
      `).join("");

      for (const card of elements.sampleList.querySelectorAll(".sample-card")) {{
        card.addEventListener("click", () => {{
          state.selectedSampleId = card.dataset.sampleId;
          renderSampleList();
          renderDetailPanel();
        }});
      }}

      renderDetailPanel();
    }}

    function renderDetailPanel() {{
      const sample = benchmarkSamples.find((item) => item.sample_id === state.selectedSampleId);
      if (!sample) {{
        elements.detailPanel.innerHTML = `<div class="empty">Không tìm thấy sample đang chọn.</div>`;
        return;
      }}

      const quantities = sample.symbolic_annotation?.quantities || [];
      const metadataTags = sample.metadata.tags || [];

      elements.detailPanel.innerHTML = `
        <div class="section">
          <h3>Tổng quan</h3>
          <div class="kv">
            <div class="k">Sample ID</div><div>${escapeHtml(sample.sample_id)}</div>
            <div class="k">Problem ID</div><div>${escapeHtml(sample.source_problem_id)}</div>
            <div class="k">Split</div><div>${escapeHtml(sample.split)}</div>
            <div class="k">Nhãn lỗi chính</div><div><span class="badge label-${sample.gold_diagnosis.primary_label}">${escapeHtml(sample.gold_diagnosis.primary_label)}</span></div>
            <div class="k">Localization</div><div>${escapeHtml(sample.gold_diagnosis.localization)}</div>
            <div class="k">Confidence</div><div>${escapeHtml(sample.gold_diagnosis.confidence)}</div>
            <div class="k">Review status</div><div>${escapeHtml(sample.metadata.review_status)}</div>
          </div>
        </div>

        <div class="section">
          <h3>Đề bài (problem)</h3>
          <p>${escapeHtml(sample.problem.text)}</p>
        </div>

        <div class="section">
          <h3>Student case</h3>
          <div class="kv">
            <div class="k">Raw answer</div><div>${escapeHtml(sample.student_case.student_answer_raw)}</div>
            <div class="k">Parsed value</div><div>${escapeHtml(sample.student_case.student_answer_value)}</div>
            <div class="k">Source</div><div>${escapeHtml(sample.student_case.answer_source)}</div>
            <div class="k">Generation method</div><div>${escapeHtml(sample.student_case.error_generation_method)}</div>
          </div>
        </div>

        <div class="section">
          <h3>Gold diagnosis</h3>
          <div class="kv">
            <div class="k">Primary label</div><div>${escapeHtml(sample.gold_diagnosis.primary_label)}</div>
            <div class="k">Secondary label</div><div>${escapeHtml(sample.gold_diagnosis.secondary_label || "-")}</div>
            <div class="k">Localization</div><div>${escapeHtml(sample.gold_diagnosis.localization)}</div>
            <div class="k">Confidence</div><div>${escapeHtml(sample.gold_diagnosis.confidence)}</div>
            <div class="k">Rationale</div><div>${escapeHtml(sample.gold_diagnosis.rationale)}</div>
            <div class="k">Review notes</div><div>${escapeHtml(sample.gold_diagnosis.review_notes || "-")}</div>
          </div>
        </div>

        <div class="section">
          <h3>Gold reference</h3>
          <div class="kv">
            <div class="k">Final answer</div><div>${escapeHtml(sample.gold_reference.final_answer)}</div>
            <div class="k">Answer span</div><div>${escapeHtml(sample.gold_reference.answer_span || "-")}</div>
            <div class="k">Answer format</div><div>${escapeHtml(sample.gold_reference.answer_format)}</div>
          </div>
          <div class="code-block">${escapeHtml(sample.gold_reference.solution_text)}</div>
        </div>

        <div class="section">
          <h3>Symbolic annotation</h3>
          <div class="kv">
            <div class="k">Expected operation</div><div>${escapeHtml(sample.symbolic_annotation?.expected_operation || "-")}</div>
            <div class="k">Expected relation</div><div>${escapeHtml(sample.symbolic_annotation?.expected_relation || "-")}</div>
            <div class="k">Target type</div><div>${escapeHtml(sample.symbolic_annotation?.target_type || "-")}</div>
            <div class="k">Target text</div><div>${escapeHtml(sample.symbolic_annotation?.target_text || "-")}</div>
          </div>
          <div class="table-wrap" style="margin-top:12px;">
            <table>
              <thead>
                <tr>
                  <th>Value</th>
                  <th>Surface text</th>
                  <th>Role</th>
                  <th>Provenance</th>
                </tr>
              </thead>
              <tbody>
                ${quantities.length ? quantities.map((q) => `
                  <tr>
                    <td>${escapeHtml(q.value)}</td>
                    <td>${escapeHtml(q.surface_text)}</td>
                    <td>${escapeHtml(q.role)}</td>
                    <td>${escapeHtml(q.provenance)}</td>
                  </tr>
                `).join("") : `<tr><td colspan="4" class="muted">Không có quantity annotation.</td></tr>`}
              </tbody>
            </table>
          </div>
        </div>

        <div class="section">
          <h3>Metadata</h3>
          <div class="kv">
            <div class="k">Created by</div><div>${escapeHtml(sample.metadata.created_by)}</div>
            <div class="k">Review status</div><div>${escapeHtml(sample.metadata.review_status)}</div>
            <div class="k">Tags</div><div>${metadataTags.length ? metadataTags.map((tag) => `<span class="badge">${escapeHtml(tag)}</span>`).join(" ") : "-"}</div>
            <div class="k">Notes</div><div>${escapeHtml(sample.metadata.notes || "-")}</div>
          </div>
        </div>

        <div class="section">
          <h3>JSON thô của sample</h3>
          <div class="code-block">${escapeHtml(prettyJson(sample))}</div>
        </div>
      `;
    }}

    function renderScoreTable() {{
      elements.scoreTableBody.innerHTML = selectionScores.map((row) => `
        <tr>
          <td>${escapeHtml(row.problem_id)}</td>
          <td>
            <strong>${escapeHtml(row.score)} / 15</strong>
            <div class="score-bar"><div class="score-fill" style="width:${(row.score / 15) * 100}%"></div></div>
          </td>
          <td>${row.reasons.map((reason) => `<div>${escapeHtml(reason)}</div>`).join("")}</td>
        </tr>
      `).join("");
    }}

    function wireFilters() {{
      elements.searchBox.addEventListener("input", (event) => {{
        state.search = event.target.value.trim().toLowerCase();
        renderSampleList();
      }});
      elements.splitFilter.addEventListener("change", (event) => {{
        state.split = event.target.value;
        renderSampleList();
      }});
      elements.labelFilter.addEventListener("change", (event) => {{
        state.label = event.target.value;
        renderSampleList();
      }});
      elements.difficultyFilter.addEventListener("change", (event) => {{
        state.difficulty = event.target.value;
        renderSampleList();
      }});
      elements.reviewFilter.addEventListener("change", (event) => {{
        state.review = event.target.value;
        renderSampleList();
      }});
    }}

    buildSelect(elements.splitFilter, uniqueValues(benchmarkSamples, (sample) => sample.split), "Tất cả split");
    buildSelect(elements.labelFilter, uniqueValues(benchmarkSamples, (sample) => sample.gold_diagnosis.primary_label), "Tất cả nhãn lỗi");
    buildSelect(elements.difficultyFilter, uniqueValues(benchmarkSamples, (sample) => sample.problem.difficulty), "Tất cả độ khó");
    buildSelect(elements.reviewFilter, uniqueValues(benchmarkSamples, (sample) => sample.metadata.review_status), "Tất cả review status");

    wireFilters();
    computeStats();
    renderSampleList();
    renderScoreTable();
  </script>
</body>
</html>
"""


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def build_html(benchmark_samples: list[dict], selection_scores: list[dict]) -> str:
    benchmark_json = json.dumps(benchmark_samples, ensure_ascii=False)
    selection_json = json.dumps(selection_scores, ensure_ascii=False)
    template = HTML_TEMPLATE.replace("{{", "{").replace("}}", "}")
    return (
        template
        .replace("__BENCHMARK_JSON__", benchmark_json)
        .replace("__SELECTION_JSON__", selection_json)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a self-contained HTML review page for benchmark drafts")
    parser.add_argument(
        "--benchmark",
        default="data/benchmark/benchmark_draft.jsonl",
        help="Path to benchmark draft JSONL",
    )
    parser.add_argument(
        "--scores",
        default="data/benchmark/benchmark_selection_scores.json",
        help="Path to benchmark selection scores JSON",
    )
    parser.add_argument(
        "--output",
        default="data/benchmark/benchmark_review.html",
        help="Path to output HTML file",
    )
    args = parser.parse_args()

    benchmark_path = Path(args.benchmark)
    scores_path = Path(args.scores)
    output_path = Path(args.output)

    benchmark_samples = load_jsonl(benchmark_path)
    selection_scores = json.loads(scores_path.read_text(encoding="utf-8"))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_html(benchmark_samples, selection_scores), encoding="utf-8")

    label_counts = Counter(sample["gold_diagnosis"]["primary_label"] for sample in benchmark_samples)
    print(f"Generated review HTML: {output_path}")
    print(f"Samples: {len(benchmark_samples)}")
    print("Label distribution:")
    for label, count in sorted(label_counts.items()):
        print(f"  - {label}: {count}")


if __name__ == "__main__":
    main()
