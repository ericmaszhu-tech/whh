#!/usr/bin/env python3
"""Text ingestion and structure detection for the whh skill.

Turns a textbook file into chapters / sections / content units. Deliberately
conservative: it never invents content, and it marks anything it cannot read
as unparsed rather than guessing.

Supported: .docx (python-docx), .txt, .md
Not supported here: PDF, EPUB, scanned pages. Those belong to the adapter layer.
"""

from __future__ import annotations

import re
from pathlib import Path


CHAPTER_PATTERNS = [
    re.compile(r"^第\s*([0-9一二三四五六七八九十百]+)\s*[章讲篇]"),
    re.compile(r"^(Chapter|CHAPTER)\s+(\d+)"),
    re.compile(r"^(\d+)\s*[.、]\s*(?!\d)\S"),
]

SECTION_PATTERNS = [
    re.compile(r"^第\s*([0-9一二三四五六七八九十百]+)\s*节"),
    re.compile(r"^(\d+)\.(\d+)\s+\S"),
    re.compile(r"^([0-9]+)\.([0-9]+)\s*\S"),
    re.compile(r"^[一二三四五六七八九十]{1,3}[　 、.]\S"),
    re.compile(r"^[（(][一二三四五六七八九十]{1,3}[）)]\S"),
]

# Scored content-type cues. Title hits weigh three times a body hit, so a section
# called 「结论」 is typed as a conclusion even if the body is argumentative.
TYPE_CUES: dict[str, list[str]] = {
    "练习题": ["练习", "习题", "课后题", "思考题"],
    "例题": ["例题", "例 1", "例1", "解：", "求"],
    "实验": ["实验", "操作步骤", "仪器", "观察结果"],
    "证明": ["证明", "证：", "证毕", "所以", "即得"],
    "公式推导": ["推导", "由上式", "代入", "化简"],
    "定理与规律": ["定理", "定律", "引理", "推论", "法则"],
    "定义": ["定义", "是指", "所谓", "叫做", "称为"],
    "结论": ["结论", "总之", "综上所述", "总起来说", "由此可见"],
    "论证": ["因为", "所以", "因此", "由于", "既然", "如果"],
    "举例": ["例如", "譬如", "比如", "举例", "以…为例"],
    "背景": ["当时", "历史背景", "时代背景", "甲午", "五四运动", "鸦片战争"],
    "复习总结": ["小结", "总结", "本章回顾"],
}

MAX_UNIT_CHARS = 900
MIN_UNIT_CHARS = 40


def _classify(title: str, body: str) -> str:
    head = (title or "")[:40]
    blob = (body or "")[:1200]
    scores: dict[str, int] = {}
    for label, cues in TYPE_CUES.items():
        score = 0
        for cue in cues:
            score += head.count(cue) * 3 + blob.count(cue)
        if score:
            scores[label] = score
    if not scores:
        return "概念介绍"
    return max(scores.items(), key=lambda kv: kv[1])[0]


def _norm(text: str) -> str:
    return re.sub(r"[ \t\u3000]+", " ", (text or "").strip())


def _read_docx_stdlib(path: Path) -> list[tuple[int, str]]:
    """Read a .docx with the standard library only.

    A .docx is a zip holding word/document.xml. Falls back to this when
    python-docx is not installed, so the skill runs on a bare Python 3.
    """
    import xml.etree.ElementTree as ET
    import zipfile

    ns_w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))

    blocks: list[tuple[int, str]] = []
    for para in root.iter(f"{ns_w}p"):
        style = ""
        ppr = para.find(f"{ns_w}pPr")
        if ppr is not None:
            pstyle = ppr.find(f"{ns_w}pStyle")
            if pstyle is not None:
                style = (pstyle.get(f"{ns_w}val") or "").lower()
        text = _norm("".join(t.text or "" for t in para.iter(f"{ns_w}t")))
        if not text:
            continue
        if style.startswith("heading1") or style == "title":
            blocks.append((1, text))
        elif style.startswith("heading"):
            blocks.append((2, text))
        else:
            blocks.append((0, text))
    return blocks


def read_blocks(path: Path) -> list[tuple[int, str]]:
    """Return [(level, text)] where level 0 = body, 1 = chapter, 2 = section."""
    suffix = path.suffix.lower()

    if suffix == ".docx":
        try:
            from docx import Document
        except ImportError:
            return _read_docx_stdlib(path)
        doc = Document(str(path))
        blocks: list[tuple[int, str]] = []
        for para in doc.paragraphs:
            text = _norm(para.text)
            if not text:
                continue
            style = (para.style.name or "").lower()
            if style.startswith("heading 1") or style == "title":
                blocks.append((1, text))
            elif style.startswith("heading 2") or style.startswith("heading 3"):
                blocks.append((2, text))
            else:
                blocks.append((0, text))
        return blocks

    if suffix in {".txt", ".md", ".markdown"}:
        raw = path.read_text(encoding="utf-8", errors="replace")
        blocks = []
        for line in raw.splitlines():
            text = _norm(line)
            if not text:
                continue
            m = re.match(r"^(#{1,3})\s+(.*)$", text)
            if m:
                depth = len(m.group(1))
                label = _norm(m.group(2))
                if depth == 1:
                    blocks.append((1, label))
                elif _looks_like_section(label):
                    blocks.append((2, label))
                elif _looks_like_chapter(label):
                    blocks.append((1, label))
                else:
                    blocks.append((2, label))
            else:
                blocks.append((0, text))
        return blocks

    raise RuntimeError(
        f"unsupported source type {suffix or '(none)'}; "
        "supported: .docx .txt .md. PDF/EPUB require the adapter layer."
    )


