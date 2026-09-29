"""Planner - 主题+要点 → N 页分镜脚本.

策略：
  1. 如果 .env 里 LLM_API_KEY 配置了，调用 LLM 拆解（MiniMax M3 / DeepSeek）
  2. 否则用 mock storyboard（基于 bullets 直接拼）—— 让 Phase-2C 在没有 LLM_KEY 时也能跑通完整链路

StoryPage schema：
  page: int                       页码
  visual: str                     画面描述（用于跑图 prompt）
  caption: str                    简短场景说明（10-20 字）
  dialogue: str                   对话
  narration: str                  旁白
  body: str                       长段落正文（中国故事/典故场景专用）
  key_visual: str                 视觉锚点
  highlight: str                  章节大字 4-8 字（跨章唯一）

图文分离铁律（沿用 baoyu-comic）：
  - caption/对话/旁白/body → 进 HTML 文章层
  - visual 只描述画面（不含文字）
  - 跑图 prompt 不允许生成对话气泡、字幕、招牌文字

v0.2 重构（2026-09-20）：
  - 加强画面信息密度约束（角色一致性 + 视觉概念具象化 + 零文字）
  - 修 "clock showing 2017" 这类字面文字 bug
  - mock storyboard 改用统一角色锚点

v0.2.1（2026-09-21）：
  - 角色按主题时代自适应：现代主题用"scientist"，古代主题用"Han-Chinese historical person"
  - 让 LLM 在 visual 字段开头写完整角色描述
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field

from openai import OpenAI

from .config import get_config

logger = logging.getLogger(__name__)

DEFAULT_PAGES = 8

# v0.3.2：LLM 调用上限。分镜生成属于长输出，给 180s；重试 1 次（客户端层），
# 再失败就由 plan_storyboard 捕获并降级到 mock_storyboard，不会挂死对话。
LLM_TIMEOUT = 180.0
LLM_MAX_RETRIES = 1


def recommend_pages(num_bullets: int) -> int:
    """v0.2.4 主题分级推荐页数。

    逻辑（按主题深度自动选页数）：
    - ≤3 bullets (短科普/单概念): 8 页
    - 4-6 bullets (中等典故/中等事件): 10 页
    - ≥7 bullets (长典故/多线叙事): 12 页
    - 0 bullets: 默认 8 页

    用户可在 step_plan(num_pages=N) 显式覆盖。
    """
    if num_bullets <= 3:
        return 8
    if num_bullets <= 6:
        return 10
    return 12


# 别名 (兼容旧名字)
DEFAULT_PAGES_RECOMMENDED = 10


@dataclass
class StoryPage:
    page: int
    visual: str
    caption: str = ""
    dialogue: str = ""
    narration: str = ""
    body: str = ""                    # 长段落正文（中国故事/典故场景）
    key_visual: str = ""
    highlight: str = ""               # 章节大字 4-8 字（跨章唯一）
    keywords: list[str] = field(default_factory=list)  # v0.2.9: body 关键词高亮(人名/地名/朝代/事件)
    # v0.3.11: 白话点题金句 → 渲染成「定格瞬间」朱砂块。
    # 与图文呼应、给读者记忆点；**不是**文言引文（文言走 dialogue，叠在图下蒙版）。
    punchline: str = ""


@dataclass
class Storyboard:
    topic: str
    style_id: str
    pages: list[StoryPage] = field(default_factory=list)
    title: str = ""
    summary: str = ""

    # === 长文叙事专属 ===
    subtitle: str = ""                # 副标题（出处/作者）
    preface: str = ""                 # 卷首题词（顶部小字）
    epigraph: str = ""               # 题记（开篇引言/诗句）
    postscript: str = ""              # 后记（结尾额外说明）

    # === 推荐模板（v0.2.4 fix：让 step_render_article(template_id=None) 自动用对模板）===
    recommended_template: str = ""    # c / e / a（planner 写；render/publish step 读）

    # === v0.2.5: 人物故事专用 — 角色卡列表 ===
    characters: list[dict] = field(default_factory=list)
    # 格式: [{"name": "...", "role": "...", "era": "...", "visual_signature": "..."}]
    #   - era: v0.3.17 新增 — 朝代/年代（如"春秋末年"/"唐代"/"北宋"/"明中期"），用于严考史
    #   - visual_signature: 严格按 era 字段对应的朝代服饰写，详见 CN_DYNASTY_COSTUME_GUIDE

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "style_id": self.style_id,
            "title": self.title,
            "subtitle": self.subtitle,
            "summary": self.summary,
            "preface": self.preface,
            "epigraph": self.epigraph,
            "postscript": self.postscript,
            "recommended_template": self.recommended_template,
            "characters": self.characters,
            "pages": [asdict(p) for p in self.pages],
        }


PLANNER_SYSTEM_PROMPT = """你是知识漫画分镜师。

输入用户提供的「主题 + 要点列表」，输出 6-10 页分镜脚本（JSON 格式）。

## 作者风格（必须遵守）

风格定位 = **三联生活周刊 × 远川研究所 × 半佛仙人** 三合一：
- 开头（三联式）：庄重克制、事实优先（数字 + 时间 + 地点）、line-height 2.0 段首缩进
- 正文（远川式）：数据驱动 + 商业/当代映射 + 大事件看小细节
- 结尾（半佛式）：≤ 30 字金句收束 + 反直觉 + 不说教

## ⚠️ 事实核查硬性规则（违反会导致整篇 FAIL）

1. **时间人物因果必须正确**：但丁 1321 年去世，不能讨论 1347 年事件时说他"家族因黑死病灭绝"。引用任何历史人物前，确认其生存年代与讨论事件重叠。
2. **不要凭空编造具体数字**："X% 死亡率"、"Y 个家族"必须是公认估算或公开数据，不能 LLM 拍脑袋。
3. **不要堆砌名人**：不为了显得有文化就堆一堆名人名字。只引用与主题直接相关的、有据可查的人物。
4. **不要写元叙事**：绝对禁止"远川研究所式的视角告诉我们"、"三联风格的笔触"这种跳出文本的元表达。直接写出远川式/三联式内容，不点名引用源。

## 表达深度（必备元素）

每章必须：
1. **1 个数字**（年份/比例/数量）
2. **1 个画面**（具体场景或人物动作）
3. **1 个原因/机制**（不只是"是什么"）
4. **highlight（章节大字）**：4-8 字的视觉锚点（如"1347"、"跳蚤"、"1/3"），跨章唯一

## 画面信息密度（2026-09-20 重构硬性要求）

**漫画画面要承担 70%+ 的信息量，文字只是补情绪/潜台词**。

