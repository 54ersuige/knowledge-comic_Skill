"""分镜审阅页（v0.3.4 新增）。

解决的问题：Checkpoint 1（生图前定方向和内容）原本只能让用户/raw JSON 审阅，
但 storyboard.json 有 keywords / body / visual / highlight 等多层嵌套字段，
用户（和 Mavis）很难快速判断"哪几页不合格"。跑图很贵，分镜错了后面全白费。

本模块提供三样东西：
  1. check_quality()      —— 自动体检，算出每页的硬约束问题（不调 LLM，纯规则）
  2. render_markdown()    —— 对话里直接贴给用户的审阅卡（紧凑，只展开问题页）
  3. render_html()        —— 完整 HTML 审阅页（浏览器看，逐页详情 + 统计看板）

设计原则：**先给结论，再给细节**。体检有问题的页排在最前、全文展开；
全过的页只给一行摘要，避免 10 页正文把对话刷屏。

Mavis 对话流里的用法：
    md_path, html_path = step_review_storyboard(job_id)
    # → 把 md_path 的内容贴给用户 + deliver-assets 送 html_path
    # → ask_user 拍板
"""
from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass

# 硬约束阈值（与 planner.py 的 prompt 铁律保持一致）
BODY_MIN = 100
BODY_MAX = 150
KEYWORDS_MIN = 3
KEYWORDS_IDEAL = 5
VISUAL_MIN = 300
MULTI_FIGURE_MIN = 2


@dataclass
class Issue:
    """单页的一条体检问题。level: error=必须修 / warn=建议修 / ok=通过"""

    page: int
    level: str      # "error" | "warn"
    field: str      # body / keywords / visual / highlight / caption
    msg: str

    @property
    def icon(self) -> str:
        return "❌" if self.level == "error" else "⚠️"


# --- 单项检查 ---------------------------------------------------------------

def _check_body(p: dict, is_story: bool) -> Issue | None:
    """正文长度。用户偏好：100-150 字硬上限，图为主文字为脚注。"""
    body = (p.get("body") or "").strip()
    if not body:
        return Issue(p["page"], "error", "body", "正文为空")
    n = len(body)
    if n > BODY_MAX:
        return Issue(p["page"], "error", "body",
                     f"正文 {n} 字，超出 {BODY_MAX} 字上限（文字太重会压过画面）")
    if n < BODY_MIN:
        return Issue(p["page"], "warn", "body",
                     f"正文 {n} 字，低于 {BODY_MIN} 字下限（可补画面没说的事）")
    return None


def _check_keywords(p: dict) -> Issue | None:
    kws = p.get("keywords") or []
    if not kws:
        return Issue(p["page"], "error", "keywords",
                     "keywords 为空 —— 朱砂红高亮会完全失效")
    if len(kws) < KEYWORDS_MIN:
        return Issue(p["page"], "warn", "keywords",
                     f"keywords 仅 {len(kws)} 个，建议 {KEYWORDS_IDEAL}+ 个")
    return None


def _check_visual(p: dict) -> Issue | None:
    v = (p.get("visual") or "").strip()
    if not v:
        return Issue(p["page"], "error", "visual", "画面描述为空")
    if len(v) < VISUAL_MIN:
        return Issue(p["page"], "warn", "visual",
                     f"画面描述仅 {len(v)} 字，偏短可能信息密度不足（七要素建议 ≥{VISUAL_MIN} 字）")
    return None


def _check_gender_tag(p: dict, style_id: str) -> Issue | None:
    """连环画风格必须每页带 [GENDER:xx]，否则男性主角会被性转成女性脸。"""
    if style_id != "chinese_lianhuanhua_classic":
        return None
    v = p.get("visual") or ""
    if "[GENDER:" not in v.upper():
        return Issue(p["page"], "error", "visual",
                     "缺 [GENDER:xx] 标记 —— 连环画风格靠它区分男女角色，"
                     "缺失会把男性主角画成女性脸")
    return None


def _check_multi_figure(p: dict, style_id: str) -> Issue | None:
    """连环画风格要求多人物满画幅（戴敦邦/顾炳鑫派），单人工笔淡彩不符。"""
    if style_id != "chinese_lianhuanhua_classic":
        return None
    v = (p.get("visual") or "").upper()
    markers = ("SECONDARY", "SUBJECT 2", "SECOND", "THIRD", "ATTENDANT",
               "CROWD", "GUARDS", "SOLDIER", "MULTIPLE FIGURES", "3+")
    if not any(m in v for m in markers):
        return Issue(p["page"], "warn", "visual",
                     "画面似为单人物 —— 连环画风格要求 3+ 主人物 + 远景配角 + 多道具")
    return None


