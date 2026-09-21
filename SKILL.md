---
name: knowledge-comic
description: Knowledge comic generator that turns a topic + bullet list into a publication-ready WeChat MP draft. Use when user asks for "知识漫画", "公众号知识漫画", "科普漫画", "典故解读", "历史故事漫画", "一图读懂", "科普文章配图". Hands off the entire pipeline — style recommendation, storyboard split, image generation, article HTML render, and WeChat draft creation — through step-by-step Python APIs that Mavis calls directly inside the conversation.
version: 0.2.4
---

# Knowledge Comic (WeChat MP) — v0.2.4

把「主题 + 要点」变成可一键发布到公众号草稿箱的知识漫画图文。**端到端在 Mavis 对话里逐步执行 + 用户拍板**。

## When to use

- 用户说"做一个知识漫画" / "科普配图" / "典故解读漫画"
- 用户给主题 + 要点列表（≥2 条），想直接看到公众号草稿
- 用户明确要 5 种锁定风格里的某一类（new_yorker / us_mid_century / cn_xuanfeng / guochao_manhua / chinese_lianhuanhua_classic）

## Mavis 触发引导（/knowledge-comic 后第一步）

**用户说 `/knowledge-comic` 或 "做个知识漫画 / 科普配图 / 典故解读"**：

1. **如果用户没说主题 + 要点**：用 `ask_user` 问：
   - 主题（一个具体短问）
   - 要点列表（≥2 条，每条一行）
2. **如果只说主题没说要点**：用 `ask_user` 追问要点列表
3. **拿到主题 + 要点后**：调下面的 `guide.recommend(topic)` 拿到推荐
4. **用 `ask_user` 让用户拍板**：
   - 选项 1：风格 A + 模板 X（推荐第一选择）
   - 选项 2：风格 B + 模板 Y（备选第二）
   - 选项 3：风格 C + 模板 Z（备选第三）
   - 选项 4（Other）：自定义风格 / 模板
5. **拍板后**：调 `step_plan(topic, bullets, style_id, template_id)` 开始 Step 1
6. **遇到歧义**：先调 `guide.show_intent(topic, bullets, style_id, template_id)` 展示完整推荐 + 理由

**辅助脚本**：

```bash
python guide.py              # 列所有可用脚本 + 推荐矩阵
python guide.py "Transformer" # 拿主题推荐
python guide.py "张巡守睢阳"   # 中文主题
```

返回 JSON：`{"style_id": "chinese_lianhuanhua_classic", "template_id": "c", "alternates": [...], "rationale": "..."}`

## v0.2.4 核心变化（2026-09-21，戴敦邦派连环画定版）

1. **风格锁定到 5 种**（v0.2 砍到 4，v0.2.4 增到 5）：
   - `new_yorker`（经济学/心理学/严肃）
   - `us_mid_century`（商业模式/品牌/设计）
   - `cn_xuanfeng`（历史典故/国学/东方美学 — 传统水墨写意）
   - `guochao_manhua`（历史典故/中国故事/武侠 — 国潮赛璐璐/古风条漫，《镖人》《一人之下》类现代国漫分镜语言）
   - `chinese_lianhuanhua_classic`（**v0.2.4 新增** · 历史典故/中国故事第一推荐 — 戴敦邦派工笔重彩连环画，刘继卣史诗构图 + 王叔晖线条 + 顾炳鑫/贺友直分镜，宣纸 + 飞白 + 朱砂勾线 + 工笔重彩）
2. **排版锁定到 3 个**：`a`（撕纸手账）、`c`（中国古典故事专版）、`e`（典雅知识风）
3. **工作流：纯对话流**——Mavis 在对话里直接调 `step_plan / step_gen_images / step_render_article / step_publish_draft`，每步用 `ask_user` 让用户拍板
4. **画面质量三重硬约束**（v0.2.3）：
   - **零文字铁律**：禁年份/数字/字母/符号/对话气泡/字幕/招牌字
   - **角色一致性铁律**：5-tuple bible（面 + 眼 + 眉 + 唇 + 发 + 服）逐页一致
   - **视觉概念具象化铁律**：抽象概念转具体可见元素（数据符号 + 隐喻物 + 时间指示器）
5. **七要素铁律**（v0.2.3）——每页 visual 按 SUBJECT / ACTION / CAMERA / PLACEMENT / DEPTH LAYERS / LIGHTING / MOOD 七段结构组织
6. **Prompt 截断保护**（v0.2.4）——拼出 prompt > 9800 字符时自动砍 scene_description

