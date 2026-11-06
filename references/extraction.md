# 抽取契约

方案确认后，按 `plan.json` 的 selections 逐条抽取。本文规定读什么、写什么、什么算不合格。

## 只看当前单元

```
whh.py unit-text --id ch03.u02
```

或直接读 `books/<slug>/units/ch03.u02.txt`。

只读该单元。不要为了「上下文连贯」把整章塞进来——那会让每个单元重复处理同样的文字，也让结果不可复现。

## 写两个文件

`entities.jsonl` 与 `relations.jsonl`，字段见 `data-model.md`。写完用 `entities-import` 导入，它负责去重与引用校验。

## 实体 id

```
<subject>:<type>:<slug>
```

- subject：`math` / `phys` / `hist` / `cs` / `lang` / `mus` / `musa`
- type：实体类型小写，如 `theorem`、`chord`、`composer`
- slug：名称规范化后生成——去空格、全半角统一、去标点、转小写

同名不同义加 `@<chapter_id>` 后缀，例如 `math:concept:function@ch05`。

跨章同一个东西必须合并成同一个 id，否则知识图会碎。

## 抽多深

selection 的 depth 决定抽到什么程度，不多不少：

| 深度 | 该抽 | 不该抽 |
|---|---|---|
| L1 | 名称、所属章节、一句话定位 | 定义全文、推导 |
| L2 | 名称、定义、结论、主要公式 | 证明步骤、易错点 |
| L3 | 加上条件、证明链条、适用边界、易错点 | 完整多解、逐项映射 |
| L4 | 加上完整推导步骤、多种解法、题目逐项映射 | — |

L4 不是「写得更长」，是多出结构化的步骤条目。

## source_reference

```json
{"page": null, "para": 3, "quote": "原文片段"}
```

`quote` 必须能在单元原文里原样找到（子串匹配，允许省略首尾标点）。找不到的整条丢弃——这是防止模型改写原文的硬闸。

`entities-import` 会自动做这个检查：引文未命中的实体被拒收并列入 `unverified`。确实需要保留时用 `--allow-unverified`，该条会被标成 `partial`，不计入完成度。

## provenance

| 值 | 什么时候用 |
|---|---|
| `textbook` | 教材原文 |
| `author` | 教材作者的解释性文字 |
| `ai-inference` | 模型补的上下文，如「此定理等价于…」 |

V1 抽取阶段不允许出现 `ai-supplement`。补充内容只能来自用户明确要求。

## 不合格判定

以下任一情况，该实体不算完成：

- 没有 `source_reference`
- `quote` 在原文中找不到
- 定义/定理/公式与原文语义不一致
- `confidence` 缺失

不合格的标 `extraction_status: partial`，并让对应 selection 保持未完成。不要把 partial 计入完成度。

## 分批与导入

一个内容单元一次，一章抽完导入一次。

导入后看两件事：

```
whh.py status
```

实体与关系计数是否合理；`entities-import --kind relations` 返回的 `orphans` 必须为空。

`orphans` 不为空说明关系指向了不存在的实体——要么实体漏抽，要么 id 写错了。先查 id，不要用 `--allow-orphans` 掩盖。

## 失败处理

单元读不到或内容为空：标 `pending` 继续下一个，最后汇总告诉用户哪几个单元没抽。

不许静默跳过，也不许用相邻单元的内容顶替。
