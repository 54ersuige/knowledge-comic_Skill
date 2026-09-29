"""跑图后 LLM 视觉审核（v0.3.15 新增）。

**为什么需要**：preflight 只能查**输入**，查不了**输出**。苏武项目里真正烧掉
额度的返工，全部发生在跑图之后 —— 画风漂移、性别画反、图上冒出字。
这些**只能看图才知道**，正则永远查不出来。

**已验证能力**：`agnes-3.0-flash`（`https://apihub.agnes-ai.cn/v1`）支持视觉
输入，对 p9 图能准确回答"2 人、都是男性、无文字"。

**设计原则（与 preflight 一致）**：
  1. **宁可漏报也不误报** —— LLM 视觉判断本身有方差，所以每条 finding 带
     `confidence`，只有高置信度才升级为 block。低置信度一律 warn，且
     提示人工复核。**绝不让不可靠的自动判断拦住用户的流程**。
  2. **不阻塞主流程** —— 审核失败（网络/超时/模型报错）绝不抛异常打断跑图，
     降级为一条 warn。审核是辅助，不是单点。
  3. **逐页串行** —— 并发会打爆配额且难以归因哪张图对应哪条 finding。

**与 preflight 的分工**：
  preflight 查"描述写得对不对"（跑图前，0 成本）
  visual_qa 查"图画得对不对"（跑图后，有成本但比返工便宜得多）
"""
from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# 视觉审核的置信度门槛 —— 只有 >= 该值的 finding 才升级为 block。
# 低于此值一律 warn，理由：LLM 视觉判断有方差，误报的代价（用户开始无视
# 整个审核层）远大于漏报。
BLOCK_CONFIDENCE = 0.85

# 画风锚点：每种风格问 LLM 的判定问题不同。
# 只问**能被单图回答**的问题，不问需要跨页对比的问题（单图看不出来）。
STYLE_QUESTIONS = {
    "chinese_lianhuanhua_classic": (
        "Is the whole image rendered as a classical Chinese lianhuanhua "
        "(连环画) painted illustration on rice paper, in the Dai Dunbang / "
        "He Youzhi tradition — brush lines, flat mineral pigment washes, "
        "visible paper texture, muted earth palette?"
    ),
    "cn_xuanfeng": (
        "Is the whole image a traditional Chinese ink-wash painting "
        "(水墨写意) on rice paper — flying-white brushwork, vermilion accents, "
        "generous empty space?"
    ),
    "guochao_manhua": (
        "Is the whole image a modern Chinese manhua / guochao cel-shaded "
        "illustration — flat vibrant colour blocks, clean line art, "
        "contemporary comic panel language?"
    ),
}

DEFAULT_STYLE_QUESTION = (
    "Does the whole image share one consistent, deliberate illustration "
    "style (not a mix, not a photograph, not a 3D render)?"
)


@dataclass
class VisualFinding:
    page: int
    level: str            # "block" / "warn"
    code: str
    msg: str
    confidence: float
    evidence: str = ""

    def report_line(self) -> str:
        where = f"p{self.page:02d}"
        c = f" (置信 {self.confidence:.0%})" if self.confidence < 0.99 else ""
        line = f"[{self.code}] {where}{c}：{self.msg}"
        if self.evidence:
            line += f"\n        依据：{self.evidence}"
        return line


@dataclass
class VisualQAResult:
    findings: list[VisualFinding] = field(default_factory=list)
    checked: int = 0
    skipped: int = 0
    error: str = ""

    @property
    def blocks(self) -> list[VisualFinding]:
        return [f for f in self.findings if f.level == "block"]

    @property
    def warns(self) -> list[VisualFinding]:
        return [f for f in self.findings if f.level == "warn"]

    @property
    def ok(self) -> bool:
        return not self.findings

    def report(self) -> str:
        if not self.findings:
            head = f"✅ 视觉审核通过（{self.checked} 页"
            return head + ("，有页面未能审核）\n" if self.skipped else "）\n")
        lines = [f"共审核 {self.checked} 页"]
        if self.blocks:
            lines.append(f"🔴 高置信问题 {len(self.blocks)} 个 —— 建议重画")
            lines += [f"   {f.report_line()}" for f in self.blocks]
        if self.warns:
            lines.append(f"🟡 待人工确认 {len(self.warns)} 个")
            lines += [f"   {f.report_line()}" for f in self.warns]
        if self.error:
            lines.append(f"⚠️ {self.error}")
        return "\n".join(lines)


