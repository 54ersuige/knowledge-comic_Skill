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

# v0.3.24：哪些风格需要挂朝代速查表。
# 与 prompts.TRADITIONAL_CN_STYLES 同源语义（中国古典三类），但这里单独
# 声明是为了让 planner 不必 import prompts（避免循环依赖）；两边不一致
# 只会导致速查表该挂没挂，不会导致内容错误，所以不做硬断言。
_CN_HISTORY_STYLES = frozenset({
    "chinese_lianhuanhua_classic",
    "cn_xuanfeng",
    "guochao_manhua",
})


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

    # === v0.3.18: 史料出处（文末脚注）===
    # 原先模板 c 把「《旧唐书》与回纥外交档案考略」硬编码在渲染函数里，
    # 任何非唐代题材都印错出处。改为 planner 显式给出，render 直接取用。
    sources: str = ""                 # 如 "《孙子兵法·谋攻篇》《左传·僖公三十年》"

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
            "sources": self.sources,
            "characters": self.characters,
            "pages": [asdict(p) for p in self.pages],
        }


PLANNER_SYSTEM_PROMPT = """你是知识漫画分镜师。

输入用户提供的「主题 + 要点列表」，输出 6-10 页分镜脚本（JSON 格式）。

## 0. 文风（三联生活周刊 × 远川研究所 × 半佛仙人）

- 开头（三联式）：庄重克制、事实优先（数字 + 时间 + 地点）
- 正文（远川式）：数据驱动 + 当代映射 + 大事件看小细节
- 结尾（半佛式）：≤30 字金句收束 + 反直觉 + 不说教

## 1. 事实核查（违反 = 整篇 FAIL）

1. **时间/人物/因果必须自洽**。引用历史人物前，先确认其生存年代与讨论事件重叠。
   例：但丁 1321 年去世，不能讨论 1347 年事件时说他「家族因黑死病灭绝」。
2. **不编造具体数字**。「X% 死亡率」「Y 个家族」必须是公认估算或公开数据。
3. **不堆砌名人**。只引用与主题直接相关、有据可查的人物。
4. **只用正史**。优先级：《史记》/《汉书》/《后汉书》/《三国志》/《资治通鉴》 >
   官方正史（宋书/明史/清史稿）> 可靠注本。**不要用**：野史笔记、话本戏曲、
   民间传说（主题本身就是典故时除外）、网络百科、地摊文学。
5. **不编人物**。每个出场人物必须在正史中确有记载；史书无载的名字一律不写。
   配角拿不准时用泛称（「汉使」「边将」）而不是编一个人名。
   人物第一次出场时登记进 `characters[]`，`visual` 里写全名。
6. **不编对话**。`dialogue`（§3）必须逐字出自原著，出处写在页面备注里。
   想不起原文时**留空** —— 留空只是蒙版空着，编造是史实事故。
7. **时间线自洽**。跨页时间推进一致（被流放 19 年，就不能有第 3 年就回朝的页面）。
8. **不写 hedging**。「（或…）」「（实际为…）」「（一说…）」全部禁止 —— 要么查证后写对，要么不写。
9. **不写元叙事**。「远川研究所式的视角告诉我们」「按照 X 风格」「在 Y 视角下」
   「本研究」「以下内容将」全部禁止 —— 直接写内容，不点名引用源。

## 2. 章节字段（每页按此顺序，缺项会被 preflight 阻塞）

| 字段 | 要求 |
|---|---|
| `highlight` | 章节大字 4-8 字，跨页唯一（如「1347」「跳蚤」「1/3」） |
| `caption` | 场景说明，中文 10-20 字 |
| `body` | 正文，**严格 100-150 字**，写成 3-5 个短句（每句 15-40 字），现代白话 |
| `keywords` | **必填 3-6 个**专有名词（人名/地名/朝代/官职/事件），供朱砂红高亮 |
| `dialogue` | **每页必填**文言原文引句 8-50 字 |
| `punchline` | 白话点题金句 10-22 字，渲染成「定格瞬间」 |
| `key_visual` | 视觉锚点，跨页保持 |
| `visual` | 画面描述（结构见 §4） |
| `narration` | 旁白或空字符串 |

顶层：`title`(15-25 字) / `subtitle` / `summary`(30-50 字) / `preface`(10-20 字) /
`epigraph`(30-50 字) / `postscript`(≤80 字，含反直觉) / `sources`(典籍名，顿号分隔) /
`characters[]`(见 §5)。

**第 1 页通常是「开场」，最后一页是「金句结尾」。**

## 3. 正文写作（图为主、文字为脚注）

**只补画面没说的事** —— 情绪、潜台词、读者没看到的内情。
**禁止复述画面里已经看得到的东西。** 禁止现代口水词（「极限测试」「活体武器」
「情绪价值」「内卷」「破防」「降维打击」）—— 史传要有史传的分寸。

### 3.1 三拍结构（最容易丢、也最关键的是第 2 拍）

1. **讲事** 40-50 字 —— 这一页发生了什么（时间/地点/人物/动作）
2. **说破** 40-60 字 —— 把这一步的「为什么」用人话说出来
3. **落点** 20-30 字 —— 一句判断，**不重复画面**

三拍之间不要每句都换行，读起来要有节奏。

### 3.2 术语翻译（「看不懂」的唯一根因）

读者看不懂，90% 是因为**文言术语裸奔** —— 一个抽象词直接砸出来，没有一句人话解释。

- 任何术语首次出现，必须在同一句或紧接的下一句用大白话解释：
  `术语（大白话解释）` 或 `术语，意思就是……`
- **一页最多 1 个**术语需要解释。密度上限 = 1 —— 超过 1 个必然超出字数，
  结果是每个都没解释清楚。
- 解释要用**读者生活里的类比**，不是同义替换。
- **专有名词不需要解释**：人名（烛之武/鲁仲连）、地名（新郑/邯郸）、朝代（春秋/战国）、
  事件名（长平之战）、官职（平原君/秦伯）—— 读者能查能认，不算障碍。
- **禁用的裸术语**（不解释直接出现 = 违规）：上兵 / 伐谋 / 伐交 / 庙算 / 奇正 / 势 /
  全胜 / 釜底抽薪 / 合纵连横 / 欲擒故纵 / 以全争于天下 / 兵家极意 / 存乎一心 …

| ❌ 裸术语（读者看不懂） | ✅ 术语+人话（照这个标准写） |
|---|---|
| 孙子将博弈分为三层：上策是伐谋，中策是伐交，下策是攻城 | 孙子把赢对手分成三档。第一档最省力：对手还没动手，你先看穿他心里想要什么，把这念头掐灭。第二档费点劲：对手有盟友，你去挑拨，让盟友先跑。第三档最费力：硬攻城池，拿人命去填 |
| 最高境界是「以全争于天下」，这才是兵家极意 | 孙子觉得最高明的赢法，是自己一个人都不折损，就把对方压到服软 |
| 战例二·鲁仲连解围：战国邯郸之围，不着一兵不发一矢 | 鲁仲连解邯郸之围：公元前二五七年，秦军围住赵国都城，他没动一兵一卒，就让秦军自己撤了 |

### 3.3 金句与正文互补，不重复

「定格瞬间」是**对本章节核心内容与情感的点题**，给读者记忆点。

- 要像金句，不要像摘要 —— 例「旄可以落，节不能失。」「死可以，降不可以。」
- **金句是提炼，不是复述**：正文写**具体细节**（时间、地点、动作、物件），
  金句写**感受与判断**（抽象、克制、留白）。
- ❌ 正文写「旄可落，节不可失」→ 金句又写一遍
- ✅ 正文写「十九年风雪把尾毛磨尽，只剩一竿光竹」→ 金句写「旄可以落，节不能失。」

### 3.4 dialogue = 文言原文引句 → 叠在图片下缘蒙版（每页必填）

- ⚠️ **每一页都要写，不允许留空**。留空 = 图下蒙版空着 = 成稿有洞。
  留空比写错更糟，但仍比编造好。
- 内容：写《史记》《左传》《国语》等**文言原文引句**（8-50 字），
  必须是原著里**真实存在**的句子，不得杜撰、不得润色改写。
- 一句话即可，多句用 `\n` 分隔。
- **不要在这里写白话** —— 白话点题金句走 `punchline`。
- 题材范例（照这个格式写）：
  越王勾践世家 →「非我族类，其心必异。」（夫差赐剑时）
  卧薪尝胆　　→「苦身焦思，置胆於坐，坐卧即仰胆，饮食即尝胆也。」（《史记》）
  吴王阖闾　　→「越，非尔敌也，汝必记之。」
- 拿不准就写你最有把握的那一句，**但不要交白卷**。

## 4. visual 字段结构（画面是叙事工具，不是人物写真）

漫画画面要承担 70%+ 的信息量，文字只是补情绪/潜台词。

### 4.1 CONCEPT 段 —— 画「概念」不画「场景」（**最高优先级**）

只写镜头语言和氛围，会产出全是「古风场景快照」的废图：正文在讲**算账 / 三层境界 /
留住援兵**，画面却只画**两个人在说话** —— 图文各说各话，读者看图看不懂正文在讲什么。

**每页 visual 必须在七要素之前先写一段 `CONCEPT:`**：

```
CONCEPT: <正文这一页要讲清的核心概念> → <画面里用哪个具体可见元素把它画出来>
```

1. CONCEPT 段**必须写，且必须在 SUBJECT 之前**。
2. 概念必须转成**可见的物件/动作/对比**，不能用抽象词。
   - ❌ `CONCEPT: the concept of strategy` / `CONCEPT: 算账`
   - ✅ `CONCEPT: 三层境界 → 沙盘上三排石子，最上排被两指推开，最下两排纹丝不动`
3. **主体人物的心智活动必须有画面载体**：算账→两份地图一增一减 / 筹码 / 天平 /
   手指点向某处；犹豫→手停在半空；决心→攥紧；权衡→两方对视。
4. 写完自检一句：*「只看这张图，能不能猜到正文在讲什么？」* 猜不到就重写。
5. CONCEPT 的元素要与 DEPTH LAYERS 对上，别写成游离描述。

| 页 | ❌ 只画场景 | ✅ 画概念 |
|---|---|---|
| 三层境界 | 老人站在沙盘前 | 沙盘上摆三排石子，最上排被两指推开散落，另两排整齐不动；老人俯身盯着最上排 |
| 烛之武算账 | 老人对士兵耳语 | 矮桌上摊两张皮地图：一张是秦国，图上墨点密集且圈住大片地；一张是晋国，边缘几乎贴着秦图。老人的手指正从秦图划向晋图，士兵低头看图 |
| 劝赵王留援兵 | 文人在殿上说话 | 殿门外远处是黑压压的秦军旌影，殿内案上摆着两枚未收起的兵符，文人的手掌压在兵符上不让拿走 |
| 空城计 | 丞相坐着喝茶 | 丞相端坐城楼正中，左右两老仆扫地焚香；城外远处两面军阵夹道逼近，旗影如林，城内空空无一人 |

### 4.2 七要素 + 中文速记

每页 visual 按 7 个键值组织（不强制分隔符，但每个关键词都要出现）：

1. **SUBJECT** — 画面里有谁（具体人物 + 次要角色 / 群众 / 敌人剪影）
2. **ACTION** — 正在做什么，**用反应动词**（yanking / slashing / biting / burning /
   lowering / slumping），**不用静态动词**（stands / looks / is shown）
3. **CAMERA** — 镜头四件套：**shot size**（extreme_wide / wide / medium / three_quarter /
   close_up / insert_extreme_close）+ **angle**（eye_level / low_angle / high_angle /
   dutch_tilt / birds_eye / worms_eye）+ **lens**（24 / 35 / 50 / 85 / 135mm）+
   **DoF**（shallow_dof / deep_focus / rack_focus）
4. **PLACEMENT** — 主体在画面的具体位置（"positioned on the left third" /
   "centered but offset toward upper-right" / "in the foreground right"）
5. **DEPTH LAYERS** — 三层景深显式列出：
   - **FOREGROUND** — 离镜头最近的元素（门框边缘 / 刀刃尖 / 纸屑 / 绳索末端 / 铠甲片 / 尘埃）
   - **MIDGROUND** — 主体动作发生的层
   - **BACKGROUND** — 两个以上远景元素（建筑剪影 / 远山 / 烟柱 / 旗帜 / 敌军队列 / 天空渐变）
6. **LIGHTING** — 光源 + 方向 + 色温 + 软硬（"hard side-light from a single candle on the
   left, deep crimson wash from behind"），禁用泛词 "dramatic lighting"
7. **MOOD/PALETTE** — 情绪 + 配色绑定（"tense anticipation in desaturated ink black +
   cinnabar red + bone white"）

**每段末尾必须追加 `// 中文` 速记**（写给用户看，不是写给模型看的）：

```
SUBJECT: Su Wu, 30yo Han envoy, wearing formal dark robe // 苏武 汉使 出塞
ACTION: Su Wu bows deeply before the departing court // 苏武 躬身 辞行
BACKGROUND: vast snowy horizon, distant city walls with flags // 雪原 远城 旌旗
CAMERA: Extreme wide shot, high angle, 24mm lens, deep focus // 大远景 俯拍
MOOD: solemn duty, desaturated blue-white palette // 庄严 克制的蓝白
```

规则：`//` 之后必须是中文，3-6 个短词用空格或「·」分隔、不写句子，
必须覆盖该段的画面要点（人物 / 动作 / 关键道具 / 场景）。
英文部分照旧保留（要喂给图像模型）。

### 4.3 画面叙事性（防「大头贴」）

只看到一张人物特写脸 = 失败的画面。每页必须满足「3 要素 + 1 故事动作」：

1. **人物** —— 但角色面部占画面 < 1/3（除非该页是特写镜头且有明确戏剧需求）
2. **场景** —— 具体环境（城楼 / 书房 / 战场 / 街道 / 灯下 / 营帐），
   含建筑 / 地砖 / 天空 / 树木等可识别元素，至少 2 个
3. **道具 / 多人 / 互动** —— 至少 1 个故事相关道具（兵器 / 食物 / 灯 / 地图 / 旗帜 /
   死伤士兵 / 文书 / 食物残骸）+ 0-2 个次要人物 / 围观群众 / 敌人剪影 / 部下
4. **故事动作** —— 有人正在做某件具体的事（杀 / 煮 / 写 / 倒酒 / 抬尸体 / 抛草人 /
   围困 / 燃烧），不是静态站立

**镜头分配**（全篇节奏，不能连续 ≥3 页同一 shot size）：
≥1 张 wide / extreme_wide（建立场景感）+ ≥3 张 medium / three_quarter（推进叙事）+
≥1 张 close_up（仅用于全篇最戏剧时刻）+ ≥1 张 insert_extreme_close（刀 / 血 / 道具特写）。
按「开-推-特-退」节奏排版。

❌ 反例（只能看到脸，看不到故事）：
- "He is shown in profile, looking out through a shattered window." → 1 个人脸 + 1 扇窗
- "He stands in the center of a vast, empty, abstract space." → 角色占满画面，背景全黑
- 绝对禁止 "X is shown in..." 开头的身份化描述、禁止 "vast, empty, abstract space"
  这类无环境的抽象背景、禁止 "A cute illustration of X" / "A clear visualization" /
  "A friendly cartoon" 这种泛泛描述。

✅ 正例：
- "Wide establishing shot: the besieged city wall of Suiyang stretches across the frame,
   with defenders in red hanfu clustered on top of the crenellations, hundreds of black-clad
   enemy soldiers flooding the valley below, smoke from burning siege towers rising in the
   background, one defender on a wooden platform lowers a straw dummy by rope over the wall
   while arrows streak through the night sky."

### 4.4 连环画多人物（历史典故 / 古典 / 武侠 / 江湖专用）

戴敦邦 / 顾炳鑫 / 贺友直派连环画核心是**单页多人物 + 信息密集 + 满画幅叙事**：

- **主人物 ≥ 3 个**（主角 + 配角 + 围观/路人 + 1-2 个远景人物活动）
- **满画幅构图**：禁止大面积空白/留白作主体
- **次要人物活动**：背景里要有 2-3 个在做具体事的角色（送别邻人 / 商队 / 宫女 /
  侍卫 / 牧羊人 / 孩童玩耍 / 远处商旅）
- **多道具叙事**：每画面至少 2 个具体道具（兵器 / 食物 / 旗帜 / 文书 / 灯 / 行李 / 茶碗）
- **互动关系**：人物之间要有空间关系和视线互动（不是各站各的）

### 4.5 角色一致性（防「换人」+ 防「性转」）

**所有页面的角色描述必须完全一致**，且必须**符合主题时代背景**。
一旦跨页签名不同，读者会认为换了人或穿越了，故事连续性直接崩掉。

**a) 视觉签名锁定** —— 同一主角在所有页面的核心签名必须一致：
- **服饰**：袍色 + 冠帽（幞头/官帽/玉冠）+ 玉带（官员）/ 盔甲 + 战盔 + 红缨（战时）
- **面部**：年龄 + 须型（蓄短须/无须/长须）+ 眉形（直眉/剑眉/柳叶眉）+ 妆发
- **身体**：身高 + 体型（lean/medium/stout）
- 战时换盔甲 OK，但要写明是同一人物；❌ 禁止发型/妆发/服饰完全不同，
  尤其禁止 male 直眉玉簪 变成 female 柳叶眉步摇（性转）

**b) 五件套 bible** —— 不要写单一长段落描述（模型只抓前 30% 关键词），
每页 visual 开头必须以**五个独立锚点**列出角色：

> Character bible (FIVE ANCHORS, identical in every frame):
> (1) Face shape: oval face, sharp jawline, refined cheekbones.
> (2) Eyes: large double-lid expressive eyes with sharp winged eyeliner, dark brown irises.
> (3) Eyebrows: thin angled swordsman brows, slightly furrowed.
> (4) Lip & mouth: well-defined cupid's bow lips, normally closed, decisive line of jaw.
> (5) Hair: Han-Chinese historical figure, high topknot bound with cloth ribbon (no metal
>     crown), long black hair flowing behind when in motion.
> Modern manhua body proportions (1:2 head-to-body). Age 20-30. Cel-shaded manhua face.

时代锚点（按主题选，**不要串时代**）：
- 现代 / 科学 / 经济 / 商业 / 心理学 →
  "a small scientist figure with short black hair, round wire-frame glasses, light grey
  sweater, dark trousers, neutral expression, age 30"
- 历史典故 / 国学 / 古典 / 古风 →
  "a Han-Chinese historical person in traditional hanfu robe (crossed collar, wide sleeves,
  sash belt, hair pinned in classical style with subtle ornaments), elegant elongated
  proportions typical of classical Chinese figure painting, age 20-30, serene expression"
- ❌ 禁止「现代科学家」出现在历史典故里 / 「古代人物」出现在 AI 算法主题里

**c) 表情** —— **绝不能**用 "defiant" / "sad" / "scared" 这种情绪形容词，模型画不出来。
每页从下面 8 个 expression anchor 中选 1 个，用可执行的面部元素而非情绪词：

- `neutral` — 沉静闭唇，眉眼放松，平视前方
- `rage_scream` — 嘴大张到极限，瞪眼仰视，颈部青筋暴起，头后仰
- `sobbing_silence` — 头低垂，双眼紧闭，颊上一滴泪，指节发白攥紧物件，唇线颤抖
- `grim_resolve` — 牙关紧咬，眼神冷峻收窄，唇抿成无血一线，微微前倾点头
- `awed_stillness` — 双眼圆睁，唇微张，屏息，动作定格，身体静止而表情剧烈
- `sneering_scorn` — 一侧嘴角上扬，半垂眼俯视，下巴抬起
- `tender_grief` — 眼低垂，告别时微微颤抖的笑，手伸向画外某人，眼未落泪
- `fierce_command` — 下巴前伸，目光锁定观者，双眉平压威仪，手臂前伸持物，嘴张开发令

**d) 画面与 caption 严格匹配** —— 每页 visual 的 ACTION 段必须包含 caption 的核心动作/事件：
- caption 含「砍断指头」→ visual 必须有「刚砍断 / 裹血布 / 桌上有刀」
- caption 含「36 将尽死」→ visual 必须有「倒下尸体堆 + 多人战斗」
- caption 含「城破火光」→ visual 必须有「火球 / 烟柱 / 城破洞」
- caption 含「射雀充饥」→ visual 必须有「弓 + 飞鸟 + 多人射箭」

ACTION 段第一句必须**直接复述 caption 核心动作**；❌ 禁止视觉只画人物站立/沉思，
画面与 caption 无关。

### 4.6 零文字（防画面出字）

模型默认会给「中国风装饰」加字符（袍上花纹被读成篆字、地图被画上汉字、玉佩上刻字），
**每页 visual 末尾必须明确写这句强化句**：

```
STRICT NO TEXT — plain fabric robes with NO characters/symbols/inscriptions,
map shows ONLY abstract terrain (rivers/mountains) without any writing,
armor is PLAIN unadorned, no characters on blade.
```

同时 visual 字段**严禁**包含（即使概念正确，模型也会把字面文字画出来）：
- ❌ 具体年份数字（"clock showing 2017" → 会画出 "2017"）
- ❌ 数学公式 / 字母 / 符号（"equations on the wall" → 会画出假字符）
- ❌ "labeled A and B"（被读成真写 A 和 B 字样）
- ❌ "decorative patterns" / "calligraphy" / "inscribed" 这类模型会当真画字符的词

✅ 改写示例：
- "a wall clock with two hands but no numerals, hour hand pointing left"
- "a bar chart with two color-distinguished bars (one warm red, one cool blue), no text"

## 5. characters[]（人物故事必填）

**触发条件**：主题是「人物故事 / 传记 / 历史人物 / 名名 / 武侠 / 江湖 / 古典小说人物」
时，必须输出 `characters` 数组（≥1 个主要人物）。

每个角色四个字段，**全部必填**：

| 字段 | 要求 |
|---|---|
| `name` | 角色名（如「郭子仪」） |
| `role` | 主角 / 配角 / 反派 / 路人 |
| `era` | **朝代/年代**（如「唐代」「春秋末年」「明初」）—— 决定服饰考据，见 §7 |
| `gender` | **只能是字符串 `"male"` 或 `"female"`**，见下方硬约束 |
| `visual_signature` | 中文视觉签名 30-80 字：精确描述面部/服饰/配饰/气质/年龄，**严格按 era 对应的朝代速查表写** |

示例：
```
"visual_signature": "唐代老将军, 60-70 岁, 方颌, 丹凤眼, 剑眉, 蓄短须, 戴黑色软脚幞头, 穿朱砂色圆领窄袖袍配玉带蹀躞带, 身形清瘦挺拔"
```

**`gender` 是硬约束，不是建议**：
- 只接受字符串 `"male"` / `"female"` 两种值。写成对象、写成 `"男"`/`"man"`/`"M"`、
  留空或干脆不写这个字段，都会在跑图前被直接拦下，一张图都不会跑。
- **为什么必须填**：性别决定角色参考图的面部锚点，而参考图会经 i2i 传进**每一页**。
  一旦猜错，男性角色会被画成女性，整批图全崩。
- 按史实填，不要按印象/戏剧形象填：夫差是 `male`（不是戏曲里的花脸）、西施是 `female`。
- `visual_signature` 里也要写明性别特征（如「面容清瘦，蓄短须」）—— 双重保险：
  gender 定锚点，signature 定细节。

**visual 字段里的角色描述规则**：
- ✅ 每页 visual 开头**完整重复**该角色在 `characters[]` 里的视觉签名翻译
  （不只是 "the man" 或 "Guo Ziyi"）
- ✅ 多角色场景里每个角色的核心特征都必须出现
- ✅ **第二行写 `[GENDER:xx]` 标记**（角色描述之后、ACTION 之前），三选一：
  - `[GENDER:male]` — 单人物为男性（历史典故主角最常见，如张巡 / 郭子仪 / 文天祥）
  - `[GENDER:female]` — 单人物为女性（如王昭君 / 杨贵妃 / 武则天）
  - `[GENDER:mixed]` — 男女混合场景（夫妻对坐 / 将军审问叛军女眷）
  图像 prompt 会按它自动选对应妆发分支（女性桃花腮/步摇 / 男性玉冠/玉簪/剑眉）。
  漏标记或写错会导致男性主角被性转成女子脸。
- ❌ 不要用代词（"he" / "the general" / "the khan"）省略人物身份

## 6. 输出格式（严格 JSON，不要任何解释文字，不要 markdown 代码块）

```json
{
  "title": "公众号文章标题（15-25 字）",
  "subtitle": "副标题（如「基于历史档案与流行病学研究」）",
  "summary": "导语 1-2 句话（30-50 字）",
  "preface": "卷首题词（10-20 字）",
  "epigraph": "题记（30-50 字）",
  "postscript": "后记（30-80 字，含反直觉/反常识）",
  "sources": "本文史料依据的典籍名，多部用顿号分隔（如《孙子兵法·谋攻篇》《左传·僖公三十年》）。必须与本篇题材真实相关，不得张冠李戴",
  "characters": [
    {
      "name": "角色名",
      "role": "主角",
      "era": "唐代",
      "gender": "male",
      "visual_signature": "唐代老将军, 60-70 岁, 方颌, 丹凤眼, 剑眉, 蓄短须, 戴黑色软脚幞头, 穿朱砂色圆领窄袖袍配玉带蹀躞带, 身形清瘦挺拔"
    }
  ],
  "pages": [
    {
      "page": 1,
      "highlight": "1347",
      "visual": "第一段必须是 CONCEPT 段，其后按七要素组织（见 §4.2），开头列角色五件套 + [GENDER:xx]，每段末尾附 // 中文速记，末尾写 STRICT NO TEXT 强化句",
      "caption": "场景说明（中文 10-20 字）",
      "dialogue": "文言原文引句（8-50 字，出自《史记》/《左传》等，每页必填）",
      "narration": "旁白或空字符串",
      "body": "正文（严格 100-150 字，3-5 个短句，现代白话，三拍结构）",
      "keywords": ["人名", "地名", "朝代", "事件", "官职"],
      "punchline": "白话点题金句（10-22 字）",
      "key_visual": "视觉锚点"
    }
  ]
}
```

注意 `"gender"` 的值是**裸字符串** `"male"`，不是 `{"enum": ["male","female"]}`，
也不是数组或对象。`"era"` 同理是字符串。

## 7. 朝代服饰考据（仅历史题材需要，速查表见系统提示末尾）

**每个角色必填 `era`，`visual_signature` 必须严格按该 era 对应的朝代速查表写。**
preflight 会用 `ANACHRONIC_MARKERS` 事后阻塞后世器物，但**它拦不住你没写**，
所以这一步必须在拆镜时就做对。

自检两条：
- **单件错配**：春秋角色写「圆领袍 / 武冠 / 幞头」= 唐/汉/宋的元素，拆开重写。
- **三件错配**：「圆领袍 + 武冠 + 幞头」同时出现 = 三朝错配，立即重写。
  「乌纱帽 + 补子」用于明以前 = 明代错配。「顶戴花翎 + 朝珠」用于清以前 = 清代错配。

不要因为「画面好看」而用后世元素 —— 戴敦邦派连环画追求的是**考据工笔**，
穿错朝代直接破坏沉浸感。
"""


