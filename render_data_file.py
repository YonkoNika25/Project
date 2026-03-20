"""Render a single JSON / JSONL / CSV file into a static review HTML page."""
from __future__ import annotations

import argparse
import csv
import html
import json
from pathlib import Path
from typing import Any


PAGE_TEMPLATE = """<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      --bg: #f6f3ee;
      --panel: #fffdf9;
      --line: #d8cfc0;
      --ink: #1e1b18;
      --muted: #6b645a;
      --accent: #a24b2a;
      --shadow: 0 16px 38px rgba(72, 53, 30, 0.12);
    }}

    * {{ box-sizing: border-box; }}

    body {{
      margin: 0;
      color: var(--ink);
      font-family: "Segoe UI", "Helvetica Neue", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(162, 75, 42, 0.08), transparent 24%),
        linear-gradient(180deg, #fbf8f3 0%, var(--bg) 100%);
      min-height: 100vh;
    }}

    .page {{
      max-width: 1500px;
      margin: 0 auto;
      padding: 24px;
    }}

    .hero {{
      background: linear-gradient(135deg, rgba(162, 75, 42, 0.12), rgba(255,255,255,0.96));
      border: 1px solid rgba(162, 75, 42, 0.16);
      border-radius: 22px;
      padding: 24px;
      box-shadow: var(--shadow);
      margin-bottom: 18px;
    }}

    .hero h1 {{
      margin: 0 0 10px;
      font-size: 32px;
      line-height: 1.1;
    }}

    .hero p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.6;
    }}

    .stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-top: 18px;
    }}

    .stat {{
      background: rgba(255,255,255,0.84);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px 16px;
    }}

    .stat .label {{
      display: block;
      font-size: 12px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 4px;
    }}

    .stat .value {{
      font-size: 28px;
      font-weight: 700;
    }}

    .section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 20px;
      box-shadow: var(--shadow);
      padding: 18px;
      margin-bottom: 18px;
    }}

    .section h2 {{
      margin: 0 0 14px;
      font-size: 20px;
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

    .table-wrap {{
      display: block;
      width: 100%;
      overflow-x: auto;
      overflow-y: auto;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: rgba(255,255,255,0.82);
      max-width: 100%;
    }}

    table {{
      width: max-content;
      min-width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}

    th, td {{
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      white-space: nowrap;
      min-width: 160px;
    }}

    th {{
      background: rgba(255,255,255,0.92);
      position: sticky;
      top: 0;
      z-index: 1;
    }}

    .note {{
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 10px;
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
      overflow: auto;
      max-height: 700px;
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
      margin-right: 6px;
    }}
  </style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <h1>{title}</h1>
      <p>{description}</p>
      <div class="stats">
        {stats_html}
      </div>
    </section>

    <section class="section">
      <h2>Tổng quan file</h2>
      <div class="kv">
        {overview_html}
      </div>
    </section>

    <section class="section">
      <h2>Preview dữ liệu</h2>
      <div class="note">{preview_note}</div>
      {preview_html}
    </section>

    <section class="section">
      <h2>Raw content</h2>
      <div class="code-block">{raw_html}</div>
    </section>
  </div>
</body>
</html>
"""


def _escape(value: Any) -> str:
    return html.escape(str(value))


def _format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.2f} MB"


def _load_data(path: Path) -> tuple[str, Any, str]:
    suffix = path.suffix.lower()
    raw_text = path.read_text(encoding="utf-8")
    if suffix == ".json":
        return raw_text, json.loads(raw_text), "json"
    if suffix == ".jsonl":
        rows = []
        for line in raw_text.splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
        return raw_text, rows, "jsonl"
    if suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        return raw_text, rows, "csv"
    raise ValueError(f"Unsupported file type: {path.suffix}")


def _object_to_rows(data: dict) -> list[dict[str, str]]:
    return [
        {
            "key": str(key),
            "value": (
                json.dumps(value, ensure_ascii=False)
                if isinstance(value, (dict, list))
                else str(value)
            ),
        }
        for key, value in data.items()
    ]