## Mavis 对话工作流（端到端）

```
[1] 用户说"做个知识漫画" → Mavis 问主题 + 要点（≥2 条）
[2] Mavis 用 recommend_style() + recommend_template() 推荐（基于主题关键词）
    + 用 `planner.recommend_pages(len(bullets))` 推荐页数（≤3 bullets=8 / 4-6=10 / ≥7=12）
[3] Mavis 用 ask_user 让用户拍板风格 + 模板 + 页数
[4] step_plan(topic, bullets, style_id, template_id, num_pages=None)
    num_pages 默认 None = 按 bullets 数量自动推荐（8/10/12）。用户可显式传 6-15 覆盖。
    → 拿到 (storyboard, job_id, work_dir)
    → Mavis 用 read tool 读 work_dir/storyboard.json → 展示给用户
[5] Mavis 用 ask_user 让用户拍板分镜（接受 / 改某页 caption/visual/body / 重跑）
    (可选) review.set_page_field(job_id, page, field, value) 改字段
[6] step_gen_images(job_id)
    → 拿到 [Path, ...] PNG 列表
    → Mavis 用 deliver-assets 展示给用户
[7] ★ 必附"分镜意图 vs 实际画面"对照表 ★ → ask_user 让用户拍板（接受 / 重画某些页）
    (可选) step_gen_images(job_id, regenerate_pages=[N, ...]) 只重画指定页
[8] step_render_article(job_id)  # template_id=None 自动用 recommended_template
    → 拿到 html_path
[9] Mavis 用 read tool 读 HTML 预览 → ask_user 让用户拍板（接受发草稿 / 改模板 / 拒绝）
[10] step_publish_draft(job_id)  # template_id=None 自动用 recommended_template
    → 拿到 draft_media_id
    → Mavis 报告 draft_media_id + 公众号后台链接
```

**关键：每个 step 都要用户拍板才进下一步**，Mavis 不能全自动跑完。

## 锁定的 5 风格

| ID | 中文名 | 类别 | 适合 | 视觉特征 |
|---|---|---|---|---|
| **new_yorker** | 纽约客式 · 报刊讽刺 | 黑白 Risograph | **经济学 / 心理学 / 严肃 / 成人** | 米色纸 + 平面色块 + 细线条 + 网点 |
| **us_mid_century** | 美式中世纪 · 复古杂志 | 50-60s 杂志 | **商业模式 / 品牌 / 设计 / 生活美学** | mustard + teal + 砖红 + 平面色块 + 几何构图 |
| **cn_xuanfeng** | 宣风 · 国风写意 | 中国水墨 | **历史典故 / 国学 / 古籍解读 / 东方美学** | 飞白 + 朱砂 + 宣纸 + 大胆笔触 + 留白 |
| **guochao_manhua** | 国潮古风条漫 | 国潮赛璐璐 + 古装 + 现代条漫分镜 | **历史典故 / 中国故事 / 武侠 / 江湖** | 朱砂 + 鸦青 + 玉绿 + 金 + 月白 + 赛璐璐平涂 + 现代 1:2 头身比 |
| **chinese_lianhuanhua_classic** | **中国古典连环画（戴敦邦派）** ★ 历史典故第一推荐 | 工笔重彩 + 白描红线 + 水墨淡彩连环画派 | **历史典故 / 古典小说插图 / 圣贤帝王 / 江湖侠义** | 宣纸 + 毛笔 + 工笔 + 白描 + 飞白 + 朱砂勾线 + 工笔重彩（朱砂/靛青/赭石/墨/留白） + 戴敦邦派古典脸（方颌/丹凤/三角眼/剑眉/朝代蓄须） |

**历史典故类第一推荐：`chinese_lianhuanhua_classic`**（2026-09-21 校准，戴敦邦派连环画）。备选按顺序：`guochao_manhua`（现代国潮条漫）→ `cn_xuanfeng`（传统水墨写意）。
**已砍掉 5 个风格**（kid_picture_book / kid_science_diagram / cn_contemporary / jp_kawaii_warm / jp_terada）—— 砍掉是为了每个风格打磨到位。

## 锁定的 3 模板