# --- LLM 调用 ---------------------------------------------------------------

def _encode_image(path: Path) -> str:
    """PNG → data URL。Agnes 的 OpenAI 兼容接口吃标准 data URL。"""
    b = path.read_bytes()
    return "data:image/png;base64," + base64.b64encode(b).decode()


def _build_prompt(style_id: str, page: dict) -> str:
    """审核 prompt —— 强制 JSON 输出，便于解析。"""
    q = STYLE_QUESTIONS.get(style_id, DEFAULT_STYLE_QUESTION)
    # 只喂**人看的中文速记 + caption**，不喂整段英文 visual ——
    # 英文七要素又长又噪，会稀释模型的观察力。速记是最有效的画面索引。
    note = ""
    m = re.search(r"//\s*([^\n]+)", page.get("visual") or "")
    if m:
        note = m.group(1).strip()
    return f"""你是连环画画稿质检员。只依据图像本身作答，不要推测。

画面意图（中文速记，仅供你核对，不要写进答案）：{note or page.get('caption') or '无'}

逐项判断，每项给出 0-1 的置信度：

1. "style_ok" —— {q}
2. "has_text" —— 画面里**是否出现任何可读文字**（汉字、字母、数字、符号、
   书法、匾额、旗帜上的字、卷轴上的字）？模型常在织物/卷轴上"补"纹样字符。
3. "people" —— 画面里有几个人？列出每个人的性别（male/female/unclear）。
4. "note_consistent" —— 画面内容与上面的画面意图是否一致？

严格输出这个 JSON，不要任何其他文字：
{{"style_ok": [true/false, 0-1],
 "has_text": [true/false, 0-1],
 "people": [{{"gender": "male/female/unclear", "desc": "一句话"}}],
 "note_consistent": [true/false, 0-1],
 "evidence": "一句话说明你看到了什么"}}"""


def _parse_reply(text: str) -> dict:
    """解析 LLM 回复。容忍 markdown 包裹、思考标签、尾随文字。"""
    t = text.strip()
    t = re.sub(r"<think>[\s\S]*?</think>", "", t).strip()
    m = re.search(r"```(?:json)?\s*\n?([\s\S]*?)```", t)
    if m:
        t = m.group(1).strip()
    if not t.startswith("{"):
        i = t.find("{")
        if i < 0:
            raise ValueError(f"回复里找不到 JSON: {text[:120]!r}")
        t = t[i:]
    depth, end = 0, -1
    for i, ch in enumerate(t):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end < 0:
        raise ValueError("JSON 括号不配对")
    return json.loads(t[:end])


_TRUTHY = {"yes", "true", "y", "1", "是", "有", "对"}
_FALSY = {"no", "false", "n", "0", "否", "无", "错"}


def _norm_pair(v) -> tuple[bool, float]:
    """LLM 返回的 [bool, confidence] 元组，归一化。

    容忍三种形态：标准二元组 / 裸 bool / 裸字符串。
    裸值一律按**低置信 0.5** 处理 —— 形态不规范本身就是不确定的信号，
    不该拿它当高置信结论去阻塞用户的流程。
    """
    if isinstance(v, (list, tuple)) and len(v) >= 2:
        try:
            return bool(v[0]), float(v[1])
        except (TypeError, ValueError):
            return False, 0.0
    if isinstance(v, bool):
        return v, 0.5
    if isinstance(v, str):
        s = v.strip().lower()
        if s in _TRUTHY:
            return True, 0.5
        if s in _FALSY:
            return False, 0.5
    return False, 0.0


# --- 单页审核 ---------------------------------------------------------------

