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

图文分离铁律（沿用 baoyu-comic）：
  - caption/对话/旁白/body → 进 HTML 文章层
  - visual 只描述画面（不含文字）
  - 跑图 prompt 不允许生成对话气泡、字幕、招牌文字
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
      "visual": "画面描述（英文 30-80 词）",
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


def _call_llm_storyboard(topic: str, bullets: list[str], style_id: str, canon_injection: str = "") -> Storyboard:
    cfg = get_config()
    if not cfg.llm_api_key or cfg.llm_api_key.startswith("sk-placeholder"):
        raise RuntimeError(
            "LLM_API_KEY not configured. Fill it in .env, "
            "or call mock_storyboard() instead."
        )

    client = OpenAI(api_key=cfg.llm_api_key, base_url=cfg.llm_base_url)
    user_msg = _build_planner_user_msg(topic, bullets, style_id, canon_injection)

    logger.info("Planner LLM call: model=%s, topic=%s, bullets=%d",
                cfg.llm_model, topic[:30], len(bullets))

    try:
        resp = client.chat.completions.create(
            model=cfg.llm_model,
            messages=[
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
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
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.S)
    if m:
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    if data is None:
        # 尝试找最后一个完整 {...}
        m = re.search(r"\{[\s\S]*\}\s*$", content)
        if m:
            try:
                data = json.loads(m.group(0))
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


def mock_storyboard(topic: str, bullets: list[str], style_id: str) -> Storyboard:
    """无 LLM 时的占位 storyboard（沿用 baoyu-comic 经验 + 零文字铁律）。"""
    pages: list[StoryPage] = []

    # 第 1 页：开场（视觉锚点 = 卡通狐狸，画面无文字）
    pages.append(StoryPage(
        page=1,
        visual=(
            "A friendly cartoon fox standing in front of a giant floating question mark, "
            "gesturing welcomingly with both paws, hand-drawn style, clean ink lines, "
            "cream paper background, NO text anywhere."
        ),
        caption="今天聊聊一个话题。",
        dialogue="（狐狸在招手）",
        narration="",
        key_visual="friendly cartoon fox",
    ))

    # 中间页：每条 bullet 一页（visual 只描述画面，不含文字）
    for i, bullet in enumerate(bullets, start=2):
        pages.append(StoryPage(
            page=i,
            visual=(
                f"A clear illustration of a single visual metaphor for: {bullet[:60]}. "
                f"Friendly hand-drawn characters, clear composition, soft palette, "
                f"ABSOLUTELY NO TEXT, NO labels, NO arrows-with-words."
            ),
            caption=bullet[:25] + ("…" if len(bullet) > 25 else ""),
            dialogue="",
            narration=bullet if len(bullet) < 50 else "",
            key_visual="same cartoon fox narrator",
        ))

    # 最后一页：结尾金句
    pages.append(StoryPage(
        page=len(pages) + 1,
        visual=(
            "The cartoon fox giving a thumbs up, warm encouraging atmosphere, "
            "subtle sparkles around, NO text on image."
        ),
        caption="所以，下次再遇到类似场景——",
        dialogue="（狐狸竖起拇指）",
        narration="懂这个话题的人，不过是把它当成一件平常事。",
        key_visual="same cartoon fox narrator",
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
    style_id: str = "cn_contemporary",
    use_llm: bool = True,
    canon_injection: str = "",
) -> Storyboard:
    if use_llm:
        try:
            return _call_llm_storyboard(topic, bullets, style_id, canon_injection)
        except RuntimeError as e:
            logger.warning("LLM unavailable (%s), falling back to mock storyboard", e)
            return mock_storyboard(topic, bullets, style_id)
    return mock_storyboard(topic, bullets, style_id)