| ID | 中文名 | 配色 | 适合 |
|---|---|---|---|
| **a** | 撕纸手账风 | 黄便签 + 胶带 + 手写体 | 情感/旅行/通用兜底 |
| **c** | 中国古典故事专版 | 米色羊皮纸 + **朱砂红** + 印章 | 历史典故/古文/国学 |
| **e** | 典雅知识风 | 米色羊皮纸 + **深蓝灰** + 印章 | 知识/科普/商业/严肃 |

## 风格 + 模板配对推荐

| 主题类型 | 风格 | 模板 |
|---|---|---|
| **历史典故 / 国学 / 古籍解读** | **chinese_lianhuanhua_classic**（戴敦邦派，第一推荐）/ guochao_manhua / cn_xuanfeng | **c（朱砂红 + 印章）** |
| **武侠 / 江湖 / 侠义** | **chinese_lianhuanhua_classic** / guochao_manhua | **c（朱砂红 + 印章）** |
| **宏大 / 史诗 / 战争 / 重大事件** | **chinese_lianhuanhua_classic** / new_yorker / guochao_manhua | **c** 或 **e** |
| **文学 / 人物 / 哲学 / 文化** | chinese_lianhuanhua_classic / guochao_manhua / cn_xuanfeng | **c** |
| **经济学知识 / 心理学 / 严肃** | new_yorker | **e（深蓝灰）** |
| **商业模式 / 品牌 / 设计** | us_mid_century | **e（深蓝灰）** |
| **AI / 算法 / 工程 / 科技 / 互联网** | new_yorker / us_mid_century | **e** |
| **科学 / 物理 / 化学 / 生物 / 医学** | new_yorker / us_mid_century | **e** |
| **通用兜底 / 情感 / 旅行** | new_yorker / us_mid_century / chinese_lianhuanhua_classic | a |

## 4 个 step API（Python 直接 import 调）

```python
from scripts.run import (
    step_plan,           # → (storyboard, job_id, work_dir)
    step_gen_images,     # → [Path, ...] PNG（regenerate_pages=[N,...] 单页重跑）
    step_render_article, # → html_path（template_id=None 自动用 storyboard 推荐）
    step_publish_draft,  # → {"draft_media_id": ..., ...}（template_id=None 自动用推荐）
)

sb, job_id, work_dir = step_plan(
    topic="峰终定律",
    bullets=["1993 年卡尼曼实验", "峰 = 最高点 终 = 结束感", "持续时间被忽略"],
    style_id="new_yorker",     # 可选,默认自动推荐
    template_id="e",           # 可选,默认自动推荐
    num_pages=10,              # 可选,默认按 bullets 数量自动推荐 (≤3=8 / 4-6=10 / ≥7=12)
)

image_paths = step_gen_images(job_id)  # 全跑
# 或：image_paths = step_gen_images(job_id, regenerate_pages=[10, 11])  # 只重画

html_path = step_render_article(job_id)  # template_id=None 自动用 storyboard.json 里 recommended_template

result = step_publish_draft(job_id)  # template_id=None 自动用推荐
# result = {"draft_media_id": "...", "uploaded_count": N, "title": "...", "work_dir": "..."}
```

## CLI 兼容入口（cron / CI 场景）

```bash
# 一键跑完整链路
python scripts/run.py all "峰终定律" -b "1993 年卡尼曼实验" -b "峰终概念" -b "应用启示" -s new_yorker -t e

# 单步
python scripts/run.py plan "峰终定律" -b "..." -s new_yorker -t e
python scripts/run.py gen --job-id kc_xxx
python scripts/run.py render --job-id kc_xxx
python scripts/run.py publish --job-id kc_xxx
```

## 核心原则（不可破坏）

### 1. 用户主导（User-in-the-loop）

**每一篇知识漫画的核心创作决策,用户必须亲自介入**。
- 风格 + 模板拍板 → Mavis 用 `ask_user`
- 分镜审阅 → Mavis 用 `read tool` 读 `work_dir/storyboard.json` 展示 + `ask_user` 拍板
- 图片审阅 → Mavis 用 `deliver-assets` 展示 PNG + **必附"分镜意图 vs 实际画面"对照表** + `ask_user` 拍板
- HTML 预览拍板 → Mavis 用 `read tool` 读 HTML + `ask_user` 拍板

**不能跳过介入**：Mavis 不能全自动跑完发草稿。自动化是减少体力劳动,不是替代用户审美。

### 2. 图文分离铁律

