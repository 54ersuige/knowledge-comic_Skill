---
name: knowledge-comic
description: |
  把「主题 + 要点列表」变成可一键发布到公众号草稿箱的知识漫画图文：选风格 → 拆分镜
  → 跑图 → 渲染 HTML → 建草稿。支持 5 种锁定画风（古典连环画 / 国潮条漫 / 国风水墨 /
  纽约客 / 美式中世纪）。
  Use when 用户说「做个知识漫画」「公众号知识漫画」「科普漫画」「典故解读」「历史故事漫画」
  「一图读懂」「给这篇文章配图做成漫画」，或给出一个主题 + 要点列表想要成品图文。
  Do NOT use for：单张插画/封面图（直接跑图即可，不需要分镜与排版）；纯文案撰写（用公众号写作类
  skill）；已有图片要排版成文章（用排版类 skill）；科普长文而非漫画（用知识解读类 skill）。
version: 0.3.28
---

# Knowledge Comic (WeChat MP)

把「主题 + 要点」变成公众号知识漫画图文。**逐个 step 在 Mavis 对话里执行，每个决策点由用户拍板。**

**这个 skill 的第一原则是「用户主导」。** 不是因为流程好看，而是因为实测事故：一次任务里
12 页图全跑完、用了 3 轮 `ask_user`、每一步都"符合流程"，但**用户从头到尾没看过一张图**
（用 `read` 看图只进了模型自己的上下文）—— 最后是在用户投诉"我没有效参与"之后才补发。

## Inputs to collect

调用前必须拿到，缺了就用 `ask_user` 问，**不要自己编**：

1. **主题** —— 一个具体短题（「张巡守睢阳」而不是「唐朝历史」）
2. **要点列表** —— ≥ 2 条，每条一行。这是分镜的骨架，不是正文
3. **风格 + 模板偏好** —— 用户没说就用 `guide.recommend(topic)` 出推荐再让用户拍板

页数不用问：默认按要点数自动推荐（≤3 条 = 8 页 / 4-6 条 = 10 页 / ≥7 条 = 12 页），
用户想覆盖再显式传 `num_pages`（6-15）。

## Procedure

### 0. 先推荐，再开工

先调 `guide.recommend(topic)` 拿推荐（返回 `style_id` / `template_id` / 备选 / 理由），
用 `ask_user` 给 3 个候选组合 + Other 让用户拍板。**风格是审美决策，不能替用户定。**

### 1. `step_plan` → 分镜 JSON

```python
sb, job_id, work_dir = step_plan(
    topic="张巡守睢阳",
    bullets=["燕军围城", "六千八百人", "粮尽食人", "骂贼至死"],
    style_id="chinese_lianhuanhua_classic",   # 可选，默认自动推荐
    template_id="c",                          # 可选，默认自动推荐
    characters=[],                            # 人物故事必填，见下
)
```

**人物故事必须传 `characters`**，每个角色要带 `name` / `role` / `era` / `gender` /
`visual_signature`。理由：角色参考图会经 i2i 传进每一页，锚点错一次整批图全崩（实测
kc_1790664590 夫差被画成女性，污染了所有含他的页面）。`gender` 缺失会**直接阻塞**，
内置人名表**不再兜底**。

### 2. `step_layout_preview` → 生图前审阅（**唯一产物**）

```python
html_path = step_layout_preview(job_id)
```

一个文件同时展示**成品排版 + 每页分镜意图**（主体/动作/配角/背景/景别/情绪/关键词）。

用 `<deliver-assets>` 送 `html_path` 给用户 → `ask_user` 拍板。**这一步是省钱关卡**：
分镜错了后面全白费。

用户发现某页图文不符 → `step_set_page_field(job_id, page, field, value)` 改字段，
**改完必须重新调 `step_layout_preview` 重发预览**，否则用户没参与这次修改。
（可用字段：`highlight` / `caption` / `visual` / `body` / `dialogue` / `narration`）

### 3. `step_gen_images` → 跑图

```python
image_paths = step_gen_images(job_id)
```

执行顺序：`preflight` 体检（阻塞）→ 角色参考图 → 逐页跑图 → `visual_qa` 视觉审核。

- 有阻塞项 → `SystemExit(1)`，**一张图都不跑**。逃生阀 `skip_preflight=True`
- `regenerate_pages=[N, ...]` 只重画指定页
- `auto_char_refs=False` 跳过角色参考（**概念页 / 大场面页必须这样跑**，i2i 参考图会压制
  概念场景）
- `auto_visual_qa=False` 关掉跑图后审核

跑 8-12 页约 3-6 分钟，全程有进度输出（`[gen] p3/10 done (62s, 约还需 124s)`）。

