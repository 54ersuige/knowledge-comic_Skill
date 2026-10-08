# 质量关卡（Quality Gates）

> 这份文档是两道自动关卡的**完整判据清单**。`SKILL.md` 只写"有两道关卡、会拦什么"，
> 具体 code 与阈值查这里。
>
> **数据来源是代码，不是文档** —— 改判据必须同时改这里，否则就是新的漂移点。

## 为什么有两道关卡

```bash
# 关卡 1：生图前体检（阻塞）
python -c "from scripts.run import step_preflight_images; print(step_preflight_images('<job_id>')['report'])"

# 关卡 2：跑图后视觉审核（不阻塞）
python -c "from scripts.run import step_visual_qa; print(step_visual_qa('<job_id>')['report'])"
```

两道关卡定位不同，**不要混用**：

| | 关卡 1 `preflight` | 关卡 2 `visual_qa` |
|---|---|---|
| 时机 | 跑图**前** | 跑图**后** |
| 对象 | 输入（描述写得对不对） | 输出（图画得对不对） |
| 依据 | **确定**的规则违反 | **概率性**的 LLM 判断 |
| 处置 | 阻塞 `SystemExit(1)`，一张图都不跑 | 只打印报告，用户拍板 |
| 成本 | 0 | token + 时间 |
| 位置 | `step_gen_images` 开头，**角色参考图之前**（那里开始烧钱） | `step_gen_images` 结尾（`auto_visual_qa=True`） |

设计理由：preflight 拦的是确定错误，拦得住；LLM 视觉判断有方差，拦不住就只会变成
"狼来了"。所以关卡 2 只有高置信项才升级为 block。

## 关卡 1 · preflight 判据（22 个 code）

以 `scripts/core/preflight.py` 为准。**阻塞项一条不过就 `SystemExit(1)`，一张图都不跑。**

### 阻塞项（block，9 个）

| code | 拦什么 | 为什么是阻塞 |
|---|---|---|
| `KW_EMPTY` | `keywords` 为空 | 朱砂高亮整条链路失效 |
| `BODY_EMPTY` | 正文为空 | 页面没有内容 |
| `BODY_LONG` | 正文 > **170** 字 | 文字压过画面 |
| `HEDGING` | 「（或…）」「（实际为…）」「我不确定」 | LLM 不确定时的自我暴露，会印到成品上 |
| `GENDER_PARTIAL` | 前缀式多角色页有段漏标 `[GENDER]` | 漏标会让模型自由发挥性别 → 整批图跑偏 |
| `TEXT_INVITING` | visual 含 `calligraphy` / `inscribed` / `signboard` / `banner text` / `characters on` 等诱导词 | 模型会**真的把字画进图里**（本项目最常复发的 bug）。**注意**：裸词 `banner` 已于 v0.3.28 移出 —— 它在历史战争题材里指军旗/旌旗（实测「叛军的黑红旗帜」被误判，12 页全阻塞）；带文字的横幅由 `banner text` 覆盖 |
| `CHAR_GENDER_MISSING` | 角色没填 `gender` | v0.3.22 起阻塞，且内置人名表**不再兜底** |
| `ERA_ANACHRONISM` | 角色 `visual_signature` 含后世器物 | 春秋角色写幞头这类时代穿帮 |
| `ALIGN_HIGH` | 图文不符高风险页 | 需传入 `alignment` 才检查 |

### 建议项（warn，13 个）

只打印报告，不拦。

| code | 提示什么 |
|---|---|
| `KW_TOO_FEW` | `keywords` < 3 个，高亮撑不起来 |
| `KW_TOO_MANY` | `keywords` > 6 个，正文里碎成一片 |
| `BODY_LONG_SOFT` | 正文略超 150 字目标带 |
| `BODY_SHORT` | 正文 < 90 字，内容偏薄 |
| `MODERN_TONE` | 「极限测试」「破防」「内卷」等现代口水词 |
| `GENDER_NONE` | 无性别标记且角色未登记进 `characters[]` |
| `NAME_UNKNOWN` | 带身份头衔却不在正史表 → 疑似编造人物 |
| `RAGGED_NO_PLAIN` | 衣物写破损但无 `PLAIN unadorned` → 出字风险 |
| `NO_TEXT_MISSING` | visual 没写零文字声明（代码层已兜底） |
| `PUNCH_EMPTY` | 「定格瞬间」金句为空 |
| `PUNCH_LONG` | 金句超 22 字 |
| `QUOTE_EMPTY` | 文言引句为空 |
| `QUOTE_LONG` | 文言引句超 50 字 |

### 逃生阀

```python
step_gen_images(job_id, skip_preflight=True)   # 用户确认要硬跑时才用
```

## 阈值真源 · `scripts/core/thresholds.py`