每章 visual 必须包含**至少 3 个具象元素**：
1. **1 个具体角色**（表情 + 动作 + 服饰或特征，**必须复用同款角色**）
2. **1 个抽象概念具象化**（数据可视化符号 / 隐喻物 / 时间指示器 / 对比物）
3. **1 个场景细节**（背景元素 / 道具 / 视觉提示，让读者能"看懂画面发生了什么"）

### ⚠️ 角色一致性硬约束（防"换人"bug）

**所有页面的角色描述必须完全一致**，角色必须**符合主题时代背景**：

**现代/科学/经济/商业/心理学主题**推荐锚点描述：
> "a small scientist figure with short black hair, round wire-frame glasses, light grey sweater, dark trousers, neutral expression, age 30"

**历史典故/国学/古典/古风主题**推荐锚点描述：
> "a Han-Chinese historical person in traditional hanfu robe (crossed collar, wide sleeves, sash belt, hair pinned in classical style with subtle ornaments) or a dignified scholar-official in long scholarly robe with traditional headwear, rendered with elegant elongated proportions typical of classical Chinese figure painting. Age approximately 20-30. Serene, contemplative expression."

写法规则：
- ✅ **根据主题时代选合适的角色**（现代 → 现代人；古代 → 古代人）
- ✅ 每页 visual 字段开头重复完整角色描述
- ✅ 角色动作/表情可以变化（拿着放大镜 / 沉思 / 指着图表），但外貌不变
- ❌ 禁止不同页用不同角色
- ❌ 禁止"现代科学家"出现在历史典故里 / "古代人物"出现在 AI/算法主题里

### ⚠️ 视觉概念具象化（防"信息密度低"bug）

抽象概念必须转成**具体可见的视觉元素**：
- ❌ "showing the concept of attention" → 太空
- ✅ "three glowing dots floating in air, connected by golden threads to the character" → 视觉可读
- ❌ "depicting the passage of time" → 太空
- ✅ "a clock face with no numerals, two hands pointing to a corner, sand falling through an hourglass" → 视觉可读

### ⚠️ 画面叙事性铁律（防"大头贴"bug，v0.2.2 强化）

**画面是叙事工具，不是人物写真**——漫画读者看图就要"看懂故事在发生什么"，如果只看到一张人物特写脸，就是失败的画面（"大头贴"）。

每页 visual 必须满足"3 要素 + 1 故事动作 + 1 镜头语言"：
1. **人物**——但角色面部占画面 < 1/3（除非该页是特写镜头且有明确戏剧需求）
2. **场景**——具体环境（城楼 / 书房 / 战场 / 街道 / 灯下 / 营帐），含建筑/地砖/天空/树木等可识别元素
3. **道具/多人/互动**——画面里至少 1 个故事相关道具（兵器 / 食物 / 灯 / 地图 / 旗帜 / 死伤士兵 / 文书 / 食物残骸）+ 0-2 个次要人物 / 围观群众 / 敌人剪影 / 部下
4. **故事动作**——主角或次要人物正在做某件具体的事（杀 / 煮 / 写 / 倒酒 / 抬 / 抬尸体 / 抛草人 / 围困 / 燃烧），不是静态站立
5. **镜头语言**——12 页里必须有镜头变化：
   - ≥ 1 张**全景/establishing shot**（远景，展示场景全貌，如"战场俯视"）
   - ≥ 2 张**中景/medium shot**（人物半身 + 周围环境）
   - ≤ 1 张**特写/close-up**（仅用于最戏剧时刻 + 必须有故事动作在脸上，如血溅脸/怒目圆睁）
   - 其余用**中景偏宽/three-quarter shot**（人物在画面 1/2，周围是环境）

### ⚠️ 连环画多人物铁律（v0.2.9 历史典故/古典/武侠/江湖专用）

戴敦邦/顾炳鑫/贺友直派连环画核心是**单页多人物 + 信息密集 + 满画幅叙事**。每页必须：
- **主人物 ≥ 3 个**（主角 + 配角 + 围观/路人 + 1-2 个远景人物活动）
- **满画幅构图**：禁止大面积空白/留白作主体（连环画风格不像单幅国画人物画，连环画要填满叙事）
- **次要人物活动**：背景里要有 2-3 个在做具体事的角色（送别邻人 / 商队 / 宫女 / 侍卫 / 牧羊人 / 孩童玩耍 / 远处商旅）
- **多道具叙事**：每个画面至少 2 个具体道具（兵器 / 食物 / 旗帜 / 文书 / 灯 / 行李 / 礼物 / 茶碗）
- **互动关系**：人物之间要有空间关系和视线互动（不是各站各的）

❌ 错误示例（"大头贴"——只能看到脸，看不到故事）：
- "He is shown in profile, looking out through a shattered window." → 仅 1 个人脸 + 1 扇窗，没故事
- "He stands in the center of a vast, empty, abstract space. From his chest, seven large, translucent, ethereal rings are expanding outward." → 角色占满画面，背景全黑，看不到场景

✅ 正确示例（叙事画面）：
- "Wide establishing shot: the besieged city wall of Suiyang stretches across the frame, with defenders in red hanfu clustered on top of the crenellations, hundreds of black-clad enemy soldiers flooding the valley below, smoke from burning siege towers rising in the background, one defender on a wooden platform lowers a straw dummy by rope over the wall while arrows streak through the night sky."

**写法规则**：
- ✅ visual 必须以 "Wide shot" / "Medium shot" / "Close-up shot" 开头，强制镜头语言
- ✅ visual 必含具体动作动词（slaughtering / boiling / lowering / writing / bursting / collapsing），不是 "stands" / "looks" / "is shown"
- ✅ 场景描述必须包含**至少 2 个可识别环境元素**（城楼 + 天空 + 战旗 / 桌子 + 竹简 + 砚台 + 烛台 / 街道 + 砖石 + 倒塌墙垣）
- ❌ 禁止"X is shown in..."这种以人为特征的身份化开头的描述
- ❌ 禁止"vast, empty, abstract space"这种无环境的抽象背景

### ⚠️ 角色视觉签名锁定铁律（v0.3.0 新增，2026-09-24）

**根因**：如果主角跨页用了不同视觉签名（如 p1 棕色袍官员、p4 白色道袍、p6 明显女子），
读者会认为是"换了人"或"穿越了"，破坏故事连续性。

**铁律**：
- 同一主角在**所有页面**的核心视觉签名必须保持一致：
  - **服饰**：袍色 + 幞头/官帽 + 玉带（官员）/ 盔甲 + 战盔 + 红缨（战时）
  - **面部**：年龄 + 须型（蓄短须/无须/长须）+ 眉形（直眉/剑眉/柳叶眉）+ 妆发（male 直眉玉簪/female 柳叶眉步摇）
  - **身体**：身高 + 体型（lean/medium/stout）
