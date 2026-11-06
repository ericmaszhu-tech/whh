#!/usr/bin/env python3
"""whh — deterministic state layer for the whh textbook skill.

The model does classification, extraction and diagram authoring. This script owns
everything that must be identical across runs: the book registry, the extraction
plan, cache keys, the artifact index and index.html.

Run `python whh.py --help` for commands. Every command prints machine-readable
JSON on stdout, so the skill can relay results without re-deriving them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCHEMA_VERSION = "0.1.0"
BOOKS_DIRNAME = "books"
WORKS_DIRNAME = "works"

DEPTHS = ["L1", "L2", "L3", "L4"]

PRODUCTS = {
    "知识地图": {"figure": "Tree / Dependency graph", "scopes": ["all", "chapter", "unit"], "layout": "layered"},
    "定理体系": {"figure": "Dependency graph", "scopes": ["all", "chapter", "unit"], "layout": "layered"},
    "时间线": {"figure": "Timeline", "scopes": ["all", "chapter", "unit"], "layout": "timeline"},
    "因果链": {"figure": "Dependency graph（左→右）", "scopes": ["all", "chapter", "unit"], "layout": "layered"},
    "实验分析": {"figure": "Process", "scopes": ["chapter", "unit"], "layout": "layered"},
    "架构图": {"figure": "Architecture", "scopes": ["all", "chapter", "unit"], "layout": "layered"},
    "学习路径": {
        "figure": "Dependency graph",
        "scopes": ["all", "chapter"],
        "layout": "layered",
        "edge_types": ["prerequisite_of", "precedes", "requires", "depends_on", "derives_from"],
    },
    "结构图": {"figure": "Nested", "scopes": ["all", "chapter", "unit"], "layout": "nested"},
    "详解": {"figure": "无图", "scopes": ["unit"], "layout": "layered"},
    "练习": {"figure": "无图", "scopes": ["chapter", "unit"], "layout": "layered"},
    "专业拆解": {"figure": "无图", "scopes": ["all"], "layout": "layered"},
    "听赏指南": {"figure": "Timeline", "scopes": ["all", "chapter"], "layout": "timeline"},
}

PROFILE_PRODUCTS = {
    "mathematics": ["知识地图", "定理体系", "学习路径", "详解", "练习"],
    "natural-science": ["知识地图", "实验分析", "学习路径", "详解", "练习"],
    "humanities": ["知识地图", "时间线", "因果链", "学习路径", "详解"],
    "computer": ["知识地图", "架构图", "学习路径", "详解", "练习"],
    "language": ["知识地图", "学习路径", "详解", "练习"],
    "music-learning": ["知识地图", "结构图", "学习路径", "详解", "练习"],
    "music-appreciation": ["专业拆解", "听赏指南", "知识地图", "时间线", "结构图", "学习路径", "详解"],
}

SCOPE_LABEL = {"all": "全部", "chapter": "章节", "unit": "节点"}


# ---------------------------------------------------------------- utilities


def die(msg: str, code: int = 2) -> None:
    print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False))
    raise SystemExit(code)


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def now() -> str:
    from datetime import datetime

    return datetime.now().astimezone().isoformat(timespec="seconds")


def books_root() -> Path:
    return Path.cwd() / BOOKS_DIRNAME


def works_root() -> Path:
    return Path.cwd() / WORKS_DIRNAME


def load_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    path.write_text(body + ("\n" if body else ""), encoding="utf-8")


def slugify(text: str) -> str:
    keep = [c if (c.isalnum() or c in "-_") else "-" for c in text.strip()]
    slug = "".join(keep).strip("-").lower()
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:60] or "book"


REGISTRY_NAMES = ("book.json", "work.json")


def book_path(slug: str) -> Path:
    """Resolve a slug to its directory, checking books/ first, then works/."""
    for root in (books_root(), works_root()):
        candidate = root / slug
        if candidate.exists():
            return candidate
    return books_root() / slug


def load_registry(directory: Path) -> dict | None:
    for name in REGISTRY_NAMES:
        data = load_json(directory / name)
        if data:
            return data
    return None


def registry_file(book: dict) -> Path:
    name = "work.json" if book.get("kind") == "work" else "book.json"
    return book_path(book["slug"]) / name


def all_entries() -> list[Path]:
    found: list[Path] = []
    for root in (books_root(), works_root()):
        if not root.exists():
            continue
        found.extend(d for d in root.glob("*") if any((d / n).exists() for n in REGISTRY_NAMES))
    return found


def resolve_book(slug: str | None) -> dict:
    if slug:
        book = load_registry(book_path(slug))
        if not book:
            die(f"not found: {slug}")
        return book
    dirs = all_entries()
    if not dirs:
        die("nothing found; run: whh.py init <file> or work-init --meta <json>")
    if len(dirs) > 1:
        die("multiple entries present; pass --book <slug>: " + ", ".join(sorted(d.name for d in dirs)))
    book = load_registry(dirs[0])
    if not book:
        die(f"registry unreadable in {dirs[0]}")
    return book


def structure_of(book: dict) -> dict:
    return load_json(book_path(book["slug"]) / "structure.json") or {"chapters": []}


def chapter_version(book: dict, chapter_id: str | None) -> int:
    if chapter_id is None:
        return 1
    rec = book.get("chapters", {}).get(chapter_id)
    return int(rec.get("version", 1)) if rec else 1


def scope_version(book: dict, scope: str) -> int:
    if scope == "all":
        return sum(chapter_version(book, cid) for cid in book.get("chapters", {})) or 1
    chapter_id = scope.split(".")[0]
    return chapter_version(book, chapter_id)


def cache_key(book: dict, scope: str, product: str, depth: str) -> str:
    parts = [
        book["slug"],
        scope,
        product,
        depth,
        book.get("schema_version", SCHEMA_VERSION),
        str(scope_version(book, scope)),
    ]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12]


def find_unit(structure: dict, unit_id: str):
    for ch in structure.get("chapters", []):
        for unit in ch.get("units", []):
            if unit["unit_id"] == unit_id:
                return ch, unit
    return None, None


def scope_units(structure: dict, scope: str) -> list[dict]:
    if scope == "all":
        return [u for ch in structure.get("chapters", []) for u in ch.get("units", [])]
    if "." in scope:
        _, unit = find_unit(structure, scope)
        return [unit] if unit else []
    for ch in structure.get("chapters", []):
        if ch["chapter_id"] == scope:
            return ch.get("units", [])
    return []


# ---------------------------------------------------------------- commands


def cmd_init(args) -> None:
    from ingest import build_structure, read_blocks, summarize

    src = Path(args.source).expanduser()
    if not src.exists():
        die(f"source not found: {src}")

    blocks = read_blocks(src)
    structure = build_structure(blocks)
    if not structure["chapters"]:
        die("no chapters detected; the file may be empty or not a textbook")

    title = args.title or structure.get("title_hint") or src.stem
    slug = args.slug or slugify(title)
    if book_path(slug).exists() and not args.force:
        die(f"book already exists: {slug} (use --force to overwrite)")

    root = book_path(slug)
    (root / "views").mkdir(parents=True, exist_ok=True)
    (root / "units").mkdir(parents=True, exist_ok=True)

    # Full unit text goes to its own file so extraction can read it and the
    # structure index stays small.
    for ch in structure["chapters"]:
        for unit in ch.get("units", []):
            body = unit.pop("text", "")
            if body:
                (root / "units" / f"{unit['unit_id']}.txt").write_text(body, encoding="utf-8")

    book = {
        "slug": slug,
        "title": title,
        "source": str(src),
        "profile": args.profile,
        "subject": args.subject or "",
        "schema_version": SCHEMA_VERSION,
        "created_at": now(),
        "chapters": {
            ch["chapter_id"]: {"title": ch["title"], "version": 1, "updated_at": now()}
            for ch in structure["chapters"]
        },
    }
    save_json(root / "book.json", book)
    save_json(root / "structure.json", structure)
    for name in ("entities.jsonl", "relations.jsonl", "artifacts.jsonl"):
        (root / name).touch()

    emit(
        {
            "ok": True,
            "book": slug,
            "path": str(root),
            "title": title,
            "profile": args.profile,
            "summary": summarize(structure),
            "dropped_empty": structure.get("dropped_empty", 0),
            "unparsed": structure.get("unparsed", False),
        }
    )


def cmd_status(args) -> None:
    book = resolve_book(args.book)
    structure = structure_of(book)
    artifacts = read_jsonl(book_path(book["slug"]) / "artifacts.jsonl")
    plan = load_json(book_path(book["slug"]) / "plan.json")
    deepen = load_json(book_path(book["slug"]) / "deepen.json")
    units = scope_units(structure, "all")
    emit(
        {
            "ok": True,
            "book": book["slug"],
            "kind": book.get("kind", "textbook"),
            "title": book["title"],
            "composer": book.get("composer"),
            "profile": book.get("profile"),
            "chapters": len(structure.get("chapters", [])),
            "units": len(units),
            "plan": {
                "exists": bool(plan),
                "confirmed": bool(plan and plan.get("confirmed")),
                "intent": (plan or {}).get("intent"),
            },
            "artifacts": len(artifacts),
            "entities": len(read_jsonl(book_path(book["slug"]) / "entities.jsonl")),
            "relations": len(read_jsonl(book_path(book["slug"]) / "relations.jsonl")),
            "deepening": {
                "active": bool(deepen),
                "target_depth": (deepen or {}).get("target_depth"),
                "pending_units": len((deepen or {}).get("units", [])),
            },
        }
    )


def cmd_chapters(args) -> None:
    book = resolve_book(args.book)
    structure = structure_of(book)
    rows = []
    for ch in structure.get("chapters", []):
        types: dict[str, int] = {}
        for u in ch.get("units", []):
            types[u["content_type"]] = types.get(u["content_type"], 0) + 1
        rows.append(
            {
                "chapter_id": ch["chapter_id"],
                "index": ch["index"],
                "title": ch["title"],
                "units": len(ch.get("units", [])),
                "chars": sum(u.get("chars", 0) for u in ch.get("units", [])),
                "content_types": types,
                "version": chapter_version(book, ch["chapter_id"]),
            }
        )
    emit({"ok": True, "book": book["slug"], "chapters": rows})


def cmd_units(args) -> None:
    book = resolve_book(args.book)
    structure = structure_of(book)
    if args.chapter:
        units = scope_units(structure, args.chapter)
        if not units:
            die(f"chapter not found: {args.chapter}")
    else:
        units = scope_units(structure, "all")
    emit(
        {
            "ok": True,
            "book": book["slug"],
            "units": [
                {
                    "unit_id": u["unit_id"],
                    "title": u["title"],
                    "content_type": u["content_type"],
                    "chars": u["chars"],
                }
                for u in units
            ],
        }
    )


def cmd_unit_text(args) -> None:
    book = resolve_book(args.book)
    structure = structure_of(book)
    _, unit = find_unit(structure, args.id)
    if not unit:
        die(f"unit not found: {args.id}")
    path = book_path(book["slug"]) / "units" / f"{args.id}.txt"
    if not path.exists():
        die(f"unit text missing: {path}")
    emit(
        {
            "ok": True,
            "unit_id": args.id,
            "title": unit["title"],
            "content_type": unit["content_type"],
            "path": str(path),
            "chars": unit.get("chars", 0),
            "text": path.read_text(encoding="utf-8"),
        }
    )


def _parse_scope(raw: str | None) -> set[str] | None:
    if not raw or raw.strip().lower() == "all":
        return None
    return {part.strip() for part in raw.split(",") if part.strip()}


def _parse_depth_map(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    out: dict[str, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            die(f"depth map entry must look like ch03=L3, got: {part}")
        chapter, depth = part.split("=", 1)
        if depth.strip() not in DEPTHS:
            die(f"depth must be one of {DEPTHS}, got: {depth}")
        out[chapter.strip()] = depth.strip()
    return out


def cmd_plan_create(args) -> None:
    book = resolve_book(args.book)
    structure = structure_of(book)
    depth = args.depth
    if depth not in DEPTHS:
        die(f"depth must be one of {DEPTHS}")

    scope = _parse_scope(args.scope)
    depth_map = _parse_depth_map(args.depth_map)
    known = {ch["chapter_id"] for ch in structure.get("chapters", [])}
    unknown = (scope or set()) - known
    if unknown:
        die(f"unknown chapters in --scope: {sorted(unknown)}")
    unknown = set(depth_map) - known
    if unknown:
        die(f"unknown chapters in --depth-map: {sorted(unknown)}")

    selections = []
    for ch in structure.get("chapters", []):
        chapter_id = ch["chapter_id"]
        if scope is not None and chapter_id not in scope:
            continue
        unit_depth = depth_map.get(chapter_id, depth)
        for unit in ch.get("units", []):
            selections.append(
                {
                    "chapter_id": chapter_id,
                    "chapter_title": ch["title"],
                    "content_unit_id": unit["unit_id"],
                    "content_type": unit["content_type"],
                    "depth": unit_depth,
                    "recommended": True,
                    "selected": True,
                    "reason": "默认纳入当前范围",
                }
            )

    total_units = sum(len(ch.get("units", [])) for ch in structure.get("chapters", []))
    plan = {
        "plan_id": hashlib.sha1(f"{book['slug']}|{now()}".encode()).hexdigest()[:10],
        "created_at": now(),
        "book": book["slug"],
        "profile": book.get("profile"),
        "schema_version": book.get("schema_version", SCHEMA_VERSION),
        "user_intent": args.intent or "",
        "confirmed": False,
        "confirmed_at": None,
        "selectors": {
            "scope": sorted(scope) if scope else "all",
            "depth": depth,
            "depth_map": depth_map,
        },
        "summary": {
            "total_units": total_units,
            "selected_units": len(selections),
        },
        "selections": selections,
    }
    if not selections:
        die("the selected scope contains no content units")
    save_json(book_path(book["slug"]) / "plan.json", plan)
    emit(
        {
            "ok": True,
            "plan": plan["plan_id"],
            "summary": plan["summary"],
            "selectors": plan["selectors"],
            "confirmed": False,
        }
    )


def cmd_plan_confirm(args) -> None:
    book = resolve_book(args.book)
    path = book_path(book["slug"]) / "plan.json"
    plan = load_json(path)
    if not plan:
        die("no plan; run plan-create first")
    plan["confirmed"] = True
    plan["confirmed_at"] = now()
    plan["confirmed_by"] = args.by or "user"
    save_json(path, plan)
    emit({"ok": True, "plan": plan["plan_id"], "confirmed": True, "scope": plan["summary"]})


def cmd_plan_show(args) -> None:
    book = resolve_book(args.book)
    plan = load_json(book_path(book["slug"]) / "plan.json")
    if not plan:
        die("no plan; run plan-create first")
    if args.summary:
        plan = {k: v for k, v in plan.items() if k != "selections"}
    emit({"ok": True, "plan": plan})


def cmd_key(args) -> None:
    book = resolve_book(args.book)
    if args.product not in PRODUCTS:
        die(f"unknown product: {args.product}")
    if args.depth not in DEPTHS:
        die(f"depth must be one of {DEPTHS}")
    key = cache_key(book, args.scope, args.product, args.depth)
    root = book_path(book["slug"])
    rows = read_jsonl(root / "artifacts.jsonl")
    hit = next((r for r in rows if r["key"] == key), None)
    emit(
        {
            "ok": True,
            "key": key,
            "scope": args.scope,
            "product": args.product,
            "depth": args.depth,
            "scope_version": scope_version(book, args.scope),
            "hit": bool(hit),
            "artifact": hit,
            "figure": PRODUCTS[args.product]["figure"],
        }
    )


def cmd_artifact_put(args) -> None:
    book = resolve_book(args.book)
    if args.product not in PRODUCTS:
        die(f"unknown product: {args.product}")
    key = cache_key(book, args.scope, args.product, args.depth)
    root = book_path(book["slug"])
    view = Path(args.file)
    if not view.exists():
        die(f"view file not found: {view}")
    target = root / "views" / f"{key}{view.suffix or '.html'}"
    if view.resolve() != target.resolve():
        target.write_bytes(view.read_bytes())

    rows = read_jsonl(root / "artifacts.jsonl")
    entry = {
        "key": key,
        "scope": args.scope,
        "product": args.product,
        "depth": args.depth,
        "figure": PRODUCTS[args.product]["figure"],
        "file": f"views/{target.name}",
        "chapter_id": args.scope.split(".")[0] if args.scope != "all" else None,
        "nodes": args.nodes,
        "created_at": now(),
        "scope_version": scope_version(book, args.scope),
    }
    replaced = False
    for i, row in enumerate(rows):
        if row["key"] == key:
            rows[i] = entry
            replaced = True
            break
    if not replaced:
        rows.append(entry)
    write_jsonl(root / "artifacts.jsonl", rows)
    emit({"ok": True, "key": key, "file": entry["file"], "replaced": replaced, "total": len(rows)})


def cmd_artifact_list(args) -> None:
    book = resolve_book(args.book)
    rows = read_jsonl(book_path(book["slug"]) / "artifacts.jsonl")
    if args.scope:
        rows = [r for r in rows if r["scope"] == args.scope]
    emit({"ok": True, "count": len(rows), "artifacts": rows})


def _squash(text: str) -> str:
    """Drop whitespace and CJK/ASCII punctuation so quotes can be matched loosely."""
    return re.sub(r"[\s，。、；：？！「」『』“”‘’（）()《》〈〉…—－·,.;:?!\"']+", "", text or "")


def _unit_text(root: Path, unit_id: str) -> str | None:
    path = root / "units" / f"{unit_id}.txt"
    return path.read_text(encoding="utf-8") if path.exists() else None


def cmd_entities_import(args) -> None:
    book = resolve_book(args.book)
    root = book_path(book["slug"])
    src = Path(args.file)
    if not src.exists():
        die(f"file not found: {src}")
    incoming = read_jsonl(src)
    if not incoming:
        die("no rows in import file")
    kind = "relations" if args.kind == "relations" else "entities"
    path = root / f"{kind}.jsonl"
    existing = [] if args.replace else read_jsonl(path)
    by_id = {r.get("entity_id") or r.get("relation_id"): r for r in existing}

    entity_ids = {e.get("entity_id") for e in read_jsonl(root / "entities.jsonl")}
    orphans: list[dict] = []
    unverified: list[dict] = []
    accepted: list[str] = []

    for row in incoming:
        rid = row.get("entity_id") or row.get("relation_id")
        if not rid:
            die(f"row missing id: {row}")
        if kind == "relations":
            missing = [
                end
                for end in (row.get("source_entity_id"), row.get("target_entity_id"))
                if end not in entity_ids
            ]
            if missing:
                orphans.append({"relation_id": rid, "missing": missing})
                if not args.allow_orphans:
                    continue
        else:
            quote = (row.get("source_reference") or {}).get("quote")
            unit_id = row.get("content_unit_id")
            if quote and unit_id:
                text = _unit_text(root, unit_id)
                if text is not None and _squash(quote) not in _squash(text):
                    unverified.append({"entity_id": rid, "quote": quote[:40]})
                    if not args.allow_unverified:
                        continue
                    row["extraction_status"] = "partial"
        accepted.append(rid)
        by_id[rid] = row

    order = [r.get("entity_id") or r.get("relation_id") for r in existing]
    added = sum(1 for rid in accepted if rid not in order)
    updated = len(accepted) - added
    write_jsonl(path, list(by_id.values()))
    emit(
        {
            "ok": True,
            "kind": kind,
            "added": added,
            "updated": updated,
            "total": len(by_id),
            "orphans": orphans,
            "rejected": 0 if args.allow_orphans else len(orphans),
            "unverified": unverified,
            "rejected_unverified": 0 if args.allow_unverified else len(unverified),
        }
    )


def cmd_version_bump(args) -> None:
    book = resolve_book(args.book)
    if args.chapter not in book.get("chapters", {}):
        die(f"chapter not found: {args.chapter}")
    rec = book["chapters"][args.chapter]
    rec["version"] = int(rec.get("version", 1)) + 1
    rec["updated_at"] = now()
    save_json(registry_file(book), book)

    rows = read_jsonl(book_path(book["slug"]) / "artifacts.jsonl")
    stale = [r["key"] for r in rows if r["scope"].split(".")[0] == args.chapter or r["scope"] == "all"]
    emit({"ok": True, "chapter": args.chapter, "version": rec["version"], "stale": stale})


def scan_candidate_files(limit: int = 8) -> list[Path]:
    """Candidate textbook files in the working directory, newest first."""
    exts = {".docx", ".txt", ".md", ".markdown"}
    try:
        files = [p for p in Path.cwd().iterdir() if p.is_file() and p.suffix.lower() in exts]
    except OSError:
        return []
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]


def entity_depth(entities: list[dict], scope: str) -> tuple[int, int]:
    """Highest modelled depth in scope, and how many entities it holds."""
    if scope == "all":
        rows = entities
    else:
        cid = scope.split(".")[0]
        rows = [e for e in entities if e.get("chapter_id") == cid]
    best = 0
    for e in rows:
        best = max(best, int(str(e.get("extraction_depth", "L0"))[1:] or 0))
    return best, len(rows)


def depth_options(structure: dict, entities: list[dict], scope: str) -> list[dict]:
    covered, _ = entity_depth(entities, scope)
    labels = {"L1": "结构", "L2": "知识点", "L3": "深度", "L4": "精细"}
    out = []
    for d in DEPTHS:
        level = int(d[1])
        detail = "已有 · 直接复用" if covered >= level else "需抽取"
        out.append({"value": d, "label": f"{d} {labels[d]}", "detail": detail})
    return out


def scope_options(book: dict, structure: dict) -> list[dict]:
    rows = [{"value": "all", "label": "全部", "detail": f"{len(scope_units(structure, 'all'))} 个内容单元"}]
    for ch in structure.get("chapters", []):
        rows.append(
            {
                "value": ch["chapter_id"],
                "label": ch["title"],
                "detail": f"{len(ch.get('units', []))} 单元 · 版本 v{chapter_version(book, ch['chapter_id'])}",
            }
        )
    return rows


def _ranks(ids: set[str], edges: list[dict]) -> dict[str, int]:
    """Longest-path ranking with cycle tolerance."""
    out: dict[str, list[str]] = {i: [] for i in ids}
    indeg: dict[str, int] = {i: 0 for i in ids}
    for edge in edges:
        src, dst = edge.get("source"), edge.get("target")
        if src in ids and dst in ids and src != dst:
            out[src].append(dst)
            indeg[dst] += 1
    rank = {i: 0 for i in ids}
    queue = [i for i in ids if indeg[i] == 0]
    seen: set[str] = set()
    while queue:
        cur = queue.pop(0)
        if cur in seen:
            continue
        seen.add(cur)
        for nxt in out[cur]:
            rank[nxt] = max(rank[nxt], rank[cur] + 1)
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    leftover = [i for i in ids if i not in seen]
    if leftover:
        base = max(rank.values(), default=0) + 1
        for i in leftover:
            rank[i] = base
    return rank


def _order_key(entity: dict) -> str:
    """Timeline ordering hint: attributes.order, then year, then time."""
    attrs = entity.get("attributes") or {}
    for key in ("order", "year", "time", "period"):
        value = attrs.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def build_view_spec(book: dict, structure: dict, entities: list[dict], relations: list[dict],
                    scope: str, product: str, depth: str, max_nodes: int = 9) -> dict:
    if scope == "all":
        pool = list(entities)
    else:
        chapter_id = scope.split(".")[0]
        pool = [e for e in entities if e.get("chapter_id") == chapter_id]
    if not pool:
        pool = entities

    keep_ids = {e.get("entity_id") for e in pool}
    edges = [
        r
        for r in relations
        if r.get("source_entity_id") in keep_ids and r.get("target_entity_id") in keep_ids
    ]

    allowed_types = PRODUCTS.get(product, {}).get("edge_types")
    if allowed_types:
        edges = [r for r in edges if r.get("relation_type") in allowed_types]

    degree: dict[str, int] = {}
    for edge in edges:
        degree[edge["source_entity_id"]] = degree.get(edge["source_entity_id"], 0) + 1
        degree[edge["target_entity_id"]] = degree.get(edge["target_entity_id"], 0) + 1

    truncated = {"shown": len(pool), "total": len(pool)}
    if len(pool) > max_nodes:
        if PRODUCTS.get(product, {}).get("layout") == "timeline":
            dated = sorted([e for e in pool if _order_key(e)], key=_order_key)
            undated = [e for e in pool if not _order_key(e)]
            ordered = dated + undated
            pool = ordered[:max_nodes]
        else:
            pool = sorted(pool, key=lambda e: (-degree.get(e.get("entity_id"), 0), e.get("name", "")))[:max_nodes]
        keep_ids = {e.get("entity_id") for e in pool}
        edges = [r for r in edges if r["source_entity_id"] in keep_ids and r["target_entity_id"] in keep_ids]
        truncated = {"shown": len(pool), "total": truncated["total"]}

    ids = {e.get("entity_id") for e in pool}
    norm_edges = [
        {"source": r["source_entity_id"], "target": r["target_entity_id"]} for r in edges
    ]
    ranks = _ranks(ids, norm_edges)
    has_incoming = {r["target_entity_id"] for r in edges}
    top_degree = sorted(ids, key=lambda i: -degree.get(i, 0))[:2]
    focal = {i for i in top_degree if degree.get(i, 0) > 0}

    nodes = [
        {
            "id": e.get("entity_id"),
            "label": e.get("name") or e.get("entity_id"),
            "type": str(e.get("entity_type", "")),
            "depth": e.get("extraction_depth", ""),
            "rank": ranks.get(e.get("entity_id"), 0),
            "has_incoming": e.get("entity_id") in has_incoming,
            "focal": e.get("entity_id") in focal,
            "order": _order_key(e),
            "time_label": _order_key(e),
        }
        for e in pool
    ]

    types = sorted({n["type"] for n in nodes if n["type"]})
    scope_label = "全部" if scope == "all" else scope
    note_bits = []
    if truncated["shown"] < truncated["total"]:
        note_bits.append(
            f"本图只画了关联度最高的 {truncated['shown']} 个节点，范围内共 {truncated['total']} 个；"
            "其余未显示，不是不存在。"
        )
    if not edges:
        note_bits.append("当前范围内没有已建立的关系，图中只有节点。")
    if truncate_warn := [n for n in nodes if not n["depth"]]:
        note_bits.append(f"{len(truncate_warn)} 个节点未标注深度。")

    return {
        "slug": cache_key(book, scope, product, depth),
        "title": f"{book.get('title', '')} · {product}",
        "eyebrow": product,
        "subtitle": f"{scope_label} · {len(nodes)} 个节点 · {len(edges)} 条关系 · 深度 {depth}",
        "desc": f"{book.get('title', '')} 的{product}，包含 {len(nodes)} 个节点和 {len(edges)} 条关系。",
        "nodes": nodes,
        "edges": [{"source": e["source_entity_id"], "target": e["target_entity_id"], "type": e.get("relation_type", "")} for e in edges],
        "legend": [{"label": t} for t in types],
        "note": " ".join(note_bits),
        "truncated": truncated,
        "figure": PRODUCTS.get(product, {}).get("figure", ""),
        "layout": PRODUCTS.get(product, {}).get("layout", "layered"),
    }


def build_overview_spec(book: dict, structure: dict, entities: list[dict], relations: list[dict],
                        product: str, depth: str) -> dict:
    """Chapter-level overview: one node per chapter, edges aggregate cross-chapter relations."""
    order = {ch["chapter_id"]: ch["index"] for ch in structure.get("chapters", [])}
    titles = {ch["chapter_id"]: ch["title"] for ch in structure.get("chapters", [])}

    counts: dict[str, int] = {}
    for entity in entities:
        cid = entity.get("chapter_id")
        if cid:
            counts[cid] = counts.get(cid, 0) + 1

    chapter_of = {e.get("entity_id"): e.get("chapter_id") for e in entities}
    agg: dict[tuple[str, str], int] = {}
    for rel in relations:
        src = chapter_of.get(rel.get("source_entity_id"))
        dst = chapter_of.get(rel.get("target_entity_id"))
        if src and dst and src != dst:
            agg[(src, dst)] = agg.get((src, dst), 0) + 1

    nodes = []
    for cid in sorted(counts, key=lambda c: order.get(c, 0)):
        nodes.append(
            {
                "id": cid,
                "label": titles.get(cid, cid),
                "type": f"{counts[cid]} 项",
                "depth": depth,
                "rank": order.get(cid, 0) - 1,
                "has_incoming": any(dst == cid for _, dst in agg),
                "focal": False,
            }
        )

    edges = [{"source": s, "target": d, "type": f"{n} 条"} for (s, d), n in agg.items()]

    return {
        "slug": cache_key(book, "all", product, depth) + "-ov",
        "title": f"{book.get('title', '')} · {product}（总览）",
        "eyebrow": product,
        "subtitle": f"全书总览 · {len(nodes)} 章 · {len(entities)} 个知识点，逐章展开看细节",
        "desc": f"{book.get('title', '')} 的章节级知识总览。",
        "nodes": nodes,
        "edges": edges,
        "legend": [{"label": "Chapter"}],
        "note": "总览只到章。每章的实体在对应的分章图里。",
        "truncated": {"shown": len(nodes), "total": len(nodes)},
        "figure": PRODUCTS.get(product, {}).get("figure", ""),
        "layout": "layered",
    }


def _persist_view(book: dict, root: Path, scope: str, product: str, depth: str, spec: dict,
                  force: bool = False) -> dict:
    from render_diagram import render as render_diagram

    key = cache_key(book, scope, product, depth)
    target = root / "views" / f"{key}.html"
    rows = read_jsonl(root / "artifacts.jsonl")
    existing = next((r for r in rows if r["key"] == key), None)
    if existing and target.exists() and not force:
        return {"scope": scope, "key": key, "file": existing["file"], "reused": True,
                "nodes": existing.get("nodes"), "edges": None}

    spec = dict(spec)
    spec["slug"] = key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_diagram(spec), encoding="utf-8")

    entry = {
        "key": key,
        "scope": scope,
        "product": product,
        "depth": depth,
        "figure": spec["figure"],
        "file": f"views/{target.name}",
        "chapter_id": scope.split(".")[0] if scope != "all" else None,
        "nodes": len(spec["nodes"]),
        "created_at": now(),
        "scope_version": scope_version(book, scope),
    }
    replaced = False
    for i, row in enumerate(rows):
        if row["key"] == key:
            rows[i] = entry
            replaced = True
            break
    if not replaced:
        rows.append(entry)
    write_jsonl(root / "artifacts.jsonl", rows)
    return {
        "scope": scope,
        "key": key,
        "file": entry["file"],
        "reused": False,
        "nodes": len(spec["nodes"]),
        "edges": len(spec["edges"]),
        "truncated": spec["truncated"],
        "note": spec.get("note", ""),
        "replaced": replaced,
    }


def cmd_view(args) -> None:
    book = resolve_book(args.book)
    root = book_path(book["slug"])
    if args.product not in PRODUCTS:
        die(f"unknown product: {args.product}")
    if args.depth not in DEPTHS:
        die(f"depth must be one of {DEPTHS}")

    structure = structure_of(book)
    entities = read_jsonl(root / "entities.jsonl")
    relations = read_jsonl(root / "relations.jsonl")
    if not entities:
        die("知识库为空，先完成抽取（entities-import）")

    if args.split and args.scope == "all":
        views = []
        if len(entities) > args.max_nodes:
            overview = build_overview_spec(book, structure, entities, relations, args.product, args.depth)
            views.append(_persist_view(book, root, "all", args.product, args.depth, overview, args.force))
            for ch in structure.get("chapters", []):
                cid = ch["chapter_id"]
                if not any(e.get("chapter_id") == cid for e in entities):
                    continue
                spec = build_view_spec(
                    book, structure, entities, relations, cid, args.product, args.depth, args.max_nodes
                )
                views.append(_persist_view(book, root, cid, args.product, args.depth, spec, args.force))
        else:
            spec = build_view_spec(
                book, structure, entities, relations, "all", args.product, args.depth, args.max_nodes
            )
            views.append(_persist_view(book, root, "all", args.product, args.depth, spec, args.force))
        emit({"ok": True, "split": True, "views": views})
        return

    spec = build_view_spec(
        book, structure, entities, relations, args.scope, args.product, args.depth, args.max_nodes
    )
    result = _persist_view(book, root, args.scope, args.product, args.depth, spec, args.force)
    result["ok"] = True
    emit(result)


def _depth_level(depth: str) -> int:
    return int(str(depth or "L0")[1:] or 0) if str(depth or "").startswith("L") else 0


def cmd_deepen(args) -> None:
    """Plan or apply an incremental deepening pass.

    Without --apply it only computes the worklist. With --apply it assumes the
    extraction is already imported, bumps the affected chapter versions and marks
    the stale artifacts.
    """
    book = resolve_book(args.book)
    root = book_path(book["slug"])
    structure = structure_of(book)
    entities = read_jsonl(root / "entities.jsonl")
    plan = load_json(root / "plan.json") or {}
    existing_task = load_json(root / "deepen.json") if args.apply else None

    target = args.depth or (existing_task or {}).get("target_depth")
    if not target:
        die("--depth is required unless there is an active deepening task")
    if target not in DEPTHS:
        die(f"depth must be one of {DEPTHS}")
    target_level = _depth_level(target)

    chapters = structure.get("chapters", [])
    if args.scope and args.scope != "all":
        wanted = _parse_scope(args.scope) or set()
        unknown = wanted - {c["chapter_id"] for c in chapters}
        if unknown:
            die(f"unknown chapters: {sorted(unknown)}")
        chapters = [c for c in chapters if c["chapter_id"] in wanted]

    unit_depth: dict[str, int] = {}
    for entity in entities:
        unit_id = entity.get("content_unit_id")
        unit_depth[unit_id] = max(unit_depth.get(unit_id, 0), _depth_level(entity.get("extraction_depth")))

    worklist = []
    for chapter in chapters:
        for unit in chapter.get("units", []):
            current = unit_depth.get(unit["unit_id"], 0)
            if current < target_level:
                worklist.append(
                    {
                        "unit_id": unit["unit_id"],
                        "chapter_id": chapter["chapter_id"],
                        "title": unit.get("title", ""),
                        "current_depth": f"L{current}" if current else "未抽取",
                        "target_depth": target,
                    }
                )

    affected = sorted({w["chapter_id"] for w in worklist})

    if not args.apply:
        task = {
            "created_at": now(),
            "target_depth": target,
            "scope": args.scope or "all",
            "units": worklist,
        }
        save_json(root / "deepen.json", task)
        emit(
            {
                "ok": True,
                "applied": False,
                "target_depth": target,
                "pending_units": len(worklist),
                "chapters": affected,
                "units": worklist[: args.limit],
                "next": "抽完之后跑 deepen --apply 让受影响的产物失效",
            }
        )
        return

    task = existing_task
    if args.apply and not task:
        die("no deepening task; run deepen without --apply first")
    improved = len(task.get("units", [])) - len(worklist)
    warning = None if improved > 0 else "没有检测到新增或加深的实体，确认抽取结果已经导入"
    if not affected:
        (root / "deepen.json").unlink(missing_ok=True)
        emit({"ok": True, "applied": True, "note": "没有需要深化的单元", "bumped": [], "stale": []})
        return

    bumped = []
    for chapter_id in affected:
        rec = book.get("chapters", {}).get(chapter_id)
        if not rec:
            continue
        rec["version"] = int(rec.get("version", 1)) + 1
        rec["updated_at"] = now()
        bumped.append({"chapter_id": chapter_id, "version": rec["version"]})
    save_json(registry_file(book), book)

    stale = []
    for artifact in read_jsonl(root / "artifacts.jsonl"):
        chapter_of_scope = None if artifact["scope"] == "all" else artifact["scope"].split(".")[0]
        if artifact["scope"] == "all" or chapter_of_scope in affected:
            stale.append(artifact["key"])

    if plan.get("selections"):
        for selection in plan["selections"]:
            if selection.get("chapter_id") in affected and _depth_level(selection.get("depth")) < target_level:
                selection["depth"] = target
        plan["summary"]["selected_units"] = len(plan["selections"])
        save_json(root / "plan.json", plan)

    (root / "deepen.json").unlink(missing_ok=True)
    emit({"ok": True, "applied": True, "bumped": bumped, "stale": stale, "units": len(worklist), "warning": warning})


def cmd_guide(args) -> None:
    """Return every choice the user can make right now, so no entry dead-ends."""
    entries = all_entries()

    if not entries:
        files = scan_candidate_files()
        options = [
            {
                "value": p.name,
                "label": p.name,
                "detail": f"{p.suffix.lstrip('.').upper()} · {max(1, p.stat().st_size // 1024)} KB",
            }
            for p in files
        ]
        if not options:
            options = [{"value": "", "label": "当前目录没有教材文件", "detail": "放入 .docx/.txt/.md 后重试"}]
        emit(
            {
                "ok": True,
                "mode": "start",
                "state": {"entries": 0, "cwd": str(Path.cwd())},
                "steps": [{"id": "file", "label": "选择要拆解的教材", "options": options}],
                "note": "还没有任何教材或作品。选中一个文件后执行拆解。",
            }
        )
        return

    if not args.book and len(entries) > 1:
        options = []
        for d in entries:
            reg = load_registry(d) or {}
            kind = "作品" if reg.get("kind") == "work" else "教材"
            options.append(
                {
                    "value": reg.get("slug", d.name),
                    "label": f"{reg.get('title', d.name)}",
                    "detail": f"{kind} · {reg.get('composer') or reg.get('profile') or ''}".strip(" ·"),
                }
            )
        emit(
            {
                "ok": True,
                "mode": "select-entry",
                "state": {"entries": len(entries)},
                "steps": [{"id": "entry", "label": "选择要操作的对象", "options": options}],
                "note": "存在多个教材/作品，先选一个。",
            }
        )
        return

    book = resolve_book(args.book)
    root = book_path(book["slug"])
    structure = structure_of(book)
    entities = read_jsonl(root / "entities.jsonl")
    artifacts = read_jsonl(root / "artifacts.jsonl")
    plan = load_json(root / "plan.json") or {}
    sources = read_jsonl(root / "sources.jsonl")
    kinds = [a.get("product") for a in artifacts]

    base_state = {
        "book": book["slug"],
        "title": book.get("title"),
        "kind": book.get("kind", "textbook"),
        "chapters": len(structure.get("chapters", [])),
        "units": len(scope_units(structure, "all")),
        "entities": len(entities),
        "artifacts": len(artifacts),
        "sources": len(sources),
    }

    # ---- 作品模式 ----
    if book.get("kind") == "work":
        steps = []
        if len(sources) < 3:
            steps.append(
                {
                    "id": "sources",
                    "label": f"补足来源（当前 {len(sources)}/3）",
                    "options": [
                        {"value": "search", "label": "继续检索并记录来源", "detail": "至少三个独立来源"},
                        {"value": "skip", "label": "用现有来源继续", "detail": "报告会标「来源不足」"},
                    ],
                }
            )
        else:
            if "专业拆解" not in kinds:
                steps.append(
                    {
                        "id": "analysis",
                        "label": "生成专业拆解",
                        "options": [
                            {"value": "L2", "label": "L2 基础", "detail": "基本信息 + 结构"},
                            {"value": "L3", "label": "L3 深度", "detail": "加曲式与和声"},
                            {"value": "L4", "label": "L4 精细", "detail": "加版本比较"},
                        ],
                    }
                )
            if "听赏指南" not in kinds:
                steps.append(
                    {
                        "id": "guide-scope",
                        "label": "生成听赏指南",
                        "options": scope_options(book, structure),
                    }
                )
        if not steps:
            steps = [
                {
                    "id": "refresh",
                    "label": "专业拆解与听赏指南都已生成",
                    "options": [
                        {"value": "open", "label": "打开产物目录", "detail": "index.html"},
                        {"value": "redo", "label": "换深度重做", "detail": "会替换旧条目"},
                    ],
                }
            ]
        emit({"ok": True, "mode": "work", "state": base_state, "steps": steps})
        return

    # ---- 教材模式 ----
    if not plan:
        steps = [
            {
                "id": "scope",
                "label": "选择拆解范围",
                "options": scope_options(book, structure),
            },
            {
                "id": "depth",
                "label": "选择建模深度",
                "options": depth_options(structure, entities, "all"),
            },
        ]
        note = "选定范围与深度后生成方案；方案确认后才开始抽取。"
    elif not plan.get("confirmed"):
        summary = plan.get("summary", {})
        steps = [
            {
                "id": "confirm",
                "label": f"确认方案（{summary.get('selected_units', 0)} 单元）",
                "options": [
                    {"value": "accept", "label": "按这个方案铺开", "detail": "确认后开始抽取"},
                    {"value": "depth", "label": "调整深度", "detail": "重建方案"},
                    {"value": "scope", "label": "调整范围", "detail": "只做部分章节"},
                ],
            }
        ]
        note = "未确认前不会抽取。"
    elif not entities:
        steps = [
            {
                "id": "extract",
                "label": "选择先抽取的范围",
                "options": scope_options(book, structure),
            }
        ]
        note = "方案已确认，按选定范围抽取实体与关系。"
    else:
        profile = book.get("profile") or "mathematics"
        products = PROFILE_PRODUCTS.get(profile) or list(PRODUCTS)
        steps = [
            {"id": "scope", "label": "选择范围", "options": scope_options(book, structure)},
            {
                "id": "product",
                "label": "选择产物",
                "options": [
                    {
                        "value": name,
                        "label": name,
                        "detail": PRODUCTS[name]["figure"],
                        "generated": kinds.count(name),
                    }
                    for name in products
                ],
            },
            {"id": "depth", "label": "选择深度", "options": depth_options(structure, entities, "all")},
        ]
        note = "选完范围、产物、深度后先查重，命中直接复用。"

    emit({"ok": True, "mode": "book", "state": base_state, "steps": steps, "note": note})


def cmd_work_init(args) -> None:
    meta_path = Path(args.meta)
    if not meta_path.exists():
        die(f"metadata not found: {meta_path}")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        die(f"metadata is not valid JSON: {exc}")

    title = (meta.get("title") or "").strip()
    if not title:
        die("metadata needs a title")
    composer = (meta.get("composer") or "").strip()
    slug = args.slug or slugify(f"{composer}-{title}" if composer else title)

    root = works_root() / slug
    if root.exists() and not args.force:
        die(f"work already exists: {slug} (use --force to overwrite)")

    sections = meta.get("sections") or [{"title": "全曲"}]
    if not isinstance(sections, list) or not sections:
        die("sections must be a non-empty list")

    chapters = []
    for i, sec in enumerate(sections, start=1):
        sec_title = str(sec.get("title") or f"段落 {i}").strip()
        chapter_id = f"ch{i:02d}"
        chapters.append(
            {
                "chapter_id": chapter_id,
                "index": i,
                "title": sec_title,
                "sections": [],
                "time": {"start": sec.get("start", ""), "end": sec.get("end", "")},
                "units": [
                    {
                        "unit_id": f"{chapter_id}.u01",
                        "title": sec_title,
                        "content_type": "听赏段落",
                        "chars": 0,
                        "preview": str(sec.get("note") or "")[:160],
                    }
                ],
            }
        )

    (root / "views").mkdir(parents=True, exist_ok=True)
    work = {
        "slug": slug,
        "kind": "work",
        "title": title,
        "composer": composer,
        "genre": meta.get("genre", ""),
        "key": meta.get("key", ""),
        "year": meta.get("year", ""),
        "duration": meta.get("duration", ""),
        "profile": "music-appreciation",
        "source_query": meta.get("query", ""),
        "schema_version": SCHEMA_VERSION,
        "created_at": now(),
        "chapters": {
            ch["chapter_id"]: {"title": ch["title"], "version": 1, "updated_at": now()} for ch in chapters
        },
    }
    save_json(root / "work.json", work)
    save_json(root / "structure.json", {"title_hint": title, "chapters": chapters})
    for name in ("sources.jsonl", "artifacts.jsonl"):
        (root / name).touch()

    emit(
        {
            "ok": True,
            "work": slug,
            "path": str(root),
            "title": title,
            "composer": composer,
            "sections": len(chapters),
        }
    )


def cmd_source_add(args) -> None:
    book = resolve_book(args.book)
    path = book_path(book["slug"]) / "sources.jsonl"
    rows = read_jsonl(path)
    url = (args.url or "").strip()
    if not url:
        die("--url is required")
    entry = {
        "url": url,
        "title": args.title or "",
        "publisher": args.publisher or "",
        "excerpt": args.excerpt or "",
        "accessed": args.accessed or now(),
        "kind": args.kind,
    }
    for i, row in enumerate(rows):
        if row.get("url") == url:
            rows[i] = entry
            write_jsonl(path, rows)
            emit({"ok": True, "url": url, "replaced": True, "sources": len(rows)})
            return
    rows.append(entry)
    write_jsonl(path, rows)
    emit({"ok": True, "url": url, "replaced": False, "sources": len(rows)})


def cmd_source_list(args) -> None:
    book = resolve_book(args.book)
    rows = read_jsonl(book_path(book["slug"]) / "sources.jsonl")
    emit({"ok": True, "count": len(rows), "sources": rows})


def cmd_pending(args) -> None:
    """Units that still have no entities — the extraction worklist."""
    book = resolve_book(args.book)
    root = book_path(book["slug"])
    structure = structure_of(book)
    entities = read_jsonl(root / "entities.jsonl")
    covered = {e.get("content_unit_id") for e in entities}

    rows = []
    for ch in structure.get("chapters", []):
        for unit in ch.get("units", []):
            if unit["unit_id"] in covered:
                continue
            rows.append(
                {
                    "unit_id": unit["unit_id"],
                    "chapter_id": ch["chapter_id"],
                    "chapter_title": ch["title"],
                    "title": unit.get("title", ""),
                    "content_type": unit.get("content_type", ""),
                    "chars": unit.get("chars", 0),
                }
            )
    total = sum(len(ch.get("units", [])) for ch in structure.get("chapters", []))
    emit(
        {
            "ok": True,
            "book": book["slug"],
            "total_units": total,
            "done": total - len(rows),
            "remaining": len(rows),
            "progress": round((total - len(rows)) / total, 3) if total else 0,
            "units": rows[: args.limit],
        }
    )


def cmd_check(args) -> None:
    """Report consistency problems the import step cannot catch on its own."""
    book = resolve_book(args.book)
    root = book_path(book["slug"])
    structure = structure_of(book)
    entities = read_jsonl(root / "entities.jsonl")
    relations = read_jsonl(root / "relations.jsonl")

    issues: list[dict] = []

    by_name: dict[str, list[str]] = {}
    for entity in entities:
        key = _squash(entity.get("name") or "")
        if key:
            by_name.setdefault(key, []).append(entity.get("entity_id"))
    for name, ids in by_name.items():
        if len(set(ids)) > 1:
            issues.append({"type": "duplicate_name", "name": name, "ids": sorted(set(ids))})

    covered = {e.get("content_unit_id") for e in entities}
    for ch in structure.get("chapters", []):
        for unit in ch.get("units", []):
            if unit["unit_id"] not in covered:
                issues.append(
                    {
                        "type": "unit_without_entities",
                        "unit_id": unit["unit_id"],
                        "title": unit.get("title", ""),
                    }
                )

    for entity in entities:
        ref = entity.get("source_reference") or {}
        if not ref.get("quote"):
            issues.append({"type": "missing_quote", "entity_id": entity.get("entity_id")})
            continue
        text = _unit_text(root, entity.get("content_unit_id", ""))
        if text is not None and _squash(ref["quote"]) not in _squash(text):
            issues.append({"type": "quote_not_found", "entity_id": entity.get("entity_id")})

    ids = {e.get("entity_id") for e in entities}
    for rel in relations:
        missing = [
            end
            for end in (rel.get("source_entity_id"), rel.get("target_entity_id"))
            if end not in ids
        ]
        if missing:
            issues.append({"type": "orphan_relation", "relation_id": rel.get("relation_id"), "missing": missing})

    by_type: dict[str, int] = {}
    for issue in issues:
        by_type[issue["type"]] = by_type.get(issue["type"], 0) + 1

    emit(
        {
            "ok": not issues,
            "book": book["slug"],
            "entities": len(entities),
            "relations": len(relations),
            "issues": issues[: args.limit],
            "total_issues": len(issues),
            "by_type": by_type,
        }
    )


def cmd_search(args) -> None:
    """Find entities by name/description and return them with their neighbours."""
    book = resolve_book(args.book)
    root = book_path(book["slug"])
    entities = read_jsonl(root / "entities.jsonl")
    relations = read_jsonl(root / "relations.jsonl")

    query = _squash(args.query)
    if not query:
        die("--query is required")

    matches = []
    for entity in entities:
        if args.chapter and entity.get("chapter_id") != args.chapter:
            continue
        name = _squash(entity.get("name") or "")
        blob = _squash((entity.get("name") or "") + (entity.get("description") or ""))
        if query in name:
            score = 3
        elif query in blob:
            score = 1
        else:
            continue
        matches.append({**entity, "_score": score})

    matches.sort(key=lambda m: (-m["_score"], len(m.get("name") or "")))
    matches = matches[: args.limit]

    hit_ids = {m.get("entity_id") for m in matches}
    linked = [
        r
        for r in relations
        if r.get("source_entity_id") in hit_ids or r.get("target_entity_id") in hit_ids
    ]
    neighbour_ids = {
        end
        for r in linked
        for end in (r.get("source_entity_id"), r.get("target_entity_id"))
        if end not in hit_ids
    }
    neighbours = [e for e in entities if e.get("entity_id") in neighbour_ids]

    emit(
        {
            "ok": True,
            "query": args.query,
            "matches": [{k: v for k, v in m.items() if k != "_score"} for m in matches],
            "relations": linked,
            "neighbours": [
                {
                    "entity_id": e.get("entity_id"),
                    "name": e.get("name"),
                    "entity_type": e.get("entity_type"),
                    "chapter_id": e.get("chapter_id"),
                }
                for e in neighbours
            ],
        }
    )


def cmd_report(args) -> None:
    """Write the modelling report: committed scope vs what is actually done."""
    book = resolve_book(args.book)
    root = book_path(book["slug"])
    structure = structure_of(book)
    entities = read_jsonl(root / "entities.jsonl")
    relations = read_jsonl(root / "relations.jsonl")
    artifacts = read_jsonl(root / "artifacts.jsonl")
    plan = load_json(root / "plan.json") or {}

    all_units = [u for ch in structure.get("chapters", []) for u in ch.get("units", [])]
    covered = {e.get("content_unit_id") for e in entities}
    done_units = [u for u in all_units if u["unit_id"] in covered]
    pending_units = [u for u in all_units if u["unit_id"] not in covered]

    committed = [s["content_unit_id"] for s in plan.get("selections", [])]
    committed_set = set(committed)
    committed_done = [u for u in committed if u in covered]
    committed_pending = [u for u in committed if u not in covered]

    if committed:
        completion = round(len(committed_done) / len(committed), 3)
        completion_text = f"{completion:.1%}（{len(committed_done)}/{len(committed)} 个已承诺单元）"
    else:
        completion = None
        completion_text = "无方案基线，不计算完成度"

    if plan.get("confirmed"):
        plan_state = "已确认"
    elif plan:
        plan_state = "未确认"
    else:
        plan_state = "不存在"

    lines = [
        f"# 建模报告 · {book.get('title', '')}",
        "",
        f"- 学科 Profile：{book.get('profile', '')}",
        f"- 方案：{plan_state}",
        f"- 生成时间：{now()}",
        "",
        "## 范围",
        "",
        f"- 全书内容单元：{len(all_units)}",
        f"- 方案承诺单元：{len(committed) if committed else '—'}",
        "",
        "## 进度",
        "",
        f"- 已抽取单元：{len(done_units)}",
        f"- 待抽取单元：{len(pending_units)}",
        f"- 建模完成度：{completion_text}",
        "",
        "## 知识库",
        "",
        f"- 实体：{len(entities)}",
        f"- 关系：{len(relations)}",
        f"- 产物：{len(artifacts)}",
        "",
    ]

    if committed_pending:
        lines += ["## 待深化（已承诺但未完成）", ""]
        for unit_id in committed_pending[:20]:
            unit = next((u for u in all_units if u["unit_id"] == unit_id), None)
            title = unit.get("title", "") if unit else ""
            lines.append(f"- {unit_id} · {title}")
        if len(committed_pending) > 20:
            lines.append(f"- …其余 {len(committed_pending) - 20} 项")
        lines.append("")

    if artifacts:
        lines += ["## 产物", "", "| 范围 | 产物 | 深度 | 节点 | 生成时间 |", "|---|---|---|---|---|"]
        for row in artifacts:
            lines.append(
                f"| {row.get('scope')} | {row.get('product')} | {row.get('depth')} "
                f"| {row.get('nodes')} | {(row.get('created_at') or '')[:16].replace('T', ' ')} |"
            )
        lines.append("")

    lines.append("成本、Token 与时长不做估算，报告中不出现这类数字。")

    out = root / "report.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    emit(
        {
            "ok": True,
            "file": str(out),
            "plan_state": plan_state,
            "committed_units": len(committed),
            "done_units": len(done_units),
            "pending_units": len(pending_units),
            "completion": completion,
            "entities": len(entities),
            "relations": len(relations),
            "artifacts": len(artifacts),
        }
    )


def cmd_render_index(args) -> None:
    from render_index import render

    book = resolve_book(args.book)
    root = book_path(book["slug"])
    structure = structure_of(book)
    artifacts = read_jsonl(root / "artifacts.jsonl")
    plan = load_json(root / "plan.json") or {}
    html = render(book, structure, artifacts, plan)
    out = root / "index.html"
    out.write_text(html, encoding="utf-8")
    emit({"ok": True, "file": str(out), "artifacts": len(artifacts)})


# ---------------------------------------------------------------- entrypoint


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="whh.py", description="whh textbook skill state layer")
    sub = p.add_subparsers(dest="cmd", required=True)

    def book_arg(sp):
        sp.add_argument("--book", help="book slug (defaults to the only book in ./books)")

    sp = sub.add_parser("init", help="ingest a textbook and detect its structure")
    sp.add_argument("source")
    sp.add_argument("--title")
    sp.add_argument("--slug")
    sp.add_argument("--profile", default="mathematics")
    sp.add_argument("--subject", default="")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("status", help="show book state")
    book_arg(sp)
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("guide", help="list the choices available right now")
    book_arg(sp)
    sp.set_defaults(func=cmd_guide)

    sp = sub.add_parser("chapters", help="list chapters for a selector")
    book_arg(sp)
    sp.set_defaults(func=cmd_chapters)

    sp = sub.add_parser("units", help="list content units")
    book_arg(sp)
    sp.add_argument("--chapter")
    sp.set_defaults(func=cmd_units)

    sp = sub.add_parser("unit-text", help="print one unit's full text")
    book_arg(sp)
    sp.add_argument("--id", required=True)
    sp.set_defaults(func=cmd_unit_text)

    sp = sub.add_parser("plan-create", help="build an extraction plan")
    book_arg(sp)
    sp.add_argument("--depth", default="L2", choices=DEPTHS)
    sp.add_argument("--depth-map", default="", help="per-chapter overrides, e.g. ch03=L3,ch05=L4")
    sp.add_argument("--intent", default=None)
    sp.add_argument("--scope", default="all", help="all, or comma-separated chapter ids")
    sp.set_defaults(func=cmd_plan_create)

    sp = sub.add_parser("plan-confirm", help="mark the plan confirmed")
    book_arg(sp)
    sp.add_argument("--by", default="user")
    sp.set_defaults(func=cmd_plan_confirm)

    sp = sub.add_parser("plan-show", help="print the plan")
    book_arg(sp)
    sp.add_argument("--summary", action="store_true")
    sp.set_defaults(func=cmd_plan_show)

    sp = sub.add_parser("key", help="compute the artifact cache key")
    book_arg(sp)
    sp.add_argument("--scope", required=True)
    sp.add_argument("--product", required=True)
    sp.add_argument("--depth", required=True, choices=DEPTHS)
    sp.set_defaults(func=cmd_key)

    sp = sub.add_parser("view", help="generate a diagram view from the knowledge base")
    book_arg(sp)
    sp.add_argument("--scope", required=True)
    sp.add_argument("--product", required=True)
    sp.add_argument("--depth", required=True, choices=DEPTHS)
    sp.add_argument("--max-nodes", type=int, default=9)
    sp.add_argument("--split", action="store_true", help="overview + per-chapter detail when oversized")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_view)

    sp = sub.add_parser("artifact-put", help="register a generated view")
    book_arg(sp)
    sp.add_argument("--scope", required=True)
    sp.add_argument("--product", required=True)
    sp.add_argument("--depth", required=True, choices=DEPTHS)
    sp.add_argument("--file", required=True)
    sp.add_argument("--nodes", type=int, default=None)
    sp.set_defaults(func=cmd_artifact_put)

    sp = sub.add_parser("artifact-list", help="list registered views")
    book_arg(sp)
    sp.add_argument("--scope")
    sp.set_defaults(func=cmd_artifact_list)

    sp = sub.add_parser("entities-import", help="merge extracted entities/relations")
    book_arg(sp)
    sp.add_argument("--file", required=True)
    sp.add_argument("--kind", default="entities", choices=["entities", "relations"])
    sp.add_argument("--replace", action="store_true")
    sp.add_argument("--allow-orphans", action="store_true", help="keep relations whose endpoints are missing")
    sp.add_argument(
        "--allow-unverified",
        action="store_true",
        help="keep entities whose quote is not found in the source unit (marks them partial)",
    )
    sp.set_defaults(func=cmd_entities_import)

    sp = sub.add_parser("version-bump", help="mark a chapter changed after incremental extraction")
    book_arg(sp)
    sp.add_argument("--chapter", required=True)
    sp.set_defaults(func=cmd_version_bump)

    sp = sub.add_parser("work-init", help="register a piece of music from a metadata file")
    sp.add_argument("--meta", required=True, help="JSON with title, composer, sections[]")
    sp.add_argument("--slug")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_work_init)

    sp = sub.add_parser("source-add", help="record a web source for a work")
    book_arg(sp)
    sp.add_argument("--url", required=True)
    sp.add_argument("--title", default="")
    sp.add_argument("--publisher", default="")
    sp.add_argument("--excerpt", default="")
    sp.add_argument("--accessed", default="")
    sp.add_argument(
        "--kind",
        default="reference",
        choices=["reference", "score", "academic", "liner-notes", "encyclopedia"],
    )
    sp.set_defaults(func=cmd_source_add)

    sp = sub.add_parser("source-list", help="list recorded sources")
    book_arg(sp)
    sp.set_defaults(func=cmd_source_list)

    sp = sub.add_parser("pending", help="units still waiting to be extracted")
    book_arg(sp)
    sp.add_argument("--limit", type=int, default=10)
    sp.set_defaults(func=cmd_pending)

    sp = sub.add_parser("check", help="report consistency problems in the knowledge base")
    book_arg(sp)
    sp.add_argument("--limit", type=int, default=40)
    sp.set_defaults(func=cmd_check)

    sp = sub.add_parser("deepen", help="plan or apply an incremental deepening pass")
    book_arg(sp)
    sp.add_argument("--scope", default="all")
    sp.add_argument("--depth", choices=DEPTHS, help="required unless resuming an active task")
    sp.add_argument("--apply", action="store_true")
    sp.add_argument("--limit", type=int, default=10)
    sp.set_defaults(func=cmd_deepen)

    sp = sub.add_parser("search", help="find entities and their neighbours")
    book_arg(sp)
    sp.add_argument("--query", required=True)
    sp.add_argument("--chapter")
    sp.add_argument("--limit", type=int, default=8)
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("report", help="write the modelling report")
    book_arg(sp)
    sp.set_defaults(func=cmd_report)

    sp = sub.add_parser("render-index", help="rebuild index.html")
    book_arg(sp)
    sp.set_defaults(func=cmd_render_index)

    return p


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
