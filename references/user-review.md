# 用户介入 checkpoint 设计（v0.2.4 Mavis 对话流版）

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

v0.2（2026-09-20）**完全去掉** `subprocess.run([sys.executable, review.py])` 的 stdin checkpoint 模式（已确认 Mavis 对话接不到 subprocess stdin，会静默 EOFError）。改为 Mavis 在主对话里：
- 用 `read tool` 读产物（JSON / HTML / PNG）
- 用 `ask_user` 让用户拍板
- 用 `deliver-assets` 展示图

---

## 3 个核心 checkpoint（Mavis 对话流版）

### Checkpoint 1：分镜审阅（Step 1.5）—— Mavis 必做

**触发时机**：LLM 生成 storyboard.json 后、跑图前。

**Mavis 操作**：
1. 调 `step_plan(topic, bullets, style_id, template_id)` 拿到 `(sb, job_id, work_dir)`
2. 用 `read tool` 读 `work_dir/storyboard.json`
3. 把分镜摘要（标题 / 副标题 / 每页 caption + highlight + key_visual + body 摘要）展示给用户
4. 用 `ask_user` 让用户拍板

**用户操作（ask_user 选项）**：
- ✅ **接受** — 跑图
- 🔧 **改某页 caption/visual/body** — Mavis 调 `scripts/review.py:set_page_field(job_id, page, field, value)` 或直接编辑 JSON
- 🔧 **改 highlight** — 跨章唯一的章节大字
- 🔄 **重跑整组分镜** — 重跑 step_plan
- ❌ **拒绝** — 删 work_dir

**为什么这一刻关键**：
- highlight 是"章节大字"，读者第一眼看到的内容
- caption 是章节题，决定读者翻页动机
- visual 决定画面信息密度（本文最容易被 LLM 偷懒的地方）
- body 是正文（可以接受 LLM 默认，但前 3 项必须过手）

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

- `scripts/run.py` — 主入口，4 个 step_* API
- `scripts/review.py` — 分镜 JSON 读写工具（无 stdin，Mavis 不直接用）
- `scripts/image_review.py` — 图片 rerender 标记工具
- `references/user-review.md` — 本文档
- `references/workflow.md` — 端到端流程图 + 调试指南