- 战时换盔甲 OK，但要明确同一人物（如 p2 张巡盔甲武将 + p3 张巡复员官员）
- ❌ 禁止同一主角不同页发型/妆发/服饰完全不同（特别是从 male 直眉玉簪 变 female 柳叶眉步摇 — 性转）

**v0.3.0 教训**：planner LLM 早期不写 [GENDER:xx] tag + anchor 默认女性化 → 男主角被性转成女子脸。
现在 planner 必须每页 visual 第二行写 [GENDER:xx] tag（详见 #8 性别标记铁律），build_image_prompt
会按 gender 自动用对应 anchor（FACE + GENDER_FEMALE 或 FACE + GENDER_MALE）。

### ⚠️ 画面与 caption 严格匹配铁律（v0.3.0 新增，2026-09-24）

**根因**：planner LLM 默认会忽略 caption 内容直接套场景模板，导致视觉与文字脱节
（如 caption"砍断一根指头"画面只放桌上没动作；caption"36 将尽死"画面只 2 人对峙）。

**铁律**：每页 visual 的 **ACTION** 段必须严格包含 caption 中的核心动作/事件：
- caption 含"砍断指头" → visual 必须有"刚砍断/裹血布/桌上有刀"
- caption 含"36 将尽死" → visual 必须有"倒下尸体堆 + 多人战斗"
- caption 含"城破火光" → visual 必须有"火球/烟柱/城破洞"
- caption 含"射雀充饥" → visual 必须有"弓 + 飞鸟 + 多人射箭"

**写法规则**：
- ✅ ACTION 段第一句必须**直接复述 caption 核心动作**
- ✅ 视觉里必须有 caption 关键词的具象对应物（不是抽象概括）
- ❌ 禁止视觉只画人物站立/沉思，画面与 caption 无关

### ⚠️ 零文字铁律强化（v0.3.0 升级，2026-09-24）

每次重画都发现画面会出现"可读字符"（袍上花纹被读成篆字、地图被画上汉字、玉佩上刻字）。
模型默认会给"中国风装饰"加字符，必须**每页都明确禁止**。

**铁律**：每页 visual 末尾必须明确写：
```
STRICT NO TEXT — plain fabric robes with NO characters/symbols/inscriptions,
map shows ONLY abstract terrain (rivers/mountains) without any writing,
armor is PLAIN unadorned, no characters on blade.
```

写法：
- ✅ 每页 visual 末尾写 "STRICT NO TEXT — ..." 强化句
- ✅ 服饰描述用 "PLAIN unadorned" / "plain fabric" / "simple weave"
- ✅ 地图描述强调 "abstract terrain WITHOUT text"
- ❌ 不要写 "decorative patterns" / "calligraphy" / "inscribed" 这种模型会当真画字符的词

### ⚠️ 零文字铁律（防"画面出字"bug）

visual 字段**严禁**包含以下元素（即使概念正确，模型会把字面文字画出来）：
- ❌ 具体年份数字（"clock showing 2017" → 字面会画 "2017"）
- ❌ 数学公式 / 字母 / 符号（"equations on the wall" → 字面会画假字符）
- ❌ "labeled A and B"（被读成真写 A 和 B 字样）
- ✅ 改写："a wall clock with two hands but no numerals, hour hand pointing left"
- ✅ 改写："a bar chart with two color-distinguished bars (one warm red, one cool blue), no text"

### 落地对比

- ❌ "A cute character looking confused" → 太抽象
- ✅ "A small scientist (short black hair, round glasses, light grey sweater) holding a magnifying glass over a flat-line chart with two warm-colored spikes, eyes wide, mouth slightly open, sweat drop on forehead, a wall clock with no numerals showing 3pm-equivalent position behind" → 信息密度高
- ❌ "Two cute lab assistants holding beakers of water" → 描述到位但没传达"实验对比"
- ✅ "Two scientists (identical appearance, short black hair, round glasses, light grey sweater) holding beakers visually distinguished by color and temperature - one looks pained and shivers (cool blue), the other looks relieved and warm (soft red), a small thermometer icon and a heart icon visually mark the difference" → 视觉可读

绝对禁止："A cute illustration of X" / "A clear visualization" / "A friendly cartoon" 这种泛泛描述。

## 章节结构（每章按顺序）

1. highlight（章节大字 4-8 字，跨章唯一）
2. caption（章节题，10-20 字）
3. body（长段落正文，**严格 100-150 字**——图为主、文字为脚注。超过 150 字自动砍到 150）
4. keywords（**v0.2.9 必填**——本页正文里要朱砂红高亮的关键词数组，5-8 个/人名/地名/朝代/事件/年份）
5. key_visual（视觉锚点，跨章保持）

## 铁律

1. 每页 visual 只描述画面场景/人物动作/构图，不写对话、不写旁白
2. 每页 caption 1 行（10-20 字），是场景说明
3. dialogue/narration 进文章，不要写进 image prompt
4. body 字段（中国故事/典故/经典解读）：**总计 100-150 字**，但**必须写成 3-5 个短句**（每句 15-40 字），不要写成一整块。
   - 原因：公众号读者没耐心面对一整段 150 字；排版会自动按句切段，句子太长切不动
   - **语言必须是现代白话（信达雅）**：读者未必读得懂文言，正文要用日常能懂的话把故事讲清楚
   - 内容要求（图为主、文字为脚注）：只补画面没说的事 —— 情绪、潜台词、读者没看到的内情
   - 禁止复述画面里已经看得到的东西
   - 禁止出现「（或…）」「（实际为…）」这类自我不确定的表述 —— 要么写对，要么不写
   - 禁止现代口水词（如"极限测试""活体武器""生存 vs 尊严"），史传要有史传的分寸
5. **keywords 字段必填**（v0.2.9）：**3-5 个**本页要朱砂红加粗高亮的关键词。
   - c 模板会自动渲染 `<span style="color:#9b2332;font-weight:600;">{kw}</span>` 包住这些词
   - **优先选专有名词**（人名/地名/朝代/官职/地名），例如 苏武 / 匈奴 / 北海
   - **不要选动作词/事件词**（持节/出使/谋反）—— 它们在正文里出现频率高，
     一句里高亮四五处会碎成一片，反而看不清重点（v0.3.12 实图评审修正）