def audit_page(img_path: Path, page: dict, style_id: str) -> list[VisualFinding]:
    """审一页。失败返回一条 warn，不抛异常 —— 审核不能打断主流程。"""
    from openai import OpenAI

    from scripts.core.config import get_config

    pg_no = int(page.get("page") or _page_no_from_name(img_path))
    cfg = get_config()
    client = OpenAI(api_key=cfg.llm_api_key, base_url=cfg.llm_base_url,
                    timeout=90.0, max_retries=1)

    try:
        resp = client.chat.completions.create(
            model=cfg.llm_model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": _build_prompt(style_id, page)},
                    {"type": "image_url",
                     "image_url": {"url": _encode_image(img_path)}},
                ],
            }],
            temperature=0.1,       # 审核要稳定，不要创造性
        )
        data = _parse_reply(resp.choices[0].message.content or "")
    except Exception as e:
        logger.warning("visual_qa p%02d 审核失败: %s", pg_no, e)
        return [VisualFinding(pg_no, "warn", "QA_ERROR",
                              f"视觉审核失败，无法判断本图：{e}",
                              0.0, "网络/模型异常，不是图的问题")]

    out: list[VisualFinding] = []
    ev = str(data.get("evidence", ""))[:120]

    # --- 图上出字（本项目最常复发的 bug）---
    has_text, c_text = _norm_pair(data.get("has_text"))
    if has_text:
        level = "block" if c_text >= BLOCK_CONFIDENCE else "warn"
        out.append(VisualFinding(
            pg_no, level, "TEXT_ON_IMAGE",
            "画面里出现了文字", c_text, ev))

    # --- 画风漂移 ---
    style_ok, c_style = _norm_pair(data.get("style_ok"))
    if not style_ok:
        level = "block" if c_style >= BLOCK_CONFIDENCE else "warn"
        out.append(VisualFinding(
            pg_no, level, "STYLE_DRIFT",
            f"画风与 {style_id} 不符（可能漂到现代写实/3D/彩绘）",
            c_style, ev))

    # --- 人物性别（p9 常惠事故的通用形态）---
    expected = _expected_genders(page)
    people = data.get("people") or []
    if isinstance(people, list):
        got = [str(p.get("gender", "unclear")).lower()
               for p in people if isinstance(p, dict)]
        n_exp, n_got = len(expected), len(got)
        if n_exp and n_got and n_got != n_exp:
            conf = 0.6
            out.append(VisualFinding(
                pg_no, "warn", "PEOPLE_COUNT",
                f"画面 {n_got} 人，描述预期 {n_exp} 人"
                f"（描述要求 {'/'.join(expected)}）", conf, ev))
        fem = sum(1 for g in got if g == "female")
        exp_fem = expected.count("female")
        if expected and n_exp == 1 and exp_fem == 0 and fem == 1:
            out.append(VisualFinding(
                pg_no, "block", "GENDER_WRONG",
                "描述要求男性，图里画成了女性", 0.9, ev))

    # --- 图画不符 ---
    ok, c_note = _norm_pair(data.get("note_consistent"))
    if not ok:
        level = "block" if c_note >= BLOCK_CONFIDENCE else "warn"
        out.append(VisualFinding(
            pg_no, level, "NOTE_MISMATCH",
            "画面与画面意图不符", c_note, ev))

    return out


def _page_no_from_name(p: Path) -> int:
    m = re.match(r"(\d+)", p.stem)
    return int(m.group(1)) if m else 0


def _expected_genders(page: dict) -> list[str]:
    """从 visual 的 [GENDER:xx] 标记读出本页预期性别列表。"""
    v = page.get("visual") or ""
    return [g.lower() for g in re.findall(r"\[GENDER:(\w+)\]", v, re.I)]


# --- 主入口 -----------------------------------------------------------------

def run_visual_qa(
    job_id: str,
    data_dir: Path | None = None,
    pages: list[int] | None = None,
    style_id: str = "",
) -> VisualQAResult:
    """审整个 job（或指定页）。

    Args:
        job_id: job id
        pages: 只审这几页；None = 全部
        style_id: 为空则从 storyboard.json 读
    """
    from scripts.core.config import get_config

    res = VisualQAResult()
    cfg = get_config()
    work_dir = (data_dir or cfg.data_dir) / job_id
    sb_path = work_dir / "storyboard.json"

    if not cfg.llm_api_key or cfg.llm_api_key.startswith("sk-placeholder"):
        res.error = "LLM_API_KEY 未配置，视觉审核跳过"
        return res
    if not sb_path.exists():
        res.error = f"storyboard.json 不存在：{sb_path}"
        return res

    sb = json.loads(sb_path.read_text(encoding="utf-8"))
    style_id = style_id or sb.get("style_id", "")
    by_page = {p.get("page"): p for p in sb.get("pages", [])}

    imgs = sorted((work_dir / "pages").glob("*.png"))
    if not imgs:
        res.error = f"没有找到图片：{work_dir / 'pages'}"
        return res

    for img in imgs:
        no = _page_no_from_name(img)
        if pages and no not in pages:
            continue
        page = by_page.get(no, {"page": no, "visual": "", "caption": ""})
        res.findings.extend(audit_page(img, page, style_id))
        res.checked += 1

    if res.checked < len(imgs):
        res.skipped = len(imgs) - res.checked
    return res
