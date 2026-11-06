#!/usr/bin/env python3
"""Unit tests for the pure parts of the whh state layer.

Run: python test_units.py
End-to-end behaviour lives in selftest.py; this file only covers functions that
should never depend on the filesystem.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import render_diagram as rd  # noqa: E402
import whh  # noqa: E402


class TestSquash(unittest.TestCase):
    def test_strips_punctuation_and_space(self):
        self.assertEqual(whh._squash("用孤立的、静止的 观点"), "用孤立的静止的观点")

    def test_strips_quotes(self):
        self.assertEqual(whh._squash("“对立统一”"), "对立统一")

    def test_empty(self):
        self.assertEqual(whh._squash(""), "")


class TestRanks(unittest.TestCase):
    def test_chain(self):
        ranks = whh._ranks({"a", "b", "c"}, [
            {"source": "a", "target": "b"},
            {"source": "b", "target": "c"},
        ])
        self.assertEqual(ranks, {"a": 0, "b": 1, "c": 2})

    def test_diamond_takes_longest_path(self):
        ranks = whh._ranks({"a", "b", "c", "d"}, [
            {"source": "a", "target": "b"},
            {"source": "a", "target": "c"},
            {"source": "b", "target": "d"},
            {"source": "c", "target": "d"},
        ])
        self.assertEqual(ranks["d"], 2)

    def test_cycle_does_not_hang(self):
        ranks = whh._ranks({"a", "b"}, [
            {"source": "a", "target": "b"},
            {"source": "b", "target": "a"},
        ])
        self.assertEqual(set(ranks), {"a", "b"})

    def test_isolated_node(self):
        self.assertEqual(whh._ranks({"solo"}, []), {"solo": 0})

    def test_self_loop_ignored(self):
        ranks = whh._ranks({"a"}, [{"source": "a", "target": "a"}])
        self.assertEqual(ranks, {"a": 0})


class TestCacheKey(unittest.TestCase):
    book = {"slug": "demo", "schema_version": "0.1.0", "chapters": {"ch01": {"version": 1}}}

    def test_stable(self):
        a = whh.cache_key(self.book, "all", "知识地图", "L2")
        b = whh.cache_key(self.book, "all", "知识地图", "L2")
        self.assertEqual(a, b)
        self.assertEqual(len(a), 12)

    def test_depth_changes_key(self):
        self.assertNotEqual(
            whh.cache_key(self.book, "all", "知识地图", "L2"),
            whh.cache_key(self.book, "all", "知识地图", "L3"),
        )

    def test_chapter_version_changes_key(self):
        bumped = {"slug": "demo", "schema_version": "0.1.0", "chapters": {"ch01": {"version": 2}}}
        self.assertNotEqual(
            whh.cache_key(self.book, "ch01", "知识地图", "L2"),
            whh.cache_key(bumped, "ch01", "知识地图", "L2"),
        )

    def test_other_chapter_unaffected_by_bump(self):
        bumped = {
            "slug": "demo",
            "schema_version": "0.1.0",
            "chapters": {"ch01": {"version": 1}, "ch02": {"version": 5}},
        }
        self.assertEqual(
            whh.cache_key(self.book, "ch01", "知识地图", "L2"),
            whh.cache_key(bumped, "ch01", "知识地图", "L2"),
        )


class TestOrderKey(unittest.TestCase):
    def test_prefers_order(self):
        self.assertEqual(whh._order_key({"attributes": {"order": 3, "year": 1990}}), "3")

    def test_falls_back_to_year(self):
        self.assertEqual(whh._order_key({"attributes": {"year": "1905"}}), "1905")

    def test_missing(self):
        self.assertEqual(whh._order_key({}), "")


class TestViewSpec(unittest.TestCase):
    structure = {
        "chapters": [
            {"chapter_id": "ch01", "index": 1, "title": "第一章", "units": []},
            {"chapter_id": "ch02", "index": 2, "title": "第二章", "units": []},
        ]
    }
    book = {"slug": "demo", "title": "演示", "schema_version": "0.1.0", "chapters": {}}

    def _entities(self, n=6):
        return [
            {
                "entity_id": f"e{i}",
                "entity_type": "Concept",
                "name": f"概念{i}",
                "chapter_id": "ch01",
                "extraction_depth": "L2",
            }
            for i in range(n)
        ]

    def test_truncates_to_max_nodes(self):
        spec = whh.build_view_spec(
            self.book, self.structure, self._entities(12), [], "all", "知识地图", "L2", 9
        )
        self.assertEqual(len(spec["nodes"]), 9)
        self.assertEqual(spec["truncated"], {"shown": 9, "total": 12})

    def test_edges_only_between_kept_nodes(self):
        entities = self._entities(3)
        relations = [
            {"relation_id": "r1", "source_entity_id": "e0", "target_entity_id": "e1"},
            {"relation_id": "r2", "source_entity_id": "e1", "target_entity_id": "e9"},
        ]
        spec = whh.build_view_spec(self.book, self.structure, entities, relations, "all", "知识地图", "L2", 9)
        self.assertEqual(len(spec["edges"]), 1)

    def test_focal_capped_at_two(self):
        entities = self._entities(5)
        relations = [
            {"relation_id": f"r{i}", "source_entity_id": "e0", "target_entity_id": f"e{i}"}
            for i in range(1, 5)
        ]
        spec = whh.build_view_spec(self.book, self.structure, entities, relations, "all", "知识地图", "L2", 9)
        self.assertLessEqual(sum(1 for n in spec["nodes"] if n["focal"]), 2)

    def test_scope_filters_chapter(self):
        entities = self._entities(2) + [
            {"entity_id": "x1", "entity_type": "Concept", "name": "另一个", "chapter_id": "ch02",
             "extraction_depth": "L2"}
        ]
        spec = whh.build_view_spec(self.book, self.structure, entities, [], "ch02", "知识地图", "L2", 9)
        self.assertEqual([n["id"] for n in spec["nodes"]], ["x1"])

    def test_layout_follows_product(self):
        spec = whh.build_view_spec(self.book, self.structure, self._entities(2), [], "all", "时间线", "L2", 9)
        self.assertEqual(spec["layout"], "timeline")


class TestRenderHelpers(unittest.TestCase):
    def test_clip_counts_cjk_as_two(self):
        self.assertEqual(rd._clip("一二三四五六", 4), "一二…")

    def test_clip_keeps_short(self):
        self.assertEqual(rd._clip("短", 9), "短")

    def test_elbow_is_orthogonal(self):
        path = rd._elbow(0, 0, 200, 100, False, 0)
        self.assertTrue(path.startswith("M "))
        self.assertNotIn("L 200 0", path)

    def test_timeline_orders_by_year(self):
        spec = {
            "layout": "timeline",
            "nodes": [
                {"id": "b", "label": "后", "rank": 0, "order": "1925", "type": "Period", "depth": "L2"},
                {"id": "a", "label": "前", "rank": 0, "order": "1919", "type": "Period", "depth": "L2"},
            ],
        }
        placed, _, _, _ = rd._place_timeline(spec)
        self.assertEqual([n["id"] for n in placed], ["a", "b"])

    def test_nested_groups_children(self):
        spec = {
            "layout": "nested",
            "nodes": [
                {"id": "p", "label": "父", "type": "Concept", "depth": "L2", "rank": 0},
                {"id": "c", "label": "子", "type": "Concept", "depth": "L2", "rank": 0},
            ],
            "edges": [{"source": "p", "target": "c", "type": "contains"}],
        }
        placed, _, _, bands = rd._place_nested(spec)
        # 容器本身不是节点框，它由 band 标题承载；只有子节点排进框里。
        self.assertTrue(any(b["label"] == "父" and b["count"] == 1 for b in bands))
        self.assertEqual({n["id"] for n in placed}, {"c"})

    def test_nested_without_containment_falls_back_to_column(self):
        spec = {
            "layout": "nested",
            "nodes": [
                {"id": "a", "label": "甲", "type": "Concept", "depth": "L2", "rank": 0},
                {"id": "b", "label": "乙", "type": "Concept", "depth": "L2", "rank": 0},
            ],
            "edges": [{"source": "a", "target": "b", "type": "prerequisite_of"}],
        }
        placed, _, _, bands = rd._place_nested(spec)
        self.assertEqual({n["id"] for n in placed}, {"a", "b"})
        self.assertFalse(any(b["label"] for b in bands))


if __name__ == "__main__":
    unittest.main(verbosity=2)