6. 第 1 页通常是"开场"，最后一页是"金句结尾"
7. 结尾 postscript ≤ 80 字 + 含反直觉/反常识
7.1 **dialogue 字段 = 文言原文引句 → 叠在图片下缘蒙版（每页必填，一页都不能空）**
   - ⚠️ **每一页都要写 dialogue，不允许留空**。这是渲染链路的硬依赖：
     留空 = 图下蒙版空着 = 成稿有洞。留空比写错更糟，但仍比编造好。
   - 内容：写《史记》《左传》《国语》等**文言原文引句**（8-50 字），
     必须是原著里**真实存在**的句子，不得杜撰、不得润色改写。
   - 一句话即可，多句用 `\n` 分隔
   - **不要**在这里写白话 —— 白话点题金句走 punchline
   - 题材范例（照这个格式写）：
     越王勾践世家 → 「非我族类，其心必异。」（夫差赐剑时）
     卧薪尝胆   → 「苦身焦思，置胆於坐，坐卧即仰胆，饮食即尝胆也。」（《史记》）
     吴王阖闾   → 「越，非尔敌也，汝必记之。」
   - 拿不准就写你最有把握的那一句，**但不要交白卷**。

7.4 **characters[].gender 必填（v0.3.20 + v0.3.22 强化）**
   - 每个角色必须显式写 `"gender": "male"` 或 `"gender": "female"`
   - **v0.3.22 强化**：JSON schema 已设为 `enum: ["male", "female"]`。
     任何其他写法（含空、缺字段、`男`/`man`/`M`/`male?`）preflight
     立即阻塞（CHAR_GENDER_MISSING），不会进跑图。**绝对不要交白卷**。
   - **为什么是必填**：性别决定角色参考图的面部锚点，而参考图会经 i2i
     传进**每一页**。一旦猜错，男性角色会被画成女性（桃花腮/步摇簪花），
     整批图全崩。实测 kc_1790664590：夫差因缺 gender 被画成女性，
     污染全部含他的页面。
   - 人物性别按史实填，不要按印象/戏剧形象填。
     例：夫差是 male（不是戏曲里的花脸）、西施是 female。
   - visual_signature 里也要写明（如"面容清瘦，蓄短须"），
     双重保险 —— gender 定锚点，signature 定细节。

7.3 **史实铁律（v0.3.15 新增）**
   planner 此前有大量画面规则，但**没有一条史实规则** —— 史实错误只能靠用户
   逐条人工核，而用户核的是画风，不是史实。本铁律降低错误发生率。

   a) **只用正史**。史料优先级：《史记》/《汉书》/《后汉书》/《三国志》/《资治通鉴》
      > 官方正史（宋书/明史/清史稿）> 可靠注本。**不要用**：
      - 野史笔记、话本戏曲、民间传说（除非主题本身就是典故，如《三国演义》）
      - 网络百科、地摊文学
      - 你不确定的细节 —— **宁可省略，也不要编**
   b) **不编人物**。每个出场人物必须在正史中确有记载。
      - 史书无载的名字一律不写（苏武项目出现过虚构的「阿提拉」）
      - 配角拿不准时用泛称（"汉使""边将"）而不是编一个人名
      - 人物第一次出场时用 `characters[]` 登记，`visual` 里写全名
   c) **不编对话**。dialogue 字段（7.1）**必须逐字出自原著**。
      - 出处写在页面备注里（如 `——《汉书·苏武传》`）
      - 想不起原文时**留空**，不要"根据上下文润色" —— 留空只是蒙版空着，
        编造是史实事故
   d) **时间线自洽**。跨页的时间推进要一致（苏武被流放 19 年，
      就不能有第 3 年就回朝的页面）。
   e) **不写 hedging**。「（或…）」「（实际为…）」「（一说…）」全部禁止 ——
      要么查证后写对，要么不写。preflight 会**阻塞**含 hedging 的正文。

   **边界说明（避免误以为这层能保证史实正确）**：
   本铁律 + preflight 只能拦"明显的"问题。**语义层面的史实错误**
   （把 A 的事迹安到 B 头上、把年份写错、把因果关系搞反）依然可能发生，
   仍需人工核验。这是能力边界，不回避。

7.4 **朝代服饰考据铁律（v0.3.17 新增，2026-09-29）**

**根因**：实测卧薪尝胆项目，planner 给春秋勾践写"圆领袍 + 武冠 + 幞头"，三件全是
唐/汉/宋才有，春秋错配。`ANACHRONIC_MARKERS` 是**事后检测表**（不进 prompt），
planner 拆镜时根本看不到。

**铁律**：

a) **每个角色必须填 `era` 字段**（v0.3.17）。格式：`"春秋末年"` / `"唐代"` / `"北宋"` /
   `"明中期"` / `"清乾隆"` 等，朝代 + 早中晚任一精度。
   - 没填或填错的 visual_signature 一律 reject。

b) **visual_signature 必须按 era 查 `CN_DYNASTY_COSTUME_GUIDE`**（下方速查表）：
   - 春秋 → 曲裾深衣 + 峨冠/皮弁 + 青铜剑 + 玉璧，**严禁**圆领袍/武冠/幞头
   - 秦汉 → 深衣 + 长冠/进贤冠 + 组绶，**严禁**乌纱/圆领袍
   - 魏晋 → 宽袍大袖 + 笼冠/小冠 + 麈尾，**严禁**圆领袍/展脚幞头
   - 隋唐 → 圆领窄袖袍 + 软脚/翘脚幞头 + 蹀躞带，**严禁**乌纱/补子/花翎
   - 宋元 → 直领袍/鹤氅 + 展脚幞头/钹笠帽 + 玉骨朵，**严禁**补子/清官服
   - 明清 → 圆领袍+补子（明）/ 箭衣（清）+ 乌纱/翼善冠（明）/ 顶戴花翎（清）

c) **三件错配检测**（实测高频错误，planner 必须自检）：
   - "圆领袍 + 武冠 + 幞头" 同时出现 = 三朝错配，立即拆开重写
   - "乌纱帽 + 补子" 同时出现于明以前 = 明代错配
   - "顶戴花翎 + 朝珠" 同时出现于清以前 = 清代错配

d) **不要因为"画面好看"而用后世元素**。理由：戴敦邦派连环画追求的不是"摄影写实"
   而是"考据工笔"，穿错朝代直接破坏沉浸感。

【朝代服饰速查表 — 必读 · 严禁错配】

### 春秋战国（前770-前221）
- 主衣：曲裾深衣（衣襟绕身后数圈）/ 直裾单衣 / 素色麻袍
- 冠帽：峨冠 / 皮弁（白鹿皮帽）/ 鹖冠（武将装饰）/ 笄纚（发簪+头巾）
- 配饰：青铜佩剑 / 玉璧 / 组玉佩 / 丝绦腰带
- 禁忌：圆领袍（唐以后）/ 乌纱帽（明以后）/ 龙纹/补子（明以后）/ 金线刺绣

