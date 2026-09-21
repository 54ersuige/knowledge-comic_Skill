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


# ========== 模板 B：复古报纸风 ==========
def render_template_b(inp: ArticleInput) -> str:
    """B. 复古报纸风（历史/商业评论/老物件）"""
    sb = inp.storyboard
    title = inp.title or sb.title
    out = ['<section data-template="b">']
    out.append(
        '<div style="background:linear-gradient(180deg,#f5f0d8 0%,#ebe2c0 100%);'
        'padding:24px 16px 16px;margin:16px 0;border:1px solid #c9b87a;'
        'position:relative;box-shadow:inset 0 0 30px rgba(101,67,33,0.15);">'
        '<div style="border-bottom:3px double #654321;padding-bottom:12px;'
        'margin-bottom:16px;display:flex;justify-content:space-between;'
        'align-items:flex-end;">'
        '<span style="font-family:Georgia,serif;font-size:11px;color:#654321;'
        'font-style:italic;">No. 001 · TODAY EDITION</span>'
        '<span style="font-family:Georgia,serif;font-size:11px;color:#654321;">'
        '2026 · 第 1 卷</span>'
        '</div>'
        f'<h1 style="font-family:Georgia,SimSun,serif;font-size:24px;'
        f'font-weight:bold;color:#1a1a1a;text-align:center;margin:8px 0;'
        f'letter-spacing:2px;">{_esc(title).upper()}</h1>'
        f'<p style="font-family:Georgia,serif;font-size:13px;color:#654321;'
        f'text-align:center;font-style:italic;margin:0 0 16px;">'
        f'— {_esc(sb.summary)} —</p>'
        '</div>'
    )
    for i, page in enumerate(sb.pages):
        out.append(
            '<div style="background:rgba(245,240,216,0.7);margin:16px 0;'
            'padding:16px 12px 16px 50px;border-left:3px solid #654321;'
            'position:relative;">'
            f'<div style="position:absolute;left:-20px;top:8px;width:50px;'
            f'height:50px;border-radius:50%;background:#b91c1c;color:white;'
            f'display:flex;align-items:center;justify-content:center;'
            f'font-family:Georgia,serif;font-size:10px;font-weight:bold;'
            f'box-shadow:2px 2px 4px rgba(0,0,0,0.2);">'
            f'<div style="text-align:center;line-height:1.2;">PAGE<br>{page.page:02d}</div>'
            f'</div>'
        )
        if page.caption:
            out.append(
                f'<p style="font-family:Georgia,SimSun,serif;font-size:15px;'
                f'color:#1a1a1a;margin:0 0 8px;font-weight:bold;'
                f'text-transform:uppercase;letter-spacing:1px;">'
                f'— {_esc(page.caption)} —</p>'
            )
        if page.dialogue:
            out.append(
                f'<p style="font-family:Georgia,serif;font-size:15px;'
                f'color:#1a1a1a;margin:8px 0;padding:8px 0;'
                f'font-style:italic;border-top:1px solid #c9b87a;'
                f'border-bottom:1px solid #c9b87a;">'
                f'▎ 「{_esc(page.dialogue)}」 ▎</p>'
            )
        if page.narration:
            out.append(
                f'<p style="font-family:Georgia,serif;font-size:13px;'
                f'color:#654321;margin:8px 0;font-style:italic;">'
                f'{_esc(page.narration)}</p>'
            )
        if i < len(inp.page_image_urls):
            url = inp.page_image_urls[i]
            out.append(
                f'<div style="margin:12px 0;text-align:center;">'
                f'<img src="{_esc(url)}" '
                f'style="max-width:90%;border:1px solid #654321;'
                f'filter:sepia(15%) contrast(1.05);" data-page="{page.page}" />'
                f'</div>'
            )
        out.append('</div>')
    if sb.pages:
        last = sb.pages[-1]
        if last.narration:
            out.append(
                '<div style="background:rgba(101,67,33,0.08);margin:24px 0;'
                'padding:24px 16px;border-top:3px double #654321;'
                'border-bottom:3px double #654321;text-align:center;">'
                f'<p style="font-family:Georgia,SimSun,serif;font-size:18px;'
                f'font-weight:bold;color:#1a1a1a;margin:0;letter-spacing:1px;">'
                f'「{_esc(last.narration)}」</p>'
                '<p style="font-family:Georgia,serif;font-size:11px;color:#654321;'
                'font-style:italic;margin:12px 0 0;">— EDITORIAL —</p>'
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
    """从 body 提取一句「金句/数据」作为数据卡内容（≤30 字）。"""
    body = body or ""
    # 1. 引号内容
    m = re.search(r"「([^」]{2,30})」", body)
    if m:
        return m.group(1)
    # 2. 数据句（含率/比例/达/分之）
    m = re.search(r"([^。，]{4,30}?(?:率|比例|分之|达|占)[^。，]{0,15})", body)
    if m:
        quote = m.group(1).strip()
        if len(quote) <= 30:
            return quote
    # 3. 第一句
    first = body.split("。")[0].strip()
    if len(first) > 30:
        first = first[:30] + "..."
    return first


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
    title = inp.title or sb.title
    out = ['<section data-template="c-v2">']

    preface = sb.preface or "知 识 故 事"
    subtitle = sb.subtitle or ""
    epigraph = sb.epigraph or ""
    summary = sb.summary or ""
    postscript = sb.postscript or ""

    # 外层：手机框 + 米色羊皮纸背景
    out.append(
        '<div style="background:#eee8da;padding:24px 0;">'
        '<div style="max-width:420px;margin:0 auto;background:#fff;'
        'box-shadow:0 4px 20px rgba(0,0,0,.15);border-radius:8px;'
        'overflow:hidden;padding:0;">'
    )

    # === 开篇 ===
    # 1. 卷首朱砂题词（v2: 朱砂红而非灰）
    out.append(
        f'<p style="font-size:13px;color:#9b2332;letter-spacing:3px;'
        f'text-align:center;margin:32px 20px 20px 20px;font-weight:600;">'
        f'　{_esc(preface)}　</p>'
    )
    # 2. 大标题 h1（v2: 32px）
    out.append(
        f'<h1 style="text-align:center;font-size:32px;color:#1a1a1a;'
        f'margin:0 20px 12px 20px;font-weight:700;letter-spacing:6px;'
        f'line-height:1.4;">{_esc(title)}</h1>'
    )
    # 3. 副标题（v2: 朱砂装饰短线）
    if subtitle:
        out.append(
            '<div style="text-align:center;margin:12px 20px 24px 20px;">'
            '<span style="display:inline-block;width:24px;height:1px;'
            'background:#9b2332;vertical-align:middle;"></span>'
            f'<span style="font-size:13px;color:#9b2332;letter-spacing:2px;'
            f'margin:0 12px;font-weight:500;">{_esc(subtitle)}</span>'
            '<span style="display:inline-block;width:24px;height:1px;'
            'background:#9b2332;vertical-align:middle;"></span>'
            '</div>'
        )
    else:
        out.append('<div style="margin-bottom:24px;"></div>')

    # 4. 导语（v2: 加粗 18px 1.9 行高）
    if summary:
        out.append(
            f'<p style="font-size:18px;color:#222;margin:0 20px 24px 20px;'
            f'text-indent:2em;font-weight:600;line-height:1.9;">'
            f'{_esc(summary)}</p>'
        )

    # 5. 题记（v2: 朱砂竖线 + 浅色底）
    if epigraph:
        out.append(
            f'<div style="margin:0 20px 32px 20px;padding:14px 18px;'
            f'background:rgba(155,35,50,0.06);border-left:3px solid #9b2332;">'
            f'<p style="font-size:15px;color:#9b2332;margin:0;'
            f'letter-spacing:2px;font-style:italic;line-height:1.7;'
            f'font-family:STKaiti,KaiTi,楷体,serif;">'
            f'　{_esc(epigraph)}　</p>'
            '</div>'
        )

    # 6. 朱砂红双线分隔
    out.append(
        '<div style="margin:0 20px 8px 20px;border-top:2px solid #9b2332;'
        'border-bottom:1px solid #9b2332;height:4px;"></div>'
    )

    # === 正文 ===
    for i, page in enumerate(sb.pages):
        body = page.body or page.narration or ""
        section_num = _cn_section(page.page)
        highlight = _extract_highlight(page.caption, body, page.page)
        quote = _extract_quote(body)

        # 章节大字 highlight（v2 新增：朱砂 80px 大字标识）
        if highlight and highlight != f"第{page.page:02d}章":
            out.append(
                f'<div style="text-align:center;margin:48px 20px 8px 20px;">'
                f'<span style="display:inline-block;font-size:80px;'
                f'color:#9b2332;font-weight:bold;letter-spacing:6px;'
                f'font-family:STSong,SimSun,宋体,serif;line-height:1;">'
                f'{_esc(highlight)}</span>'
                f'</div>'
                f'<p style="text-align:center;font-size:12px;color:#9b2332;'
                f'letter-spacing:8px;margin:0 20px 4px 20px;font-weight:600;">'
                f'第 {section_num} 章</p>'
            )
        else:
            out.append(
                f'<p style="text-align:center;font-size:12px;color:#9b2332;'
                f'letter-spacing:8px;margin:48px 20px 8px 20px;font-weight:600;">'
                f'第 {section_num} 章</p>'
            )

        # h2 章节题（v2: 颜色 #1a1a1a 黑）
        if page.caption:
            out.append(
                f'<h2 style="font-size:20px;color:#1a1a1a;'
                f'border-bottom:2px solid #9b2332;padding-bottom:8px;'
                f'margin:16px 20px 18px 20px;font-weight:700;'
                f'font-family:STSong,SimSun,宋体,serif;line-height:1.5;">'
                f'{_esc(page.caption)}</h2>'
            )

        # 图
        if i < len(inp.page_image_urls):
            url = inp.page_image_urls[i]
            out.append(
                f'<p style="text-align:center;margin:0 20px 16px 20px;">'
                f'<img src="{_esc(url)}" '
                f'style="max-width:100%;border-radius:4px;" '
                f'data-page="{page.page}" /></p>'
            )

        # 正文（v2: line-height 2.0）
        if body:
            out.append(
                f'<p style="font-size:15px;line-height:2.0;color:#2a2a2a;'
                f'margin:0 20px 20px 20px;padding:0 4px;'
                f'text-align:justify;text-indent:2em;">'
                f'{_esc(body)}</p>'
            )

        # 数据卡 / 引文卡（v2 新增）
        if quote and len(quote) >= 4:
            out.append(
                f'<div style="margin:8px 20px 32px 20px;padding:14px 18px;'
                f'background:#f5f0e8;border-left:3px solid #9b2332;">'
                f'<p style="font-size:13px;color:#9b2332;margin:0 0 4px 0;'
                f'letter-spacing:2px;font-weight:600;">关键节点</p>'
                f'<p style="font-size:14px;color:#1a1a1a;margin:0;'
                f'line-height:1.7;font-weight:500;">'
                f'　{_esc(quote)}　</p>'
                '</div>'
            )

        # dialogue
        if page.dialogue:
            out.append(
                f'<p style="font-size:15px;line-height:1.9;color:#9b2332;'
                f'margin:0 20px 24px 20px;padding:8px 12px;'
                f'background:rgba(155,35,50,0.05);border-left:3px solid #9b2332;'
                f'text-indent:0;font-family:STKaiti,KaiTi,楷体,serif;">'
                f'「{_esc(page.dialogue)}」</p>'
            )

    # === 结尾 ===
    # 朱砂印章（v2: 64x64 加大）
    out.append(
        '<div style="margin:56px 20px 20px 20px;border-top:1px solid #9b2332;'
        'border-bottom:2px solid #9b2332;padding:24px 0;text-align:center;">'
        '<div style="display:inline-block;width:64px;height:64px;background:#9b2332;'
        'color:white;font-family:STKaiti,KaiTi,楷体,serif;font-size:30px;'
        'font-weight:bold;line-height:64px;text-align:center;'
        'box-shadow:0 0 12px rgba(155,35,50,0.5);letter-spacing:4px;">完</div>'
        '</div>'
    )

    # 启示金句（v2 新增：朱砂渐变背景卡）
    if postscript:
        first_sentence = postscript.split('。')[0] if '。' in postscript else postscript[:30]
        out.append(
            '<div style="margin:24px 20px 16px 20px;padding:20px;'
            'background:linear-gradient(135deg,#9b2332 0%,#c4644a 100%);'
            'border-radius:4px;color:white;text-align:center;">'
            '<p style="font-size:11px;letter-spacing:3px;margin:0 0 8px 0;'
            'opacity:0.85;">现 代 启 示</p>'
            f'<p style="font-size:17px;margin:0;line-height:1.7;font-weight:500;">'
            f'　{_esc(first_sentence)}　</p>'
            '</div>'
        )

    # 后记
    if postscript:
        out.append(
            '<div style="margin:8px 20px 32px 20px;padding:18px;'
            'background:rgba(155,35,50,0.04);border-left:3px solid #9b2332;">'
            '<p style="font-size:13px;color:#9b2332;font-weight:bold;'
            'letter-spacing:2px;margin:0 0 10px 0;'
            'font-family:STKaiti,KaiTi,楷体,serif;">后　记</p>'
            f'<p style="font-size:14px;line-height:2.0;color:#2a2a2a;'
            f'margin:0;text-indent:2em;text-align:justify;">'
            f'{_esc(postscript)}</p>'
            '</div>'
        )

    out.append('</div></div>')
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
                # 后续句做正文（分段）
                for s in sentences[1:]:
                    out.append(
                        f'<p style="font-size:13px;line-height:1.9;color:#2a2a2a;'
                        f'margin:0 20px 8px 20px;text-align:justify;text-indent:2em;">'
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
    """按 。！？ 拆句,过滤空白,返回非空句子列表。"""
    import re as _re
    parts = _re.split(r'(?<=[。！？])', body)
    return [s.strip() for s in parts if s.strip()]






def render_template_d(inp: ArticleInput) -> str:
    """D. 多巴胺手绘卡片（科普/教育/亲子）"""
    sb = inp.storyboard
    title = inp.title or sb.title
    out = ['<section data-template="d">']
    out.append(
        '<div style="background:linear-gradient(135deg,#ff6b9d 0%,#ff9a6b 50%,#ffd93d 100%);'
        'padding:28px 16px;border-radius:0 0 32px 32px;margin-bottom:24px;'
        'box-shadow:0 8px 24px rgba(255,107,157,0.3);">'
        f'<h1 style="font-size:24px;color:white;text-align:center;margin:0;'
        f'font-weight:bold;text-shadow:2px 2px 4px rgba(0,0,0,0.1);">'
        f'🌈 {_esc(title)} 🎨</h1>'
        f'<p style="font-size:14px;color:white;text-align:center;'
        f'margin:8px 0 0;text-shadow:1px 1px 2px rgba(0,0,0,0.1);">'
        f'✨ {_esc(sb.summary)} ✨</p>'
        '</div>'
    )
    palette = [
        ("#ff6b9d", "#fff0f5"), ("#4ecdc4", "#e6fffa"),
        ("#ffd93d", "#fffbeb"), ("#a78bfa", "#f3e8ff"),
        ("#6ee7b7", "#ecfdf5"),
    ]
    for i, page in enumerate(sb.pages):
        accent, light_bg = palette[i % len(palette)]
        out.append(
            f'<div style="background:{light_bg};border:3px solid {accent};'
            f'border-radius:24px;padding:20px;margin:16px 0;'
            f'box-shadow:0 4px 12px rgba(0,0,0,0.08);">'
            f'<div style="display:inline-block;background:{accent};'
            f'color:white;padding:4px 14px;border-radius:12px;'
            f'font-size:12px;font-weight:bold;margin-bottom:8px;">'
            f'📍 第 {page.page} 步</div>'
        )
        if page.caption:
            out.append(
                f'<p style="font-size:17px;color:#1a1a1a;margin:8px 0;'
                f'font-weight:bold;">{_esc(page.caption)}</p>'
            )
        if page.dialogue:
            out.append(
                f'<div style="background:white;border:2px solid {accent};'
                f'border-radius:20px;padding:10px 16px;margin:12px 0;'
                f'display:inline-block;font-size:15px;color:#525252;'
                f'box-shadow:0 2px 4px rgba(0,0,0,0.05);">'
                f'💬 {_esc(page.dialogue)}</div>'
            )
        if page.narration:
            out.append(
                f'<p style="font-size:14px;color:#737373;margin:12px 0;'
                f'font-style:italic;">{_esc(page.narration)}</p>'
            )
        if i < len(inp.page_image_urls):
            url = inp.page_image_urls[i]
            out.append(
                f'<div style="margin:12px 0;text-align:center;">'
                f'<img src="{_esc(url)}" '
                f'style="max-width:100%;border-radius:16px;'
                f'box-shadow:0 6px 16px rgba(0,0,0,0.12);" data-page="{page.page}" />'
                f'</div>'
            )
        out.append('</div>')
    if sb.pages:
        last = sb.pages[-1]
        if last.narration:
            out.append(
                '<div style="background:linear-gradient(135deg,#a78bfa 0%,#ec4899 100%);'
                'border-radius:24px;padding:24px;margin:32px 0;'
                'text-align:center;color:white;'
                'box-shadow:0 8px 24px rgba(167,139,250,0.4);">'
                f'<p style="font-size:20px;margin:0;font-weight:bold;'
                f'text-shadow:1px 1px 2px rgba(0,0,0,0.1);">'
                f'🎉 「{_esc(last.narration)}」</p>'
                '<p style="font-size:13px;margin:12px 0 0;opacity:0.9;">🌟 THE END 🌟</p>'
                '</div>'
            )
    out.append('</section>')
    return "\n".join(out)


# ========== 模板 C v3：现代极简风（Apple/MUJI 大字留白）==========
# 设计哲学：
#   - 全 sans-serif（system-ui）
#   - 纯白底 + 黑字 + 朱砂红（#c4644a）单一强调色
#   - 巨量留白（每个段落 60-80px 上下间距）
#   - 跨页大图（cover/toc/chapter/quote/closing 五段式）
#   - 巨字章节大字（120-160px）
#   - 首字下沉（drop cap，3 行高度）
#   - 极简分割（0.5px 灰线 / 无）
#   - line-height 2.2（大呼吸）
#
# 结构：
#   1. 封面页（cover）：hero 图（首图满宽） + 1/3 高度巨字标题 + 期刊标识
#   2. 目录页（toc）：极简数字列表
#   3. 章节页（chapter × N）：版式 A/B 交替（左图右文 / 上图下巨字）
#   4. 大字 quote 页（quote）：每 2-3 章出现一次，满屏朱砂大字
#   5. 结尾页（closing）：极简后记 + 期刊标识

_COVER_BG = "#fff"
_INK = "#1a1a1a"
_INK_LIGHT = "#666"
_INK_FAINT = "#999"
_RULE = "#e5e5e5"
_ACCENT = "#c4644a"  # 朱砂红 v3 调色

_FONT_SANS = (
    "-apple-system, BlinkMacSystemFont, 'PingFang SC', 'Helvetica Neue', "
    "Helvetica, 'Microsoft YaHei', sans-serif"
)


def _render_cover(sb: Storyboard, page_image_urls: list[str]) -> str:
    """封面页：hero 图（首图满宽）+ 巨字标题"""
    hero_url = page_image_urls[0] if page_image_urls else _placeholder_img("封面图", h=400)
    title = sb.title
    subtitle = sb.subtitle
    summary = sb.summary
    out = []
    out.append(
        # 整页外层
        '<div style="background:' + _COVER_BG + ';padding:0;margin:0;">'
        '<div style="max-width:420px;margin:0 auto;background:#fff;padding:0;">'
    )
    # Hero 图（满宽 50% 高度）
    out.append(
        f'<div style="width:100%;height:280px;overflow:hidden;background:#000;">'
        f'<img src="{_esc(hero_url)}" '
        f'style="width:100%;height:100%;object-fit:cover;display:block;" />'
        f'</div>'
    )
    # 留白
    out.append('<div style="height:60px;"></div>')
    # 期刊标识（顶部小字 + 强调色横线）
    out.append(
        '<div style="padding:0 32px;">'
        f'<p style="font-family:{_FONT_SANS};font-size:11px;'
        f'color:{_INK_LIGHT};letter-spacing:4px;margin:0 0 4px 0;'
        f'font-weight:500;">KNOWLEDGE COMIC</p>'
        f'<div style="width:24px;height:2px;background:{_ACCENT};'
        f'margin:0 0 32px 0;"></div>'
        f'<p style="font-family:{_FONT_SANS};font-size:13px;'
        f'color:{_INK};margin:0 0 4px 0;font-weight:400;'
        f'letter-spacing:1px;">{_esc(subtitle)}</p>'
        f'</div>'
    )
    # 留白
    out.append('<div style="height:40px;"></div>')
    # 巨字标题
    out.append(
        '<div style="padding:0 32px;">'
        f'<h1 style="font-family:{_FONT_SANS};font-size:64px;'
        f'color:{_INK};font-weight:800;margin:0;line-height:1.05;'
        f'letter-spacing:-2px;">{_esc(title)}</h1>'
        f'</div>'
    )
    # 留白
    out.append('<div style="height:48px;"></div>')
    # 导语（细线 + 小字）
    out.append(
        '<div style="padding:0 32px;">'
        f'<div style="width:32px;height:1px;background:{_INK};'
        f'margin:0 0 16px 0;"></div>'
        f'<p style="font-family:{_FONT_SANS};font-size:15px;'
        f'color:{_INK};line-height:1.7;margin:0;font-weight:400;">'
        f'{_esc(summary)}</p>'
        f'</div>'
    )
    # 底部留白
    out.append('<div style="height:60px;"></div>')
    out.append('</div></div>')
    return "\n".join(out)


def _render_toc(sb: Storyboard) -> str:
    """目录页：极简数字列表 + 朱砂页码"""
    out = []
    out.append(
        '<div style="background:' + _COVER_BG + ';padding:0;margin:0;">'
        '<div style="max-width:420px;margin:0 auto;background:#fff;padding:60px 32px;">'
    )
    # 顶部小字
    out.append(
        f'<p style="font-family:{_FONT_SANS};font-size:11px;'
        f'color:{_INK_LIGHT};letter-spacing:4px;margin:0 0 24px 0;">'
        f'CONTENTS</p>'
    )
    # 巨字"目录"
    out.append(
        f'<h2 style="font-family:{_FONT_SANS};font-size:48px;'
        f'color:{_INK};font-weight:800;margin:0 0 56px 0;'
        f'letter-spacing:6px;">目 录</h2>'
    )
    # 章节列表（极简）
    for i, page in enumerate(sb.pages, start=1):
        cn_num = _cn_section(i)
        out.append(
            f'<div style="display:flex;align-items:baseline;'
            f'padding:18px 0;border-bottom:1px solid {_RULE};">'
            f'<span style="font-family:{_FONT_SANS};font-size:14px;'
            f'color:{_ACCENT};font-weight:600;width:48px;flex-shrink:0;'
            f'letter-spacing:2px;">{cn_num}</span>'
            f'<span style="font-family:{_FONT_SANS};font-size:15px;'
            f'color:{_INK};font-weight:500;flex:1;'
            f'line-height:1.5;">{_esc(page.caption)}</span>'
            f'<span style="font-family:{_FONT_SANS};font-size:12px;'
            f'color:{_INK_FAINT};font-weight:400;width:36px;'
            f'text-align:right;flex-shrink:0;">P{page.page:02d}</span>'
            f'</div>'
        )
    out.append('</div></div>')
    return "\n".join(out)


def _render_chapter_a(sb: Storyboard, page, page_index: int, page_image_urls: list[str]) -> str:
    """版式 A：左图右文（左右分栏）"""
    image_url = page_image_urls[page_index] if page_index < len(page_image_urls) else _placeholder_img(f"page {page.page}")
    body = page.body or page.narration or ""
    out = []
    out.append(
        '<div style="background:' + _COVER_BG + ';padding:0;margin:0;">'
        '<div style="max-width:420px;margin:0 auto;background:#fff;padding:60px 0;">'
    )
    # 章节大字（顶部小）
    if page.highlight:
        out.append(
            '<div style="padding:0 32px 0 32px;">'
            f'<p style="font-family:{_FONT_SANS};font-size:12px;'
            f'color:{_ACCENT};letter-spacing:4px;margin:0 0 8px 0;'
            f'font-weight:600;">{_esc(_cn_section(page.page))} · {_esc(page.highlight)}</p>'
            f'</div>'
        )
    out.append('<div style="height:16px;"></div>')
    # caption（h2 大字）
    out.append(
        '<div style="padding:0 32px;">'
        f'<h2 style="font-family:{_FONT_SANS};font-size:24px;'
        f'color:{_INK};font-weight:700;margin:0 0 32px 0;'
        f'line-height:1.4;letter-spacing:-0.5px;">'
        f'{_esc(page.caption)}</h2>'
        f'</div>'
    )
    # 留白
    out.append('<div style="height:24px;"></div>')
    # 左图右文（移动端改上下，但桌面是分栏）
    out.append(
        '<div style="display:flex;gap:0;align-items:flex-start;'
        'padding:0 32px;'
        '@media (max-width: 600px) { flex-direction: column; }">'
    )
    # 左图
    out.append(
        f'<div style="width:42%;flex-shrink:0;">'
        f'<img src="{_esc(image_url)}" '
        f'style="width:100%;display:block;border-radius:0;" />'
        f'</div>'
    )
    # 右文（首字下沉 + body）
    if body:
        out.append(
            f'<div style="width:58%;padding-left:20px;">'
            f'<p style="font-family:{_FONT_SANS};font-size:14px;'
            f'color:{_INK};line-height:2.0;margin:0;'
            f'text-align:justify;">'
            f'{_esc(body)}'
            f'</p>'
            f'</div>'
        )
    out.append('</div>')
    # 底部留白
    out.append('<div style="height:80px;"></div>')
    out.append('</div></div>')
    return "\n".join(out)


def _render_chapter_b(sb: Storyboard, page, page_index: int, page_image_urls: list[str]) -> str:
    """版式 B：上 50% 图 + 下 50% 巨字 + 短文"""
    image_url = page_image_urls[page_index] if page_index < len(page_image_urls) else _placeholder_img(f"page {page.page}")
    body = page.body or page.narration or ""
    out = []
    out.append(
        '<div style="background:' + _COVER_BG + ';padding:0;margin:0;">'
        '<div style="max-width:420px;margin:0 auto;background:#fff;padding:0;">'
    )
    # 上半：图（满宽 50%）
    out.append(
        f'<div style="width:100%;height:300px;overflow:hidden;background:#000;">'
        f'<img src="{_esc(image_url)}" '
        f'style="width:100%;height:100%;object-fit:cover;display:block;" />'
        f'</div>'
    )
    # 留白
    out.append('<div style="height:48px;"></div>')
    # 章节标识
    if page.highlight:
        out.append(
            '<div style="padding:0 32px;">'
            f'<p style="font-family:{_FONT_SANS};font-size:12px;'
            f'color:{_ACCENT};letter-spacing:4px;margin:0 0 12px 0;'
            f'font-weight:600;">{_esc(_cn_section(page.page))} · {_esc(page.highlight)}</p>'
            f'</div>'
        )
    out.append('<div style="height:8px;"></div>')
    # caption（巨字 32px）
    out.append(
        '<div style="padding:0 32px;">'
        f'<h2 style="font-family:{_FONT_SANS};font-size:32px;'
        f'color:{_INK};font-weight:800;margin:0 0 24px 0;'
        f'line-height:1.3;letter-spacing:-0.5px;">'
        f'{_esc(page.caption)}</h2>'
        f'</div>'
    )
    out.append('<div style="height:24px;"></div>')
    # 短文（首字下沉简化版：直接 body）
    if body:
        out.append(
            '<div style="padding:0 32px;">'
            f'<p style="font-family:{_FONT_SANS};font-size:14px;'
            f'color:{_INK};line-height:2.0;margin:0;'
            f'text-align:justify;">'
            f'{_esc(body)}'
            f'</p>'
            f'</div>'
        )
    # 底部留白
    out.append('<div style="height:80px;"></div>')
    out.append('</div></div>')
    return "\n".join(out)


def _render_quote_page(page) -> str:
    """大字 quote 页：满屏朱砂大字金句"""
    out = []
    out.append(
        '<div style="background:#fff;padding:0;margin:0;">'
        '<div style="max-width:420px;margin:0 auto;background:#fff;'
        'padding:120px 40px;min-height:500px;'
        'display:flex;flex-direction:column;justify-content:center;align-items:flex-start;">'
    )
    # 朱砂小标
    out.append(
        f'<p style="font-family:{_FONT_SANS};font-size:12px;'
        f'color:{_ACCENT};letter-spacing:4px;margin:0 0 32px 0;'
        f'font-weight:600;">KEY · 关键节点</p>'
    )
    # 大字 quote（从 body 提取第一句）
    body = page.body or page.narration or ""
    first_sentence = body.split("。")[0] + "。" if "。" in body else body[:30]
    out.append(
        f'<p style="font-family:{_FONT_SANS};font-size:32px;'
        f'color:{_INK};line-height:1.5;font-weight:700;'
        f'letter-spacing:-0.5px;margin:0;">'
        f'{_esc(first_sentence)}</p>'
    )
    # 留白 + 小字出处
    out.append('<div style="height:48px;"></div>')
    out.append(
        f'<p style="font-family:{_FONT_SANS};font-size:12px;'
        f'color:{_INK_LIGHT};letter-spacing:2px;margin:0;">'
        f'— {_esc(_cn_section(page.page))} {_esc(page.caption)}</p>'
    )
    out.append('</div></div>')
    return "\n".join(out)


def _render_closing(sb: Storyboard) -> str:
    """结尾页：极简后记 + 期刊标识"""
    postscript = sb.postscript or ""
    out = []
    out.append(
        '<div style="background:#fff;padding:0;margin:0;">'
        '<div style="max-width:420px;margin:0 auto;background:#fff;padding:80px 32px;">'
    )
    # 极简"完"（大字符 + 朱砂）
    out.append(
        f'<p style="font-family:{_FONT_SANS};font-size:120px;'
        f'color:{_ACCENT};font-weight:200;margin:0 0 24px 0;'
        f'line-height:1;letter-spacing:0;">完</p>'
    )
    # 留白
    out.append('<div style="height:24px;"></div>')
    # 极简细线
    out.append(
        f'<div style="width:32px;height:1px;background:{_INK};'
        f'margin:0 0 16px 0;"></div>'
    )
    out.append(
        f'<p style="font-family:{_FONT_SANS};font-size:11px;'
        f'color:{_INK_LIGHT};letter-spacing:4px;margin:0 0 32px 0;'
        f'font-weight:500;">POSTSCRIPT</p>'
    )
    # 后记
    if postscript:
        out.append(
            f'<p style="font-family:{_FONT_SANS};font-size:15px;'
            f'color:{_INK};line-height:2.0;margin:0 0 48px 0;'
            f'font-weight:400;">'
            f'{_esc(postscript)}</p>'
        )
    # 极简 divider
    out.append(
        f'<div style="width:100%;height:1px;background:{_RULE};'
        f'margin:48px 0;"></div>'
    )
    # 期刊标识（底部）
    out.append(
        f'<p style="font-family:{_FONT_SANS};font-size:11px;'
        f'color:{_INK_LIGHT};letter-spacing:3px;margin:0 0 4px 0;'
        f'font-weight:500;">KNOWLEDGE COMIC</p>'
        f'<p style="font-family:{_FONT_SANS};font-size:11px;'
        f'color:{_INK_FAINT};letter-spacing:2px;margin:0;font-weight:400;">'
        f'二随哥哥好好说 · 2026</p>'
    )
    out.append('</div></div>')
    return "\n".join(out)


def render_template_c_v3(inp: ArticleInput) -> str:
    """C v3 · 现代极简风（Apple/MUJI 大字留白）

    五段式结构：cover → toc → chapter(交替) → quote(每 2 章) → closing
    """
    sb = inp.storyboard
    title = inp.title or sb.title
    out = ['<section data-template="c-v3">']

    # 1. 封面页（用首图）
    out.append(_render_cover(sb, inp.page_image_urls))

    # 2. 目录页
    out.append(_render_toc(sb))

    # 3. 章节页（版式 A/B 交替）
    for i, page in enumerate(sb.pages):
        # 版式 A 和 B 交替（A=左图右文, B=上图下巨字）
        if i % 2 == 0:
            out.append(_render_chapter_a(sb, page, i, inp.page_image_urls))
        else:
            out.append(_render_chapter_b(sb, page, i, inp.page_image_urls))

        # 每 2 章插入一个 quote 页（取自当前章节）
        if (i + 1) % 2 == 0 and i < len(sb.pages) - 1:
            out.append(_render_quote_page(page))

    # 4. 结尾页
    out.append(_render_closing(sb))

    out.append('</section>')
    return "\n".join(out)


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


def render_preview_article(sb: Storyboard, image_paths: list[Path], template: str = "a") -> str:
    page_urls = [file_to_data_uri(p) for p in image_paths]
    return render_article(ArticleInput(
        storyboard=sb, page_image_urls=page_urls,
    ), template=template)


def render_publish_article(sb: Storyboard, wechat_image_urls: list[str], template: str = "e") -> str:
    return render_article(ArticleInput(
        storyboard=sb, page_image_urls=wechat_image_urls,
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


def render_mock_preview_v3(storyboard, template: str = "c_v3") -> str:
    """c v3 mock preview（占位图）。"""
    from .planner import StoryPage

    image_urls = [_placeholder_img(f"p{i+1}", h=300) for i in range(len(storyboard.pages))]
    return render_article(ArticleInput(
        storyboard=storyboard, page_image_urls=image_urls,
    ), template=template)