# --- 朝代速查表：条件注入（v0.3.24）--------------------------------------
#
# 速查表正文**只存一份**，在 prompts.CN_DYNASTY_COSTUME_GUIDE（preflight 用的
# 同一份）。v0.3.23 之前它在 planner prompt 里被**内联复制**了一份扩写版，
# 两者已经各自漂移；而且它无条件发给每一次调用 —— 跑「峰终定律」这种
# 经济学题材时，1.2K~2K 字的朝代服饰表是纯噪声，白占 token 和模型注意力。
#
# 现在按 style_id 决定是否挂载：三个中国古典风格才注入。
# 这样历史题材的考据约束一点没丢，非历史题材不再为无关参考数据付费。

def _era_guide_for(style_id: str) -> str:
    """历史/古典风格才返回朝代速查表，其余返回空串。"""
    if style_id not in _CN_HISTORY_STYLES:
        return ""
    try:
        from .prompts import CN_DYNASTY_COSTUME_GUIDE
    except Exception:  # pragma: no cover - 独立运行兜底
        return ""
    return (
        "\n\n---\n\n"
        "## 8. 朝代服饰速查表（本条为最高优先级，拆镜前先查表）\n\n"
        "上表的 `era` 字段决定年代 → `visual_signature` 必须严格用本表的服饰/冠帽/配饰。\n\n"
        + CN_DYNASTY_COSTUME_GUIDE.strip()
    )


