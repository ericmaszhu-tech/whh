# whh

把一本教科书拆成结构化知识库，再从库里生成学科视图的 Agent Skill。

不是"把书变成摘要"，而是把书变成**可查询、可展开、可增量深化**的知识系统：
先扫描出结构，让人确认范围与深度，再按内容单元抽取实体和关系，最后按学科画出知识图。

## 安装

克隆到 Agent 的 skills 目录：

```bash
git clone https://github.com/ericmaszhu-tech/whh.git ~/.dsh/skills/whh
```

Windows：

```powershell
git clone https://github.com/ericmaszhu-tech/whh.git "$env:USERPROFILE\.dsh\skills\whh"
```

装完验证：

```bash
python scripts/selftest.py
```

87 项全过就是装好了。它会自建临时目录跑完整链路，不碰你的数据。

## 依赖

只有 **Python 3.8+**，无第三方包。

`.docx` 用标准库解析（zip + XML）。装了 python-docx 会自动用，没装也不影响。

不支持 PDF、EPUB、扫描件、乐谱、音频。

## 用法

两条入口：

```
whh 拆解 <教材文件>          # 一次性建库
whh <范围> <产物>            # 在已有库上出视图，如：whh 章节 知识地图
```

`whh 拆解` 会先扫描结构、给出抽取方案，**确认之后才抽取**。跳过确认直接跑全书是最容易踩的坑。

## 九个产物

知识地图、定理体系、时间线、因果链、实验分析、架构图、学习路径、结构图、详解、练习、专业拆解、听赏指南。

不同学科只显示适用的那些。

## 七类学科

数学、自然科学、人文社科、计算机与工程、语言学习、音乐学习、音乐鉴赏。

每类有独立的实体表、关系类型、深度定义和视图映射，见 `references/profiles/`。

## 目录

```
SKILL.md              调度器：入口、铁律、命令表、工作流
references/           抽取契约、数据模型、交互规则、七个 Profile
scripts/whh.py        状态层 CLI（24 个命令）
scripts/ingest.py     DOCX/TXT/MD 解析与结构识别
scripts/render_diagram.py  视图渲染（分层 / 时间线 / 嵌套）
scripts/render_index.py    index.html 产物目录
scripts/selftest.py   87 项端到端自检
scripts/test_units.py 26 项单元测试
```

## 数据在哪

运行时的 `books/` 和 `works/` 建在**你当时的工作目录**下，不在 skill 目录里。升级 skill 不会影响已拆的书。

## 设计约束

- 确定性逻辑（缓存键、幂等、去重、状态）在脚本里，不靠提示词自觉。
- 学科规则在 `references/profiles/`，按需加载，不塞主提示词。
- 不估算 Token、费用、时长——这类数字估不准也校验不了。
- 引文必须能在原文里命中，命中不了整条拒收。

## 许可

MIT
