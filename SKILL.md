---
name: knowledge-comic
description: Knowledge comic generator that turns a topic + bullet list into a publication-ready WeChat MP draft. Use when user asks for "知识漫画", "公众号知识漫画", "科普漫画", "典故解读", "历史故事漫画", "一图读懂", "科普文章配图". Hands off the entire pipeline — style recommendation, storyboard split, image generation, article HTML render, and WeChat draft creation — through step-by-step Python APIs that Mavis calls directly inside the conversation.
version: 0.3.4
---

# Knowledge Comic (WeChat MP) — v0.3.4

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

## v0.3.4 核心变化（2026-09-28，分镜审阅页 + 真实题材冒烟测试）

**背景**：用户看完 v0.3.3 产出的 storyboard JSON 提了两个问题——「用户不一定能看懂 JSON」和「这一步是要在生图前确定方向和内容，对吗」。第二个答案是**对的**：`references/user-review.md` 的 Checkpoint 1 就是这个设计，跑图很贵、分镜错了后面全白费。但原来的审阅方式确实不可用——只能让用户看多层嵌套的 JSON 原文。

1. **新增排版预览（`step_layout_preview()` + `article.render_layout_preview()`）—— Checkpoint 1 的正确产物**
   - **这一关要确认的是「文字排版效果」**：标题怎么排、章节题多大、正文什么字体、朱砂红高亮打在哪些词上、对话引文和收束段落在哪。用户确认排版满意，才值得花钱跑图（10-12 页十几分钟 + 额度）。
   - 用**真实模板 + 占位图**渲染完整版面 → 生图之前就能看
   - 支持 `compare_templates=["c","e"]` 多模板对比
   - 顺带修 `_placeholder_img()`：旧实现返回 `<div>` 标签字符串，被塞进 `<img src>` 会**破图**——而这恰好破坏了排版预览的意义。改用 SVG data URI（零依赖）

2. **分镜体检报告（`step_review_storyboard()` + `core/review_page.py`）—— 辅助工具**
   - 8 项硬约束自动体检，输出 Markdown 审阅卡 + HTML 报告页
   - **定位**：它是「哪几页不合格」的补充检查，**不是** Checkpoint 1 的主角。主角是上面的排版预览。
   - 检查项：正文 100-150 字 / keywords ≥3 / `[GENDER:xx]` / caption 非空 / visual ≥300 字 / 零文字声明 / 多人物构图 / 章节大字唯一

2. **新增真实题材冒烟测试（`scripts/tests/test_live_smoke.py`）**
   - **动机**：v0.3.2 / v0.3.3 的两个真 bug（苏武牧羊分类失败、keywords 被解析层丢弃）**都是只有真跑才现形的**，纯 mock 回归看不见「LLM 是否真的按 schema 输出」「解析层是否接住了」。
   - 默认 **skip**（不烧额度），加 `--live` 才调真 LLM
   - 题材固定用「苏武牧羊」—— 苏武不在人名表里、又无朝代词，是 v0.3.3 兜底层最易回退的用例
   - 断言全部对着踩过的坑：风格 / 模板跟随 / keywords 非空 / GENDER 齐全 / 页数 / 审阅模块能处理真实数据

## v0.3.3 核心变化（2026-09-28，苏武牧羊真实端到端测试暴露的 2 个 bug）

**背景**：v0.3.2 修复后，用「苏武牧羊」跑真实端到端测试（调真 LLM），又暴露 2 个问题。都是**只靠静态审查发现不了、必须真跑才现形**的。

1. **分类器对「名单外人名」失效** — 根因：v0.3.2 的分类器依赖 120+ 人物名表，而名单永远补不完。苏武不在表里、没有朝代词、"牧羊"不匹配古典双人物句式 → 三类信号全落空 → 被误判成 `new_yorker`。
   - 修复：新增 `_looks_like_cn_history()` —— **不依赖人名表**的通用中国历史题材识别，三条命中任一即可：
     1. 史事动作词（牧羊 / 被贬 / 流放 / 卧薪 / 戍边 / 殉国 / 纳谏 …）
     2. 史事语境词（漠北 / 塞外 / 朝廷 / 匈奴 / 朝堂 …）
     3. 古典双人物叙事句式
     排除含拉丁字母/数字 及 `_MODERN_BLOCKLIST` 命中的现代题眼
   - 同时修 `recommend_template` 逻辑漏洞：原"分类器落空 → 回退类型词匹配"会**覆盖**风格派生结果，导致兜底层命中时出现"风格对、模板错"的分裂输出
   - 回归测试补 6 组**名单外用例**（苏武牧羊 / 范仲淹被贬 / 卧薪尝胆 / 负荆请罪 …）防止回退