- 对话/旁白/标题/正文 → 进 HTML 文章层
- image 里严禁出现文字（年份/数字/字母/符号/对话气泡/字幕/招牌字）

### 3. 角色一致性铁律（v0.2.3 五件套）

跨页角色描述必须完全一致。三个角色锚点（按风格自动选）：
- 现代/科学家 → `a small scientist figure with short black hair, round wire-frame glasses, light grey sweater, dark trousers, neutral expression, age 30`
- 国潮/古代 → `Character bible (FIVE ANCHORS): oval face + sharp jawline + 大眼双睑 sharp winged eyeliner + swordsman brows + cupid's bow lips + 高髻 + cloth ribbon + Han-Chinese historical hanfu`
- 戴敦邦派（chinese_lianhuanhua_classic）→ `Dai Dunbang-style: square jaw + phoenix-eye 丹凤眼 / triangular-eye 三角眼 + sword-brow 剑眉 + 朝代蓄须 + 朝代高髻/幞头/乌纱`

### 4. 七要素结构铁律（v0.2.3）

每页 visual 必须按 7 段组织：

| # | 段名 | 必填内容 |
|---|---|---|
| 1 | SUBJECT | 主角 + 陪伴角色 + 物件（名词短语列举） |
| 2 | ACTION | 反应动词（yanking / slashing / biting），禁用静态"stands/looks" |
| 3 | CAMERA | shot size + angle + lens + DoF 四件套 |
| 4 | PLACEMENT | 主体在画面位置（rule of thirds / asymmetric） |
| 5 | DEPTH LAYERS | foreground / midground / background 三层显式 |
| 6 | LIGHTING | 光源 + 方向 + 色温 + 质感 |
| 7 | MOOD/PALETTE | 情绪基调 + 配色 |

### 5. 视觉概念具象化铁律

抽象概念必须转成**具体可见的视觉元素**：
- ❌ "showing the concept of attention" → 太空
- ✅ "three glowing dots floating in air, connected by golden threads to the character" → 视觉可读

### 6. AI 出图现代写实锚点防范 (v0.2.4)

**症状**：做"国画 / 工笔 / 水墨 / 连环画 / 古风条漫"等非写实风格图时，凡 prompt 里出现 candle / lantern / desk / porcelain rest / modern Chinese minimalism / cinematic studio lighting 等"现代写实"物件词，模型自动走"现代写实油画 / 3D 渲染 / 摄影"风。

**修复**：
1. 把"painted illustration"声明放 SUBJECT 第一句：`CRITICAL — The entire frame is rendered as a classical Chinese lianhuanhua painted illustration, NOT a photograph, NOT a 3D render...`
2. 把人物描述成 `brush-painted figure on rice paper, NOT a photorealistic person`
3. 在视觉描述里**避免** candle / lantern / desk / porcelain rest / modern Chinese minimalism / cinematic studio lighting 等词
4. 把"volumetric light"改成"painted warm wash"

**踩坑验证**：张巡守睢阳 v0.2.4 chinese_lianhuanhua_classic 风格 — p1-p9（战场 / 粮仓 / 城墙）自动到位，p10-p11（书房 + 学者）反复跑偏现代写实风，重写 visual 加 v2 fix 后到位。

### 7. 公众号 IP 白名单 + 编码

- 第一次跑前提示用户加公网 IP 到 mp.weixin.qq.com → IP 白名单（errcode 40164）
- `requests.post` 必须 `ensure_ascii=False`，否则中文变 `\uXXXX` 字面量

## 文件结构

```
knowledge-comic/
├── SKILL.md                  ← 你正在读的（v0.2.4）
├── references/
│   ├── handraw_styles.md     ← 5 个锁定风格完整定义 + 推荐矩阵
│   ├── templates.md          ← 3 个排版模板详情 + 配色对照
│   ├── user-review.md        ← Mavis 对话流 + 分镜意图 vs 实际画面对照表模板
│   ├── workflow.md           ← 端到端流程图 + 调试指南
│   └── style_guide.md        ← 文章内容评分维度（深度/一致性/作者风格 100 分制）
├── scripts/
│   ├── run.py                ← 主入口：4 个 step_* API + CLI 兼容
│   ├── canon.py              ← 一致性检查工具（术语/数字/视觉锚点）
│   ├── image_review.py       ← 图片 rerender 标记工具
│   ├── publish_existing.py   ← 重发草稿（图片复用）
│   └── core/                 ← 核心模块（planner/image_gen/article/publisher/prompts/config）
├── data/                     ← 生成的图 + 中间产物（git ignore）
├── .env.example
└── README.md
```

