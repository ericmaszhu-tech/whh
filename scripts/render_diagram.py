#!/usr/bin/env python3
"""Diagram renderer for whh views.

Takes a deterministic view spec (nodes with ranks, edges) and emits a single
self-contained HTML file with inline SVG, following the diagram-design
conventions: paper/ink/muted tokens, rx=6 nodes, orthogonal elbows, one arrow
marker, a bottom legend strip, and the accessible-SVG contract.

Deterministic layout on purpose: generated views must be reproducible and
cacheable. Hero diagrams can still be hand-tuned by the model afterwards.
"""

from __future__ import annotations

import html

PAPER = "#f5f5f5"
INK = "#2d3142"
MUTED = "#4f5d75"
SOFT = "#5a6580"
RULE = "rgba(45,49,66,0.16)"
ACCENT = "#bf4520"
ACCENT_TINT = "rgba(191,69,32,0.06)"
PAPER_TINT = "#efefef"

NODE_W = 212
NODE_H = 66
GAP_X = 96
GAP_Y = 26
MARGIN = 44
TAG_H = 16


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def _layout(spec: dict) -> tuple[list[dict], int, int]:
    nodes = sorted(spec["nodes"], key=lambda n: (n["rank"], n["label"]))
    ranks: dict[int, list[dict]] = {}
    for node in nodes:
        ranks.setdefault(node["rank"], []).append(node)

    max_rows = max((len(v) for v in ranks.values()), default=1)
    placed = []
    for rank, column in sorted(ranks.items()):
        col_height = len(column) * NODE_H + (len(column) - 1) * GAP_Y
        total_height = max_rows * NODE_H + (max_rows - 1) * GAP_Y
        top = MARGIN + (total_height - col_height) / 2
        for i, node in enumerate(column):
            placed.append(
                {
                    **node,
                    "x": MARGIN + rank * (NODE_W + GAP_X),
                    "y": top + i * (NODE_H + GAP_Y),
                }
            )
    width = MARGIN * 2 + (max(ranks) + 1) * NODE_W + max(ranks) * GAP_X
    height = MARGIN * 2 + total_height
    return placed, int(width), int(height)


def _elbow(x1: float, y1: float, x2: float, y2: float, back: bool, stagger: int = 0) -> str:
    """Orthogonal route: horizontal out, one vertical run in the column gap, horizontal in."""
    r = 8
    if abs(y1 - y2) < 0.5:
        return f"M {x1:.1f} {y1:.1f} L {x2:.1f} {y2:.1f}"

    mx = (x1 + x2) / 2 + stagger
    dy = 1 if y2 > y1 else -1
    if back:
        mx = x1 + 34 + stagger

    return (
        f"M {x1:.1f} {y1:.1f} "
        f"L {mx - r:.1f} {y1:.1f} "
        f"Q {mx:.1f} {y1:.1f} {mx:.1f} {y1 + dy * r:.1f} "
        f"L {mx:.1f} {y2 - dy * r:.1f} "
        f"Q {mx:.1f} {y2:.1f} {mx + r:.1f} {y2:.1f} "
        f"L {x2:.1f} {y2:.1f}"
    )


def _place_timeline(spec: dict) -> tuple[list[dict], int, int, int]:
    """Single horizontal axis; nodes alternate above and below it."""
    nodes = sorted(spec["nodes"], key=lambda n: (n.get("order", n.get("rank", 0)), n.get("label", "")))
    step = 226
    axis_y = MARGIN + 118
    placed = []
    for i, node in enumerate(nodes):
        x = MARGIN + i * step
        above = i % 2 == 0
        y = axis_y - NODE_H - 54 if above else axis_y + 54
        placed.append({**node, "x": x, "y": y, "above": above})
    width = MARGIN * 2 + max(1, len(nodes)) * step
    height = axis_y + NODE_H + 140
    return placed, int(width), int(height), axis_y


def _timeline_axis(placed: list[dict], axis_y: int, width: int) -> str:
    if not placed:
        return ""
    x1 = placed[0]["x"] - 28
    x2 = placed[-1]["x"] + NODE_W + 28
    parts = [
        f'<line x1="{x1}" y1="{axis_y}" x2="{x2}" y2="{axis_y}" stroke="{RULE}" stroke-width="1.4"/>'
    ]
    for node in placed:
        cx = node["x"] + NODE_W / 2
        top = node["y"] + NODE_H if node["above"] else axis_y
        bottom = axis_y if node["above"] else node["y"]
        parts.append(
            f'<line x1="{cx}" y1="{top}" x2="{cx}" y2="{bottom}" stroke="{RULE}" stroke-width="1" stroke-dasharray="3,3"/>'
        )
        parts.append(f'<circle cx="{cx}" cy="{axis_y}" r="3" fill="{MUTED}"/>')
        label = node.get("time_label", "")
        if label:
            ly = axis_y - 10 if node["above"] else axis_y + 18
            parts.append(
                f'<text x="{cx}" y="{ly}" text-anchor="middle" font-family="Consolas,monospace" '
                f'font-size="11" fill="{SOFT}">{esc(label)}</text>'
            )
    return "".join(parts)


