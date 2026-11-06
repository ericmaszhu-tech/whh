#!/usr/bin/env python3
"""index.html renderer for the whh skill.

The index is a catalogue, not a log: one row per artifact key, grouped by chapter,
with the modelling coverage at the top. Rendering is idempotent — it derives
everything from artifacts.jsonl, so re-rendering never duplicates entries.
"""

from __future__ import annotations

import html

CSS = """
:root {
  --paper:#f5f5f5; --card:#ffffff; --ink:#2d3142; --muted:#4f5d75;
  --soft:#5a6580; --rule:rgba(45,49,66,.12); --accent:#bf4520;
  --tint:rgba(191,69,32,.08); --ok:#2f6b4f; --warn:#8a5a12;
}
* { box-sizing:border-box; }
body {
  margin:0; padding:48px 32px 72px; background:var(--paper); color:var(--ink);
  font-family:"Segoe UI","PingFang SC","Microsoft YaHei",system-ui,sans-serif;
  font-size:15px; line-height:1.65;
}
.wrap { max-width:1040px; margin:0 auto; }
h1 { font-size:30px; font-weight:600; letter-spacing:-.01em; margin:0 0 6px; }
.sub { color:var(--muted); font-size:14px; margin:0 0 28px; }
.stats { display:flex; flex-wrap:wrap; gap:12px; margin:0 0 32px; }
.stat {
  background:var(--card); border:1px solid var(--rule); border-radius:6px;
  padding:12px 16px; min-width:112px; flex:0 0 auto;
}
.stat .k { color:var(--soft); font-size:12px; letter-spacing:.02em; }
.stat .v { font-size:20px; font-weight:600; font-variant-numeric:tabular-nums; }
h2 { font-size:15px; font-weight:600; margin:32px 0 12px; color:var(--ink); }
h2 .tag {
  font-weight:400; color:var(--soft); font-size:12px; margin-left:8px;
  font-variant-numeric:tabular-nums;
}
.group {
  background:var(--card); border:1px solid var(--rule); border-radius:6px;
  margin:0 0 10px; overflow:hidden;
}
.group > summary {
  cursor:pointer; padding:12px 16px; display:flex; gap:12px; align-items:baseline;
  list-style:none;
}
.group > summary::-webkit-details-marker { display:none; }
.group > summary:hover { background:rgba(45,49,66,.03); }
.ch-id { color:var(--soft); font-size:12px; font-variant-numeric:tabular-nums; min-width:46px; }
.ch-title { font-weight:600; flex:1; }
.ch-meta { color:var(--soft); font-size:12px; font-variant-numeric:tabular-nums; }
.rows { border-top:1px solid var(--rule); }
table { width:100%; border-collapse:collapse; }
td, th {
  text-align:left; padding:8px 16px; font-size:13.5px;
  border-bottom:1px solid var(--rule); vertical-align:top;
}
th { color:var(--soft); font-weight:400; font-size:12px; }
tr:last-child td { border-bottom:none; }
.mono { font-family:"Cascadia Mono",Consolas,monospace; font-size:12px; color:var(--soft); }
a { color:var(--accent); text-decoration:none; }
a:hover { text-decoration:underline; }
.pill {
  display:inline-block; padding:1px 7px; border-radius:3px; font-size:11.5px;
  border:1px solid var(--rule); color:var(--muted); font-variant-numeric:tabular-nums;
}
.pill.d3, .pill.d4 { border-color:rgba(191,69,32,.4); color:var(--accent); background:var(--tint); }
.empty { color:var(--soft); padding:16px; font-size:13.5px; border-top:1px solid var(--rule); }
.note { color:var(--soft); font-size:12.5px; margin:28px 0 0; }
"""


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def _depth_pill(depth: str) -> str:
    cls = "pill " + (depth or "").lower()
    return f'<span class="{cls}">{esc(depth)}</span>'


def render(book: dict, structure: dict, artifacts: list[dict], plan: dict) -> str:
    chapters = structure.get("chapters", [])
    by_chapter: dict[str, list[dict]] = {}
    global_rows: list[dict] = []
    for row in artifacts:
        scope = row.get("scope", "")
        cid = scope.split(".")[0] if scope != "all" else None
        if cid is None:
            global_rows.append(row)
        else:
            by_chapter.setdefault(cid, []).append(row)

    covered = sum(1 for ch in chapters if by_chapter.get(ch["chapter_id"]))
    if global_rows and chapters:
        covered = len(chapters)
    total_units = sum(len(ch.get("units", [])) for ch in chapters)
    confirm_state = "已确认" if (plan or {}).get("confirmed") else "未确认"
    subtitle = " · ".join(
        part for part in (book.get("subject"), book.get("profile"), f"方案{confirm_state}") if part
    )

    parts: list[str] = []
    parts.append(
        f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(book.get('title'))} · 产物目录</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<h1>{esc(book.get('title'))}</h1>
<p class="sub">{esc(subtitle)}</p>
<div class="stats">
  <div class="stat"><div class="k">章节</div><div class="v">{len(chapters)}</div></div>
  <div class="stat"><div class="k">内容单元</div><div class="v">{total_units}</div></div>
  <div class="stat"><div class="k">已产出视图</div><div class="v">{len(artifacts)}</div></div>
  <div class="stat"><div class="k">章节覆盖</div><div class="v">{covered}/{len(chapters)}</div></div>
</div>
"""
    )

    if global_rows:
        parts.append("<h2>全书</h2>")
        parts.append(_table(global_rows))

    parts.append("<h2>按章节</h2>")
    for ch in chapters:
        rows = by_chapter.get(ch["chapter_id"], [])
        cid = ch["chapter_id"]
        types: dict[str, int] = {}
        for unit in ch.get("units", []):
            types[unit["content_type"]] = types.get(unit["content_type"], 0) + 1
        type_text = " · ".join(f"{k}{v}" for k, v in sorted(types.items(), key=lambda kv: -kv[1])[:3])
        body = _table(rows) if rows else '<div class="empty">尚无产物</div>'
        parts.append(
            f"""<details class="group">
<summary>
  <span class="ch-id">{esc(cid)}</span>
  <span class="ch-title">{esc(ch['title'])}</span>
  <span class="ch-meta">{len(ch.get('units', []))} 单元 · {esc(type_text)}</span>
</summary>
<div class="rows">{body}</div>
</details>"""
        )

    parts.append(
        """<p class="note">本页由 whh 自动生成。同一产物只保留一条记录，重复生成时更新而非追加。</p>
</div>
</body>
</html>"""
    )
    return "\n".join(parts)


def _table(rows: list[dict]) -> str:
    head = (
        "<table><thead><tr>"
        "<th>产物</th><th>范围</th><th>深度</th><th>图类型</th>"
        "<th>节点</th><th>生成时间</th><th>文件</th>"
        "</tr></thead><tbody>"
    )
    body = []
    for row in sorted(rows, key=lambda r: (r.get("product", ""), r.get("depth", ""))):
        body.append(
            "<tr>"
            f"<td>{esc(row.get('product'))}</td>"
            f"<td class=\"mono\">{esc(row.get('scope'))}</td>"
            f"<td>{_depth_pill(row.get('depth'))}</td>"
            f"<td>{esc(row.get('figure'))}</td>"
            f"<td class=\"mono\">{esc(row.get('nodes') or '—')}</td>"
            f"<td class=\"mono\">{esc((row.get('created_at') or '')[:16].replace('T', ' '))}</td>"
            f"<td><a href=\"{esc(row.get('file'))}\">打开</a></td>"
            "</tr>"
        )
    return head + "".join(body) + "</tbody></table>"