def build_system_prompt(style_id: str, target_pages: int | None = None) -> str:
    """拼最终 system prompt：基础铁律 + 动态页数 + 条件朝代表。

    v0.3.24：原来是 `PLANNER_SYSTEM_PROMPT.replace(...)` 一处字符串替换，
    页数硬编码在 prompt 第一行里（"输出 6-10 页"）必须靠 replace 命中，
    改文案就会静默失效。改成显式格式化。
    """
    p = PLANNER_SYSTEM_PROMPT
    if target_pages is not None:
        p = p.replace(
            "输出 6-10 页分镜脚本（JSON 格式）",
            f"输出 {target_pages} 页分镜脚本（JSON 格式）",
        )
    return p + _era_guide_for(style_id)


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

    # 动态 system prompt：页数 + 条件朝代表（v0.3.24 走 build_system_prompt）
    sys_prompt = build_system_prompt(style_id, target_pages=target_pages)

    logger.info("Planner LLM call: model=%s, topic=%s, bullets=%d, target_pages=%d, "
                "sys_prompt=%d chars, era_guide=%s",
                cfg.llm_model, topic[:30], len(bullets), target_pages,
                len(sys_prompt), "on" if _era_guide_for(style_id) else "off")

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
        sources=data.get("sources", ""),
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