def _check_zero_text(p: dict) -> Issue | None:
    """零文字铁律：画面里出现文字是本项目最常复发的 bug。"""
    v = (p.get("visual") or "").upper()
    if "NO TEXT" not in v and "STRICT NO TEXT" not in v and "NO WRITING" not in v:
        return Issue(p["page"], "warn", "visual",
                     "未声明零文字约束 —— 建议追加 STRICT NO TEXT")
    return None


def _check_caption(p: dict) -> Issue | None:
    if not (p.get("caption") or "").strip():
        return Issue(p["page"], "error", "caption", "章节题为空")
    return None


def check_quality(raw: dict) -> dict:
    """对整个 storyboard 跑体检。

    Returns:
        {"issues": [Issue,...], "stats": {...}}
    """
    style_id = raw.get("style_id", "")
    pages = raw.get("pages", [])
    is_story = style_id in ("chinese_lianhuanhua_classic", "guochao_manhua", "cn_xuanfeng")

    issues: list[Issue] = []
    for p in pages:
        for fn in (_check_caption, _check_visual, _check_keywords, _check_zero_text):
            i = fn(p)
            if i:
                issues.append(i)
        i = _check_body(p, is_story)
        if i:
            issues.append(i)
        i = _check_gender_tag(p, style_id)
        if i:
            issues.append(i)
        i = _check_multi_figure(p, style_id)
        if i:
            issues.append(i)

    # 跨页检查
    hl = [p.get("highlight", "").strip() for p in pages]
    dupes = {h for h in hl if h and hl.count(h) > 1}
    if dupes:
        first = next(p["page"] for p in pages if p.get("highlight", "").strip() in dupes)
        issues.append(Issue(first, "warn", "highlight",
                            f"章节大字重复：{'、'.join(dupes)}（应跨章唯一）"))

    n = len(pages) or 1
    stats = {
        "pages": len(pages),
        "body_ok": sum(1 for p in pages if BODY_MIN <= len((p.get("body") or "").strip()) <= BODY_MAX),
        "kw_ok": sum(1 for p in pages if len(p.get("keywords") or []) >= KEYWORDS_MIN),
        "kw_total": sum(len(p.get("keywords") or []) for p in pages),
        "body_avg": int(sum(len((p.get("body") or "").strip()) for p in pages) / n),
        "visual_avg": int(sum(len((p.get("visual") or "")) for p in pages) / n),
        "gender_ok": sum(1 for p in pages if "[GENDER:" in (p.get("visual") or "").upper()),
        "errors": sum(1 for i in issues if i.level == "error"),
        "warns": sum(1 for i in issues if i.level == "warn"),
    }
    # 排序：error 优先，其次按页码
    issues.sort(key=lambda i: (0 if i.level == "error" else 1, i.page))
    return {"issues": issues, "stats": stats}


# --- Markdown 审阅卡 -------------------------------------------------------

