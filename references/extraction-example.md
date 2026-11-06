# 抽取示例（人文社科）

一个真实的输入→输出对照。照着这个形状抽，不要自由发挥。

## 输入

`whh.py unit-text --id ch01.u02`

```
title: 一 两种宇宙观
content_type: 论证
chars: 983
text: 在人类的认识史中，从来就有关于宇宙发展法则的两种见解，一种是形而上学的见解，
一种是辩证法的见解，形成了互相对立的两种宇宙观。……所谓形而上学的或庸俗进化论的宇宙观，
就是用孤立的、静止的和片面的观点去看世界。……由于外力的推动。……
事物因内部矛盾引起发展……
```

## 输出

```json
{"entity_id":"hist:concept:metaphysics","entity_type":"Concept","name":"形而上学",
 "description":"用孤立的、静止的、片面的观点看世界，认为变化只是数量增减与场所变更，原因在事物外部。",
 "chapter_id":"ch01","content_unit_id":"ch01.u02",
 "source_reference":{"page":null,"para":1,"quote":"用孤立的、静止的和片面的观点去看世界"},
 "confidence":0.95,"provenance_type":"textbook","extraction_depth":"L3",
 "extraction_status":"complete","attributes":{"别名":"玄学","变化观":"只有数量增减"}}

{"entity_id":"hist:cause:internal-contradiction","entity_type":"Cause","name":"内部矛盾",
 "description":"辩证法主张的发展原因：事物因内部矛盾引起发展。",
 "chapter_id":"ch01","content_unit_id":"ch01.u02",
 "source_reference":{"page":null,"para":1,"quote":"事物因内部矛盾引起发展"},
 "confidence":0.92,"provenance_type":"textbook","extraction_depth":"L3",
 "extraction_status":"complete","attributes":{"层次":"内部原因"}}
```

```json
{"relation_id":"r03","source_entity_id":"hist:concept:dialectics","relation_type":"presupposes",
 "target_entity_id":"hist:cause:internal-contradiction",
 "evidence_reference":{"quote":"事物因内部矛盾引起发展"},"confidence":0.9}
```

## 为什么这么填

- **id**：`hist:` + 类型小写 + 名称的拼音或英文短名。同一个概念在第二节和第七节出现，**必须用同一个 id**，不要因为描述不同就换一个。
- **description 一句话**：写它是什么，不是把原文抄一遍。抄原文会让 description 和 quote 重复，失去区分度。
- **quote 取最短可辨识片段**：能定位到原文即可，不必完整句子。用 20–40 字，太长反而容易因为标点差异匹配不上。
- **attributes 放结构化补充**：别名、层次、时期这类可比较的字段。不要往 attributes 里塞整段解释。
- **depth 按本次任务**：L3 才抽条件、链条、分歧；L2 只抽定义和主张。

## 常见错误

| 错误 | 后果 |
|---|---|
| quote 用自己的话概括 | 导入被拒收，标 unverified |
| 同一概念起两个 id | 图里出现两个节点，`check` 报 duplicate_name |
| description 抄原文 | 与 quote 重复，无法区分「教材说了什么」和「实体是什么」 |
| 把整节当 description | 实体膨胀，检索失效 |
| 关系只写 `related_to` | 等于没写，图里全是无信息的连线 |

## 自检

抽完一批先跑：

```
whh.py check
```

`duplicate_name`、`quote_not_found`、`orphan_relation` 都应为 0。`unit_without_entities` 的数量应等于你还没抽的单元数——它是进度条，不是错误。