## 关键 pitfall

| 坑 | 怎么避 |
|---|---|
| 公众号乱码 `\u4e00` | `requests.post` 必须 `ensure_ascii=False`（`publisher.py` 已封装） |
| 图里出现中文/年份/数字 | `prompts.py:ZERO_TEXT_BOOST` 强制 "NO text/numbers/digits/letters" + planner system prompt 严禁具体年份 |
| 角色"换人" | planner system prompt 强制同款角色锚点（5-tuple bible） |
| 大头贴（人物面部占满画面） | 七要素铁律强制 SUBJECT + CAMERA/PLACEMENT + DEPTH LAYERS + 角色面部 < 1/3 画面 |
| 风格跑偏到现代写实 | v0.2.4 §6 现代写实锚点防范（"painted illustration"声明放 SUBJECT 第一句） |
| 书房+学者+灯具 = 3D 写实 | 砍掉 "candle/lantern/desk/porcelain" + 加 "brush-painted figure" 描述 |
| Agnes 队列 503 | `core/image_gen.py` 自动 retry with 退避 |
| Agnes prompt > 10000 字符失败 | `build_image_prompt` > 9800 自动砍 scene_description |
| WeChat IP 白名单 | 第一次跑前提示用户加白名单；errcode 40164 报错时明确指出 |
| LLM 没配置 | `core/planner.py` 自动 fallback 到 mock storyboard（角色一致版） |
| **Mavis 对话接不到 subprocess stdin** | v0.2 已重构：去掉所有 `subprocess.run([sys.executable, review.py])`，Mavis 直接调 step API |
| `recommended_template` 字段丢失 | v0.2.4 修复：`Storyboard.recommended_template` 字段 + `to_dict()` 返回 + `_load_storyboard` 读 |

## 变更记录

- **0.2.4**（2026-09-21）：戴敦邦派连环画定版
  - 新增第 5 风格 `chinese_lianhuanhua_classic`（戴敦邦派工笔重彩连环画），历史典故第一推荐
  - 新增 `CHARACTER_CN_LIANHUANHUA_ANCESTOR` 锚点（5-tuple 戴敦邦派脸：方颌 + 丹凤/三角眼 + 剑眉 + 朝代蓄须 + 朝代高髻/幞头）
  - `RECOMMEND_MATRIX` 历史/文学/古风/武侠/宏大类第一优先改 `chinese_lianhuanhua_classic`
  - `build_image_prompt` > 9800 字符截断保护（保 style + 七要素套话，砍 scene_description）
  - 修 `recommended_template` 字段丢失 bug（`Storyboard.recommended_template` + `to_dict()` 返回 + `_load_storyboard` 读）
  - SKILL.md / references 升 v0.2.4
- **0.2.3**（2026-09-21）：七要素铁律
  - planner system prompt 显式七要素结构（SUBJECT / ACTION / CAMERA / PLACEMENT / DEPTH LAYERS / LIGHTING / MOOD）
  - planner 加镜头分配铁律（12 页版："开-推-特-退"节奏）
  - prompts.py 加 `CAMERA_LANGUAGE_KIT`（6 shot × 6 angle × 5 lens × 3 DoF）
  - prompts.py 加 `DEPTH_LAYERS_BOOST`（三层景深硬约束）
  - prompts.py 加 `CINEMATIC_FRAMEWORK_BOOST`（七要素结构铁律）
  - prompts.py 加 `EXPRESSION_VOCAB`（8 件套：neutral / rage_scream / sobbing_silence / grim_resolve / awed_stillness / sneering_scorn / tender_grief / fierce_command）
- **0.2.2**（2026-09-21）：新增第 4 风格 `guochao_manhua`（国潮古风条漫）—— 历史典故类第一推荐；Mavis 对话流必附"分镜意图 vs 实际画面"对照表
- **0.2.0**（2026-09-20）：砍 8 风格→3 风格，砍 5 模板→3 模板，去 subprocess 改对话流，加零文字/角色一致性/视觉具象化三重硬约束
- 0.1.1（2026-09-20）：新增 `e` 模板（典雅知识风，深蓝灰配色版，基于 `c` 模板结构）
- 0.1.0（2026-09-18）：初始版本，4 模板 + 8 风格