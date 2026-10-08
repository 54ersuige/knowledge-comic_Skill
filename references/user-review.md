# 用户介入 checkpoint 设计（v0.3.26 Mavis 对话流版）

> 核心思想：**用户的认知 / 审美 / 独特性是作品的灵魂，LLM 是工具而非作者。**
> 自动化减少体力劳动，但创作决策不可外包。

---

## 为什么需要 checkpoint

LLM 生成的内容常常"还行但不到位"：
- 标题可能"通顺但缺锋"
- caption 可能"准确但缺金句感"
- visual 可能"画面感弱、信息密度低"
- 跑图可能"构图正确但风格不达预期"
- 章节排序可能"线性叙事但缺节奏"

这些问题在 LLM 一次性输出中**无法消除**，需要人在关键节点介入。

---

## v0.2 重构：Mavis 对话流取代 subprocess checkpoint

v0.2（2026-09-20）**完全去掉** subprocess 的 stdin checkpoint 模式（已确认 Mavis 对话接不到 subprocess stdin，会静默 EOFError）。改为 Mavis 在主对话里：
- 用 `read tool` 读产物（JSON / HTML / PNG）
- 用 `ask_user` 让用户拍板
- 用 `deliver-assets` 展示图

---

## 3 个核心 checkpoint（Mavis 对话流版）

### Checkpoint 1：排版 + 分镜审阅（Step 1.5）—— Mavis 必做 ★

**触发时机**：LLM 生成 storyboard.json 后、**跑图前**。

**唯一产物：`layout_preview_<template>.html`**。用户打开**这一个文件**就能确认两件事：

1. **文字排版效果** —— 标题 / 章节题 / 正文 / 朱砂红高亮 / 印章 / 收束段落的成品版式
2. **每页画面要画什么** —— 占位图正下方直接列出 `主体 / 动作 / 配角 / 背景 / 景别 / 情绪` + 该页关键词

> **为什么是一个文件**：之前把排版预览和分镜脚本拆成两个文件，等于让用户两边对照，反而增加负担。v0.3.6 起分镜内容直接内嵌进 layout_preview，**一个文件完成审阅**。

**Mavis 操作**：
1. 调 `step_plan(...)` 拿到 `(sb, job_id, work_dir)`
2. 调 **`step_layout_preview(job_id)`** 拿到 `html_path`
3. 用 `deliver-assets` 送 html；或用 Browser 打开让用户直接看
4. `ask_user` 让用户拍板

**想同时对比多个模板**：
```python
paths = step_layout_preview(job_id, compare_templates=["c", "e"])
```

**用户操作（ask_user 选项）**：
- ✅ **图文相符，去生图** — 跑 `step_gen_images(job_id)`
- 🎨 **换模板重看** — `step_layout_preview(job_id, template_id="e")`
- 🔧 **改某页文案/分镜** — `step_set_page_field(job_id, page, field, value)`，**改完必须重调 `step_layout_preview(job_id)` 重发预览**再让用户确认
- 🔄 **重跑整组分镜** — 重跑 `step_plan`
- ❌ **拒绝** — 删 work_dir

**用户发现某页图文对不上时** → 调 `step_story_script(job_id)` 拿对齐诊断，直接告诉用户"这页 caption 里的动作『系』画面没画"，省去人工比对 visual 原文。

**关键区别**：

| API | 用在哪 | 图位 | 作用 |
|---|---|---|---|
| `step_layout_preview` | 生图**前** | 占位符 + 分镜说明 | ★ 审阅主产物 |
| `step_story_script` | 生图前，用户发现对不上时 | 无 | 图文对齐诊断 |
| `step_render_article` | 生图**后** | 真实图片 | 最终发布版 |

**代码示例**：
```python
sb, job_id, work_dir = step_plan("苏武牧羊", bullets=[...])

# ★ 生图前：排版 + 分镜都在这一个文件里
html = step_layout_preview(job_id)
deliver_assets(html)
# 用户审阅 → 拍板

# 若用户说"p09 图文不符"：
print(step_story_script(job_id))   # → 指出缺哪个动作/人物

# 确认后
image_paths = step_gen_images(job_id)
final_html = step_render_article(job_id)
draft = step_publish_draft(job_id)   # ← 这一步会真的写公众号草稿箱，需先问用户
```

---

### Checkpoint 2：图片审阅（Step 2.5）—— ★ 必附"分镜意图 vs 实际画面"对照表 ★

**触发时机**：6-12 张 PNG 生成后、渲染 HTML 前。

**Mavis 操作**：
1. 调 `step_gen_images(job_id)` 拿到 `[Path, ...]` PNG 列表
2. 用 `read tool` 实际读每一张图（**不要只 deliver-assets**）
3. 对照 storyboard.json 的 caption + key_visual + body 摘要，输出对照表
4. 用 `ask_user` 让用户拍板