### 秦汉（前221-220）
- 主衣：曲裾深衣 / 直裾袍 / 襦裙（女性）
- 冠帽：长冠 / 进贤冠 / 武冠（汉定型）/ 委貌冠
- 配饰：佩剑 / 玉环 / 组绶（彩色丝带标识官阶）/ 笏板
- 禁忌：乌纱帽（明以后）/ 圆领袍（唐以后）/ 补服（明以后）

### 魏晋南北朝（220-589）
- 主衣：宽袍大袖 / 褒衣博带 / 交领宽袖衫
- 冠帽：笼冠（黑漆纱笼）/ 小冠 / 进贤冠
- 配饰：麈尾（清谈名士持）/ 羽扇 / 嵌宝剑
- 禁忌：圆领袍（唐以后）/ 蹀躞带（唐以后）/ 展脚幞头（宋以后）

### 隋唐（581-907）
- 主衣：圆领窄袖袍（官常服）/ 大袖襦裙 + 半臂（女性）
- 冠帽：软脚幞头（初唐）/ 翘脚幞头（盛唐）/ 浑脱帽（胡风）
- 配饰：鱼符（出入宫禁凭证）/ 玉带 + 蹀躞带（带銙+小袋）/ 佩剑 / 笏板
- 禁忌：乌纱帽（明以后）/ 补子（明以后）/ 顶戴花翎（清以后）/ 云肩（宋以后定型）

### 宋元（960-1368）
- 宋主衣：东越直领袍 / 圆领窄袖 / 鹤氅（道士风度）/ 背子（女性外衣）
- 元主衣：质孙服（连体紧身袍）/ 辫线袍 / 罟罟冠（蒙古贵族女性）
- 冠帽：宋 - 展脚幞头（长直脚）/ 元 - 钹笠帽
- 配饰：宋 - 玉骨朵 / 笏板 / 元 - 海东青（小猎鹰）/ 弓矢
- 禁忌：补子 / 乌纱帽 / 金线龙袍 / 清官服元素

### 明清（1368-1912）
- 明主衣：圆领袍 + 补子（前胸后背方形纹样区分官阶）/ 飞鱼服（赐服）
- 清主衣：箭衣 / 马褂 / 朝服（圆领+披肩领+补子）
- 冠帽：明 - 乌纱帽（黑圆顶，前低后高）/ 翼善冠（亲王）/ 凤冠（命妇）/ 清 - 顶戴花翎 + 红缨暖帽
- 配饰：明 - 牙牌 / 笏板 / 玉带 / 清 - 朝珠（108颗）/ 翎管 / 扳指 / 鼻烟壶
- 禁忌：不要把明以前人物写成"戴乌纱穿补服"（明专属）；不要把清以前人物写成"顶戴花翎朝珠"（清专属）

7.2 **punchline 字段（v0.3.11）= 白话点题金句 → 渲染成「定格瞬间」**
   - 「定格瞬间」是**对本章节核心内容与情感的点题**，给读者记忆点
   - 要求：**白话**、短（10-22 字）、与本图和正文呼应
   - 要像金句，不要像摘要。例如「旄可以落，节不能失。」「死可以，降不可以。」
   - **绝不能**与 body 或 dialogue 重复
   - **金句是提炼，不是复述**（v0.3.12 实图评审后补充）：
     正文写**具体细节**（时间、地点、动作、物件），
     金句写**感受与判断**（抽象、克制、留白）。
     两者互补，不重叠。例：
       ❌ 正文写「旄可落，节不可失」→ 金句又写一遍
       ✅ 正文写「十九年风雪把尾毛磨尽，只剩一竿光竹」→ 金句写「旄可以落，节不能失。」
8. **绝对禁止**写"按照X风格"、"在Y视角下"、"本研究"、"以下内容将"等元叙事或程式化引导语

## v0.2.3 七要素铁律（2026-09-21 升级，漫画画面表达系统化重写）

行业最佳实践：单纯把 v0.2.2 的"wide shot / medium shot / close-up"塞进 prompt，模型容易忽视。
升级到**显式七要素结构**，每页 visual 必须按 7 个键值组织（不强制分隔符，但每个关键词都要出现）：

1. **SUBJECT** — 画面里有谁（具体人物 + 次要角色 / 群众 / 敌人剪影）
2. **ACTION** — 正在做什么，**用反应动词**（yanking、slashing、biting、burning、lowering、slumping），不用静态动词（stands, looks, is shown）
3. **CAMERA** — 镜头四件套完整：**shot size**（extreme_wide / wide / medium / three_quarter / close_up / insert_extreme_close）+ **angle**（eye_level / low_angle / high_angle / dutch_tilt / birds_eye / worms_eye）+ **lens**（24mm / 35mm / 50mm / 85mm / 135mm）+ **DoF**（shallow_dof / deep_focus / rack_focus）
4. **PLACEMENT** — 主体在画面的具体位置（"positioned on the left third" / "centered but offset toward upper-right" / "in the foreground right"）
5. **DEPTH LAYERS** — 三层景深显式列出：
   - **FOREGROUND** — 离镜头最近的元素（门框边缘 / 刀刃尖 / 纸屑 / 绳索末端 / 铠甲片 / 烛火 / 尘埃）
   - **MIDGROUND** — 主体动作发生的层
   - **BACKGROUND** — 两个以上远景元素（建筑剪影 / 远山 / 烟柱 / 旗帜 / 敌军队列 / 天空渐变）
6. **LIGHTING** — 光源 + 方向 + 色温 + 软硬（"hard side-light from a single candle on the left, deep crimson wash from behind"），禁用泛词 "dramatic lighting"
7. **MOOD/PALETTE** — 情绪 + 配色绑定（"tense anticipation in desaturated ink black + cinnabar red + bone white"）

### v0.3.7 每段必须附中文速记（新增 · 用户可读性硬要求）

用户要审阅分镜「文字说的」和「画面画的」对不对得上，但画面描述如果全是英文，
用户看不懂；如果被截断，信息就残缺。所以**每个要素段末尾必须追加 `// 中文` 速记**：

```
SUBJECT: Su Wu, 30yo Han envoy, wearing formal dark robe // 苏武 汉使 出塞
ACTION: Su Wu bows deeply before the departing court // 苏武 躬身 辞行
BACKGROUND: vast snowy horizon, distant city walls with flags // 雪原 远城 旌旗
CAMERA: Extreme wide shot, high angle, 24mm lens, deep focus // 大远景 俯拍
MOOD: solemn duty, desaturated blue-white palette // 庄严 克制的蓝白
```

**规则**：
1. `//` 之后必须是**中文**，写给用户看，不是写给模型的
2. 3-6 个短词，用空格或「·」分隔，**不写句子**
3. 必须覆盖该段的画面要点（人物 / 动作 / 关键道具 / 场景）
4. 英文部分照旧保留（要喂给图像模型），中文部分是给人看的