2. **keywords 在 LLM 解析层被静默丢弃** —— 根因：`planner.py` 构造 `StoryPage` 时漏了 `keywords` 字段。v0.2.9 加 keywords 时只改了 prompt schema 和 dataclass 定义，**忘了同步解析层** —— LLM 按 schema 正常输出了，却在解析时被丢掉。朱砂红高亮整条链路失效。
   - 这是典型的"改了一处没改另一处"漏改：prompt 侧看起来一切正常，只有端到端实跑才暴露。
   - 实测对比（苏武牧羊 10 页）：

     | 指标 | 修复前 | 修复后 |
     |---|---|---|
     | 有 keywords 的页 | 0/10 | **10/10** |
     | body 在 100-150 字 | 2/10 | **9/10** |
     | body 平均字数 | 93 | **114** |

   - 修复：`keywords=p.get("keywords", []) or []` 补进解析层

**验证**：苏武牧羊 10 页实跑 → 风格 `chinese_lianhuanhua_classic` + 模板 `c` 正确，GENDER 标记 10/10，keywords 10/10；3 个测试全绿（26 组分类用例）

## v0.3.2 核心变化（2026-09-28，代码审核修复 7 个 bug）

**背景**：2026-09-28 对 skill 做了一轮全量代码审核（读 run/planner/prompts/image_gen/article/publisher/check_alignment 全模块 + 实测），修掉 7 个 bug。其中 1 个是 P0 功能性 bug，直接让"历史典故第一推荐 chinese_lianhuanhua_classic"在自动推荐路径上完全失效。

1. **【P0】风格/模板推荐对真实题材失效** —— 根因：推荐矩阵的 key 是**主题类型词**（"历史"/"典故"/"国学"），而 `recommend_style()` 拿**真实主题**（"张巡守睢阳"）做 `k in topic` 字面匹配，几乎永远不命中，全部掉进 `new_yorker` 兜底。
   - 实测修复前：张巡守睢阳 / 王昭君出塞 / 岳飞抗金 / 赤壁之战 / 三国演义 / 论语 → 全部误判 `new_yorker` + `e`
   - 修复：改为**加权信号分类器** `_classify_signals()` —— 专有名词表（120+ 历史人物）+ 朝代词（强/弱两档）+ 事件词 + 领域词，三档权重（10/5/1），**长词优先**（"商业模式" 压过 "商业"，"西汉" 压过 "汉"，"王昭君" 压过 "昭君"）
   - 补一层**古典双人物叙事句式识别**：纯中文 + "X与Y" 对举 + 古典叙事词 → 判为连环画（覆盖名单外的历史轶事，如"看石崇与王恺争豪"）；带 `_MODERN_BLOCKLIST` 排除现代商战题眼（"华为与腾讯的竞争" 不再被"争"字误判）
   - 同步补齐 `RECOMMEND_TEMPLATE_MATRIX` 缺失的 **武侠 / 宏大** 两类 key（原先只有风格矩阵有，模板掉进兜底拿到 e）
   - 应用到：`scripts/core/prompts.py` `_SIGNAL_TABLE` + `recommend_style()` + `recommend_template()`

2. **【P1】LLM 调用无 timeout，会无限挂死** —— `OpenAI(...)` 客户端没传 `timeout`/`max_retries`，卡住时对话里表现为"跑着跑着没动静"，无法区分在跑还是在死（实测挂 90s 无输出只能手动 kill）。
   - 修复：`LLM_TIMEOUT = 180.0` + `LLM_MAX_RETRIES = 1`；超时后由 `plan_storyboard` 捕获并降级 mock，不再挂死
   - 应用到：`scripts/core/planner.py`

