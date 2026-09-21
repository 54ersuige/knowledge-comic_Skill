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
3. body（长段落正文，≥ 80 字，三联/远川式）
4. key_visual（视觉锚点，跨章保持）

## 铁律

1. 每页 visual 只描述画面场景/人物动作/构图，不写对话、不写旁白
2. 每页 caption 1 行（10-20 字），是场景说明
3. dialogue/narration 进文章，不要写进 image prompt
4. body 字段（如果是中国故事/典故/经典解读）：≥ 80 字长段落正文
5. 第 1 页通常是"开场"，最后一页是"金句结尾"
6. 结尾 postscript ≤ 80 字 + 含反直觉/反常识
7. **绝对禁止**写"按照X风格"、"在Y视角下"、"本研究"、"以下内容将"等元叙事或程式化引导语

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
  "pages": [
    {
      "page": 1,
      "highlight": "1347",
      "visual": "画面描述（英文 80-150 词，必须按 v0.2.3 七要素结构组织：SUBJECT / ACTION / CAMERA 四件套 / PLACEMENT / DEPTH LAYERS / LIGHTING / MOOD；开头列角色五件套；选 1 个 expression anchor）",
      "caption": "场景说明（中文 10-20 字）",
      "dialogue": "对话或空字符串",
      "narration": "旁白或空字符串",
      "body": "长段落正文（≥ 80 字，三联/远川式）",
      "key_visual": "视觉锚点"
    }
  ]
}
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

    client = OpenAI(api_key=cfg.llm_api_key, base_url=cfg.llm_base_url)
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
            body=p.get("body", ""),
            key_visual=p.get("key_visual", ""),
            highlight=p.get("highlight", ""),
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
    )


def mock_storyboard(
    topic: str,
    bullets: list[str],
    style_id: str,
    num_pages: int | None = None,
) -> Storyboard:
    """无 LLM 时的占位 storyboard。角色按主题时代自适应。

    num_pages: 显式目标页数（None = 自动按 recommend_pages 推荐）。
    注意：mock 模式下页数实际由 bullets 数 + 起页 + 结尾页决定，
    num_pages 仅作 informational 输出（actual LLM 模式下才严格生效）。
    """
    pages: list[StoryPage] = []

    # 角色锚点（按 style_id 选）
    if style_id == "cn_xuanfeng":
        character = "A Han-Chinese historical person in traditional hanfu robe (crossed collar, wide sleeves, sash belt, hair pinned in classical style with subtle ornaments), serene contemplative expression, age 20-30, rendered with elegant elongated proportions typical of classical Chinese figure painting"
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
            return _call_llm_storyboard(topic, bullets, style_id, canon_injection)
        except RuntimeError as e:
            logger.warning("LLM unavailable (%s), falling back to mock storyboard", e)
            return mock_storyboard(topic, bullets, style_id, num_pages)
    return mock_storyboard(topic, bullets, style_id, num_pages)