→ 用 `<deliver-assets>` 把 PNG 送用户，**必附「分镜意图 vs 实际画面」对照表**（模板见
`references/user-review.md`）→ `ask_user` 拍板。

### 4. `step_render_article` → HTML

```python
html_path = step_render_article(job_id)   # template_id=None 自动用推荐
```

→ 把 HTML 送用户 → `ask_user` 拍板（接受发草稿 / 换模板 / 拒绝）。

### 5. `step_publish_draft` → 公众号草稿

```python
result = step_publish_draft(job_id)   # → {"draft_media_id", "uploaded_count", "title", ...}
```

→ 报告 `draft_media_id` + 公众号后台链接。

### CLI 兼容入口（cron / CI，非主路径）

```bash
python scripts/run.py all "峰终定律" -b "要点1" -b "要点2" -s new_yorker -t e
python scripts/run.py plan|gen|render|publish --job-id kc_xxx
```

## Output contract

- **对话内产物**：每一步的资产都要用 `<deliver-assets>` 真正发到用户窗口
- **落盘产物**（`data/<job_id>/`）：`storyboard.json` / `layout_preview.html` /
  `pages/*.png` / `article.html` / `preflight_report.json` / `visual_qa_report.json`
- **最终交付**：公众号草稿箱一条草稿 + `draft_media_id`
- **审阅环节必须附对照表**，不能只发图

## Failure handling

| 症状 | 处置 |
|---|---|
| `CHAR_GENDER_MISSING` 阻塞 | planner 没填 `gender`。手工传 `characters=` 时自己带上 `gender`（`male`/`female`）。内置人名表**不再兜底** |
| `ERA_ANACHRONISM` 阻塞 | 角色 `visual_signature` 含后世器物。按 `era` 查朝代服饰速查表改写 |
| `TEXT_INVITING` 阻塞 | visual 里有 `calligraphy`/`inscribed`/`banner` 等诱导词 → 模型会真画字 |
| LLM 调用/解析失败 | **默认当场抛错**（带尝试记录 + `finish_reason` + 首尾 300 字符）。这是有意的 —— 静默降级到 mock 会没有 `keywords`/`[GENDER]`，整条链路悄悄废掉。仅 CI/离线批量可传 `allow_mock_fallback=True` |
| 没配 `LLM_API_KEY` | 合法离线模式 → 降级到 mock 并**明确告知用户**（区别于上面的真故障） |
| `errcode=40164` | 公网 IP 没加白名单 → 公众号后台加 IP |
| 图上出现文字 | `visual_qa` 报 `TEXT_ON_IMAGE`。**肉眼容易漏**（要放大看衣物纹样）→ 改 visual 正面描述 + 塞进 `CONCEPT` 段，**不要靠负面提示词**（本管线里基本无效） |
| 风格跑偏到现代写实 | visual 里出现了 candle / lantern / desk / porcelain / cinematic studio lighting → 见下方铁律 6 |

## 核心铁律（不可破坏）

### 1. 用户主导 —— 先发资产，再让用户拍板

**没发过资产的步骤 = 没做完。**

每个审阅步骤开工前自查：

| 问自己 | 是 → 做法 |
|---|---|
| 用户能**看到**这个产物吗？ | 不能 → 先用 `<deliver-assets>` 发出去，再提问 |
| 我的提问需要用户"凭描述判断"吗？ | 是 → 产物没发对，回去发 |
| 这是我的审美判断还是客观缺陷？ | 审美 → 标明"这是我的看法"，给用户反驳余地 |

- **核查结论不能替代原件。** 可以说"p2 有题跋"（客观），但"好不好看""要不要重画"这类
  审美决策必须让用户自己看图。
- **自己的判断要标明出处**，不能包装成结论让用户默认接受。
- 流程里的箭头（`→ 用 deliver-assets 展示给用户`）是**必做项**，不是可选建议。跳过的后果
  不是报错，而是用户失去判断依据。

### 2. 图文分离

- 对话/旁白/标题/正文 → 进 HTML 文章层
- 图里严禁出现文字（年份/数字/字母/符号/对话气泡/字幕/招牌字）

### 3. 角色一致性

跨页角色描述必须完全一致。角色锚点按风格自动选，**不要手工拼**（`prompts.get_character_anchor`）。
`chinese_lianhuanhua_classic` 有性别分支：女性 = 桃花腮 + 花钿 + 步摇 + 柳叶眉 + 樱桃小口；
男性 = 玉冠/幞头/束发 + 直眉/剑眉 + 无桃花腮 + 朝代配饰。**planner 必须每页 visual 第二行
写 `[GENDER:male|female|mixed]` tag**，否则性别检测失效。