**★ 必附对照表模板**（用户 2026-09-21 张巡守睢阳项目反馈：必须有，否则用户无法判断是否合适）：
```markdown
| 页 | 章节 | 分镜意图 | 实际画面 | 评估 |
|---|---|---|---|---|
| p1 烽起 | 张巡赴任真源 | 烛光 + 持卷轴 + 看地图 + 风雪夜 | ✅ 张巡持卷轴 ✅ 烛光 ✅ 桌上地图 ✅ 窗外飞雪 | ✅ 完全符合 |
| p9 骂贼 | 嚼齿穿龈、骂贼至死 | 被绑木桩 + 嘴角带血 + 仰天长啸 | ✅ 张巡站姿仰望 ✅ 敌人执矛剪影 ⚠ 未呈现"被绑" ⚠ 未呈现"血" | ❌ 关键元素缺失 |
```

每页用 ✅ / ⚠ / ❌ 标记关键元素是否到位。

**用户操作（ask_user 选项）**：
- ✅ **接受** — 渲染 HTML
- 🔄 **重画某页** — Mavis 调 `step_gen_images(job_id, regenerate_pages=[N, ...])`
- 🔄 **重画全部** — 重跑全图
- 🚫 **风格不对全部换风格** — 改 `style_id` 重跑
- ❌ **拒绝** — 删 work_dir

**为什么这一刻关键**：
- 视觉信息密度比文字更"主观" — 用户对自己作品的画面要求是核心审美
- Agnes 跑图有 10-20% 概率出现风格偏移 / 构图偏差 / 元素缺失
- 重画某页比推翻整个分镜成本低

**重画机制**：`regenerate_pages` 参数写到 `step_gen_images` 调用里，run.py 自动只重画指定页（其他图复用）。

---

### Checkpoint 3：HTML 预览拍板（Step 3.5）

**Mavis 操作**：
1. 调 `step_render_article(job_id, template_id=None)` 拿到 `html_path`
2. 用 `read tool` 读 HTML 重点段（前 100 行 + 章节标题）
3. 用 `ask_user` 让用户拍板

**用户操作（ask_user 选项）**：
- ✅ **接受** — 发草稿
- 🔄 **换模板** — 改 `template_id` 重渲染（推荐 → c / e / a）
- 🔧 **改章节题 / 改 body** — 编辑 storyboard.json 后重渲染
- ❌ **拒绝** — 产物留 data dir 不发

**为什么这一刻关键**：
- 真实公众号编辑器对 HTML 的渲染与本地浏览器不完全一致（色差 / 字号 / 断行）
- 用户要看到"真正会呈现的版本"再决定发不发
- 章节结构 / 引文节奏在 HTML 里最直观

---

### Checkpoint 4：草稿拍板（Step 4.5）—— 自动但报告

**Mavis 操作**：
1. 调 `step_publish_draft(job_id, template_id=None)` 拿到 `draft_media_id`
2. 报告 `draft_media_id` + 公众号后台链接（`https://mp.weixin.qq.com → 内容管理 → 草稿箱`）

**这一步没有 ask_user**（已发到草稿箱，用户到公众号后台预览即可）。

---

## 用户介入的最小信息量

**不要全盘接管，会变疲劳**。最小干预原则：
- **Checkpoint 1**：改 2-3 处关键字段（标题 / 1-2 个 highlight / 1-2 个 caption）
- **Checkpoint 2**：0-2 张重画（只针对明显有问题的图）
- **Checkpoint 3**：直接接受 / 换模板
- **Checkpoint 4**：无操作（自动）

总耗时 < 5 分钟（熟练后）。

---

## 自动化场景

`step_*` API 不带自动跳过参数。Mavis 在批量生成场景下（如 cron / CI）可以：
- 跳过 Checkpoint 1（用默认推荐风格 + 模板）
- 跳过 Checkpoint 2（接受全部跑图结果）
- 跳过 Checkpoint 3（默认接受）
- 只在 Checkpoint 2 拿报告 + 重画某页

适用：
- CI / cron 跑批量
- 信任 LLM 的 demo 测试
- "批量生成后人工筛选"的工作流

---

## 后续可扩展

1. **单页 LLM 重生成**（现在只支持手动编辑） — 让 r N 真正调 LLM 单页重生成
2. **风格对照预览** — 同时跑 2-3 种风格的图，让用户挑
3. **A/B 测试** — 同一主题生成 2 个分镜版本，让用户挑
4. **回退历史** — checkpoint 接受后保留旧版本，让用户可回滚

---

## 相关文件

- `scripts/run.py` — 主入口，全部 `step_*` API（详见 `SKILL.md` 的「API 索引」）
- `scripts/review.py` — 旧分镜 JSON 读写工具，**已删除**；字段编辑能力已上收为 `run.py` 的 `step_set_page_field`（Mavis 直接用它）
- `scripts/image_review.py` — 旧图片 rerender 标记工具，**已删除**（它写的 `rerender.json` 全项目无人读取）。重画请用 `step_gen_images(job_id, regenerate_pages=[N, ...])`
- `references/user-review.md` — 本文档
- `references/workflow.md` — 端到端流程图 + 调试指南
- `references/quality-gates.md` — 两道关卡的完整判据与阈值真源