def render_markdown(raw: dict, health: dict) -> str:
    """对话里贴给用户的审阅卡。

    结构：标题 → 自动体检看板 → 问题页详情 → 全部页一览
    问题页展开 caption/body/keywords/visual 全字段；正常页只给一行。
    """
    e = _html.escape
    stats = health["stats"]
    issues = health["issues"]
    pages = raw.get("pages", [])
    by_page: dict[int, list[Issue]] = {}
    for i in issues:
        by_page.setdefault(i.page, []).append(i)

    out: list[str] = []
    out.append(f"## 《{raw.get('title', raw.get('topic', ''))}》分镜审阅")
    if raw.get("subtitle"):
        out.append(f"*{raw['subtitle']}*")
    out.append("")
    out.append(
        f"`{raw.get('style_id')}` · 模板 `{raw.get('recommended_template', '?')}` · "
        f"{stats['pages']} 页"
    )

    # 体检看板
    out.append("")
    out.append("### 自动体检")
    out.append("")
    err, warn = stats["errors"], stats["warns"]
    if err == 0 and warn == 0:
        out.append("✅ 全部硬约束通过")
    else:
        head = "🔴" if err else "🟡"
        out.append(f"{head} **{err} 个必修项** / {warn} 个建议项")
    out.append("")
    out.append("| 检查项 | 结果 |")
    out.append("|---|---|")
    out.append(f"| 正文 {BODY_MIN}-{BODY_MAX} 字 | {stats['body_ok']}/{stats['pages']} "
               f"（平均 {stats['body_avg']} 字） |")
    out.append(f"| 关键词高亮 | {stats['kw_ok']}/{stats['pages']} 页"
               f"（共 {stats['kw_total']} 个） |")
    if raw.get("style_id") == "chinese_lianhuanhua_classic":
        out.append(f"| 性别标记 [GENDER:xx] | {stats['gender_ok']}/{stats['pages']} |")
    out.append(f"| 画面描述长度 | 平均 {stats['visual_avg']} 字 |")

    # 问题页详情
    bad_pages = sorted(by_page)
    if bad_pages:
        out.append("")
        out.append("### ⚠ 需要过手的页")
        for pno in bad_pages:
            pg = next((x for x in pages if x["page"] == pno), None)
            if not pg:
                continue
            out.append("")
            out.append(f"**p{pno:02d} {pg.get('highlight') or '(无章节题)'}**")
            for i in by_page[pno]:
                out.append(f"- {i.icon} `{i.field}`：{i.msg}")
            out.append("")
            if pg.get("caption"):
                out.append(f"  > {pg['caption']}")
            body = (pg.get("body") or "").strip()
            if body:
                out.append("")
                out.append(f"  正文（{len(body)} 字）：{body}")
            kws = pg.get("keywords") or []
            if kws:
                out.append("")
                out.append("  关键词：" + " / ".join(kws))
            v = (pg.get("visual") or "").strip()
            if v:
                out.append("")
                out.append("  画面：")
                for seg in [s.strip() for s in re.split(r"(?<=[.。])\s+", v) if s.strip()][:4]:
                    out.append(f"  > {seg}")

    # 全页一览
    out.append("")
    out.append("### 全部页面")
    out.append("")
    out.append("| 页 | 章节题 | caption | 正文 | 关键词 |")
    out.append("|---|---|---|---|---|")
    for pg in pages:
        flag = " ⚠" if pg["page"] in by_page else ""
        body = (pg.get("body") or "").strip()
        kws = pg.get("keywords") or []
        cap = (pg.get("caption") or "").replace("|", "\\|")[:26]
        out.append(
            f"| p{pg['page']:02d}{flag} | {pg.get('highlight') or '—'} | {cap} | "
            f"{len(body)}字 | {' / '.join(kws[:4]) or '—'} |"
        )
    out.append("")
    return "\n".join(out)


# --- HTML 审阅页 -----------------------------------------------------------

_HTML_TMPL = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ · 分镜审阅</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#f4efe4;color:#2b2622;
  font:15px/1.75 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:920px;margin:0 auto;padding:32px 20px 80px}