def _infer_columns(rows: list[Any]) -> list[str]:
    if not rows or not isinstance(rows[0], dict):
        return []
    columns: list[str] = []
    for row in rows[:20]:
        if not isinstance(row, dict):
            continue
        for key in row.keys():
            if key not in columns:
                columns.append(key)
    return columns


def _render_stats(file_type: str, data: Any, size_bytes: int) -> str:
    if isinstance(data, list):
        item_count = len(data)
        count_label = "Rows"
    elif isinstance(data, dict):
        item_count = len(data)
        count_label = "Keys"
    else:
        item_count = 1
        count_label = "Items"

    items = [
        ("Loại file", file_type.upper()),
        (count_label, item_count),
        ("Dung lượng", _format_bytes(size_bytes)),
    ]
    return "\n".join(
        f'<div class="stat"><span class="label">{_escape(label)}</span><span class="value">{_escape(value)}</span></div>'
        for label, value in items
    )


def _render_overview(path: Path, file_type: str, data: Any) -> str:
    if isinstance(data, list):
        structure = "Dữ liệu dạng danh sách / nhiều dòng"
    elif isinstance(data, dict):
        structure = "Dữ liệu dạng object"
    else:
        structure = "Dữ liệu scalar"

    pairs = [
        ("Tên file", path.name),
        ("Đường dẫn", str(path).replace("\\", "/")),
        ("Loại file", file_type.upper()),
        ("Cấu trúc", structure),
    ]
    return "\n".join(
        f'<div class="k">{_escape(k)}</div><div>{_escape(v)}</div>'
        for k, v in pairs
    )


def _render_table(columns: list[str], rows: list[dict[str, Any]]) -> str:
    if not columns or not rows:
        return '<div class="code-block">Không có dữ liệu dạng bảng để preview.</div>'

    head = "".join(f"<th>{_escape(column)}</th>" for column in columns)
    body_rows = []
    for row in rows:
        cells = "".join(
            f"<td>{_escape(json.dumps(row.get(column), ensure_ascii=False) if isinstance(row.get(column), (dict, list)) else row.get(column, ''))}</td>"
            for column in columns
        )
        body_rows.append(f"<tr>{cells}</tr>")

    return f"""
    <div class="table-wrap">
      <table>
        <thead><tr>{head}</tr></thead>
        <tbody>{''.join(body_rows)}</tbody>
      </table>
    </div>
    """


def _render_preview(data: Any) -> tuple[str, str]:
    if isinstance(data, dict):
        rows = _object_to_rows(data)
        columns = ["key", "value"]
        return "Preview 50 dòng đầu từ object-level summary.", _render_table(columns, rows[:50])
    if isinstance(data, list):
        if data and isinstance(data[0], dict):
            columns = _infer_columns(data)[:20]
            return "Preview 50 dòng đầu. Nếu bảng rộng, hãy kéo ngang trong khung bảng.", _render_table(columns, data[:50])
        rows = [{"value": item} for item in data[:50]]
        return "Preview 50 phần tử đầu.", _render_table(["value"], rows)
    return "Dữ liệu không ở dạng bảng.", f'<div class="code-block">{_escape(data)}</div>'


def render_file_to_html(input_path: Path, output_path: Path) -> None:
    raw_text, data, file_type = _load_data(input_path)
    preview_note, preview_html = _render_preview(data)
    html_text = PAGE_TEMPLATE.format(
        title=_escape(input_path.name),
        description=_escape("Trang HTML tĩnh để rà soát một file dữ liệu duy nhất. Không dùng JavaScript động để tránh lỗi hiển thị."),
        stats_html=_render_stats(file_type, data, input_path.stat().st_size),
        overview_html=_render_overview(input_path, file_type, data),
        preview_note=_escape(preview_note),
        preview_html=preview_html,
        raw_html=_escape(raw_text[:50000]),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render one JSON / JSONL / CSV file into static HTML")
    parser.add_argument("--input", required=True, help="Path to JSON / JSONL / CSV file")
    parser.add_argument("--output", default=None, help="Optional output HTML path")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    output_path = Path(args.output) if args.output else input_path.with_suffix(input_path.suffix + ".html")
    render_file_to_html(input_path, output_path)

    print(f"Rendered HTML: {output_path}")


if __name__ == "__main__":
    main()