这样 layout_preview 展示分镜时直接用中文速记，用户不用读英文，也不用看被截断的长句。

### 角色一致性五件套 bible（v0.2.3 升级）

不要写单一长段落描述（模型只抓前 30% 关键词）。每页 visual 开头必须以**五个独立锚点**列出角色：

> "Character bible (FIVE ANCHORS, identical in every frame):
> (1) Face shape: oval face, sharp jawline, refined cheekbones.
> (2) Eyes: large double-lid expressive eyes with sharp winged eyeliner, dark brown irises.
> (3) Eyebrows: thin angled swordsman brows, slightly furrowed.
> (4) Lip & mouth: well-defined cupid's bow lips, normally closed, decisive line of jaw.
> (5) Hair: Han-Chinese historical figure, high topknot bound with cloth ribbon (no metal crown), long black hair flowing behind when in motion.
> Modern manhua body proportions (1:2 head-to-body). Age 20-30. Cel-shaded manhua face."

### 表情 anchor（v0.2.3 升级）

**绝不能**用 "defiant" / "sad" / "scared" 这种形容词描述情绪，模型画不出来。
必须从以下 8 个 expression anchors 中**每页选 1 个**直接写到 visual 字段里，
**用可执行的具体面部元素**而非情绪词：

- **neutral** — serene closed lips, relaxed brow, eyes looking forward, neutral composed face
- **rage_scream** — mouth FORCIBLY WIDE OPEN stretching jaw, eyes glaring skyward with visible white, veins on neck bulging, brow deeply furrowed, brow drawn down hard over glaring eyes, head tilted back
- **sobbing_silence** — head bowed low, eyes closed tight, single tear visible on cheek, knuckles white gripping object, mouth pressed in trembling thin line
- **grim_resolve** — jaws clenched, eyes narrowed with cold focus, lips pressed in a thin bloodless line, slight nod forward
- **awed_stillness** — eyes wide round staring, lips parted in shock, breath held, freezing mid-motion, body stillness while expression active
- **sneering_scorn** — one corner of mouth lifted, eyes half-lidded looking down at subject, chin tilted up, dismissive head tilt
- **tender_grief** — soft downcast eyes, faint trembling smile of farewell, hand reaching toward something / someone just out of frame, tears unshed
- **fierce_command** — chin forward, eyes locked on viewer, brows drawn flat in cold authority, arm extended forward with object, mouth open giving order

### 镜头分配铁律（12 页版）

每篇必须有**至少 4 张 wide/extreme_wide**（建立场景感）+ **至少 3 张 medium/three-quarter**（推进叙事）+ **至少 1 张 close_up**（仅用于全篇最戏剧时刻）+ **至少 1 张 insert_extreme_close**（刀 / 血 / 道具符号特写）。
绝不能连续 ≥ 3 页同一 shot size。给每章分配镜头时按"开-推-特-退"节奏排版。

## 输出格式（严格 JSON，不要任何解释文字）

{
  "title": "公众号文章标题（15-25 字）",
  "subtitle": "副标题（如「基于历史档案与流行病学研究」）",
  "summary": "导语 1-2 句话（30-50 字）",
  "preface": "卷首题词（10-20 字）",
  "epigraph": "题记（30-50 字）",
  "postscript": "后记（30-80 字）",
  "characters": [{"name": "角色名", "role": "主角/配角/反派",
                  # v0.3.22: enum 而不是字符串 —— 避免 LLM 输出 "男"/"man"/"M"
                  # 这类乱七八糟的值让 preflight 校验不通过。enum 强制两个之一。
                  "gender": {"enum": ["male", "female"]},
                  "visual_signature": "..."}]
    {
      "name": "主角姓名（如「郭子仪」）",
      "role": "角色身份（主角 / 配角 / 反派 / 路人）",
      "era": "v0.3.17 必填 — 朝代/年代（如「唐代」「春秋末年」「明初」）",
      "visual_signature": "中文视觉签名（30-80 字）：精确描述面部/服饰/配饰/气质/年龄，**严格按 era 字段对应的朝代速查表写**。例：'唐代老将军, 60-70 岁, 方颌, 丹凤眼, 剑眉, 蓄短须, 戴黑色软脚幞头, 穿朱砂色圆领窄袖袍配玉带蹀躞带, 身形清瘦挺拔'"
    }
  ],
  "pages": [
    {
      "page": 1,
      "highlight": "1347",
      "visual": "画面描述（英文 80-150 词，必须按 v0.2.3 七要素结构组织：SUBJECT / ACTION / CAMERA 四件套 / PLACEMENT / DEPTH LAYERS / LIGHTING / MOOD；开头列角色五件套；v0.3.0 第二行写 [GENDER:male|female|mixed] 性别标记；选 1 个 expression anchor）",
      "caption": "场景说明（中文 10-20 字）",
      "dialogue": "文言原文引句（8-50字，出自《史记》/《左传》等，**每页必填**）",
      "narration": "旁白或空字符串",
      "body": "长段落正文（**严格 100-150 字**——图为主、文字为脚注）",
      "keywords": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"],
      "punchline": "白话点题金句（10-22字，渲染成定格瞬间）",
      "key_visual": "视觉锚点"
    }
  ]
}

### v0.2.5 人物一致性规则（人物故事必读）

**触发条件**：当主题是「人物故事 / 传记 / 历史人物 / 名人 / 武侠 / 江湖 / 古典小说人物」时，必须输出 `characters` 数组（≥1 个主要人物）。

**visual 字段角色描述规则**：
- ✅ 每页 visual 开头必须**完整重复**该角色在 characters 数组里的视觉签名翻译（不只是"the man"或"Guo Ziyi"）
- ✅ 多角色场景里每个角色的核心特征都必须出现（避免换脸/换人 bug）
- ❌ 不要用代词（"he" / "the general" / "the khan"）省略人物身份

**作用**：Mavis 拿到 storyboard 后会先用 characters 跑角色 4 视图参考图（front / 3-4 / side / back），再每页用 i2i 跑，保证 10 页跨章跨段角色稳定。这是 v0.2.5 强约束。

## v0.3.0 性别标记铁律（防"性转"bug，2026-09-24 新增）

**根因**：chinese_lianhuanhua_classic 默认 anchor 把妆发硬写"女性化"（桃花腮+花钿+步摇+柳叶眉），
如果 visual 描述男性主角（"Zhang Xun, 40yo male general"），anchor 强制桃花腮/步摇 → 模型脸部女性化 + 服饰中性 → 性转成女性。