def _looks_like_chapter(text: str) -> bool:
    return any(p.match(text) for p in CHAPTER_PATTERNS) and len(text) <= 60


def _looks_like_section(text: str) -> bool:
    return any(p.match(text) for p in SECTION_PATTERNS) and len(text) <= 60


def build_structure(blocks: list[tuple[int, str]]) -> dict:
    """Group blocks into chapters -> sections -> content units.

    A leading H1 is treated as the book title, not as a chapter, and chapters that
    end up with no content units are dropped — a heading with nothing under it is a
    title artefact, not a chapter. If nothing survives, the raw grouping is returned
    so the caller can report a parse failure instead of pretending success.
    """
    title_hint = None
    if blocks and blocks[0][0] == 1:
        title_hint = blocks[0][1]
        blocks = blocks[1:]

    chapters: list[dict] = []
    current_ch: dict | None = None
    current_sec_title = ""
    buffer: list[str] = []
    section_parts: dict[str, int] = {}

    def flush_unit() -> None:
        nonlocal buffer
        body = " ".join(buffer).strip()
        buffer = []
        if len(body) < MIN_UNIT_CHARS or current_ch is None:
            return
        units = current_ch["units"]
        if current_sec_title:
            section_parts[current_sec_title] = section_parts.get(current_sec_title, 0) + 1
            part = section_parts[current_sec_title]
            title = current_sec_title if part == 1 else f"{current_sec_title}｜{body[:14]}…"
        else:
            title = body[:24] + ("…" if len(body) > 24 else "")
        units.append(
            {
                "unit_id": f"{current_ch['chapter_id']}.u{len(units) + 1:02d}",
                "title": title,
                "content_type": _classify(current_sec_title or title, body),
                "chars": len(body),
                "preview": body[:160],
                "text": body,
            }
        )

    def push(body: str) -> None:
        nonlocal buffer
        buffer.append(body)
        if sum(len(x) for x in buffer) >= MAX_UNIT_CHARS:
            flush_unit()

    for level, text in blocks:
        if level == 1 or (level == 0 and _looks_like_chapter(text)):
            flush_unit()
            current_ch = {
                "chapter_id": f"ch{len(chapters) + 1:02d}",
                "index": len(chapters) + 1,
                "title": text,
                "sections": [],
                "units": [],
            }
            chapters.append(current_ch)
            current_sec_title = ""
            continue

        if level == 2 or (level == 0 and _looks_like_section(text)):
            if current_ch is None:
                current_ch = {
                    "chapter_id": "ch01",
                    "index": 1,
                    "title": title_hint or "前言",
                    "sections": [],
                    "units": [],
                }
                chapters.append(current_ch)
            flush_unit()
            current_sec_title = text
            current_ch["sections"].append(text)
            continue

        if current_ch is None:
            current_ch = {
                "chapter_id": "ch01",
                "index": 1,
                "title": title_hint or "前言",
                "sections": [],
                "units": [],
            }
            chapters.append(current_ch)
        push(text)

    flush_unit()

    kept = [ch for ch in chapters if ch["units"]]
    unparsed = not kept
    if unparsed:
        kept = chapters

    for i, ch in enumerate(kept, start=1):
        ch["index"] = i
        ch["chapter_id"] = f"ch{i:02d}"
        for j, unit in enumerate(ch["units"], start=1):
            unit["unit_id"] = f"ch{i:02d}.u{j:02d}"

    return {
        "title_hint": title_hint,
        "chapters": kept,
        "dropped_empty": len(chapters) - len(kept) if not unparsed else 0,
        "unparsed": unparsed,
    }


def summarize(structure: dict) -> dict:
    chapters = structure.get("chapters", [])
    units = [u for c in chapters for u in c.get("units", [])]
    types: dict[str, int] = {}
    for u in units:
        types[u["content_type"]] = types.get(u["content_type"], 0) + 1
    return {
        "chapters": len(chapters),
        "units": len(units),
        "chars": sum(u.get("chars", 0) for u in units),
        "content_types": dict(sorted(types.items(), key=lambda kv: -kv[1])),
    }