header{background:linear-gradient(135deg,#9b2332,#7a1b27);color:#fff;
  border-radius:12px;padding:28px 30px;margin-bottom:24px}
header h1{margin:0 0 8px;font-size:26px;letter-spacing:1px}
header .sub{opacity:.9;font-size:14px}
.badges{margin-top:14px;display:flex;gap:8px;flex-wrap:wrap}
.badge{background:rgba(255,255,255,.18);padding:4px 12px;border-radius:20px;font-size:13px}
.board{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:28px}
.card{background:#fff;border-radius:10px;padding:16px 18px;border-left:4px solid #9b2332}
.card .k{font-size:12px;color:#8a8078;letter-spacing:1px}
.card .v{font-size:22px;font-weight:700;margin-top:4px}
.card .n{font-size:12px;color:#a0968c;margin-top:2px}
.card.ok{border-left-color:#4a7c59}.card.warn{border-left-color:#c8952f}
.page{background:#fff;border-radius:10px;padding:20px 24px;margin-bottom:14px;
  border:1px solid #e5ddd0;border-left:4px solid #cfc4b4}
.page.bad{border-left-color:#9b2332;background:#fffdfa}
.page-no{font-family:Georgia,serif;font-size:13px;color:#9b2332;letter-spacing:2px}
.page h2{margin:4px 0 12px;font-size:19px;color:#2b2622}
.cap{font-size:15px;color:#4a4239;margin:10px 0;padding:10px 14px;
  background:#faf6ee;border-radius:6px;border-left:3px solid #c9a227}
.body{font-size:14.5px;line-height:1.9;color:#3a332c;margin:12px 0;white-space:pre-wrap}
.kw{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}
.kw span{background:#9b2332;color:#fff;padding:3px 10px;border-radius:4px;font-size:12.5px}
.visual{background:#f7f3ea;border-radius:6px;padding:12px 14px;font-size:13px;
  color:#5a5147;line-height:1.8;font-family:ui-monospace,Menlo,Consolas,monospace}
.issues{margin:12px 0;padding:0;list-style:none}
.issues li{font-size:13.5px;padding:7px 12px;border-radius:5px;margin-bottom:5px}
.issues li.error{background:#fdecec;color:#8b1a1a;border-left:3px solid #9b2332}
.issues li.warn{background:#fdf6e3;color:#7a5b12;border-left:3px solid #c8952f}
.tabs{display:flex;gap:8px;margin:24px 0 14px;flex-wrap:wrap}
.tab{background:#fff;border:1px solid #ddd3c3;padding:7px 16px;border-radius:20px;
  cursor:pointer;font-size:13.5px}
.tab.on{background:#9b2332;color:#fff;border-color:#9b2332}
.hide{display:none}
</style></head><body><div class="wrap">
<header>
  <h1>__TITLE__</h1>
  <div class="sub">__SUBTITLE__</div>
  <div class="badges">__BADGES__</div>
</header>
<div class="board">__BOARD__</div>
__BODY__
</div>
<script>
function only(id){document.querySelectorAll('.page').forEach(function(p){
  p.classList.toggle('hide', id!=='all' && p.dataset.flag!==id);});}
document.querySelectorAll('.tab').forEach(function(t){t.onclick=function(){
  document.querySelectorAll('.tab').forEach(function(x){x.classList.remove('on')});
  t.classList.add('on'); only(t.dataset.f);};});
</script>
</body></html>"""


def render_html(raw: dict, health: dict) -> str:
    """完整 HTML 审阅页（浏览器打开）。"""
    e = _html.escape
    stats = health["stats"]
    pages = raw.get("pages", [])
    by_page: dict[int, list[Issue]] = {}
    for i in health["issues"]:
        by_page.setdefault(i.page, []).append(i)

    bad_pages = sorted(by_page)
    badges = [
        f"{raw.get('style_id')}",
        f"模板 {raw.get('recommended_template', '?')}",
        f"{stats['pages']} 页",
        f"{len(bad_pages)} 页待改" if bad_pages else "全部通过",
    ]

    def card(k, v, n="", cls=""):
        return (f'<div class="card {cls}"><div class="k">{k}</div>'
                f'<div class="v">{v}</div><div class="n">{n}</div></div>')

    board = "".join([
        card("正文达标", f"{stats['body_ok']}/{stats['pages']}",
             f"{BODY_MIN}-{BODY_MAX} 字 · 平均 {stats['body_avg']}",
             "ok" if stats["body_ok"] == stats["pages"] else "warn"),
        card("关键词高亮", f"{stats['kw_ok']}/{stats['pages']}",
             f"共 {stats['kw_total']} 个", "ok" if stats["kw_ok"] == stats["pages"] else "warn"),
        card("必修项", stats["errors"], "必须改", "warn" if stats["errors"] else "ok"),
        card("建议项", stats["warns"], "可以不改", "warn" if stats["warns"] else "ok"),
    ])

    chunks = []
    for p in pages:
        issues = by_page.get(p["page"], [])
        flag = "bad" if any(i.level == "error" for i in issues) else (
            "warn" if issues else "ok")
        kws = p.get("keywords") or []
        body = (p.get("body") or "").strip()
        vis = (p.get("visual") or "").strip()
        li = "".join(
            f'<li class="{i.level}">{i.icon} <b>{i.field}</b>：{e(i.msg)}</li>'
            for i in issues
        )
        kw_html = "".join(f"<span>{e(k)}</span>" for k in kws)
        chunks.append(f"""<div class="page {flag if flag!='ok' else ''}" data-flag="{flag}">
<div class="page-no">PAGE {p['page']:02d}</div>
<h2>{e(p.get('highlight') or '(无章节题)')}</h2>
{f'<ul class="issues">{li}</ul>' if li else ''}
{f'<div class="cap">{e(p.get("caption") or "")}</div>' if p.get('caption') else ''}
{f'<div class="body">{e(body)}</div>' if body else ''}
{f'<div class="kw">{kw_html}</div>' if kw_html else ''}
{f'<div class="visual">{e(vis)}</div>' if vis else ''}
</div>""")

    tabs = ('<div class="tabs">'
            f'<div class="tab on" data-f="all">全部 {len(pages)}</div>'
            f'<div class="tab" data-f="bad">必修 {sum(1 for p in pages if any(i.level=="error" for i in by_page.get(p["page"],[])))}</div>'
            f'<div class="tab" data-f="warn">建议 {len(bad_pages)}</div>'
            "</div>")

    return _HTML_TMPL.replace("__TITLE__", e(raw.get("title") or raw.get("topic", ""))) \
        .replace("__SUBTITLE__", e(raw.get("subtitle") or "")) \
        .replace("__BADGES__", "".join(f'<span class="badge">{e(b)}</span>' for b in badges)) \
        .replace("__BOARD__", board) \
        .replace("__BODY__", tabs + "".join(chunks))