### 4. 七要素结构

每页 `visual` 按 7 段组织：SUBJECT / ACTION / CAMERA / PLACEMENT / DEPTH LAYERS / LIGHTING /
MOOD-PALETTE。`ACTION` 必须是反应动词（yanking / slashing），禁用静态 `stands` / `looks`。
角色面部占画面 < 1/3（防大头贴）。

### 5. 视觉概念具象化

抽象概念必须转成**具体可见的视觉元素**。

- ❌「showing the concept of attention」→ 太空
- ✅「three glowing dots floating in air, connected by golden threads to the character」

`CONCEPT:` 段画概念不画场景。**负面提示词在本管线基本无效** —— 顽固偏差（明代乌纱帽、斗笠）
要改正面描述 + 塞进 `CONCEPT` 段才压得住。

### 6. 现代写实锚点防范

做国画/工笔/水墨/连环画/古风条漫时，prompt 里一旦出现 candle / lantern / desk /
porcelain rest / modern Chinese minimalism / cinematic studio lighting，模型自动走现代写实风。

修复：① 把 `painted illustration` 声明放 SUBJECT 第一句（`CRITICAL — The entire frame is
rendered as ..., NOT a photograph, NOT a 3D render`）；② 人物描述成 `brush-painted figure on
rice paper`；③ 避开上面那串现代物件词；④ `volumetric light` 改 `painted warm wash`。

> 实测：张巡守睢阳 p1-p9（战场/粮仓/城墙）自动到位，p10-p11（书房+学者）反复跑偏，
> 重写 visual 后才到位 —— **场景是"现代写实"高发区**。

### 7. 公众号 IP 白名单 + 编码

- 第一次跑前提示用户加公网 IP 到 mp.weixin.qq.com → IP 白名单（否则 errcode 40164）
- `requests.post` 必须 `ensure_ascii=False`，否则中文变 `\uXXXX`（`publisher.py` 已封装）

### 8. 文风铁律（Mavis 审阅 `layout_preview` 时**必查**）

**8.1 术语翻译** —— 任何术语首次出现必须 `术语（大白话解释）`，**一页最多 1 个**。解释用读者
生活里的类比，不是同义替换。专有名词（人名/地名/朝代/官职）免解释。

**8.2 正文三拍结构（100-150 字）**

| 拍 | 字数 | 职责 |
|---|---|---|
| 讲事 | 40-50 字 | 这一页发生了什么 |
| **说破** | **40-60 字** | 把「**为什么**」用人话说出来 —— **最容易丢、最关键** |
| 落点 | 20-30 字 | 一句判断，**不重复画面** |

**8.3 白话 / 文言严格分层（三者不可混用）**

| 字段 | 语体 | 位置 |
|---|---|---|
| `body` | 现代白话 | 图下正文 |
| `dialogue` | 文言原文，逐字出原著 | 叠在图片下缘蒙版 |
| `punchline` | 白话金句 10-22 字 | 「定格瞬间」卡 |

**8.4 分寸禁写** —— ❌ hedging（`（或…）`/`（实际为…）`，preflight **阻塞**）；❌ 现代口水词
（内卷/破防/降维打击，warn）；❌ 复述画面已表达的内容；❌ 元叙事（「XX 式的视角告诉我们」）；
❌ 说教（「综上所述」/「我们应该…」）。

**8.5 排版** —— 正文一句一段、无首行缩进，由 `article._split_paragraphs()` 自动实现，
Mavis 不需要手动干预。

## 风格与模板

### 5 种锁定风格

| ID | 中文名 | 适合 |
|---|---|---|
| `chinese_lianhuanhua_classic` | 中国古典连环画（戴敦邦派）★ **历史典故第一推荐** | 历史典故 / 古典小说 / 圣贤帝王 / 江湖侠义 |
| `guochao_manhua` | 国潮古风条漫 | 中国故事 / 武侠 / 宏大叙事 |
| `cn_xuanfeng` | 宣风 · 国风写意 | 国学 / 古籍解读 / 东方美学 |
| `new_yorker` | 纽约客式 · 报刊讽刺 | 经济学 / 心理学 / 严肃 / 成人 |
| `us_mid_century` | 美式中世纪 · 复古杂志 | 商业模式 / 品牌 / 设计 |

### 3 种排版模板

| ID | 中文名 | 适合 |
|---|---|---|
| `c` | 中国古典故事专版（朱砂红 + 印章） | 历史典故 / 古文 / 国学 |
| `e` | 典雅知识风（深蓝灰 + 印章） | 知识 / 科普 / 商业 / 严肃 |
| `a` | 撕纸手账风 | 情感 / 旅行 / 通用兜底 |

