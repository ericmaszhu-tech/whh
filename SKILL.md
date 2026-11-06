---
name: whh
description: 把一本教科书拆解成结构化知识库，并生成学科专属视图：教材解析与章节/内容单元识别、抽取方案与深度确认、知识实体与关系抽取、知识地图/定理体系/时间线/因果链/学习路径等视图生成、按章增量深化、产物目录 index.html 维护。当用户要"拆解/分析一本教材""生成知识地图""整理这本书的知识体系"时使用。
license: MIT
metadata:
  version: "0.1.0"
---

# whh

把一本教科书变成可查询、可展开的结构化知识系统。

两条入口：**拆解**（一次性全链路）和**功能**（在已有知识库上出视图）。不存在第三条。

## 铁律

1. **用选择代替输入。** 章节、单元、深度、产物都做成选项让用户点。只有教材文件名和 `whh 提问` 的问句允许自由输入。
2. **深度必须由人选。** 任何视图生成前都要显式选一次 L1–L4，不允许静默套默认值。选项上标「已有 / 需抽取」。
3. **先生成先查重。** 出图之前必须先跑 `key`，命中就直接复用文件并把该条目标为已存在，不重新生成。
4. **index 只更新不追加。** 同一缓存键在 index.html 里永远只有一条记录。
5. **复用要明说。** 命中缓存时回一句「复用已有产物（L2 · 第 3 章）」，不能让用户以为又跑了一遍。
6. **不编造。** 知识库里没有的实体不画、不填、不用 AI 补充冒充教材内容。
7. **联网结论必须带来源。** 作品鉴赏里每条专业判断都要能指到一个 URL，指不到就不写。
8. **每一步都要有选项，而且要是可点的选项。** 入口执行后先跑 `guide`，把返回的 `steps` 用平台的选择控件（如 `ask_user_question`）渲染成选项，**不要**打印成文字清单或 JSON 让用户自己对照。用户全程只需要点，不需要知道「知识地图」「L3」这些词。

## 脚本

确定性状态由脚本管理，不要用自然语言替代它。

脚本位于本文件同目录的 `scripts/whh.py`。**在用户项目根目录下运行它**（不要在脚本目录里跑，否则 `books/` 会建错地方）。所有命令向 stdout 输出 JSON。

| 命令 | 用途 |
|---|---|
| `whh.py init <文件> --profile <p>` | 解析教材，识别章节与内容单元 |
| `whh.py status` | 查看库状态 |
| `whh.py guide` | 列出当前状态下所有可选项（不知道下一步时先跑这个） |
| `whh.py chapters` | 列章节，供选择器使用 |
| `whh.py units --chapter ch03` | 列该章内容单元 |
| `whh.py unit-text --id ch03.u02` | 读一个内容单元的原文 |
| `whh.py plan-create --depth L2` | 生成抽取方案 |
| `whh.py plan-confirm` | 确认方案，锁定承诺范围 |
| `whh.py plan-show --summary` | 查看方案摘要 |
| `whh.py key --scope --product --depth` | 计算缓存键并查重 |
| `whh.py artifact-put --scope --product --depth --file x.html` | 登记已生成的视图 |
| `whh.py view --scope --product --depth [--split]` | 从知识库生成视图并自动登记；命中缓存则复用；`--split` 出章节总览 + 分章明细 |
| `whh.py artifact-list` | 列出已登记产物 |
| `whh.py entities-import --file e.jsonl [--kind relations]` | 合并抽取结果（幂等） |
| `whh.py pending` | 列出还没抽的单元，即抽取工作队列 |
| `whh.py check` | 体检：重名实体、引文缺失、孤儿关系、未覆盖单元 |
| `whh.py search --query 关键词` | 按名称/描述找实体，连带返回相邻实体与关系（提问用这个） |
| `whh.py deepen --scope --depth [--apply]` | 增量深化：先出补抽清单，抽完再 apply 让受影响的产物失效 |
| `whh.py report` | 写建模报告：承诺范围、已完成、完成度、待深化 |
| `whh.py version-bump --chapter ch03` | 增量建模后标记该章失效 |
| `whh.py render-index` | 重建 index.html |
| `whh.py work-init --meta m.json` | 登记一部作品，段落即章节 |
| `whh.py source-add --url --title --excerpt` | 记录联网来源（同 URL 覆盖） |
| `whh.py source-list` | 列出已记录来源 |

支持的书源：`.docx` `.txt` `.md`。PDF/EPUB 需要适配层，缺库时要如实说明，不要假装解析成功。

依赖只有 Python 3（3.8+）。`.docx` 用标准库解析，不需要装 python-docx；装了就用它，没装也不影响。

自检：`python scripts/selftest.py`。覆盖状态机、缓存键、幂等、按章失效与 index 渲染。

## 拆解

1. `init` 解析文件。若只识别出 1 章且单元数极少，说明结构识别失败——回报并请用户提供目录页或改用 DOCX，不要硬拆。
2. `plan-create --depth L2` 生成方案。
3. **呈现方案并等待确认。** 用一屏讲清：多少章、多少单元、默认深度。给选项而不是表单：
   - 按这个方案铺开
   - 只做重点章节（转章节选择）
   - 提高深度（转深度选择）
   - 调整范围
