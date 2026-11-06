# 数据模型

所有文件位于 `books/<slug>/`。除 JSONL 外均为 UTF-8 JSON。

## book.json

| 字段 | 说明 |
|---|---|
| slug | 目录名，唯一 |
| title / source | 书名与源文件路径 |
| profile | 学科 Profile |
| schema_version | 抽取时使用的 schema 版本 |
| chapters | `{chapter_id: {title, version, updated_at}}`，version 用于缓存键 |

`chapters.*.version` 只在**该章内容发生变化**时前进，由 `version-bump` 维护。全书不存在统一版本号——用全书版本会让任何一次增量作废所有视图。

## structure.json

```
chapters[] { chapter_id, index, title, sections[], units[] }
units[]    { unit_id, title, content_type, chars, preview }
```

`content_type` 取值：概念介绍、定义、定理与规律、证明、公式推导、例题、练习题、实验、操作方法、案例、复习总结。

## plan.json

```
plan_id, created_at, book, profile, schema_version, user_intent
confirmed, confirmed_at, confirmed_by
selectors { scope, depth }
summary  { total_units, selected_units }
selections[] {
  chapter_id, chapter_title, content_unit_id, content_type,
  depth, recommended, selected, reason
}
```

`confirmed: false` 时不得抽取。`selectors` 记录用户的选择路径，便于复现。

## entities.jsonl

| 字段 | 说明 |
|---|---|
| entity_id | `math:<type>:<name>`；同名不同义追加 `@<chapter_id>` |
| entity_type | 学科实体类型，见 Profile |
| name / aliases | 正名与别名 |
| description | 教材原义，不扩写 |
| subject / chapter_id / content_unit_id | 归属 |
| source_reference | `{page, para, quote}`，quote 为原文片段 |
| confidence | 0–1 |
| provenance_type | `textbook` / `author` / `ai-inference` / `ai-supplement` |
| extraction_depth | L1–L4 |
| extraction_plan_id | 产生它的方案 |
| extraction_status | `complete` / `partial` / `pending` |
| attributes | 该类型专属字段的键值 |

**id 规则**：名称规范化（去空格、全半角统一、去标点）后哈希到类型下。跨章同名默认合并；规范化后仍撞名且语义不同时才加章节后缀，并在 `aliases` 记下区分依据。

## relations.jsonl

| 字段 | 说明 |
|---|---|
| relation_id | 唯一 |
| source_entity_id / target_entity_id | 两端必须存在 |
| relation_type | 学科关系类型 |
| evidence_reference | 教材出处 |
| confidence | 0–1 |

跨章关系允许，但必须能在某一章的原文里指出依据，否则标 `ai-inference`。

## artifacts.jsonl

| 字段 | 说明 |
|---|---|
| key | 12 位缓存键 |
| scope | `all` / `ch03` / `ch03.u02` |
| product | 产物名 |
| depth | L1–L4 |
| figure | 图类型 |
| file | 相对路径 `views/<key>.html` |
| chapter_id | 所属章，全书级为 null |
| nodes | 节点数 |
| created_at | 生成时间 |
| scope_version | 生成时的范围版本 |

同名 key 只保留一行，`artifact-put` 命中即替换。