**铁律**：每页 visual **第二行**（角色描述之后、ACTION 之前）必须明确写出性别标记，格式：
- `[GENDER:male]` — 单人物性别为男性（最常见于历史典故主角，如张巡/郭子仪/文天祥）
- `[GENDER:female]` — 单人物性别为女性（如王昭君/杨贵妃/武则天）
- `[GENDER:mixed]` — 男女混合场景（如"夫妻对坐"、"将军审问叛军女眷"）

**示例**：
- ✅ "SUBJECT: Zhang Xun, 40yo Tang general... [GENDER:male] ACTION: he grips his sword..."
- ✅ "SUBJECT: Wang Zhaojun... [GENDER:female] ACTION: she plays the pipa..."
- ✅ "SUBJECT: Zhang Xun and his wife [GENDER:mixed] ACTION: they examine a map..."

**作用**：build_image_prompt 按 [GENDER:xx] 自动选对应妆发分支（女性桃花腮/步摇 / 男性玉冠/玉簪/剑眉），
不会因为 anchor 默认女性化导致男性主角被性转。如果漏标记，build_image_prompt 会自动从代词检测，但显式标记更稳。
"""


def _build_planner_user_msg(topic: str, bullets: list[str], style_id: str, canon_injection: str = "") -> str:
    user_msg = (
        f"主题：{topic}\n"
        f"风格 ID：{style_id}\n"
        f"要点列表：\n" + "\n".join(f"- {b}" for b in bullets)
    )
    if canon_injection:
        user_msg += "\n\n" + canon_injection
    return user_msg


BODY_MAX_CHARS = 150


def _clamp_body(text: str) -> str:
    """v0.3.4：按 prompt 里早已承诺的规则截断超长正文。

    planner prompt 第 295/304/382 行反复写了「严格 100-150 字，超过 150 字
    自动砍到 150」，但这个"自动砍"从来没在代码里实现过 —— 只在 prompt 里承诺。
    实测三次真实跑，正文达标率在 5/10 ~ 9/10 之间波动（LLM 对字数约束本就有
    合理波动），说明**光靠 prompt 约束不住**。

    用户的硬偏好是「图为主、文字为脚注，100-150 字/页」，文字太重会压过画面。
    所以上限必须在代码层兜住，不能指望模型自觉。

    截断在句号边界下刀，尽量不把句子劈成半截；找不到句号就硬截。
    """
    s = (text or "").strip()
    if len(s) <= BODY_MAX_CHARS:
        return s
    head = s[:BODY_MAX_CHARS]
    # 在最后一个句末标点处收刀（留得下就留，找不到就硬截）
    for i in range(len(head) - 1, max(0, len(head) - 40) - 1, -1):
        if head[i] in "。！？；…":
            return head[:i + 1]
    return head


def _call_llm_storyboard(
    topic: str,
    bullets: list[str],
    style_id: str,
    canon_injection: str = "",
    num_pages: int | None = None,
) -> Storyboard:
    """调 LLM 生成 storyboard。

    num_pages: 显式页数（None = 自动按 bullets 推荐）。
    实际拼到 system prompt 末尾的 page count 指令。
    """
    cfg = get_config()
    if not cfg.llm_api_key or cfg.llm_api_key.startswith("sk-placeholder"):
        raise RuntimeError(
            "LLM_API_KEY not configured. Fill it in .env, "
            "or call mock_storyboard() instead."
        )

    target_pages = num_pages if num_pages is not None else recommend_pages(len(bullets))

    # v0.3.2：OpenAI 客户端加 timeout + max_retries。
    # 旧实现两个都不带 —— LLM 卡住时会无限期挂死（Mavis 对话里表现为"跑着跑着没动静"，
    #  无法区分是在跑还是在死）。这里给足出图级等待，但必须有上限。
    client = OpenAI(
        api_key=cfg.llm_api_key,
        base_url=cfg.llm_base_url,
        timeout=LLM_TIMEOUT,
        max_retries=LLM_MAX_RETRIES,
    )
    user_msg = _build_planner_user_msg(topic, bullets, style_id, canon_injection)

    # 动态 system prompt：把"输出 6-10 页"换成"输出 {target_pages} 页"
    sys_prompt = PLANNER_SYSTEM_PROMPT.replace(
        "输出 6-10 页分镜脚本",
        f"输出 {target_pages} 页分镜脚本",
    )

    logger.info("Planner LLM call: model=%s, topic=%s, bullets=%d, target_pages=%d",
                cfg.llm_model, topic[:30], len(bullets), target_pages)

    try:
        resp = client.chat.completions.create(
            model=cfg.llm_model,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.7,
        )
    except Exception as e:
        raise RuntimeError(f"LLM API call failed: {e}") from e

    content = resp.choices[0].message.content or ""
    if not content.strip():
        raise RuntimeError(
            f"LLM returned empty response. "
            f"model={cfg.llm_model}, base_url={cfg.llm_base_url}"
        )

    # MiniMax M3 开启 thinking 模式：content 包含 <think>...</think> + JSON
    # 提取 ```json ... ``` 块 或 最后一对 {...}
    data = None
    # 1) markdown 块（用最外层大括号提取，避免非贪婪匹配到内部 }）
    m = re.search(r"```(?:json)?\s*\n([\s\S]*?)\n\s*```", content)
    if m:
        block = m.group(1).strip()
        brace_start = block.find("{")
        if brace_start >= 0:
            depth = 0
            for i in range(brace_start, len(block)):
                if block[i] == "{":
                    depth += 1
                elif block[i] == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = block[brace_start:i + 1]
                        try:
                            data = json.loads(candidate)
                            break
                        except json.JSONDecodeError:
                            pass
    if data is None:
        # 2) 整段 content 中找最外层 {...}
        brace_start = content.find("{")
        if brace_start >= 0:
            depth = 0
            for i in range(brace_start, len(content)):
                if content[i] == "{":
                    depth += 1
                elif content[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            data = json.loads(content[brace_start:i + 1])
                            break
                        except json.JSONDecodeError:
                            pass
    if data is None:
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            raise RuntimeError(
                f"LLM returned non-JSON. Content (first 500 chars): {content[:500]!r}"
            )

    pages = [
        StoryPage(
            page=p["page"],
            visual=p["visual"],
            caption=p.get("caption", ""),
            dialogue=p.get("dialogue", ""),
            narration=p.get("narration", ""),
            body=_clamp_body(p.get("body", "")),
            key_visual=p.get("key_visual", ""),
            highlight=p.get("highlight", ""),
            # v0.3.3 修复：此处原先漏了 keywords，导致 LLM 即使按 schema 输出了
            # keywords 也会在这一步被静默丢弃 —— 实测苏武牧羊 10 页全部为空，
            # 朱砂红高亮整条链路失效。v0.2.9 加字段时只改了 prompt 和 dataclass，
            # 忘了同步这里的解析层。
            keywords=p.get("keywords", []) or [],
            # v0.3.11：白话点题金句（「定格瞬间」用），与文言引文 dialogue 分开
            punchline=p.get("punchline", "") or "",
        )
        for p in data["pages"]
    ]

    return Storyboard(
        topic=topic,
        style_id=style_id,
        pages=pages,
        title=data.get("title", topic),
        subtitle=data.get("subtitle", ""),
        summary=data.get("summary", ""),
        preface=data.get("preface", ""),
        epigraph=data.get("epigraph", ""),
        postscript=data.get("postscript", ""),
        characters=data.get("characters", []),
    )


def mock_storyboard(
    topic: str,
    bullets: list[str],
    style_id: str,
    num_pages: int | None = None,
) -> Storyboard:
    """无 LLM 时的占位 storyboard。角色按主题时代自适应。

    num_pages: 显式目标页数（None = 自动按 recommend_pages 推荐）。
    v0.3.2 修复：原先完全忽略 num_pages（只在 docstring 里说"仅作 informational"），
    导致 step_plan(num_pages=6) 在降级路径上仍按 bullets 数产出 5 页。
    现在按 num_pages 补齐/截断。
    """
    target_pages = num_pages if num_pages is not None else recommend_pages(len(bullets))

    pages: list[StoryPage] = []

    # 角色锚点（按 style_id 选）
    # v0.3.2 修复：原先只有 cn_xuanfeng 分支，其余风格（含历史类首选
    # chinese_lianhuanhua_classic）一律套"戴眼镜现代科学家"，降级后画出来
    # 是连环画里站着个现代人。改为直接用 prompts 的按风格锚点。
    if style_id == "cn_xuanfeng":
        character = "A Han-Chinese historical person in traditional hanfu robe (crossed collar, wide sleeves, sash belt, hair pinned in classical style with subtle ornaments), serene contemplative expression, age 20-30, rendered with elegant elongated proportions typical of classical Chinese figure painting"
    elif style_id == "chinese_lianhuanhua_classic":
        character = "Chinese illustrated figure on rice paper with ink-brush gongbi technique, Han-Chinese historical period costume appropriate to the scene, 3+ principal figures plus 2-3 background attendants, multi-prop full-frame narrative composition, classical Chinese lianhuanhua painted illustration, NOT a photograph, NOT a 3D render"
    elif style_id == "guochao_manhua":
        character = "Chinese manhua figure, Han-Chinese historical costume with modern cel-shaded guochao style, flat color blocks with vermilion / ink-blue / jade-green / gold accents, stylized 1:2 head-to-body ratio, NOT a photograph, NOT a 3D render"
    else:
        character = "A small scientist figure with short black hair, round wire-frame glasses, light grey sweater, dark trousers, neutral expression, age 30"

    # 第 1 页：开场
    pages.append(StoryPage(
        page=1,
        visual=(
            f"{character}, standing at the center, gesturing welcomingly with both hands, "
            f"a giant floating question mark in soft outline behind, gentle paper texture, "
            f"NO text anywhere on the image."
        ),
        caption="今天聊聊一个话题。",
        dialogue="",
        narration="",
        key_visual="consistent character anchor",
    ))

    # 中间页：每条 bullet 一页（visual 复用同款角色，只换动作/道具）
    for i, bullet in enumerate(bullets, start=2):
        bullet_short = bullet[:30]
        pages.append(StoryPage(
            page=i,
            visual=(
                f"{character}, holding a magnifying glass and pointing at a floating visual "
                f"metaphor representing the concept of {bullet_short}, clear composition, "
                f"soft warm palette, ABSOLUTELY NO TEXT, NO labels, NO arrows-with-words."
            ),
            caption=bullet[:25] + ("…" if len(bullet) > 25 else ""),
            dialogue="",
            narration="",
            key_visual="consistent character anchor",
        ))

    # 最后一页：结尾金句
    pages.append(StoryPage(
        page=len(pages) + 1,
        visual=(
            f"{character}, giving a thumbs up with a calm knowing expression, "
            f"a small glowing idea-bulb floating nearby, soft warm atmosphere, NO text on image."
        ),
        caption="所以，下次再遇到类似场景——",
        dialogue="",
        narration="懂这个话题的人，不过是把它当成一件平常事。",
        key_visual="consistent character anchor",
    ))

    # v0.3.2：按 target_pages 补齐 / 截断，保证用户显式指定的页数在降级路径也生效。
    if len(pages) > target_pages and target_pages >= 2:
        # 保留开场 + 结尾金句，中间按需裁剪
        head, tail = pages[0], pages[-1]
        mid_budget = target_pages - 2
        pages = [head] + pages[1:1 + mid_budget] + [tail]
    elif len(pages) < target_pages:
        filler_bullets = bullets or [topic]
        while len(pages) < target_pages:
            idx = len(pages) - 1
            bullet_short = filler_bullets[idx % len(filler_bullets)][:30]
            pages.append(StoryPage(
                page=len(pages) + 1,
                visual=(
                    f"{character}, a secondary moment illustrating {bullet_short}, "
                    f"clear composition, soft warm palette, "
                    f"ABSOLUTELY NO TEXT, NO labels, NO arrows-with-words."
                ),
                caption=bullet_short,
                dialogue="",
                narration="",
                key_visual="consistent character anchor",
            ))

    # 重排页码，保证连续
    for i, p in enumerate(pages, start=1):
        p.page = i

    return Storyboard(
        topic=topic,
        style_id=style_id,
        pages=pages,
        title=f"一图读懂 {topic}",
        summary=f"用 {len(pages)} 张图给你讲清楚核心要点。",
    )


def plan_storyboard(
    topic: str,
    bullets: list[str],
    style_id: str = "cn_xuanfeng",
    use_llm: bool = True,
    canon_injection: str = "",
    num_pages: int | None = None,
) -> Storyboard:
    """Step 1: 主题 + 要点 → storyboard JSON。

    Args:
        topic: 主题
        bullets: 要点列表
        style_id: 风格 ID
        use_llm: 是否调 LLM（False = mock）
        canon_injection: 一致性约束注入
        num_pages: 显式指定页数（None = 按 recommend_pages 自动推荐）
    """
    if use_llm:
        try:
            # v0.3.2 修复：原先漏传 num_pages，导致用户显式指定的页数在真 LLM 路径被丢弃
            return _call_llm_storyboard(
                topic, bullets, style_id, canon_injection, num_pages=num_pages
            )
        except RuntimeError as e:
            logger.warning("LLM unavailable (%s), falling back to mock storyboard", e)
            return mock_storyboard(topic, bullets, style_id, num_pages)
    return mock_storyboard(topic, bullets, style_id, num_pages)