def _place_nested(spec: dict) -> tuple[list[dict], int, int, list[dict]]:
    """Containment bands: a parent box wraps its children in a row."""
    nodes = spec["nodes"]
    index = {n["id"]: n for n in nodes}
    parent_of: dict[str, str] = {}
    for edge in spec.get("edges", []):
        src, dst, typ = edge.get("source"), edge.get("target"), edge.get("type", "")
        if src not in index or dst not in index:
            continue
        if typ in ("contains", "contains_movement"):
            parent_of[dst] = src
        elif typ in ("belongs_to", "is_part_of"):
            parent_of[src] = dst

    children: dict[str, list[dict]] = {}
    for node in nodes:
        parent = parent_of.get(node["id"])
        if parent:
            children.setdefault(parent, []).append(node)

    placed: list[dict] = []
    bands: list[dict] = []
    y = MARGIN
    for parent_id, kids in children.items():
        band_h = 42 + NODE_H + 24
        band_w = 24 + len(kids) * (NODE_W + GAP_X) - GAP_X + 24
        bands.append(
            {
                "x": MARGIN,
                "y": y,
                "w": band_w,
                "h": band_h,
                "label": index[parent_id]["label"],
                "count": len(kids),
            }
        )
        for i, kid in enumerate(kids):
            placed.append({**kid, "x": MARGIN + 24 + i * (NODE_W + GAP_X), "y": y + 42})
        y += band_h + 38

    grouped = {n["id"] for kids in children.values() for n in kids} | set(children)
    for node in nodes:
        if node["id"] in grouped:
            continue
        placed.append({**node, "x": MARGIN, "y": y})
        y += NODE_H + GAP_Y
        bands.append({"x": MARGIN - 12, "y": y - NODE_H - GAP_Y - 8, "w": NODE_W + 24,
                      "h": NODE_H + 16, "label": "", "count": 0})

    width = MARGIN * 2 + max([b["w"] for b in bands] + [NODE_W])
    height = max(y, MARGIN * 2 + NODE_H) + MARGIN
    return placed, int(width), int(height), bands


def _bands_svg(bands: list[dict]) -> str:
    parts = []
    for band in bands:
        if not band.get("label"):
            continue
        parts.append(
            f'<rect x="{band["x"]}" y="{band["y"]}" width="{band["w"]}" height="{band["h"]}" '
            f'rx="8" fill="{PAPER_TINT}" stroke="{RULE}" stroke-width="1"/>'
            f'<text x="{band["x"] + 18}" y="{band["y"] + 26}" font-size="12.5" font-weight="600" '
            f'fill="{MUTED}">{esc(band["label"])}'
            f'<tspan font-weight="400" font-size="11" fill="{SOFT}"> · {band["count"]} 项</tspan></text>'
        )
    return "".join(parts)


