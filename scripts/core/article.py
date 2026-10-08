"""Article - storyboard -> WeChat-compatible HTML + 4 排版模板.

Templates:
  A. 撕纸手账风      - 情感/旅行/文艺随笔
  B. 复古报纸风      - 历史/商业评论/老物件
  C. 中国古典故事专版 - 历史典故/古籍解读/经典文章（重做，加开头结尾）
  D. 多巴胺手绘卡片  - 科普/教育/亲子

图文分离铁律（沿用 baoyu-comic）：
  - caption 1 行（10-20 字）
  - dialogue 加粗或带引号
  - narration 斜体
  - body 长段落正文（中国故事专用，进文章层）
  - 不重复画面已表达内容
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

from .planner import Storyboard


@dataclass
class ArticleInput:
    storyboard: Storyboard
    page_image_urls: list[str]
    title: str | None = None
    # v0.3.18：文末史料出处。原先模板 c 把「《旧唐书》与回纥外交档案考略」
    # **硬编码**在渲染函数里（v0.2.8.0 加的脚注），任何非唐代题材都会撞上
    # 完全不搭的出处（实测「不战而屈人之兵」项目印出旧唐书/回纥）。
    # 现在改为参数：优先用调用方传入（run.py 从 storyboard.sources 取），
    # 没传就回退到中性说法，不再冒充具体典籍。
    sources: str | None = None


def _esc(s: str) -> str:
    return html.escape(s, quote=True)


# ========== Mock 内容：昭君出塞（中国古典故事专版示例） ==========
def _mock_pages_classic() -> list[dict]:
    return [
        {
            "page": 1,
            "caption": "汉元帝竟宁元年（前 33 年），南郡秭归一户普通人家，诞生了一个女孩。",
            "dialogue": "",
            "narration": "",
            "body": (
                "汉元帝竟宁元年（前 33 年），南郡秭归一户普通人家，"
                "诞生了一个女孩，名嫱，字昭君。这家人原本姓王，"
                "因避秦末战乱南迁至此，已历数代。家中无显赫背景，"
                "只在乡间略有田产。父亲王襄老识斃，托兄长王曼抚养。"
                "这一年汉朝与匈奴的关系再度紧张。"
            ),
        },
        {
            "page": 2,
            "caption": "画师毛延寿未曾受赂，将王嫱的画像画得格外平庸。",
            "dialogue": "",
            "narration": "",
            "body": (
                "汉元帝下诏广选良家女入宫。王嫱虽出身平凡，"
                "却因容貌出众被选入掖庭。然而画师毛延寿"
                "索贿不成，故意将她的画像画得略显平庸。"
                "汉元帝凭画像选人，便将她列入末等。"
                "王嫱入宫多年，竟未得见天子一面。"
            ),
        },
        {
            "page": 3,
            "caption": "后宫中王嫱始终未曾获得临幸，孤独地度过一年又一年。",
            "dialogue": "",
            "narration": "",
            "body": (
                "汉元帝后宫数千良家女，皆因画像未曾面君。"
                "王嫱起初还抱有几分期待，"
                "然而一年又一年过去，她始终未曾获得临幸。"
                "宫中岁月磨去了少女的心气，"
                "她只能在琵琶与琴声中度过漫长的等待。"
            ),
        },
        {
            "page": 4,
            "caption": "匈奴呼韩邪单于入朝请求和亲，汉廷欲遣一女远嫁。",
            "dialogue": "",
            "narration": "",
            "body": (
                "匈奴呼韩邪单于入朝请求和亲，"
                "以保北部边境安宁。汉元帝欲从后宫选派一女远嫁。"
                "消息传出，后宫一片哀戚——"
                "谁都知道，远嫁匈奴意味着永别故土，再无归期。"
                "王嫱却主动请行。"
            ),
        },
        {
            "page": 5,
            "caption": "元帝召见王嫱，方知她便是当年被画师埋没的绝色。",
            "dialogue": "",
            "narration": "",
            "body": (
                "汉元帝召见即将出塞的王嫱，"
                "方知她便是当年被画师埋没的绝色。"
                "但和亲已成定局，无法反悔。"
                "元帝悔之晚矣，只能眼睁睁看着"
                "这位绝世佳人远嫁塞外。"
            ),
        },
        {
            "page": 6,
            "caption": "昭君盛装出塞，途经秦中，元帝一望倾城。",
            "dialogue": "",
            "narration": "",
            "body": (
                "王嫱盛装出塞，途经秦中。"
                "汉元帝一望倾城，欲留不能。"
                "她怀抱琵琶，回首长安。"
                "元帝这才明白，画师所误的不仅是王嫱，"
                "更是大汉与匈奴的一段姻缘。"
            ),
        },
        {
            "page": 7,
            "caption": "昭君出塞前恳请随行子女，匈奴单于一概允准。",
            "dialogue": "",
            "narration": "",
            "body": (
                "王嫱出塞前恳请：愿带所生子女随行，"
                "以延续汉匈血脉。匈奴单于一一允准。"
                "她带着对未来的一丝期许，"
                "踏上了通往草原的漫漫长路。"
            ),
        },
        {
            "page": 8,
            "caption": "昭君抵达匈奴，被封为宁胡阏氏，育有子女。",
            "dialogue": "",
            "narration": "",
            "body": (
                "王嫱抵达匈奴，被封为宁胡阏氏，"
                "意为「匈奴的安宁」。她为呼韩邪单于育有二女，"
                "在草原上度过了数十年的岁月。"
                "她带来了汉朝的文化与和平，"
                "也让匈奴与汉朝维持了六十余年的边境安宁。"
            ),
        },
    ]


def _placeholder_img(label: str, h: int = 200) -> str:
    return (
        f'<div style="background:linear-gradient(135deg,#e8e3d8 0%,#d8d2c4 100%);'
        f'width:100%;height:{h}px;border-radius:inherit;'
        f'display:flex;align-items:center;justify-content:center;'
        f'color:#8a857c;font-size:13px;">'
        f'📷 {label}</div>'
    )


# ========== 模板 A：撕纸手账风 ==========
def render_template_a(inp: ArticleInput) -> str:
    """A. 撕纸手账风（情感/旅行/文艺随笔）"""
    sb = inp.storyboard
    title = inp.title or sb.title
    paper_clip = (
        "polygon(0% 2%, 3% 0%, 6% 1%, 9% 0%, 12% 2%, 15% 0%, 18% 1%, 21% 0%, "
        "24% 2%, 27% 0%, 30% 1%, 33% 0%, 36% 2%, 39% 0%, 42% 1%, 45% 0%, "
        "48% 2%, 51% 0%, 54% 1%, 57% 0%, 60% 2%, 63% 0%, 66% 1%, 69% 0%, "
        "72% 2%, 75% 0%, 78% 1%, 81% 0%, 84% 2%, 87% 0%, 90% 1%, 93% 0%, "
        "96% 2%, 100% 0%, 100% 100%, 0% 100%)"
    )
    out = ['<section data-template="a">']
    out.append(
        '<div style="position:relative;background:#fef3c7;padding:32px 20px 20px;'
        f'clip-path:{paper_clip};margin:20px 0;">'
        '<div style="position:absolute;top:-8px;left:20px;width:60px;height:18px;'
        'background:rgba(255,200,100,0.7);transform:rotate(-5deg);"></div>'
        '<div style="position:absolute;top:-8px;right:30px;width:50px;height:18px;'
        'background:rgba(150,200,255,0.7);transform:rotate(3deg);"></div>'
        f'<h1 style="font-family:STKaiti,KaiTi,楷体,serif;font-style:italic;'
        f'font-size:22px;color:#2a2620;text-align:center;margin:0;">'
        f'✨ {_esc(title)} ✨</h1>'
        f'<p style="font-family:STKaiti,KaiTi,楷体,serif;text-align:center;'
        f'color:#8b6b3a;font-size:13px;margin:8px 0 0;">{_esc(sb.summary)}</p>'
        '</div>'
    )
    for i, page in enumerate(sb.pages):
        tape_color = ["#fde68a", "#bae6fd", "#fbcfe8", "#bbf7d0", "#fed7aa"][i % 5]
        out.append(
            f'<div style="position:relative;background:#fffbeb;'
            f'padding:20px;margin:24px 8px;border:1px solid #fde68a;'
            f'border-radius:4px;box-shadow:2px 3px 8px rgba(0,0,0,0.05);'
            f'transform:rotate({(-1)**i * 0.5:.1f}deg);">'
            f'<div style="position:absolute;top:-10px;left:30px;width:60px;height:18px;'
            f'background:{tape_color};opacity:0.7;transform:rotate(-3deg);"></div>'
        )
        if page.caption:
            out.append(
                f'<p style="font-family:STKaiti,KaiTi,楷体,serif;'
                f'font-size:16px;color:#2a2620;margin:0 0 8px;">'
                f'📌 {_esc(page.caption)}</p>'
            )
        if page.dialogue:
            out.append(
                f'<p style="font-family:STKaiti,KaiTi,楷体,serif;'
                f'font-style:italic;font-size:15px;color:#b45309;'
                f'margin:8px 0;padding-left:12px;border-left:3px solid #f59e0b;">'
                f'「{_esc(page.dialogue)}」</p>'
            )
        if page.narration:
            out.append(
                f'<p style="font-family:STKaiti,KaiTi,楷体,serif;'
                f'font-style:italic;font-size:14px;color:#92400e;'
                f'margin:8px 0;">— {_esc(page.narration)}</p>'
            )
        if i < len(inp.page_image_urls):
            url = inp.page_image_urls[i]
            out.append(
                f'<div style="margin:12px 0;transform:rotate({(-1)**(i+1) * 1:.1f}deg);">'
                f'<img src="{_esc(url)}" '
                f'style="width:90%;border:6px solid white;'
                f'box-shadow:0 4px 12px rgba(0,0,0,0.15);" data-page="{page.page}" />'
                f'</div>'
            )
        out.append('</div>')
    if sb.pages:
        last = sb.pages[-1]
        if last.narration:
            out.append(
                '<div style="text-align:center;margin:32px 16px;padding:24px;'
                'background:#fef3c7;border:2px dashed #f59e0b;border-radius:8px;'
                'transform:rotate(-1deg);">'
                f'<p style="font-family:STKaiti,KaiTi,楷体,serif;font-style:italic;'
                f'font-size:18px;color:#92400e;margin:0;">'
                f'「{_esc(last.narration)}」</p>'
                '<p style="font-size:11px;color:#a16207;margin:8px 0 0;">— 完 —</p>'
                '</div>'
            )
    out.append('</section>')
    return "\n".join(out)


# ========== 模板 C：中国古典故事专版（v2 精细化版） ==========
_CN_NUMS = "壹贰叁肆伍陆柒捌玖拾"

def _cn_section(n: int) -> str:
    """章节中文数字。1-10 用「壹贰叁...」，>10 用阿拉伯。"""
    return _CN_NUMS[n - 1] if 1 <= n <= 10 else f"{n:02d}"


def _extract_highlight(caption: str, body: str, page_no: int) -> str:
    """从 caption/body 自动提取章节大字标识。

    优先级：
      1. body 中的 X/N 分数或 N% 数字
      2. caption 中的 4 位年份
      3. caption 第一个 2-4 字关键词（冒号后）
      4. 兜底「第 N 章」
    """
    body = body or ""
    # 1. 分数或百分比
    m = re.search(r"(\d+/\d|\d+%)", body)
    if m:
        return m.group(1)
    # 2. caption 年份
    m = re.search(r"(\d{3,4})", caption or "")
    if m:
        return m.group(1)
    # 3. caption 冒号后关键词
    if caption:
        for sep in ("：", ":"):
            if sep in caption:
                kw = caption.split(sep, 1)[1].strip().split()[0]
                if 1 <= len(kw) <= 4:
                    return kw
    return f"第{page_no:02d}章"


def _extract_quote(body: str) -> str:
    """从 body 提取完整章节要点（不再截断！v0.2.7.5）。

    优先级：
      1. 引号内容（最高优先，因为是直接引述）
      2. 第一句（保留完整，不截断）
      3. 第一段（如果第一句为空）

    返回完整文本，确保读者能看完整段。
    """
    body = (body or "").strip()
    if not body:
        return ""
    # 1. 引号内容
    m = re.search(r"「([^」]{2,200})」", body)
    if m:
        return m.group(1).strip()
    # 2. 第一句完整 (到第一个 。)
    first_sentence = body.split("。")[0].strip()
    if first_sentence:
        return first_sentence + "。"  # 补回句号
    # 3. 整个 body 第一段（到换行）
    return body.split("\n")[0].strip()


# === v0.2.7.4: body 文字关键词标记 ===
# 自动识别关键人名/年份/地点/事件，用朱砂色+加粗包裹
_HIGHLIGHT_KEYWORDS: list[str] = [
    # 人名（按长度倒序，避免短词先匹配）
    "郭子仪", "药葛罗", "仆固怀恩", "郭令公",
    "安禄山", "史思明", "唐肃宗", "唐代宗",
    "李光弼", "李豫", "李俶",
    # 民族/政权
    "回纥", "吐蕃", "唐帝国", "唐朝", "朝廷",
    # 地点
    "长安", "渭水", "邺城", "范阳", "灵武", "洛阳",
    # 关键事件
    "安史之乱", "永泰元年", "广德元年",
    # 关键概念
    "兄弟盟", "单骑闯营", "翻身下马",
]


def _split_paragraphs(text: str, max_len: int = 42,
                      merge_short: bool = True,
                      max_paras: int | None = None) -> list[str]:
    """把长正文切成 2-3 个短段 —— 公众号读者没耐心读一整块 150 字。

    v0.3.8：用户反馈「不要出现大段大段文字」。
    切分原则：
      1. 先按句号/问号/叹号断句（**引号内的句末标点不切**，
         否则会出现裸露的 `”` 这种碎片）
      2. 句子仍超长（>max_len）再按逗号/分号二次切
      3. merge_short=True 时合并过短的相邻片段，避免「3 个字一段」的碎片；
         纯拆句场景传 False（每句都独立成段）
    """
    if not text:
        return []

    # 按句末标点切，但要在引号闭合后才算真正结束：
    # “…说。”后面如果紧跟右引号/右括号，一并归入本句。
    raw = re.findall(r"[^。！？!?]*[。！？!?]+[”’\"')\]】]*|[^。！？!?]+$", text)
    parts = [p.strip() for p in raw if p.strip()]

    out: list[str] = []
    for p in parts:
        if len(p) <= max_len:
            out.append(p)
            continue
        # 超长句：按逗号/分号二次切，同样避开引号内
        subs = re.findall(r"[^，,；;：:]+[，,；;：:]?[”’\"')\]】]*", p)
        subs = [s.strip() for s in subs if s.strip()]
        buf = ""
        for s in subs:
            if buf and len(buf) + len(s) > max_len:
                out.append(buf)
                buf = s
            else:
                buf += s
        if buf:
            out.append(buf)

    if not merge_short:
        return _balance_paragraphs(out, max_paras)

    merged: list[str] = []
    for p in out:
        if merged and len(merged[-1]) < 12:
            merged[-1] += p
        else:
            merged.append(p)
    return _balance_paragraphs(merged, max_paras)


def _balance_paragraphs(paras: list[str], max_paras: int | None) -> list[str]:
    """把段数压到 <= max_paras，且各段长度尽量均衡。

    v0.3.18（图为主 · 降文字密度）：只靠 `max_len` 压不住段数。
    `max_len` 只在**单句超长**时才二次切分，而 120 字正文常是 4 个
    各 20-50 字的短句 —— 每句都不到 max_len，于是原样切成 4 段，
    图文节奏照样被切碎。要真正落到「2-3 段」，得有一个**段数上限**。

    均衡而不是贪心从前往后塞：贪心会把前面塞成一大段、后面留短段，
    视觉上更不平衡。这里按 total/k 逐段逼近，收尾时把余量并入最后一段。
    """
    if not max_paras or len(paras) <= max_paras:
        return paras

    total = sum(len(p) for p in paras)
    k = max_paras
    target = total / k

    out: list[str] = []
    buf = ""
    for i, p in enumerate(paras):
        remaining_paras = len(paras) - i
        need = k - len(out)  # 还需要切出的段数（含当前这段）
        # 剩余段数已经等于 need：必须立刻切，否则后面没段可分
        if buf and (len(buf) >= target or remaining_paras <= need):
            out.append(buf)
            buf = ""
        buf += p
    if buf:
        out.append(buf)

    # 收尾：极端情况下仍超段数（段落全为空串等），强行并入最后一段
    while len(out) > k:
        out[-2] += out[-1]
        out.pop()

    # 均衡收尾：某段明显过长（>1.5×目标）时，把最短的相邻两段并成一段。
    # 走"图为主"排版时，一条 70+ 字的整块文字在手机上就是一堵墙，
    # 和 2 段 40-60 字的观感差别很大。合并到不再超长为止。
    def _longest(idx: int) -> int:
        return max(range(len(out)), key=lambda i: len(out[i]))

    def _adjacent_shortest() -> tuple[int, int]:
        best, bi = None, 0
        for i in range(len(out) - 1):
            s = len(out[i]) + len(out[i + 1])
            if best is None or s < best:
                best, bi = s, i
        return bi, bi + 1

    while len(out) > 2 and len(out[_longest(0)]) > 1.5 * target:
        before = max(len(x) for x in out)
        i, j = _adjacent_shortest()
        out[i] += out[j]
        del out[j]
        # 合并没让最长段变短 → 继续合只会把全文并成一段。必须停。
        # v0.3.18 实测：4 段 21/27/47/27（总 122）先并成 21+27=48，
        # 最长段仍是 74 不变；不设这个下界就会一路并成 1 段 122 字。
        if max(len(x) for x in out) >= before:
            break

    return out


def _first_sentence(text: str) -> str:
    """取第一句完整句（**含句末标点**）。

    v0.3.8 修复：原实现 `body.split("。")[0]` 会把句号吃掉，
    导致「定格瞬间」里出现裸露的右引号 `”`。
    """
    if not text:
        return ""
    m = re.search(r"^(.+?[。！？!?])", text.strip(), re.S)
    return (m.group(1) if m else text.strip()).strip()


def _highlight_keywords(text: str, extra_keywords: list[str] | None = None) -> str:
    """v0.2.7.4: 把 body 里的关键人名/年份/事件用朱砂红+加粗包裹。

    使用占位符 + 二次替换避免关键词互相嵌套冲突。

    v0.2.9: 支持 per-page extra_keywords(StoryPage.keywords),与全局 _HIGHLIGHT_KEYWORDS 合并匹配。
    """
    if not text:
        return text
    escaped = _esc(text)
    # 用占位符避免 `<span>...</span>` 内嵌 `<span>`
    placeholders: list[tuple[str, str]] = []

    def wrap(kw: str) -> str:
        ph = f"\x00P{len(placeholders)}\x00"
        replacement = (
            f'<span style="color:#9b2332;font-weight:600;">{kw}</span>'
        )
        placeholders.append((ph, replacement))
        return ph

    # 合并关键词(per-page 优先,放前面避免被全局短词抢占)
    all_keywords = list(extra_keywords or []) + list(_HIGHLIGHT_KEYWORDS)

    # 按长度倒序匹配（避免短词抢占长词子串）
    matched_text = escaped
    for kw in sorted(set(all_keywords), key=len, reverse=True):
        if kw and kw in matched_text:
            # 找到所有出现的位置，用占位符替换
            ph = wrap(kw)
            matched_text = matched_text.replace(kw, ph)
    # 把占位符替换成实际 span
    for ph, replacement in placeholders:
        matched_text = matched_text.replace(ph, replacement)
    return matched_text


def render_template_c(inp: ArticleInput) -> str:
    """C v2 · 中国古典故事专版（精细化版）

    完整结构：
      [手机框 + 米色羊皮纸背景]
      开头 = 卷首朱砂题词 + 大标题 + 副标题（朱砂装饰线）+ 导语 + 题记（朱砂竖线）+ 双线分隔
      正文 = 章节大字标识（朱砂 80px）+ 中文数字 + h2 章节题 + 图 + 长段落 + 数据卡
      结尾 = 朱砂印章 + 启示金句 + 后记

    设计参考：人物/三联/远川/半佛 等公众号深度长文模板。
    """
    sb = inp.storyboard
    # 注意：模板 c 直接读 sb 上的字段（sb.title / sb.preface / …），**不认 inp.title**；
    # 模板 a（L166）与 e（L782）走的是 `title = inp.title or sb.title`。
    # 目前所有调用点都传 title=sb.title，所以无行为差异；但若将来要支持
    # "改标题不重跑分镜"，必须让 c 也认 inp.title，否则会被静默吞掉。
    out = ['<section data-template="c-v2">']

    preface = sb.preface or "知 识 故 事"
    subtitle = sb.subtitle or ""
    epigraph = sb.epigraph or ""
    summary = sb.summary or ""
    postscript = sb.postscript or ""

    # 外层：手机框 + 米色羊皮纸背景 (v0.2.7.2 WeChat-safe — 去 box-shadow/border-radius)
    out.append(
        '<section style="background-color:#eee8da;padding:20px 0;">'
        '<section style="max-width:420px;margin:0 auto;background-color:#ffffff;'
        'overflow:hidden;padding:0;">'
    )

    # === 开篇 (v0.2.8.0: 改名"本篇要旨"+ sz1 尺寸 + 文末出处) ===
    # 1. 本篇要旨 label (11px 朱砂小标)
    out.append(
        '<p style="text-align:center;font-size:11px;color:#9b2332;'
        'letter-spacing:6px;margin:32px 20px 6px 20px;font-weight:600;">'
        '·  本 篇 要 旨  ·</p>'
    )
    # 2. 题眼 quote (18px 朱砂大字, hero quote)
    if preface:
        out.append(
            f'<p style="text-align:center;font-size:18px;color:#9b2332;'
            f'margin:0 20px 16px 20px;font-weight:600;letter-spacing:2px;'
            f'line-height:24px;font-family:STKaiti,KaiTi,楷体,serif;">'
            f'{_esc(preface)}</p>'
        )

    # 3. 导语 (summary) — 首字下沉 + 紧凑 epigraph
    if summary:
        first_char = summary[0] if summary else ''
        rest = summary[1:] if summary else ''
        # 首字下沉：朱砂大字 28px，浮动 left
        out.append(
            f'<p style="font-size:15px;color:#333;margin:16px 20px 20px 20px;'
            f'text-align:justify;font-weight:500;line-height:24px;">'
            f'<span style="float:left;font-size:30px;color:#9b2332;'
            f'font-weight:700;line-height:24px;padding:2px 6px 0 0;">'
            f'{_esc(first_char)}</span>{_esc(rest)}</p>'
        )
        # epigraph 作为独立 quote block，紧凑
        if epigraph:
            out.append(
                f'<p style="font-size:13px;color:#9b2332;margin:8px 24px 24px 24px;'
                f'font-style:italic;letter-spacing:1px;line-height:24px;'
                f'border-left:2px solid #9b2332;padding-left:10px;">'
                f'{_esc(epigraph)}</p>'
            )

    # 4. 朱砂红分隔线（**单线**）
    # v0.3.18 两次修正，根因值得记下来：
    #   ① 原实现是「两个空 `<p>` 各带一条 border-top」，注释里写的是
    #      「朱砂红**双线**分隔」——双线是模板的**刻意设计**，不是 bug。
    #      浏览器里两个空段落没有文字，看起来就是两条线。
    #   ② 但公众号编辑器把空 `<p>` 当**可编辑空段落**，后台会显示成两行
    #      带框的空行，而不是装饰线（用户实测反馈）。
    #   ③ 我第一次只修了 ②（2 个空 p → 1 个 p），却保留了 border-bottom，
    #      结果视觉上**仍是两条线** —— 用户反馈"两条横线还在"。
    # 教训：修表象（编辑框）不等于修问题（两条线）。双线本身才是用户不要的东西。
    # 现在改为**单条** border-top，段内放 `&nbsp;` 保证不是空段落。
    out.append(
        '<p style="margin:14px 20px 22px 20px;padding:8px 0 0 0;'
        'border-top:1px solid #9b2332;'
        'font-size:1px;line-height:1px;">&nbsp;</p>'
    )

    # === 正文 (v0.2.7.3 高级感：章节号缩成左标签 + h2 居中大字 + 正文 line-height 1.9) ===
    for i, page in enumerate(sb.pages):
        body = page.body or page.narration or ""
        section_num = _cn_section(page.page)
        # v0.3.8.1：「定格瞬间」只放**真正的对话/旁白**。
        # 原先用 _extract_quote(body) 从正文里抽一句话当引文，结果它必然
        # 和上面的正文段落重复 —— 读者会看到同一句话出现两次。
        # 现在只认 page.dialogue；没有 dialogue 就不渲染这张卡，
        # 宁可少一个装饰，也不要重复内容。
        quote = (page.dialogue or "").strip()

        # 章节号：朱砂小标 + h2 大字 紧凑布局
        out.append(
            f'<p style="font-size:12px;color:#9b2332;'
            f'letter-spacing:3px;margin:48px 20px 4px 20px;font-weight:600;">'
            f'第 {section_num} 章</p>'
        )

        # h2 章节题 (无 border-bottom，改用下方分隔线段)
        if page.caption:
            out.append(
                f'<h2 style="font-size:20px;color:#1a1a1a;'
                f'margin:0 20px 6px 20px;font-weight:700;letter-spacing:1px;'
                f'line-height:24px;">'
                f'{_esc(page.caption)}</h2>'
            )
            # h2 下方短朱砂线
            # v0.3.18：装饰线改用**段落自身 border** 画，并在段内放 `&nbsp;`。
            #   原来靠一个空 `<span>` 撑线，整个 `<p>` 没有文字 —— 公众号编辑器
            #   会把它当可编辑空段落，在后台显示成一条空行框（用户实测）。
            out.append(
                '<p style="margin:0 20px 20px 20px;width:28px;'
                'border-top:2px solid #9b2332;'
                'font-size:1px;line-height:1px;">&nbsp;</p>'
            )

        # 图 + 图下文言蒙版（v0.3.11）
        # 用户原话：「文言文要集成在图片中，在图片的下方，用类似蒙版的效果集成在图片上」
        # 结构：图位是相对定位容器，<img> 在底层，文言引文用半透明蒙版压在图下缘。
        #
        # v0.3.12 调优（实图评审后）：
        #   初版渐变 0→0.55→0.86 太陡、蒙版太矮，把画面主体（p5 的羊群、p1 的杖）
        #   压掉了。改为更柔的长过渡 + 更足的渐变高度，文言上移一点让读起来更稳。
        # v0.3.18 重大修正：图下字幕蒙版从「定位叠加」改为「负 margin 压图」
        #   旧实现：外层 position:relative + 两层 position:absolute 蒙版。
        #   **微信编辑器会过滤 position:absolute** —— absolute 一失效，蒙版就
        #   变成普通流内元素，从"压在图底"掉成"图下面的独立色块"（用户实测）。
        #   浏览器预览正常，所以本地 HTML 看不出问题，只能在后台暴露。
        #   改法：img 和字幕放进同一个容器，字幕用 `margin-top:-62px` 上移，
        #   数学上正好盖住图片底部 62px，**下沿与图片下沿精确对齐**。
        #   微信支持负 margin，不支持定位 —— 这是唯一可靠的重叠方式。
        #   渐变+实底合并进 background 简写的多层写法（渐变在上、底色在下）。
        if i < len(inp.page_image_urls):
            url = inp.page_image_urls[i]
            quote = (getattr(page, "dialogue", "") or "").strip()
            if quote:
                q_html = _esc(quote).replace("\n", "<br/>")
                # 单行时高度精确 = 30(padding-top) + 24(line-height) + 8(padding-bottom)
                #            = 62px，与负 margin 完全抵消；多行时蒙版自然向上长高。
                mask = (
                    f'<p style="margin:-62px 0 0 0;'
                    f'padding:30px 16px 8px 16px;'
                    f'background:'
                    f'linear-gradient(180deg,'
                    f'rgba(24,18,12,0) 0%,'
                    f'rgba(24,18,12,0.24) 45%,'
                    f'rgba(24,18,12,0.50) 100%),'
                    f'rgba(28,22,16,0.40);'
                    f'font-family:STKaiti,KaiTi,楷体,serif;'
                    f'font-size:15px;line-height:24px;color:#faf6ec;'
                    f'letter-spacing:1.5px;line-break:strict;text-align:center;'
                    f'text-shadow:0 1px 4px rgba(0,0,0,0.85),0 0 14px rgba(0,0,0,0.6);">'
                    f'{q_html}</p>'
                )
            else:
                mask = ""
            out.append(
                f'<div style="margin:0 20px 22px 20px;">'
                f'<img src="{_esc(url)}" style="max-width:100%;display:block;" '
                f'data-page="{page.page}" />'
                f'{mask}'
                f'</div>'
            )

        # 正文 (line-height 1.9, 两端对齐) — v0.2.7.4 关键词高亮 + v0.2.9 per-page keywords
        # v0.3.8：切成 2-3 个短段，别让读者面对一整块 150 字
        # v0.3.8.1：去掉首行缩进 —— 缩进是"印刷体连续正文"的规矩，
        # 靠它标识段首。现在是一句一段、段间距已标明边界，再缩进只会
        # 让左边参差不齐；现代公众号主流排版也不用缩进。
        # v0.3.18（图为主 · 降文字密度）：max_len 42 → 64，段间距 14 → 16。
        #   原 42 字上限把 150 字正文切成 4-5 段，每段 1 句，图文节奏被切碎，
        #   视觉上文字块密度和图几乎持平 —— 违背「图为主」的初衷。
        #   64 字上限切成 2-3 段，每段是一个完整意思（讲事 / 说破 / 落点）。
        # v0.3.18 追加 max_paras=3：光靠 max_len 压不住段数（4 个 20-50 字的
        #   短句各自都不超限，会原样切成 4 段）。段数上限才是「降密度」的关键。
        if body:
            page_kws = getattr(page, 'keywords', []) or []
            for seg in _split_paragraphs(body, max_len=64, max_paras=3):
                out.append(
                    f'<p style="font-size:15px;line-height:28px;color:#1a1a1a;'
                    f'margin:0 20px 16px 20px;'
                    f'text-align:justify;">'
                    f'{_highlight_keywords(seg, page_kws)}</p>'
                )

        # 「定格瞬间」点题卡（v0.3.11 语义纠正）
        # 用户原话：「定格瞬间是对这个章节的核心内容和情感的点题，
        # 是给用户的记忆点，是要跟内容和图片关联的」
        # 所以它取 page.punchline（**白话点题金句**，与本图/正文呼应），
        # 而不是文言引文 —— 文言已在图下蒙版呈现。
        punch = (getattr(page, "punchline", "") or "").strip()
        if len(punch) >= 4:
            page_kws = getattr(page, 'keywords', []) or []
            content_html = _highlight_keywords(punch, page_kws)

            out.append(
                f'<p style="font-size:11px;color:#9b2332;'
                f'margin:16px 20px 4px 20px;letter-spacing:3px;font-weight:600;">'
                f'·  定 格 瞬 间  ·</p>'
                f'<p style="font-size:18px;color:#1a1a1a;'
                f'margin:0 20px 20px 20px;padding:14px 16px;'
                f'background-color:rgba(155, 35, 50, 0.07);'
                f'border-left:3px solid #9b2332;line-height:26px;'
                f'font-weight:500;white-space:pre-line;'
                f'font-family:STKaiti,KaiTi,楷体,serif;">'
                f'　{content_html}　</p>'
            )

        # v0.3.10：删除此处重复的 dialogue 渲染块。
        # dialogue 已在上方「定格瞬间」引文卡里渲染过一次，
        # 这里又渲染一遍 → 同一句文言在同一页出现两次。
        # 引文只在「定格瞬间」出现一次即可。

    # === 结尾 (v0.2.7.1: 删"完"印章 + 现代启示做大做强) ===
    # 现代启示作为"金句卡" (v0.2.7.4: 更大字 + 强 padding + 大留白收束 + 头部标识强化)
    if postscript:
        # 1) 上方细线分隔 + "本篇收束" 标
        # v0.3.18：同 h2 短线，装饰线改用段落 border + &nbsp;，避免后台空行框
        out.append(
            '<p style="margin:48px 20px 0 20px;'
            'border-top:1px solid #9b2332;'
            'font-size:1px;line-height:1px;">&nbsp;</p>'
        )
        out.append(
            '<p style="text-align:center;font-size:11px;color:#9b2332;'
            'margin:8px 20px 14px 20px;letter-spacing:6px;font-weight:600;">'
            '·  本 篇 收 束  ·</p>'
        )
        # 2) 主金句块 — 大字、强 padding、双线装饰
        out.append(
            '<section style="margin:0 20px 14px 20px;padding:40px 24px;'
            'background-color:#9b2332;color:#ffffff;text-align:center;">'
            '<p style="font-size:11px;color:#ffffff;letter-spacing:8px;'
            'margin:0 0 18px 0;font-weight:600;">·  现 代 启 示  ·</p>'
            f'<p style="font-size:19px;color:#ffffff;margin:0;'
            f'line-height:24px;font-weight:500;letter-spacing:1px;">'
            f'　{_esc(postscript)}　</p>'
            '</section>'
        )
        # 3) 收束横线 + 结尾"· · ·"
        out.append(
            '<p style="margin:0 20px 0 20px;'
            'border-top:1px solid #9b2332;'
            'font-size:1px;line-height:1px;">&nbsp;</p>'
        )
        out.append(
            '<p style="margin:24px 20px 32px 20px;text-align:center;'
            'color:#9b2332;letter-spacing:16px;font-size:14px;font-weight:600;">'
            '· · ·</p>'
        )

    # v0.2.7: 删除"后记"块（与现代启示内容重复，冗余）

    # v0.2.8.0: 文末出处脚注（用户选定方案 B）
    # v0.3.18: 去硬编码 —— 原先写死「《旧唐书》与回纥外交档案考略」，
    #   对任何非唐代题材都是错的。改为读 inp.sources，缺省用中性兜底。
    # v0.3.18: 同时修掉逐字插空格 —— 原 `src_spaced = " ".join(src)` 把
    #   《孙子兵法》渲染成「《 孙 子 兵 法 》」。标题（「第 贰 章」）逐字
    #   加空格是古籍感的设计，书名不是：拆开后无法检索、无法复制、
    #   读起来像乱码。字距已由下面的 letter-spacing:1px 负责。
    if subtitle:
        src = (inp.sources or "").strip() or "正史载记与传世文献互校"
        out.append(
            f'<p style="margin:24px auto 24px auto;width:28px;'
            f'text-align:center;border-top:1px solid #ccc;'
            f'font-size:1px;line-height:1px;">&nbsp;</p>'
            f'<p style="margin:0 20px 32px 20px;text-align:center;'
            f'font-size:10px;color:#999;letter-spacing:1px;font-weight:400;">'
            f'本 文 史 料 依 据：{src}</p>'
        )

    # v0.2.7.2: 关闭 WeChat-safe 外层
    out.append('</section></div>')
    out.append('</section>')
    return "\n".join(out)


def render_template_e(inp: ArticleInput) -> str:
    """E v3 · 典雅知识风（优化版，深蓝灰配色）

    基于 v1 版式（章节大字 + 中文数字 + h2 + 图 + 数据卡 + 对话 + 印章 + 金句）
    文字优化：
      - 删：导语、题记、后记长段（冗余）
      - 分段：正文按句号切 2-3 段，不再一大段
      - 重点标记：每章第一句 blockquote（深蓝灰左 border + 浅蓝灰背景）

    配色：朱砂红 → 深蓝灰（#2c3e5a），适合 STEM/认知/心理学/科普。
    """
    sb = inp.storyboard
    title = inp.title or sb.title
    out = ['<section data-template="e-v3">']

    subtitle = sb.subtitle or ""
    postscript = sb.postscript or ""

    # 外层：手机框 + 米色羊皮纸背景
    out.append(
        '<div style="background:#eee8da;padding:24px 0;">'
        '<div style="max-width:420px;margin:0 auto;background:#fff;'
        'box-shadow:0 4px 20px rgba(0,0,0,.15);border-radius:8px;'
        'overflow:hidden;padding:0;">'
    )

    # === 开篇（删导语+题记,精简）===
    # 1. 卷首题词
    out.append(
        '<p style="font-size:13px;color:#2c3e5a;letter-spacing:3px;'
        'text-align:center;margin:32px 20px 20px 20px;font-weight:600;">'
        '知 识 故 事 · 漫 画 解 读</p>'
    )
    # 2. 大标题 h1
    out.append(
        f'<h1 style="text-align:center;font-size:30px;color:#1a1a1a;'
        f'margin:0 20px 12px 20px;font-weight:700;letter-spacing:5px;'
        f'line-height:1.5;">{_esc(title)}</h1>'
    )
    # 3. 副标题
    if subtitle:
        out.append(
            f'<p style="text-align:center;font-size:13px;color:#2c3e5a;'
            f'margin:0 20px 24px 20px;letter-spacing:2px;font-weight:500;">'
            f'{_esc(subtitle)}</p>'
        )
    # 4. 双线分隔
    out.append(
        '<div style="margin:0 20px 8px 20px;border-top:2px solid #2c3e5a;'
        'border-bottom:1px solid #2c3e5a;height:3px;"></div>'
    )

    # === 正文（每章优化版）===
    for i, page in enumerate(sb.pages):
        body = page.body or page.narration or ""
        section_num = _cn_section(page.page)
        # 优先用 LLM 给的精彩 highlight(峰终/温水/1993 等)
        if page.highlight and page.highlight.strip():
            highlight = page.highlight.strip()
        else:
            highlight = _extract_highlight(page.caption, body, page.page)

        # 章节大字（80px）+ 章号
        if highlight and highlight != f"第{page.page:02d}章":
            out.append(
                f'<div style="text-align:center;margin:36px 20px 6px 20px;">'
                f'<span style="display:inline-block;font-size:64px;'
                f'color:#2c3e5a;font-weight:bold;letter-spacing:5px;'
                f'font-family:STSong,SimSun,宋体,serif;line-height:1;">'
                f'{_esc(highlight)}</span></div>'
                f'<p style="text-align:center;font-size:12px;color:#2c3e5a;'
                f'letter-spacing:8px;margin:0 20px 4px 20px;font-weight:600;">'
                f'第 {section_num} 章</p>'
            )
        else:
            out.append(
                f'<p style="text-align:center;font-size:12px;color:#2c3e5a;'
                f'letter-spacing:8px;margin:36px 20px 8px 20px;font-weight:600;">'
                f'第 {section_num} 章</p>'
            )

        # h2 章节题
        if page.caption:
            out.append(
                f'<h2 style="font-size:19px;color:#1a1a1a;'
                f'border-bottom:2px solid #2c3e5a;padding-bottom:6px;'
                f'margin:8px 20px 14px 20px;font-weight:700;'
                f'font-family:STSong,SimSun,宋体,serif;line-height:1.4;">'
                f'{_esc(page.caption)}</h2>'
            )

        # 图
        if i < len(inp.page_image_urls):
            url = inp.page_image_urls[i]
            out.append(
                f'<p style="text-align:center;margin:0 20px 12px 20px;">'
                f'<img src="{_esc(url)}" '
                f'style="max-width:100%;border-radius:4px;" '
                f'data-page="{page.page}" /></p>'
            )

        # 正文分段 + 重点标记
        if body:
            sentences = _split_sentences(body)[:3]  # 每章限 3 句
            if sentences:
                # 第一句做 blockquote（重点标记）
                first = sentences[0]
                out.append(
                    f'<div style="margin:0 20px 12px 20px;padding:10px 14px;'
                    f'background:rgba(44,62,90,0.06);border-left:3px solid #2c3e5a;">'
                    f'<p style="font-size:13px;line-height:1.8;color:#1a1a1a;'
                    f'margin:0;font-weight:500;">{_esc(first)}</p></div>'
                )
                # 后续句做正文（分段）—— v0.3.8.1 同样去掉首行缩进
                for s in sentences[1:]:
                    out.append(
                        f'<p style="font-size:13px;line-height:1.9;color:#2a2a2a;'
                        f'margin:0 20px 8px 20px;text-align:justify;">'
                        f'{_esc(s)}</p>'
                    )

        # dialogue
        if page.dialogue:
            out.append(
                f'<p style="font-size:14px;line-height:1.8;color:#2c3e5a;'
                f'margin:0 20px 18px 20px;padding:8px 12px;'
                f'background:rgba(44,62,90,0.05);border-left:3px solid #2c3e5a;'
                f'text-indent:0;font-family:STKaiti,KaiTi,楷体,serif;">'
                f'「{_esc(page.dialogue)}」</p>'
            )

    # === 结尾（精简：删后记长段,只保留金句）===
    out.append(
        '<div style="margin:48px 20px 16px 20px;border-top:1px solid #2c3e5a;'
        'border-bottom:2px solid #2c3e5a;padding:20px 0;text-align:center;">'
        '<div style="display:inline-block;width:60px;height:60px;background:#2c3e5a;'
        'color:white;font-family:STKaiti,KaiTi,楷体,serif;font-size:26px;'
        'font-weight:bold;line-height:60px;text-align:center;'
        'box-shadow:0 0 10px rgba(44,62,90,0.5);letter-spacing:3px;">完</div>'
        '</div>'
    )

    # 一句话金句
    if postscript:
        first_sentence = postscript.split('。')[0] if '。' in postscript else postscript[:25]
        out.append(
            f'<p style="text-align:center;font-size:15px;color:#2c3e5a;'
            f'margin:0 20px 28px 20px;font-weight:500;letter-spacing:1px;'
            f'font-family:STKaiti,KaiTi,楷体,serif;line-height:1.7;">'
            f'「{_esc(first_sentence)}」</p>'
        )

    out.append('</div></div>')
    out.append('</section>')
    return "\n".join(out)


def _split_sentences(body: str) -> list[str]:
    """按 。！？ 拆句。

    v0.3.8 修复：原实现 `_re.split(r'(?<=[。！？])', body)` 会在**引号内部**
    切开 —— "他说“好。”然后走了。" 会变成 '他说“好。' + '”然后走了。'，
    渲染出来就是裸露的 `”`。现在复用 _split_paragraphs 的引号感知切分。
    """
    return _split_paragraphs(body, max_len=999, merge_short=False)


# Dispatcher
# v0.2（2026-09-20）：从 5 模板砍到 3 模板
#   - 保留 a（撕纸手账）、c（中国古典故事专版）、e（典雅知识风）
#   - 砍掉 b（复古报纸）、c_v3（现代极简）、d（多巴胺手绘）
# 3 个模板覆盖 95% 场景：e = 知识/商业；c = 古风/历史；a = 情感/通用兜底
TEMPLATES = {
    "a": ("A · 撕纸手账风", render_template_a),
    "c": ("C · 中国古典故事专版", render_template_c),
    "e": ("E · 典雅知识风（深蓝灰配色版）", render_template_e),
}


def render_article(inp: ArticleInput, template: str = "e") -> str:
    fn = TEMPLATES.get(template, TEMPLATES["e"])[1]
    return fn(inp)


def file_to_data_uri(image_path: Path) -> str:
    import base64
    b64 = base64.b64encode(image_path.read_bytes()).decode()
    return f"data:image/png;base64,{b64}"


def placeholder_image_uri(label: str, w: int = 750, h: int = 420) -> str:
    """占位图 data URI（纯 SVG，零依赖）。

    v0.3.4：模板渲染时图位是 `<img src="...">`，必须给**真实图片 URL**。
    旧实现 `_placeholder_img()` 返回的是 `<div>` 标签字符串，被塞进 src 属性
    会导致浏览器破图 —— 而这恰好破坏了排版预览的意义（用户要看的就是版面）。
    SVG data URI 既能正常显示，又不引入 PIL 依赖。
    """
    import base64
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}">'
        '<defs><pattern id="d" width="28" height="28" patternUnits="userSpaceOnUse" '
        'patternTransform="rotate(45)">'
        '<rect width="28" height="28" fill="#e8e3d8"/>'
        '<line x1="0" y1="0" x2="0" y2="28" stroke="#d8d2c4" stroke-width="2"/>'
        '</pattern></defs>'
        f'<rect width="{w}" height="{h}" fill="url(#d)"/>'
        f'<rect x="2" y="2" width="{w-4}" height="{h-4}" fill="none" '
        'stroke="#a0988a" stroke-width="2"/>'
        f'<text x="{w//2}" y="{h//2+12}" font-size="34" fill="#787167" '
        'font-family="PingFang SC,Microsoft YaHei,sans-serif" text-anchor="middle">'
        f'{label}</text></svg>'
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode()


def _storyboard_note(p) -> str:
    """单页分镜说明块（HTML）—— 展示"这页要画什么"。"""
    from .story_script import page_elements
    import html as _h

    els = page_elements(p)
    if not els:
        return ""

    kws = (p.get("keywords") if isinstance(p, dict) else getattr(p, "keywords", None)) or []
    rows = "".join(
        f'<span class="kcf-tag"><b>{_h.escape(lab)}</b> {_h.escape(val)}</span>'
        for lab, val in els
    )
    kw_html = ""
    if kws:
        kw_html = (
            '<div style="margin-top:6px;font-size:11.5px;color:#8a857c;">'
            '关键词：<span style="color:#9b2332;">'
            + " · ".join(_h.escape(k) for k in kws)
            + "</span></div>"
        )
    return (
        '<div class="kcf-note">'
        '<div class="kcf-note-h">本图分镜意图</div>'
        f'<div class="kcf-note-b">{rows}</div>'
        f'{kw_html}</div>'
    )


# 分镜说明块的样式（渲染后注入到 <head>，避免 inline 过长）
_NOTE_CSS = (
    '<style>'
    '.kcf-note{margin:8px 0 20px 0;padding:9px 11px;background:#faf7f0;'
    'border-left:3px solid #9b2332;border-radius:0 4px 4px 0;}'
    '.kcf-note-h{font-size:11px;color:#9b2332;letter-spacing:2px;'
    'font-weight:600;margin-bottom:5px;}'
    '.kcf-note-b{line-height:1.9;}'
    '.kcf-tag{display:inline-block;margin:0 6px 4px 0;padding:1px 7px;'
    'background:#f0ebe0;border-radius:3px;font-size:11.5px;color:#6b6459;}'
    '.kcf-tag b{color:#9b2332;}'
    '</style>'
)


def render_layout_preview(sb: Storyboard, template: str = "e",
                          placeholder_h: int = 420) -> str:
    """生图前的**排版 + 分镜预览**：真实模板 + 占位图 + 每页分镜说明。

    v0.3.6：这是 Checkpoint 1 的唯一产物 —— 用户打开**一个文件**就能确认：
      1. 文字排版效果（模板成品版式）
      2. 每页画面要画什么（主体/动作/配角/背景/景别/情绪 + 关键词）
    确认图文相符后才跑 step_gen_images 生图。

    实现要点：分镜说明**不能**走 page_image_urls 通道 —— 模板会 `_esc()`
    把 URL 塞进 `<img src="...">`，整段 HTML 会被转义成可见文本。
    正确做法是：先用占位图 data URI 渲染出成品版式，再按
    `data-page="N"` 把每个 `<img>` 替换成「占位图 + 分镜说明」。
    """
    urls = [placeholder_image_uri("待生成", h=placeholder_h)
            for _ in sb.pages]
    html = render_publish_article(sb, urls, template=template)

    # 按 data-page 把分镜说明注入到图位之后。
    # v0.3.11：图位结构改成 <div style="position:relative"><img/><蒙版/></div>，
    # 原来的 <p>...</p> 正则匹配不到了。两次独立替换，避免多分支命名分组的坑。
    by_page = {p.page: p for p in sb.pages}

    def _note_for(page_no: int) -> str:
        p = by_page.get(page_no)
        return _storyboard_note(p) if p else ""

    # a) 图位 div（含蒙版）
    # v0.3.18：模板 c 的图位外层 div **不再有 position:relative**（微信过滤
    #   定位，蒙版改用负 margin 压图）。原来靠 `position:relative` 锚定图位的
    #   正则因此失配 → 分镜说明整段注不进去，layout_preview 只剩 style 壳。
    #   改为「任意 div + 紧跟 data-page 的 img」定位，并用 `(?:(?!<div).)*?`
    #   保证内部无嵌套 div 时才收口，避免跨块误吞。
    def _rep_div(m: "re.Match") -> str:
        n = _note_for(int(m.group("page")))
        return m.group(0) + n if n else m.group(0)

    html = re.sub(
        r'<div[^>]*>\s*<img[^>]*\bdata-page="(?P<page>\d+)"[^>]*/>'
        r'(?:(?!<div).)*?</div>',
        _rep_div, html, flags=re.S)

    # b) 旧结构：p 图位（其他模板仍是这种）
    def _rep_p(m: "re.Match") -> str:
        n = _note_for(int(m.group("page")))
        return m.group(0) + n if n else m.group(0)

    html = re.sub(
        r'<p[^>]*>\s*<img[^>]*\bdata-page="(?P<page>\d+)"[^>]*/>\s*</p>',
        _rep_p, html)

    # 注入样式
    if "</head>" in html:
        html = html.replace("</head>", _NOTE_CSS + "</head>", 1)
    else:
        html = _NOTE_CSS + html
    return html


def render_preview_article(sb: Storyboard, image_paths: list[Path], template: str = "a") -> str:
    page_urls = [file_to_data_uri(p) for p in image_paths]
    return render_article(ArticleInput(
        storyboard=sb, page_image_urls=page_urls,
        sources=getattr(sb, "sources", "") or None,
    ), template=template)


def render_publish_article(sb: Storyboard, wechat_image_urls: list[str], template: str = "e") -> str:
    return render_article(ArticleInput(
        storyboard=sb, page_image_urls=wechat_image_urls,
        sources=getattr(sb, "sources", "") or None,
    ), template=template)


def render_mock_preview(template: str) -> str:
    """根据模板返回不同的 mock 内容（C 模板用昭君出塞长文叙事）。"""
    from .planner import StoryPage

    if template == "c":
        # 中国古典故事专版：昭君出塞长文
        pages_data = _mock_pages_classic()
        pages = [
            StoryPage(
                page=p["page"], visual="",
                caption=p["caption"], dialogue=p["dialogue"],
                narration=p["narration"], body=p["body"],
                key_visual="",
            )
            for p in pages_data
        ]
        sb = Storyboard(
            topic="昭君出塞",
            style_id="cn_xuanfeng",
            title="昭君出塞",
            subtitle="《汉书·元帝纪》",
            summary=(
                "汉元帝竟宁元年（前 33 年），南郡秭归诞生了一位名垂青史的女子。"
                "她本可安于乡野，却因一幅画像误入深宫；"
                "又因主动请行远嫁匈奴，成就了一段跨越六十年的边境和平。"
            ),
            preface="知 识 故 事",
            epigraph="落雁昭君意，胡笳塞外声。",
            postscript=(
                "昭君出塞，是汉匈关系史上的重要转折。她以一人之远行，"
                "换来了边境六十余年的安宁，也为后世留下了"
                "「和亲」这一独特的外交典范。在王昭君的画像早已失传的今天，"
                # NOTE: 用 ASCII 引号转义 + 中文括号，避免 Python 字符串嵌套引号 syntax error
                "她留在史书中的身影，仍在草原的风中回响。"
            ),
            pages=pages,
        )
        image_urls = [_placeholder_img(f"page {p.page}", h=160) for p in pages]
        inp = ArticleInput(storyboard=sb, page_image_urls=image_urls, title=sb.title)
        return render_article(inp, template=template)

    # 默认 mock（其他模板用 transformer 短文）
    pages_data = [
        {"page": 1, "caption": "今天聊聊一个话题。", "dialogue": "（狐狸在招手）", "narration": ""},
        {"page": 2, "caption": "Transformer 是深度学习架构", "dialogue": "", "narration": "一种新的网络结构"},
        {"page": 3, "caption": "核心是注意力机制", "dialogue": "", "narration": "让模型关注重要的部分"},
        {"page": 4, "caption": "Q/K/V 三个矩阵", "dialogue": "", "narration": "Query / Key / Value"},
        {"page": 5, "caption": "所以，下次再遇到类似场景——", "dialogue": "（狐狸竖起拇指）", "narration": "懂的人，把它当成平常事。"},
    ]
    pages = [
        StoryPage(
            page=p["page"], visual="",
            caption=p["caption"], dialogue=p["dialogue"],
            narration=p["narration"], body="",
            key_visual="",
        )
        for p in pages_data
    ]
    sb = Storyboard(
        topic="Transformer", style_id="new_yorker",
        title="一图读懂 Transformer",
        summary="用 5 张图给你讲清楚核心要点。",
        pages=pages,
    )
    image_urls = [_placeholder_img(f"page {p.page}") for p in pages]
    inp = ArticleInput(storyboard=sb, page_image_urls=image_urls, title=sb.title)
    return render_article(inp, template=template)


def list_templates() -> list[dict]:
    return [
        {"id": k, "name": v[0], "use_cases": v[0].split(" · ")[1] if " · " in v[0] else ""}
        for k, v in TEMPLATES.items()
    ]