4. `plan-confirm` 后才能抽取。用户没确认就抽取，是最严重的越界。
5. 按 Content Unit 抽取（规则见 `references/extraction.md`），产出实体与关系 JSONL，`entities-import` 写入。导入后 `orphans` 必须为空。
6. `render-index` 产出产物目录页。

不做 Token 估算、费用估算和时长预估，报告里也不出现这类数字。

## 鉴赏

音乐鉴赏的作品模式：不读教材，直接对一首曲子做联网研究。

1. 用户给曲名、作曲家 + 曲名、或一句描述都可以（「婚礼上常放的那首管风琴曲」）。
2. 多个候选 → 列出来让用户选：曲名、作曲家、体裁、时长、辨识特征。未确认不产出。
3. 检索至少三个独立来源，覆盖基本信息、结构、演绎史。专业结论必须有音乐学来源（乐谱、学术、唱片内页），否则报告顶部标「未获乐谱级核实」。
4. 每条来源 `source-add` 落盘，带 URL、访问时间、原文摘录。
5. 先定段落划分，再 `work-init --meta`——段落即章节。
6. 写 `analysis.md`（专业拆解）与 `guide.md`（听赏指南），`artifact-put` 登记，`render-index` 重建目录页。
7. 来源冲突并列标 `disputed`，查不到标 `unknown`，都不用推测填充。

作品模式没有方案确认这一步，但来源必须齐。缺来源的断言不许出现在报告里。

## 批量抽取

一本书有几个单元就要跑几轮，不要试图一次抽完。

1. `pending` 取下一批（默认 10 个）。
2. 逐个 `unit-text` 读原文，按 `references/extraction.md` 和 `extraction-example.md` 抽。
3. 每批 `entities-import` 一次，看 `unverified` 和 `orphans` 是否为空。
4. 全部抽完跑 `check`。`duplicate_name` 必须为 0；不为 0 说明同一个概念起了两个 id，要合并。
5. `render-index` 更新目录页。

`pending` 里的 `progress` 是进度条，不是完成度——完成度要等方案确认后按已承诺范围算。

## 增量深化

已经建好的库要加深，重跑整本是最坏的做法。

1. `deepen --scope ch03 --depth L3` 出清单：这一章里哪些单元还没到 L3，当前深度各是多少。
2. 只补这些单元，`entities-import`。
3. `deepen --apply` 让受影响的产物失效——它只 bump 这些章的版本，别的章继续命中缓存。
4. `view` 重新生成受影响的图。

`--apply` 如果返回「没有检测到新增或加深的实体」，说明抽取还没导入，先别 apply：那会把本来还能用的图无谓地作废。

## 功能

格式是 `whh <范围> <产物>`，但**不要让用户去拼这个格式**。

用户只有两种姿态：说一句话，或者什么都不说。两种都走同一条路：

1. 调 `guide` 拿 `steps`。
2. 把 `steps` 逐个映射成交互式选择题：`id` 题目标识，`label` 题干，option 的 `label` 作选项名、`detail` 作说明。
3. 一次问完所有 step（范围 / 产物 / 深度），用户点三下就够。
4. 按选择调用 `view`，回一句结果。

示例映射：

| guide 的 step | 呈现给用户的 |
|---|---|
| `scope` | 「选范围」：全部 / 第一章 函数与极限 / 第二章 导数与微分 |
| `product` | 「选产物」：知识地图（Tree / Dependency graph）… |
| `depth` | 「选深度」：L1 结构（已有，直接复用）/ L3 深度（需抽取）… |

纪律：

- 不要打印 JSON，也不要打印文字清单。
- 不要让用户报章节号、产物名、深度代号。
- 用户不选直接确认时，执行首项并说明选了什么。
- 只有文件不在当前目录时，才允许要求用户提供路径。
- 范围选多个时逐章生成独立产物，不生成组合产物。

具体执行细节：`key` 查重 → 命中就复用并说明 → 未命中则渲染视图 → `artifact-put` → `render-index`。深度高于已建模深度时先走增量深化，再出图。

## 数据

`books/<slug>/` 下：`book.json` `structure.json` `plan.json` `entities.jsonl` `relations.jsonl` `artifacts.jsonl` `views/` `index.html`。

字段定义见 `references/data-model.md`；学科实体与视图映射见 `references/profiles/`。

## 参考

- `references/data-model.md` — 实体、关系、方案、产物字段
- `references/extraction.md` — 抽取契约：读什么、抽多深、什么算不合格
- `references/extraction-example.md` — 一个真实的输入→输出对照，照着形状抽
- `references/products.md` — 产物类型与图类型映射
- `references/profiles/mathematics.md` — 数学
- `references/profiles/natural-science.md` — 物理、化学、生物、地理
- `references/profiles/humanities.md` — 人文社科（历史、政治、哲学）
- `references/profiles/computer.md` — 计算机与工程
- `references/profiles/language.md` — 语言学习
- `references/profiles/music-learning.md` — 音乐学习（乐理、视唱、和声、器乐）
- `references/profiles/music-appreciation.md` — 音乐鉴赏（音乐史、作品、流派）
- `references/interaction.md` — 选择器、深度选择、index 与缓存规则

七类 Profile 已全部落地。识别到学科后按对应文件抽取；学科跨类时按主学科取 Profile，另一类的实体作为扩展字段记录，不强行套两套结构。
