#!/usr/bin/env python3
"""End-to-end smoke test for the whh skill state layer."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
WHH = SKILL / "scripts" / "whh.py"

failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


def run(args: list[str], cwd: Path) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, str(WHH), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {"raw_stdout": proc.stdout, "raw_stderr": proc.stderr}
    return proc.returncode, payload


FIXTURE_BLOCKS: list[tuple[int, str]] = [
    (1, "高等数学（上册）"),
    (1, "第一章 函数与极限"),
    (2, "1.1 函数的概念"),
    (0, "定义 1.1 设 A、B 是两个非空集合，如果存在一个对应法则 f，使得对 A 中每个元素 x，"),
    (0, "按照法则 f，在 B 中都有唯一确定的元素 y 与之对应，则称 f 为从 A 到 B 的函数。"),
    (0, "函数的性质包括有界性、单调性、奇偶性和周期性。这些性质在后续章节中反复使用。"),
    (2, "1.2 极限的定义"),
    (0, "定理 1.1（夹逼准则）若在某去心邻域内 g(x) ≤ f(x) ≤ h(x)，且 lim g(x) = lim h(x) = A，"),
    (0, "则 lim f(x) = A。该定理的适用前提是三者在同一去心邻域内有定义。"),
    (0, "证明 由极限定义，对任意 ε > 0 存在 δ，使得当 0 < |x - x0| < δ 时两个不等式同时成立。"),
    (2, "1.3 例题"),
    (0, "例 1.1 求 lim (sin x)/x 当 x 趋于 0 时的值。解：由夹逼准则可得结果为 1。"),
    (0, "练习 1.1 求 lim (tan x)/x 当 x 趋于 0 时的值。"),
    (1, "第二章 导数与微分"),
    (2, "2.1 导数的定义"),
    (0, "定义 2.1 设函数 y = f(x) 在点 x0 的某邻域内有定义，若极限 lim [f(x0+Δx) - f(x0)]/Δx 存在，"),
    (0, "则称该极限为 f 在 x0 处的导数，记作 f'(x0)。导数的几何意义是切线斜率。"),
    (2, "2.2 求导法则"),
    (0, "定理 2.1 若 u(x) 与 v(x) 在 x 处可导，则 (uv)' = u'v + uv'。该法则可推广到有限个因式。"),
    (0, "推导 由导数定义展开增量比，再拆分极限，即可得到乘积法则。"),
    (2, "2.3 例题与练习"),
    (0, "例 2.1 求 y = x sin x 的导数。解：由乘积法则得 y' = sin x + x cos x。"),
    (0, "练习 2.1 求 y = x^2 ln x 的导数。"),
]


def _write_docx_stdlib(path: Path) -> None:
    """Write a minimal but valid .docx without python-docx."""
    import zipfile
    from xml.sax.saxutils import escape

    parts = []
    for level, text in FIXTURE_BLOCKS:
        style = {1: "Heading1", 2: "Heading2"}.get(level)
        ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
        parts.append(f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>')

    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{''.join(parts)}</w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/></Relationships>'
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document)


def build_fixture(path: Path) -> None:
    try:
        from docx import Document
    except ImportError:
        _write_docx_stdlib(path)
        return

    doc = Document()
    for level, text in FIXTURE_BLOCKS:
        if level:
            doc.add_heading(text, level=level)
        else:
            doc.add_paragraph(text)
    doc.save(str(path))


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="whh-smoke-"))
    print(f"workspace: {tmp}")
    try:
        fixture = tmp / "高等数学.pdf.docx"
        build_fixture(fixture)

        code, g0 = run(["guide"], tmp)
        check("guide works on empty workspace", code == 0 and g0.get("mode") == "start", str(g0))
        opts = (g0.get("steps") or [{}])[0].get("options", [])
        check("guide lists candidate file", any(fixture.name == o.get("value") for o in opts), str(opts))

        code, init = run(["init", str(fixture), "--title", "高等数学（上册）", "--profile", "mathematics"], tmp)
        check("init exits 0", code == 0, str(init))
        check("init created book", init.get("ok") is True, str(init))
        summary = init.get("summary", {})
        check("chapters detected == 2", summary.get("chapters") == 2, str(summary))
        check("units detected >= 6", summary.get("units", 0) >= 6, str(summary))
        book_dir = tmp / "books" / init.get("book", "")
        unit_files = sorted((book_dir / "units").glob("*.txt")) if (book_dir / "units").exists() else []
        check("unit texts persisted", len(unit_files) >= 6, f"{len(unit_files)} files")
        structure_raw = json.loads((book_dir / "structure.json").read_text(encoding="utf-8"))
        check(
            "structure index has no inline text",
            all("text" not in u for ch in structure_raw["chapters"] for u in ch["units"]),
            "inline text leaked into structure.json",
        )
        check(
            "content types vary",
            len(summary.get("content_types", {})) >= 3,
            str(summary.get("content_types")),
        )

        book = init.get("book")
        code, g1 = run(["guide"], tmp)
        check("guide offers scope+depth before plan", [s["id"] for s in g1.get("steps", [])] == ["scope", "depth"], str(g1))
        check(
            "guide scope options include chapters",
            len((g1.get("steps") or [{}])[0].get("options", [])) == 3,
            str(g1),
        )

        code, status = run(["status"], tmp)
        check("status ok", code == 0 and status.get("plan", {}).get("exists") is False, str(status))

        code, chapters = run(["chapters"], tmp)
        check("chapters list", code == 0 and len(chapters.get("chapters", [])) == 2, str(chapters))
        check(
            "chapter carries types",
            bool(chapters["chapters"][0].get("content_types")),
            str(chapters["chapters"][0]),
        )

        code, plan = run(["plan-create", "--depth", "L2"], tmp)
        check("plan created", code == 0 and plan.get("ok"), str(plan))
        check("plan has no cost fields", "estimated_tokens" not in plan.get("summary", {}), str(plan))

        code, g2 = run(["guide"], tmp)
        check("guide asks to confirm plan", [s["id"] for s in g2.get("steps", [])] == ["confirm"], str(g2))

        code, keyinfo = run(["key", "--scope", "ch02", "--product", "知识地图", "--depth", "L2"], tmp)
        check("key computed", code == 0 and len(keyinfo.get("key", "")) == 12, str(keyinfo))
        check("key is a miss", keyinfo.get("hit") is False, str(keyinfo))
        first_key = keyinfo["key"]

        code, keyinfo2 = run(["key", "--scope", "ch02", "--product", "知识地图", "--depth", "L2"], tmp)
        check("key stable", keyinfo2.get("key") == first_key, f"{first_key} vs {keyinfo2.get('key')}")

        code, key_l3 = run(["key", "--scope", "ch02", "--product", "知识地图", "--depth", "L3"], tmp)
        check("depth changes key", key_l3.get("key") != first_key, str(key_l3))

        # extraction must not run before confirmation
        code, _ = run(["plan-show", "--summary"], tmp)
        code, confirm = run(["plan-confirm"], tmp)
        check("plan confirm", code == 0 and confirm.get("confirmed") is True, str(confirm))

        code, g3 = run(["guide"], tmp)
        check("guide moves to extract after confirm", [s["id"] for s in g3.get("steps", [])] == ["extract"], str(g3))

        view = tmp / "view.html"
        view.write_text("<html><body>dummy</body></html>", encoding="utf-8")

        code, put1 = run(
            ["artifact-put", "--scope", "ch02", "--product", "知识地图", "--depth", "L2", "--file", str(view), "--nodes", "7"],
            tmp,
        )
        check("artifact registered", code == 0 and put1.get("total") == 1, str(put1))
        check("first put is new", put1.get("replaced") is False, str(put1))

        code, put2 = run(
            ["artifact-put", "--scope", "ch02", "--product", "知识地图", "--depth", "L2", "--file", str(view), "--nodes", "7"],
            tmp,
        )
        check("second put replaces", put2.get("replaced") is True, str(put2))
        check("artifact count stays 1", put2.get("total") == 1, str(put2))

        code, hit = run(["key", "--scope", "ch02", "--product", "知识地图", "--depth", "L2"], tmp)
        check("cache hit after put", hit.get("hit") is True, str(hit))

        code, bump = run(["version-bump", "--chapter", "ch02"], tmp)
        check("bump invalidates ch02", code == 0 and first_key in bump.get("stale", []), str(bump))

        code, after = run(["key", "--scope", "ch02", "--product", "知识地图", "--depth", "L2"], tmp)
        check("bumped key misses", after.get("hit") is False and after.get("key") != first_key, str(after))

        code, other = run(["key", "--scope", "ch01", "--product", "知识地图", "--depth", "L2"], tmp)
        check("other chapter unaffected", other.get("scope_version") == 1, str(other))

        code, idx = run(["render-index"], tmp)
        check("index rendered", code == 0 and Path(idx.get("file", "")).exists(), str(idx))
        html = Path(idx["file"]).read_text(encoding="utf-8")
        check("index has one artifact row", html.count("打开") == 1, f"rows={html.count('打开')}")
        check("index lists chapters", "第一章" in html and "第二章" in html, "chapter titles missing")
        check("index shows depth pill", 'class="pill l2">L2' in html, "depth pill missing")

        # entity import idempotency
        ents = tmp / "ents.jsonl"
        ents.write_text(
            '{"entity_id":"math:theorem:jiaxbi","entity_type":"Theorem","name":"夹逼准则","extraction_depth":"L2"}\n'
            '{"entity_id":"math:definition:function","entity_type":"Definition","name":"函数","extraction_depth":"L2"}\n',
            encoding="utf-8",
        )
        code, imp1 = run(["entities-import", "--file", str(ents)], tmp)
        check("entities imported", code == 0 and imp1.get("added") == 2, str(imp1))
        code, imp2 = run(["entities-import", "--file", str(ents)], tmp)
        check("entities idempotent", imp2.get("added") == 0 and imp2.get("updated") == 2, str(imp2))

        code, st = run(["status"], tmp)
        check("status reflects entities", st.get("entities") == 2, str(st))
        check("status reflects artifacts", st.get("artifacts") == 1, str(st))

        fake = tmp / "fake.jsonl"
        fake.write_text(
            json.dumps(
                {
                    "entity_id": "math:concept:fake",
                    "entity_type": "Concept",
                    "name": "伪造概念",
                    "chapter_id": "ch01",
                    "content_unit_id": "ch01.u01",
                    "source_reference": {"quote": "这句话原文里根本没有"},
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        code, fq = run(["entities-import", "--file", str(fake)], tmp)
        check("fabricated quote rejected", fq.get("rejected_unverified") == 1, str(fq))
        code, fq2 = run(["entities-import", "--file", str(fake), "--allow-unverified"], tmp)
        check("allow-unverified marks partial", fq2.get("total") == 3, str(fq2))

        dup = tmp / "dup.jsonl"
        dup.write_text(
            json.dumps(
                {
                    "entity_id": "math:concept:function-alt",
                    "entity_type": "Concept",
                    "name": "函数",
                    "chapter_id": "ch01",
                    "content_unit_id": "ch01.u01",
                    "source_reference": {"quote": "函数"},
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        run(["entities-import", "--file", str(dup)], tmp)
        code, ck = run(["check"], tmp)
        check(
            "check flags duplicate names",
            any(i["type"] == "duplicate_name" for i in ck.get("issues", [])),
            str(ck)[:400],
        )
        check("check reports uncovered units", "unit_without_entities" in ck.get("by_type", {}), str(ck.get("by_type")))

        code, sr = run(["search", "--query", "函数"], tmp)
        check("search finds entity", code == 0 and any(m["name"] == "函数" for m in sr.get("matches", [])), str(sr)[:300])
        check("search returns neighbours", isinstance(sr.get("neighbours"), list), str(sr)[:200])

        code, rp = run(["report"], tmp)
        check("report written", code == 0 and Path(rp.get("file", "")).exists(), str(rp))
        report_text = Path(rp["file"]).read_text(encoding="utf-8")
        check("report states completion basis", "完成度" in report_text, "no completion line")

        code, v1 = run(["view", "--scope", "all", "--product", "知识地图", "--depth", "L2"], tmp)
        check("view generated", code == 0 and v1.get("nodes", 0) >= 2, str(v1))
        view_file = tmp / "books" / book / "views" / Path(v1.get("file", "x")).name
        check("view file written", view_file.exists(), str(view_file))
        check("view html has svg", "<svg" in view_file.read_text(encoding="utf-8"), "no svg")
        code, v2 = run(["view", "--scope", "all", "--product", "知识地图", "--depth", "L2"], tmp)
        check("view reuses cache", v2.get("reused") is True, str(v2))

        code, vs = run(
            ["view", "--scope", "all", "--product", "知识地图", "--depth", "L2", "--max-nodes", "2", "--split", "--force"],
            tmp,
        )
        check("split view returns several views", code == 0 and len(vs.get("views", [])) >= 2, str(vs))

        code, tv = run(["view", "--scope", "all", "--product", "时间线", "--depth", "L2"], tmp)
        check("timeline view rendered", code == 0 and tv.get("nodes", 0) >= 1, str(tv))
        tfile = tmp / "books" / book / "views" / Path(tv.get("file", "x")).name
        check("timeline has axis", "stroke-dasharray" in tfile.read_text(encoding="utf-8"), "no axis")

        code, g4 = run(["guide"], tmp)
        check(
            "guide offers scope/product/depth once modelled",
            [s["id"] for s in g4.get("steps", [])] == ["scope", "product", "depth"],
            str(g4),
        )
        prod_opts = (g4.get("steps") or [{}, {}])[1].get("options", [])
        check("guide products filtered by profile", len(prod_opts) == 5, str([p.get("label") for p in prod_opts]))
        depth_opts = (g4.get("steps") or [{}, {}, {}])[2].get("options", [])
        check(
            "guide marks existing depth as reusable",
            any(d["value"] == "L2" and "已有" in d["detail"] for d in depth_opts),
            str(depth_opts),
        )

        # ---- 作品鉴赏模式（works/） ----
        work_slug = "debussy-clair"
        meta = tmp / "meta.json"
        meta.write_text(
            json.dumps(
                {
                    "title": "月光",
                    "composer": "德彪西",
                    "genre": "钢琴小品",
                    "sections": [
                        {"title": "开头主题", "start": "0:00", "end": "0:48"},
                        {"title": "中段发展", "start": "0:48", "end": "3:10"},
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        code, work = run(["work-init", "--meta", str(meta), "--slug", work_slug], tmp)
        check("work-init ok", code == 0 and work.get("sections") == 2, str(work))
        check(
            "work stored under works/",
            (tmp / "works" / work_slug / "work.json").exists(),
            "work.json missing",
        )

        code, wst = run(["status", "--book", work_slug], tmp)
        check("work kind is work", wst.get("kind") == "work", str(wst))
        check("work composer recorded", wst.get("composer") == "德彪西", str(wst))

        code, gw = run(["guide", "--book", work_slug], tmp)
        check("work guide asks for more sources", gw.get("steps", [{}])[0].get("id") == "sources", str(gw))

        code, s1 = run(
            ["source-add", "--book", work_slug, "--url", "https://example.org/a", "--title", "A", "--kind", "academic"],
            tmp,
        )
        check("source added", code == 0 and s1.get("sources") == 1, str(s1))
        code, s2 = run(["source-add", "--book", work_slug, "--url", "https://example.org/a", "--title", "A2"], tmp)
        check("source deduped by url", s2.get("sources") == 1 and s2.get("replaced") is True, str(s2))

        code, s3 = run(["source-add", "--book", work_slug, "--url", "https://example.org/b", "--title", "B"], tmp)
        check("second distinct source kept", s3.get("sources") == 2, str(s3))

        code, s4 = run(["source-add", "--book", work_slug, "--url", "https://example.org/c", "--title", "C"], tmp)
        check("third source recorded", s4.get("sources") == 3, str(s4))

        code, gw2 = run(["guide", "--book", work_slug], tmp)
        ids2 = [s["id"] for s in gw2.get("steps", [])]
        check("work guide moves to analysis", "analysis" in ids2, str(gw2))

        code, wk = run(["key", "--book", work_slug, "--scope", "all", "--product", "专业拆解", "--depth", "L3"], tmp)
        check("work key ok", code == 0 and wk.get("figure") == "无图", str(wk))

        analysis = tmp / "analysis.md"
        analysis.write_text("# 分析", encoding="utf-8")
        code, wp = run(
            ["artifact-put", "--book", work_slug, "--scope", "all", "--product", "专业拆解", "--depth", "L3", "--file", str(analysis)],
            tmp,
        )
        check("work artifact registered", code == 0 and wp.get("total") == 1, str(wp))
        check("artifact keeps md suffix", wp.get("file", "").endswith(".md"), str(wp))

        code, wi = run(["render-index", "--book", work_slug], tmp)
        check("work index rendered", code == 0 and Path(wi.get("file", "")).exists(), str(wi))
        whtml = Path(wi["file"]).read_text(encoding="utf-8")
        check("work index lists sections", "开头主题" in whtml and "中段发展" in whtml, "sections missing")
        check("work index lists product", "专业拆解" in whtml, "product missing")

        # ---- 范围裁剪与逐章深度 ----
        code, chs = run(["chapters", "--book", book], tmp)
        ch02_units = next(c["units"] for c in chs["chapters"] if c["chapter_id"] == "ch02")

        code, sp1 = run(["plan-create", "--book", book, "--scope", "ch02"], tmp)
        check(
            "scoped plan counts only ch02",
            sp1.get("summary", {}).get("selected_units") == ch02_units,
            f"{sp1} vs ch02={ch02_units}",
        )
        code, ps = run(["plan-show", "--book", book], tmp)
        rows = ps.get("plan", {}).get("selections", [])
        check("scoped plan excludes other chapters", all(r["chapter_id"] == "ch02" for r in rows), str(rows[:2]))

        code, sp2 = run(["plan-create", "--book", book, "--depth-map", "ch02=L3"], tmp)
        check("depth map recorded", sp2.get("selectors", {}).get("depth_map", {}).get("ch02") == "L3", str(sp2))
        code, ps2 = run(["plan-show", "--book", book], tmp)
        rows2 = ps2.get("plan", {}).get("selections", [])
        check("ch02 planned at L3", all(r["depth"] == "L3" for r in rows2 if r["chapter_id"] == "ch02"), "depth not applied")
        check("ch01 stays at default", all(r["depth"] == "L2" for r in rows2 if r["chapter_id"] == "ch01"), "default depth changed")

        code, bad = run(["plan-create", "--book", book, "--scope", "ch99"], tmp)
        check("unknown scope rejected", code != 0 and bad.get("ok") is False, str(bad))

        # ---- 关系引用完整性 ----
        rels = tmp / "rels.jsonl"
        rels.write_text(
            json.dumps(
                {
                    "relation_id": "r1",
                    "source_entity_id": "math:theorem:jiaxbi",
                    "relation_type": "implies",
                    "target_entity_id": "math:missing-entity",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        code, ro = run(["entities-import", "--book", book, "--file", str(rels), "--kind", "relations"], tmp)
        check("orphan relation rejected", ro.get("rejected") == 1 and ro.get("total") == 0, str(ro))
        code, ro2 = run(
            ["entities-import", "--book", book, "--file", str(rels), "--kind", "relations", "--allow-orphans"],
            tmp,
        )
        check("allow-orphans keeps it", ro2.get("total") == 1, str(ro2))

        # ---- 增量深化 ----
        code, dp = run(["deepen", "--book", book, "--scope", "ch01", "--depth", "L4"], tmp)
        check("deepen plans worklist", code == 0 and dp.get("pending_units", 0) > 0, str(dp))
        code, st2 = run(["status", "--book", book], tmp)
        check("status shows active deepening", st2.get("deepening", {}).get("active") is True, str(st2))
        code, da = run(["deepen", "--book", book, "--apply"], tmp)
        check("deepen apply bumps chapter", code == 0 and da.get("applied") is True, str(da))
        check("deepen apply marks stale", len(da.get("stale", [])) >= 1, str(da))
        check("deepen warns when nothing improved", bool(da.get("warning")), str(da))
        code, st3 = run(["status", "--book", book], tmp)
        check("deepening cleared after apply", st3.get("deepening", {}).get("active") is False, str(st3))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if failures:
        print(f"FAILED: {len(failures)} -> {failures}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