**所有数值只在 `thresholds.py` 定义一次**，`preflight` 与 `review_page` 都 import。
不允许任何检查层自己写死字面量 —— 历史上同一份阈值被复制 2~3 份，已经漂移过一次
（`body > 150` 在 preflight 是 warn、在 review_page 是 error，同一次跑出两份矛盾结论）。

| 常量 | 值 | 含义 |
|---|---|---|
| `BODY_TARGET_LO` / `BODY_TARGET_HI` | 100 / 150 | 正文**目标带**（不是硬边界） |
| `BODY_HARD_HI` | 170 | 超过 → 阻塞 |
| `BODY_WARN_LO` | 90 | 低于 → 偏薄（warn） |
| `KEYWORDS_MIN` / `IDEAL` / `MAX` | 3 / 5 / 6 | 朱砂高亮关键词个数 |
| `PUNCH_MIN` / `PUNCH_MAX` | 10 / 22 | 「定格瞬间」金句字数 |
| `QUOTE_MIN` / `QUOTE_MAX` | 8 / 50 | 文言引句字数 |
| `VISUAL_MIN` | 300 | 画面描述太短 = 七要素没写全 |
| `MULTI_FIGURE_MIN` | 3 | 连环画单页主人物下限 |
| `CAPTION_MIN` / `CAPTION_MAX` | 10 / 20 | 画面 caption |
| `HIGHLIGHT_MIN` / `HIGHLIGHT_MAX` | 4 / 8 | 页面小标题 |

**取值原则**：用户的「100-150 字」是**目标带**，不是硬边界。preflight v0.3.15 初版把它
当硬边界，结果 93/95/154 字全被判不合格。**关卡拦"方向错"，不拦"没到理想值"** —— 这条
决定了每一档的宽严。

## 关卡 2 · visual_qa 判据（4 个 code）

以 `scripts/core/visual_qa.py` 为准。用 LLM 视觉能力逐页看图，查**只能看图才知道**的问题。

| code | 查什么 | 说明 |
|---|---|---|
| `TEXT_ON_IMAGE` | 画面里出现文字 | 本项目最常复发；**肉眼容易漏**（要放大看衣物纹样） |
| `STYLE_DRIFT` | 画风与 `style_id` 不符 | 可能漂到现代写实 / 3D / 彩绘 |
| `GENDER_WRONG` | 描述要求男性，图里唯一角色被画成女性 | **方向性**判据，不依赖人数基准 |
| `NOTE_MISMATCH` | 画面与画面意图不符 | 低置信的主观解读不算 |

### 置信门槛

| 常量 | 值 | 作用 |
|---|---|---|
| `BLOCK_CONFIDENCE` | 0.85 | ≥ 此值才升级为 block |
| `WARN_CONFIDENCE` | 0.6 | ≥ 此值才报出来 |

**为什么要有门槛**：低置信的「未体现 X 意象」是主观解读，不是可判定事实。实跑里出现过
40% 置信的纯噪声。宁可漏报也不误报 —— 误报会训练用户忽略警告。

**`PEOPLE_COUNT` 已在 v0.3.16 删除**：实跑 10 页 2/2 全是误报。根因是期望人数由
`[GENDER:xx]` 标记数推算，而 bible 式写法下这个基准本身不可靠。

### 实机验证的价值

审 `kc_1790586703` 时 LLM 对 p04 报 95% 置信 `TEXT_ON_IMAGE`，肉眼复核确认苏武破袍上
画满伪汉字 —— 用户当初只看了画风和构图，没放大看衣物。p01 干净无字、未报（无误报）。

## 能力边界（不回避）

这两道关卡**不能保证**发现：

- **语义层面的史实错误** —— 把 A 的事迹安到 B 头上、年份写错、因果搞反。preflight 只能拦
  hedging 和编造人名**结构**，语义错还得人核。
- **画风漂移** —— 图像有固有方差，即使 prompt 完全正确仍有 10-20% 漂移率，无法消除，只能检出。
- **LLM 内容质量** —— 史实、遣词、逻辑依然依赖 planner 的一次发挥。

所以流程仍然是**用户拍板制**。关卡是把"跑完才发现"变成"当场发现"，不是把用户从流程里拿掉。

## 维护规则

新增七要素段名（如 `CONCEPT:`）时，**必须同步** `_SEVEN_ELEMENT_LABELS` 与 preflight
黑名单。漏一处的后果是 `_ACTOR_LINE_RE` 把该段当成角色段 → `GENDER_PARTIAL` **永久误报
阻塞**，整条管线卡死（v0.3.18 实际踩过）。

改完跑：

```bash
python scripts/run_tests.py     # 全量测试
ruff check scripts/             # lint
```