3. **【P1】`num_pages` 在真 LLM 路径被丢弃** —— `plan_storyboard` 调 `_call_llm_storyboard()` 时漏传 `num_pages`，用户显式指定的页数被静默忽略（只有 mock 路径认）。
   - 修复：补传 `num_pages=num_pages`

4. **【P1】mock 路径忽略 `num_pages`** —— 原 docstring 写"仅作 informational"，实测 `num_pages=6` 只产出 5 页。
   - 修复：按 `target_pages` 补齐/截断（保留开场 + 结尾金句），并重排页码保证连续

5. **【P1】mock 历史风格画出现代科学家** —— `mock_storyboard` 只有 `cn_xuanfeng` 分支，其余风格一律套"戴眼镜现代科学家"，降级后连环画里站着个现代人。
   - 修复：为 `chinese_lianhuanhua_classic` / `guochao_manhua` 补专属锚点

6. **【P1】跑图失败写 0 字节 PNG 占位** —— 0 字节文件仍匹配 `pages/*.png` → 被 `_current_images()` 收进列表 → render 塞进 HTML → publish 上传时被 WeChat 拒掉（但前面 N-1 张已传，素材库留垃圾）。`step_preflight` 只查 >2MB 上限，**拦不住 0 字节**。
   - 修复：失败改为删占位 + 记入 `failed` 列表，最终抛异常暴露（附可重试命令）；`step_preflight` 新增 `image_empty` 检查项
   - 应用到：`scripts/core/image_gen.py` `generate_pages()`、`scripts/run.py` `step_preflight()`

7. **【P2】`step_rewrite_visual` 返回错页** —— `step_gen_images(regenerate_pages=[N])` 返回的是**全部页面**有序列表，原 `return paths[0]` 把 p1 当成"重画 p10 的结果"返回。
   - 修复：按页码匹配返回

**其它清理**：
- `CHARACTER_LOCK_COMPACT` → `CHARACTER_LOCK_COMPACT_LEGACY`，主路径改为从 `storyboard.characters[].visual_signature` 动态派生（原先硬编码郭子仪/药葛罗/仆固怀恩三条，换项目静默失效）
- `config.py` 硬编码 `D:/minimax-agent_cn-project/...` 绝对路径 → 改由 `KNOWLEDGE_COMIC_DEV_ENV` 环境变量驱动
- 删除死代码：`_CHARACTER_STORY_KEYWORDS`、`publisher._post_json_no_ascii_escape`（零引用）

**工程整理**：
- 新增 `scripts/tests/` 收编 3 个正式测试（`test_smoke_v029` / `test_gender_v030` / `test_regression_v032`），全部改为**路径自解析**，任意目录可运行
- 70 个一次性调试脚本（`_v30_*` / `_fix_kc_zhangxun` / `_test_gender*` 等）移入 `_archive/`，**保留可回溯但不再进版本库**
- `.gitignore` 补 `_*_*.py` + `_*.py` + `_archive/`，并显式放行 `scripts/check_alignment.py`（该文件自 v0.2.6 起就被 `run.py` 直接 import，却一直未入库）
- 同步开发源 `src/core/`（5 个文件），消除双份漂移
- SKILL.md 版本号三处对齐（原 frontmatter 0.3.0 / 标题 0.3.0 / 文件结构 0.2.4 三处不一）