风格与模板的完整定义、推荐矩阵（主题类型 → 风格 + 模板）见
`references/handraw_styles.md` 与 `references/templates.md`。
**推荐矩阵的真源是 `scripts/core/prompts.py` 的 `RECOMMEND_MATRIX`**，reference 里的表格是它的
可读镜像 —— 两者不一致时以代码为准。

## API 索引

`scripts/run.py` 是唯一入口（15 个 `step_*`）。主路径 5 个：

| step | 作用 |
|---|---|
| `step_plan` | 主题 + 要点 → 分镜 JSON |
| `step_layout_preview` | 生图前审阅页（排版 + 分镜意图） |
| `step_gen_images` | 分镜 → PNG（内含 preflight + visual_qa 两道关卡） |
| `step_render_article` | PNG → 文章 HTML |
| `step_publish_draft` | HTML → 公众号草稿 |

辅助 step：`step_preflight_images`、`step_visual_qa`、`step_story_script`、
`step_review_storyboard`、`step_set_page_field`、`step_dump_storyboard`、
`step_rewrite_visual`、`step_show_intent_vs_actual`、`step_dry_publish`、`step_preflight`。

## 文件结构

```
knowledge-comic/
├── SKILL.md                    ← 本文件（执行规约）
├── guide.py                    ← 主题 → 风格/模板推荐
├── install.ps1 / install.sh    ← 跨设备一键安装
├── requirements.txt / .env.example
├── references/
│   ├── handraw_styles.md       5 风格完整定义 + 推荐矩阵
│   ├── templates.md            3 模板详情 + 排版铁律（v0.3.8）
│   ├── style_guide.md          文风铁律（术语翻译 / 三拍结构 / 白话文言分层）
│   ├── user-review.md          Mavis 对话流 + 「分镜意图 vs 实际画面」对照表模板
│   ├── workflow.md             端到端流程图 + 调试指南
│   ├── quality-gates.md        两道关卡的完整判据（22 preflight codes + 4 visual_qa codes + 阈值真源）
│   └── CHANGELOG.md            版本变更史（维护者用，执行时不需要读）
└── scripts/
    ├── run.py                  主入口：step_* API + CLI
    ├── run_tests.py            跑全部测试的唯一入口
    ├── check_docs.py           文档引用完整性校验（文档 ↔ 代码）
    ├── check_drift.py          真源 ↔ dev 镜像一致性校验
    ├── check_alignment.py      视觉文字对齐审查
    ├── canon.py                一致性约束注入（data/canon.md）
    ├── tests/                  正式测试（全部不烧 API 额度）
    └── core/                   核心模块
```

## Setup（仅换新设备时需要）

skill 本身随仓库分发（`github.com/54ersuige/knowledge-comic_Skill`）。换设备时：

```powershell
# Windows
irm https://raw.githubusercontent.com/54ersuige/knowledge-comic_Skill/main/install.ps1 | iex
```

```bash
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/54ersuige/knowledge-comic_Skill/main/install.sh | bash
```

脚本会 clone 到 `~/.minimax/skills/knowledge-comic`、装 Python 依赖、复制 `.env.example` → `.env`、
显示本机公网 IP 并跑 smoke test。

装完必须填 `.env`：`AGNES_API_KEY`（跑图）、`WECHAT_APPID` / `WECHAT_APPSECRET`（发草稿）、
`LLM_API_KEY`（planner）。**并把本机公网 IP 加到公众号后台的 IP 白名单**（否则 errcode 40164）。

没配 `LLM_API_KEY` 也能跑 —— 会走 mock 分镜的离线模式，但产物只能用于验证流程，不能发布。

## 自检命令（改完必跑）

```bash
python scripts/run_tests.py     # 全量测试。不要用 pytest —— standalone 脚本会撞 SystemExit 导致 INTERNALERROR
ruff check scripts/             # lint
python scripts/check_docs.py    # 改了任何 .md 或删改脚本后跑：校验文档不再指向不存在的路径/函数
python scripts/check_drift.py   # 改了 core/*.py 后跑：校验真源 ↔ dev 镜像一致性
```

## 参考文件

- 风格/模板/矩阵细节 → `references/handraw_styles.md`、`references/templates.md`
- 关卡判据与阈值 → `references/quality-gates.md`
- 对话流与审阅模板 → `references/user-review.md`
- 端到端流程图与调试 → `references/workflow.md`
- 文风铁律完整版 + 改写对照表 → `references/style_guide.md`
- 版本考古（**只在排查历史行为差异时读**）→ `references/CHANGELOG.md`