def render(spec: dict) -> str:
    layout = spec.get("layout", "layered")
    axis_y = 0
    axis_svg = ""
    bands_svg = ""
    if layout == "timeline":
        placed, width, height, axis_y = _place_timeline(spec)
        axis_svg = _timeline_axis(placed, axis_y, width)
    elif layout == "nested":
        placed, width, height, bands = _place_nested(spec)
        bands_svg = _bands_svg(bands)
    else:
        placed, width, height = _layout(spec)
    legend_items = spec.get("legend") or []
    if legend_items:
        legend_w = MARGIN * 2 + sum(26 + len(item["label"]) * 8 for item in legend_items) + 32
        width = max(width, int(legend_w))
    by_id = {n["id"]: n for n in placed}
    focal = {n["id"] for n in placed if n.get("focal")}

    legend_h = 52 if legend_items else 0
    total_h = height + legend_h

    edges_svg = []
    if layout not in ("timeline", "nested"):
        for i, edge in enumerate(spec.get("edges", [])):
            src, dst = by_id.get(edge["source"]), by_id.get(edge["target"])
            if not src or not dst:
                continue
            x1, y1 = src["x"] + NODE_W, src["y"] + NODE_H / 2
            x2, y2 = dst["x"], dst["y"] + NODE_H / 2
            back = dst["rank"] <= src["rank"]
            stagger = 0
            edges_svg.append(
                f'<path d="{_elbow(x1, y1, x2, y2, back, stagger)}" fill="none" stroke="{MUTED}" '
                f'stroke-width="1.3" marker-end="url(#arrow-{spec["slug"]})" opacity="0.72"/>'
            )

    nodes_svg = []
    for node in placed:
        is_focal = node["id"] in focal and len(focal) <= 2
        stroke = ACCENT if is_focal else RULE
        fill = ACCENT_TINT if is_focal else "#ffffff"
        nodes_svg.append(
            f'<g><rect x="{node["x"]}" y="{node["y"]}" width="{NODE_W}" height="{NODE_H}" '
            f'rx="6" fill="{PAPER}"/>'
            f'<rect x="{node["x"]}" y="{node["y"]}" width="{NODE_W}" height="{NODE_H}" '
            f'rx="6" fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>'
            f'<rect x="{node["x"] + 12}" y="{node["y"] + 10}" width="{max(34, len(node["type"]) * 7 + 14)}" '
            f'height="{TAG_H}" rx="2" fill="none" stroke="{RULE}"/>'
            f'<text x="{node["x"] + 19}" y="{node["y"] + 21}" '
            f'font-family="Consolas,monospace" font-size="9.5" fill="{SOFT}" letter-spacing="0.4">'
            f'{esc(node["type"])}</text>'
            f'<text x="{node["x"] + 12}" y="{node["y"] + 48}" font-size="14.5" font-weight="600" '
            f'fill="{INK}">{esc(_clip(node["label"], 25))}</text>'
            f'<text x="{node["x"] + NODE_W - 12}" y="{node["y"] + NODE_H - 13}" text-anchor="end" '
            f'font-family="Consolas,monospace" font-size="10" fill="{SOFT}">{esc(node.get("depth", ""))}</text>'
            f"</g>"
        )

    legend_svg = ""
    if legend_items:
        lx = MARGIN
        ly = height + 18
        parts = []
        for item in legend_items:
            parts.append(
                f'<rect x="{lx}" y="{ly}" width="10" height="10" rx="2" fill="none" stroke="{RULE}"/>'
                f'<text x="{lx + 16}" y="{ly + 9}" font-size="11" fill="{SOFT}">{esc(item["label"])}</text>'
            )
            lx += 26 + len(item["label"]) * 8
        legend_svg = f'<g>{"".join(parts)}</g>'

    slug = spec["slug"]
    subtitle = spec.get("subtitle", "")
    note = spec.get("note", "")

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(spec["title"])}</title>
<style>
  :root {{ --paper:{PAPER}; --ink:{INK}; --muted:{MUTED}; --soft:{SOFT}; --rule:{RULE}; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; padding:40px 28px 56px; background:var(--paper); color:var(--ink);
         font-family:"Segoe UI","PingFang SC","Microsoft YaHei",system-ui,sans-serif; }}
  .wrap {{ max-width:100%; }}
  .eyebrow {{ font-family:Consolas,monospace; font-size:11px; letter-spacing:.14em;
              text-transform:uppercase; color:var(--soft); margin:0 0 8px; }}
  h1 {{ font-size:26px; font-weight:600; letter-spacing:-.01em; margin:0 0 6px; }}
  .sub {{ color:var(--muted); font-size:13.5px; margin:0 0 22px; }}
  .canvas {{ overflow-x:auto; }}
  svg {{ display:block; min-width:{width}px; }}
  .note {{ color:var(--soft); font-size:12.5px; margin:14px 0 0; max-width:760px; }}
</style>
</head>
<body>
<div class="wrap">
  <p class="eyebrow">{esc(spec.get("eyebrow", "知识地图"))}</p>
  <h1>{esc(spec["title"])}</h1>
  <p class="sub">{esc(subtitle)}</p>
  <div class="canvas">
    <svg width="{width}" height="{total_h}" viewBox="0 0 {width} {total_h}"
         role="img" aria-labelledby="{slug}-title {slug}-desc">
      <title id="{slug}-title">{esc(spec["title"])}</title>
      <desc id="{slug}-desc">{esc(spec.get("desc") or subtitle or spec["title"])}</desc>
      <defs>
        <marker id="arrow-{slug}" viewBox="0 0 10 10" refX="9" refY="5"
                markerWidth="7" markerHeight="7" orient="auto">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="{MUTED}"/>
        </marker>
      </defs>
      {axis_svg}
      {"".join(edges_svg)}
      {bands_svg}
      {"".join(nodes_svg)}
      {legend_svg}
    </svg>
  </div>
  <p class="note">{esc(note)}</p>
</div>
</body>
</html>"""


def _clip(text: str, limit: int) -> str:
    """Clip by display width: CJK counts as 2, everything else as 1."""
    text = str(text)
    width = 0
    for i, ch in enumerate(text):
        width += 2 if ord(ch) > 0x2E7F else 1
        if width > limit:
            return text[:i] + "…"
    return text