**验证**：三个测试从 skill 根目录和 `C:\` 各跑一轮全部通过；`guide.py "张巡守睢阳"` 正确输出 `chinese_lianhuanhua_classic` + `c`

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
[5] ★ step_layout_preview(job_id) → html_path ★【生图前的排版预览】
    真实模板 + 占位图，渲染出完整版面：标题/章节题/正文/朱砂红高亮/对话引文/收束
    → Mavis 用 deliver-assets 送 html（或 Browser 打开）+ 报摘要（正文平均字数/关键词数）
    → Mavis 用 ask_user 让用户拍板排版（OK 去生图 / 换模板 / 改文案 / 重跑分镜）
    (可选) step_layout_preview(job_id, compare_templates=["c","e"]) 多模板对比
    (可选) step_review_storyboard(job_id) 出"哪几页不合格"的体检报告（辅助，非主角）
    (可选) review.set_page_field(job_id, page, field, value) 改字段后重看预览
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
| **chinese_lianhuanhua_classic** | **中国古典连环画（戴敦邦派体裁 + 中性脸 v0.3.0 + 性别分支）** ★ 历史典故第一推荐 | 工笔重彩 + 白描红线 + 水墨淡彩连环画派 | **历史典故 / 古典小说插图 / 圣贤帝王 / 江湖侠义** | 宣纸 + 毛笔 + 工笔 + 白描 + 飞白 + 朱砂勾线 + 工笔重彩（朱砂/靛青/赭石/墨/留白）+ **中性脸 v0.3.0**（FACE 子块：鹅蛋脸/精致五官/自然肤色）+ **性别分支按 [GENDER:xx] 自动选妆发**：女性 = 桃花腮 + 花钿 + 步摇簪花 + 柳叶眉 + 樱桃小口；男性 = 玉冠/幞头/束发 + 直眉/剑眉 + 无桃花腮 + 玉簪/金簪 + 朝代配饰 + 短须或无须。**planner 必须每页 visual 第二行写 [GENDER:male\|female\|mixed] tag**。要纯古典戴敦邦派脸可显式传 `character_anchor=CHARACTER_CN_LIANHUANHUA_ANCESTOR` 覆盖。 |

**历史典故类第一推荐：`chinese_lianhuanhua_classic`**（2026-09-21 校准，戴敦邦派连环画 + 2026-09-23 校准，现代审美脸）。备选按顺序：`guochao_manhua`（现代国潮条漫）→ `cn_xuanfeng`（传统水墨写意）。
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
    characters=[               # v0.2.5 人物故事必填（其它类型 None）
        # {"name": "卡尼曼", "role": "心理学家",
        #  "visual_signature": "70 岁学者, 圆框眼镜, 短发, 灰色西装, 白衬衫, 沉静表情"}
    ],
)

image_paths = step_gen_images(job_id)  # 全跑。v0.2.5: 如果 step_plan 传了 characters，会先跑角色 4 视图参考图 + 用 i2i 跑每页
# 或：image_paths = step_gen_images(job_id, regenerate_pages=[10, 11])  # 只重画
# 或：image_paths = step_gen_images(job_id, auto_char_refs=False)  # 跳过角色参考（用纯 t2i 跑）

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
├── SKILL.md                  ← 你正在读的（v0.3.3）
├── references/
│   ├── handraw_styles.md     ← 5 个锁定风格完整定义 + 推荐矩阵
│   ├── templates.md          ← 3 个排版模板详情 + 配色对照
│   ├── user-review.md        ← Mavis 对话流 + 分镜意图 vs 实际画面对照表模板
│   ├── workflow.md           ← 端到端流程图 + 调试指南
│   └── style_guide.md        ← 文章内容评分维度（深度/一致性/作者风格 100 分制）
├── scripts/
│   ├── run.py                ← 主入口：4 个 step_* API + CLI 兼容
│   ├── canon.py              ← 一致性检查工具（术语/数字/视觉锚点）
│   ├── check_alignment.py    ← 视觉文字对齐审查（step_gen_images 自动跑）
│   ├── image_review.py       ← 图片 rerender 标记工具
│   ├── publish_existing.py   ← 重发草稿（图片复用）
│   ├── tests/                ← 正式测试（v0.3.2 新增，全部不烧 API 额度）
│   │   ├── test_smoke_v029.py      ← v0.2.9 默认值 + keywords 字段
│   │   ├── test_gender_v030.py     ← v0.3.0 性别分支 8 项
│   │   └── test_regression_v032.py ← v0.3.2 修复回归 22 项
│   └── core/                 ← 核心模块（planner/image_gen/article/publisher/prompts/config）
├── _archive/                 ← 一次性调试脚本归档（不进版本库）
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

## v0.2.6 核心变化（2026-09-22，视觉文字对齐 + 风格/人物一致性再加固）

1. **视觉文字对齐审查自动跑**（v0.2.5 漏的：planner visual 写"单骑闯营"但图里两人都在马上）
   - 新增 `scripts/check_alignment.py`：检查 caption + body 里的关键人物 / 动作是否在 visual 描述里被提及
   - `step_gen_images` 跑完自动调，HIGH/MEDIUM 风险页打印到日志
   - Mavis 必读审查输出，复审对应页

2. **build_image_prompt 自动剥 cinematic 词**（v0.2.5 漏的：planner LLM 在 visual 里写 "Wide shot (35mm, low angle, deep focus)"）
   - 中国画风格时自动 strip + 替换（wide shot → Expansive composition）
   - 未来跑 chinese_lianhuanhua_classic / cn_xuanfeng / guochao_manhua **永远**不会被 cinematic 镜头术语覆盖

3. **step_plan 自动检测人物故事 + 强制 i2i**（v0.2.5 漏的：用户没传 characters 时 planner LLM 可能漏提取）
   - `_is_character_story()` 启发式检测 topic（已知历史人物名 + 典故/故事/生平关键词）
   - 检测到人物故事但 LLM 没提取 characters → 打印 WARNING
   - 未来 run 时只会出现 2 种结果：i2i 启用 + warning

## v0.2.5 核心变化（2026-09-22，中国画风格分流 + 人物一致性 i2i）

1. **中国画风格分流到专属 booster**（根上解决"风格跑偏到现代写实"）
   - `chinese_lianhuanhua_classic` / `cn_xuanfeng` / `guochao_manhua` 三个中国画风格自动用 `CHINESE_PAINTING_BOOST`（散点透视/留白/平面色块/白描+朱砂勾线），跳过 `CAMERA_LANGUAGE_KIT` + `DEPTH_LAYERS_BOOST` + `CINEMATIC_FRAMEWORK_BOOST` 三套西方镜头语言 booster
   - prompt 头部加 `STRICT STYLE` 强约束（painted illustration on rice paper）
   - 影响：未来跑这 3 个风格不会再被 cinematic 拉偏到油画/电影截图/3D 渲染

2. **人物故事 i2i 接入**（根上解决"角色换脸"）
   - 借鉴 baoyu-comic v3.0 模式：planner 提取 characters → 自动跑 4 视图参考图（front/3-4/side/back）→ 每页 i2i 跑
   - Agnes i2i API: `agnes-image-2.0-flash` + `tags=["img2img"]` + `extra_body.image` (data: URI)
   - Agnes 硬限制：最多 6 张 input images → 自动按 front > 3-4 > side > back 优先级截断
   - 用户怎么用：`step_plan(..., characters=[{name, role, visual_signature}, ...])` 或不传（planner LLM 自动提取）

3. **代码改动文件**
   - `scripts/core/prompts.py`：新增 `CHINESE_PAINTING_BOOST` + `CHINESE_STYLE_PREFIX` + `TRADITIONAL_CN_STYLES` + `build_image_prompt` 分流
   - `scripts/core/image_gen.py`：重写 `_call_agnes` 支持 i2i，新增 `generate_character_references()`，`generate_pages` 接受 character_refs
   - `scripts/core/planner.py`：`Storyboard.characters` 字段 + LLM 输出格式加 `characters` 数组
   - `scripts/run.py`：`step_plan` 接受 `characters`，`step_gen_images` 默认 `auto_char_refs=True` 跑角色图 + i2i

## v0.2.9 核心变化（2026-09-23，正文精简 + 关键词高亮 + 多人物连环画 + 现代审美脸默认）

用户多次反馈后沉淀的默认约定（未来直接实现，不需用户重复调整）：

1. **正文长度：100-150 字/页硬上限**
   - 之前：planner 写 ≥80 字 → 实际输出 200-300 字/页（用户嫌"文字太重"）
   - 现在：planner system prompt 严格"100-150 字" + 强调"图为主、文字为脚注，只补画面没说的事"
   - 应用到 `scripts/core/planner.py` 第 4 铁律 + JSON schema

2. **关键词朱砂红高亮（per-page keywords）**
   - 之前：`_HIGHLIGHT_KEYWORDS` 全局列表硬编码（张巡守睢阳人名），其它项目高亮不到
   - 现在：`StoryPage.keywords: list[str]` 字段（每页 5-8 个），c 模板自动渲染 `<span style="color:#9b2332;font-weight:600;">{kw}</span>`
   - 改名：`CHARACTER_CN_LIANHUANHUA_ANCESTOR`（古典戴敦邦脸）保留；要纯古典脸可显式传 `character_anchor=CHARACTER_CN_LIANHUANHUA_ANCESTOR` 覆盖
   - 应用到：`scripts/core/planner.py` StoryPage 字段 + JSON schema、`scripts/core/article.py::_highlight_keywords` 接 `extra_keywords` 参数、`scripts/core/prompts.py` 新增 `CHARACTER_CN_LIANHUANHUA_MODERN` 默认锚点

3. **连环画多人物铁律**
   - 之前：planner 写"1 主角 + 1-2 次要人物"，模型跑出"主角 + 琵琶乐师 + 匈奴人"等套话场景
   - 现在：连环画风格默认每页 **3+ 主人物 + 2-3 远景配角 + 多道具 + 满画幅构图**（戴敦邦/顾炳鑫/贺友直派）
   - 应用到：`scripts/core/planner.py` 新增"连环画多人物铁律"段落

4. **chinese_lianhuanhua_classic 默认 = 戴敦邦体裁 + 现代审美脸**
   - 之前：默认是 `CHARACTER_CN_LIANHUANHUA_ANCESTOR`（方颌丹凤眼剑眉朝代蓄须）→ 太古典
   - 现在：默认是 `CHARACTER_CN_LIANHUANHUA_MODERN`（桃花腮 + 花钿 + 步摇簪花 + 柳叶眉 + 樱桃小口）→ 现代读者也能欣赏的古典美人
   - 应用到：`scripts/core/prompts.py` `CHARACTER_ANCHORS["chinese_lianhuanhua_classic"]`

## v0.3.0 核心变化（2026-09-24，性别分支 + 角色一致性 + 画面 caption 匹配 + 零文字强化）

**根因**：用户连续 3 次反馈"男主角被画成女子 + 画面和文字不符 + 摄像机偏少连环画要求" → 已知用户反复要求,**未来不会再出别的漫画时搞错**。

1. **性别分支（chinese_lianhuanhua_classic 专用）—— 防止男主角被性转成女子脸**
   - **根因**：v0.2.9 默认 anchor 是为女性主角优化的（桃花腮+花钿+步摇+柳叶眉+樱桃小口）。当主题是男性主角（张巡/郭子仪/文天祥），planner visual 写"Zhang Xun, 40+ male general"，anchor 强制女性化 → 模型脸部女性化 + 服饰中性 → 完全性转成女子。
   - **修复**：拆 anchor 为三部分：
     - `CHARACTER_CN_LIANHUANHUA_FACE` — 中性脸部特征（任何性别共用）
     - `CHARACTER_CN_LIANHUANHUA_GENDER_FEMALE` — 女性妆发分支（桃花腮+花钿+步摇+柳叶眉+樱桃小口）
     - `CHARACTER_CN_LIANHUANHUA_GENDER_MALE` — 男性妆发分支（玉冠/幞头/束发 + 直眉/剑眉 + 无桃花腮 + 玉簪/金簪 + 朝代配饰 + 短须或无须）
   - **planner 强制**：每页 visual 第二行必须写 `[GENDER:male|female|mixed]` tag
   - **`build_image_prompt(gender="auto")`** 自动从 `[GENDER:xx]` tag / 中文代词 / 英文代词 / 已知中国名字（Zhang Xun, Wang Zhaojun 等）检测 → 拼装对应 gender 子块
   - `CHARACTER_CN_LIANHUANHUA_ANCESTOR` 古典戴敦邦脸保留（要纯古典脸可显式传 `character_anchor=CHARACTER_CN_LIANHUANHUA_ANCESTOR` 覆盖）
   - 应用到：`scripts/core/prompts.py` 拆 anchor + `_resolve_cn_lianhuanhua_anchor()` helper + `build_image_prompt(gender=)` + `image_gen.generate_one(gender=)` + `planner.py` 性别标记铁律段

2. **角色视觉签名锁定铁律**（v0.3.0 新增）
   - **根因**：planner LLM 早期不写 [GENDER:xx] + anchor 默认女性化 → 男主角跨页被性转（p4/p6/p7/p8 张巡在不同页面分别是"白色道袍女子脸"+"明显女子"+"白色道袍女子脸"+"白色道袍女子脸"，与刚重画的 p3/p5/p9/p10 "棕色官员袍 + 蓄短须男性"不一致），读者会认为是"换了人"或"穿越了"。
   - **铁律**：同一主角在**所有页面**的核心视觉签名（服饰+面部+身体）必须保持一致。
   - 应用到：`scripts/core/planner.py` 新增"角色视觉签名锁定铁律"段

3. **画面与 caption 严格匹配铁律**（v0.3.0 新增）
   - **根因**：planner LLM 默认忽略 caption 内容直接套场景模板 → 视觉与文字脱节（caption"砍断一根指头"画面只放桌上没动作；caption"36 将尽死"画面只 2 人对峙；caption"城破火光"画面是单人大留白）。
   - **铁律**：每页 visual 的 ACTION 段必须严格包含 caption 中的核心动作/事件的具象对应物。
   - 应用到：`scripts/core/planner.py` 新增"画面与 caption 严格匹配铁律"段

4. **零文字铁律强化**（v0.3.0 升级）
   - **根因**：每次重画都发现画面会出现"可读字符"——袍上花纹被读成篆字、地图被画上汉字、玉佩上刻字。模型默认会给"中国风装饰"加字符。
   - **强化**：每页 visual 末尾必须明确写 `STRICT NO TEXT — plain fabric robes with NO characters/symbols/inscriptions, map shows ONLY abstract terrain WITHOUT any writing, armor is PLAIN unadorned, no characters on blade.`
   - 应用到：`scripts/core/planner.py` 强化"零文字铁律"段

5. **代码改动文件**
   - `scripts/core/prompts.py`：拆 `CHARACTER_CN_LIANHUANHUA_FACE` / `_GENDER_FEMALE` / `_GENDER_MALE`，加 `_resolve_cn_lianhuanhua_anchor()`，改 `build_image_prompt(gender=)`
   - `scripts/core/image_gen.py`：`generate_one(gender=)` 传给 `build_image_prompt`
   - `scripts/core/planner.py`：加 [GENDER:xx] 标记铁律 + 角色视觉签名锁定铁律 + 画面 caption 匹配铁律 + 零文字铁律强化
   - `scripts/_smoke_v03.py`：8 项验证测试（中性别分支 + 自动检测 + mixed 处理）

## 变更记录

- **0.3.3**（2026-09-28）：苏武牧羊真实端到端测试暴露 2 个 bug — 分类器增加史事动作词兜底层（覆盖名单外人名）/ 修复 keywords 在 LLM 解析层被静默丢弃（朱砂红高亮曾整条失效）
- **0.3.2**（2026-09-28）：全量代码审核修复 7 个 bug — P0 风格推荐对真实题材失效（改加权信号分类器）/ LLM 无 timeout 挂死 / num_pages 两处被丢弃 / mock 历史风格画出现代科学家 / 跑图失败写 0 字节污染下游 / step_rewrite_visual 返回错页；另整理 tests/ + 归档 70 个一次性脚本 + 同步 src/core
- **0.3.1**（2026-09-24）：`step_publish_draft` 加 `thumb_page` 参数（封面选页，不再固定用第 1 张）
- **0.3.0**（2026-09-24）：性别分支 + 角色视觉签名锁定 + 画面 caption 匹配 + 零文字强化
- **0.2.9**（2026-09-23）：正文精简 100-150 字 + 关键词高亮 + 连环画多人物铁律 + 现代审美脸默认
- **0.2.6**（2026-09-22）：视觉文字对齐审查 + cinematic 词自动剥离 + 人物故事自动检测
- **0.2.5**（2026-09-22）：中国画风格分流 + 人物一致性 i2i
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
