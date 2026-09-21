"""knowledge-comic Skill · 端到端 step runner

v0.2 重构（2026-09-20）：
  - 去掉 subprocess(input) checkpoint 流程（Mavis 对话里接不到 stdin）
  - 改成"step-by-step"：每个 step 独立可调，Mavis 在对话里逐步执行 + ask_user 拍板
  - 旧 CLI 兼容保留为 --all 一键跑通（适合 cron/CI）

用法（旧 CLI 兼容）：
    python scripts/run.py all --topic "X" --bullets "..." --style new_yorker --template e
    python scripts/run.py plan --topic "X" --bullets "..." --style new_yorker
    python scripts/run.py gen --job-id kc_xxx
    python scripts/run.py render --job-id kc_xxx --template e
    python scripts/run.py publish --job-id kc_xxx

新 Mavis 对话工作流（推荐）：
    from scripts.run import (
        step_plan, step_gen_images, step_render_article, step_publish_draft,
    )
    sb, job_id = step_plan(topic, bullets, style_id="new_yorker", template_id="e")
    # → Mavis 展示 storyboard（用 read tool 读 job_id/storyboard.json）+ ask_user 拍板
    image_paths = step_gen_images(job_id)
    # → Mavis 用 deliver-assets 展示图片 + ask_user 拍板
    html_path = step_render_article(job_id, template_id="e")
    # → Mavis 展示 html + ask_user 拍板
    draft_id = step_publish_draft(job_id, template_id="e")
    # → Mavis 报告 draft_media_id + 公众号后台链接
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent  # scripts/run.py → parent.parent = knowledge-comic/
sys.path.insert(0, str(SKILL_ROOT))

from scripts.core.config import get_config  # noqa: E402
from scripts.core.planner import plan_storyboard, Storyboard, StoryPage  # noqa: E402
from scripts.core.image_gen import generate_pages  # noqa: E402
from scripts.core import article as article_mod  # noqa: E402
from scripts.core import publisher as pub_mod  # noqa: E402
from scripts.core.prompts import (  # noqa: E402
    recommend_style,
    recommend_template,
    get_style,
)


# ============ Mavis 对话工作流 API（推荐入口） ============

def step_plan(
    topic: str,
    bullets: list[str],
    style_id: str | None = None,
    template_id: str | None = None,
    use_llm: bool = True,
    data_dir: Path | None = None,
) -> tuple[Storyboard, str, Path]:
    """Step 1: 主题 + 要点 → storyboard JSON + job_id + work_dir

    Returns:
        (storyboard, job_id, work_dir)

    Mavis 在对话里：
      1. 调本函数拿到 storyboard
      2. 用 read tool 读 work_dir/storyboard.json 展示给用户
      3. 用 ask_user 让用户拍板（接受 / 改某页 / 重跑）
    """
    cfg = get_config()
    work_root = data_dir or cfg.data_dir

    # 默认推荐
    if not style_id:
        style_id, _ = recommend_style(topic)
        print(f"[auto-style] 推荐 {style_id}")
    if not template_id:
        template_id, _ = recommend_template(topic)
        print(f"[auto-template] 推荐 {template_id}")

    sb = plan_storyboard(topic, bullets, style_id, use_llm=use_llm)

    job_id = f"kc_{int(time.time())}"
    work_dir = work_root / job_id
    work_dir.mkdir(parents=True, exist_ok=True)

    # 把推荐 template 写到 storyboard.json 里（便于后续 render 步用）
    sb_dict = sb.to_dict()
    sb_dict["recommended_template"] = template_id
    (work_dir / "storyboard.json").write_text(
        json.dumps(sb_dict, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"[plan] job_id={job_id}  style={style_id}  template={template_id}  pages={len(sb.pages)}")
    return sb, job_id, work_dir


def step_gen_images(
    job_id: str,
    data_dir: Path | None = None,
    regenerate_pages: list[int] | None = None,
) -> list[Path]:
    """Step 2: 从 storyboard.json 跑图 → PNG 列表

    Args:
        job_id: job id
        regenerate_pages: 重画的页码列表（用户审核后给出）
    Returns:
        图片 Path 列表（按页码排序）

    Mavis 在对话里：
      1. 调本函数拿到图片 paths
      2. 用 deliver-assets 把图送到用户面前
      3. 用 ask_user 让用户拍板（接受 / 改某页重跑）
    """
    cfg = get_config()
    work_root = data_dir or cfg.data_dir
    work_dir = work_root / job_id
    sb_path = work_dir / "storyboard.json"
    sb = _load_storyboard(sb_path)

    if regenerate_pages:
        pages_to_gen = [p for p in sb.pages if p.page in regenerate_pages]
        if not pages_to_gen:
            print(f"[gen] regenerate_pages {regenerate_pages} 不在 storyboard 中，跳过")
            return sorted((work_dir / "pages").glob("*.png"))

        rerender_sb = Storyboard(
            topic=sb.topic,
            style_id=sb.style_id,
            pages=pages_to_gen,
            title=sb.title,
            subtitle=sb.subtitle,
            summary=sb.summary,
            preface=sb.preface,
            epigraph=sb.epigraph,
            postscript=sb.postscript,
        )
        new_paths = generate_pages(rerender_sb, job_id)
        # 替换原路径
        existing = {int(p.stem.split("-")[0]): i for i, p in enumerate(_current_images(work_dir))}
        all_paths = _current_images(work_dir)
        for new_path in new_paths:
            page_no = int(new_path.stem.split("-")[0])
            if page_no in existing:
                all_paths[existing[page_no]] = new_path
        print(f"[gen] 重画 {len(new_paths)} 页,共 {len(all_paths)} 张")
        return all_paths
    else:
        paths = generate_pages(sb, job_id)
        print(f"[gen] 生成 {len(paths)} 张")
        return paths


def step_render_article(
    job_id: str,
    template_id: str | None = None,
    image_paths: list[Path] | None = None,
    data_dir: Path | None = None,
) -> Path:
    """Step 3: storyboard + 图片 → 公众号 HTML

    Args:
        job_id: job id
        template_id: 模板 ID（默认从 storyboard.json 读 recommended_template）
        image_paths: 图片路径列表（默认从 work_dir/pages/*.png 读）
    Returns:
        html_path

    Mavis 在对话里：
      1. 调本函数拿到 html_path
      2. 用 read tool 读 HTML 展示给用户
      3. 用 ask_user 让用户拍板（接受发草稿 / 改模板 / 拒绝）
    """
    cfg = get_config()
    work_root = data_dir or cfg.data_dir
    work_dir = work_root / job_id
    sb = _load_storyboard(work_dir / "storyboard.json")

    if template_id is None:
        template_id = sb.to_dict().get("recommended_template", "e")
        print(f"[auto-template] 使用推荐 {template_id}")

    if image_paths is None:
        image_paths = sorted((work_dir / "pages").glob("*.png"))

    html = article_mod.render_publish_article(
        sb, [str(p) for p in image_paths], template=template_id
    )
    html_path = work_dir / f"article_{template_id}.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"[render] template={template_id}  html={html_path}  size={len(html)} chars")
    return html_path


def step_publish_draft(
    job_id: str,
    template_id: str | None = None,
    image_paths: list[Path] | None = None,
    data_dir: Path | None = None,
    dry_run: bool = False,
) -> dict:
    """Step 4: 上传图片 + 创建草稿

    Args:
        job_id: job id
        template_id: 模板 ID
        dry_run: True = 不实际发布,只生成 publish html
    Returns:
        {"draft_media_id": "...", "uploaded_count": N, "work_dir": "..."}

    Mavis 在对话里：
      1. 调本函数拿到 draft_media_id
      2. 报告 draft_media_id + 公众号后台链接
    """
    cfg = get_config()
    work_root = data_dir or cfg.data_dir
    work_dir = work_root / job_id
    sb = _load_storyboard(work_dir / "storyboard.json")

    if template_id is None:
        template_id = sb.to_dict().get("recommended_template", "e")

    if image_paths is None:
        image_paths = sorted((work_dir / "pages").glob("*.png"))

    if dry_run:
        print(f"[publish:DRY-RUN] job={job_id}  template={template_id}  pages={len(image_paths)}")
        return {"dry_run": True, "job_id": job_id, "work_dir": str(work_dir)}

    # 上传图片到公众号素材库
    uploaded = []
    wechat_urls = []
    for i, path in enumerate(image_paths, start=1):
        print(f"  [{i}/{len(image_paths)}] uploading {path.name}", end=" ... ", flush=True)
        result = pub_mod.add_permanent_image(path)
        uploaded.append({"page": i, "media_id": result["media_id"], "url": result["url"]})
        wechat_urls.append(result["url"])
        print(f"OK")

    # 用微信 URL 重渲染（图片走微信 CDN 才不会被删）
    publish_html = article_mod.render_publish_article(
        sb, wechat_urls, template=template_id
    )
    (work_dir / f"publish_{template_id}.html").write_text(publish_html, encoding="utf-8")

    draft_id = pub_mod.create_draft(
        title=sb.title,
        content_html=publish_html,
        thumb_media_id=uploaded[0]["media_id"],
    )

    return {
        "draft_media_id": draft_id,
        "uploaded_count": len(uploaded),
        "work_dir": str(work_dir),
        "title": sb.title,
    }


# ============ Mavis 对话流辅助 step（v0.2.4 补齐） ============


def step_rewrite_visual(
    job_id: str,
    page_no: int,
    new_visual: str,
    data_dir: Path | None = None,
) -> Path:
    """Step 辅助:重写某一页 visual + 立即重跑该页图。

    用途:用户读图后发现"风格跑偏/构图不对/缺元素",直接说"p10 改成...","p11 改成..."。

    Args:
        job_id: job id
        page_no: 页码 (1-based)
        new_visual: 新的 visual 描述（按 v0.2.3 七要素结构）
        data_dir: 数据目录

    Returns:
        新生成的页面图片路径。

    Example:
        >>> path = step_rewrite_visual(
        ...     "kc_1789954427",
        ...     10,
        ...     "CRITICAL — The entire frame is a classical Chinese lianhuanhua painted illustration, NOT a photograph. "
        ...     "Han Yu kneeling on a low writing mat, brush in hand mid-arc..."
        ... )
    """
    cfg = get_config()
    work_root = data_dir or cfg.data_dir
    work_dir = work_root / job_id
    sb_path = work_dir / "storyboard.json"

    raw = json.loads(sb_path.read_text(encoding="utf-8"))
    target = next((p for p in raw["pages"] if p["page"] == page_no), None)
    if target is None:
        raise ValueError(f"job={job_id} has no page {page_no}")
    target["visual"] = new_visual
    sb_path.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[rewrite-visual] job={job_id} page={page_no} visual len={len(new_visual)}")

    # 立即重跑该页
    paths = step_gen_images(job_id, regenerate_pages=[page_no], data_dir=data_dir)
    return paths[0]


def step_show_intent_vs_actual(
    job_id: str,
    data_dir: Path | None = None,
) -> str:
    """Step 辅助:输出"分镜意图 vs 实际画面"对照表(Mavis 必调用)。

    用途:Mavis 在 step_gen_images 完成后,**必须**调本函数,把对照表嵌入到 deliver-assets 后。
    用户反馈:2026-09-21 张巡守睢阳项目明确要求"每个画表达的是什么内容必须能判断"。

    Args:
        job_id: job id
        data_dir: 数据目录

    Returns:
        Markdown 表格字符串。每页一行,含:
        - 页码 + 章节(highlight)
        - 分镜意图(caption + key_visual 摘要)
        - 实际画面描述(Mavis 自己 read tool 读 PNG 后填)
        - 评估占位(✅/⚠/❌ + 文字说明)

    Example:
        >>> table = step_show_intent_vs_actual("kc_1789954427")
        >>> # Mavis 用 read tool 实际看图,补"实际画面"列 + 评估列
    """
    cfg = get_config()
    work_root = data_dir or cfg.data_dir
    work_dir = work_root / job_id
    raw = json.loads((work_dir / "storyboard.json").read_text(encoding="utf-8"))

    lines = ["| 页 | 章节 | 分镜意图 | 实际画面 | 评估 |", "|---|---|---|---|---|"]
    for p in raw["pages"]:
        page = p["page"]
        highlight = p.get("highlight", "")
        caption = p.get("caption", "")
        key_visual = p.get("key_visual", "")
        visual = p.get("visual", "")[:120].replace("|", "\\|").replace("\n", " ")
        page_path = work_dir / "pages" / f"{page:02d}-page.png"
        exists = "[已生成]" if page_path.exists() else "[未生成]"
        lines.append(
            f"| p{page} {highlight} | {caption} | key_visual: {key_visual} \\| visual 前 120 字: {visual}... | {exists}(待 Mavis 用 read tool 实际读图后补) | (待 Mavis 标 ✅/⚠/❌ + 文字) |"
        )
    return "\n".join(lines)


def step_dry_publish(
    job_id: str,
    template_id: str | None = None,
    data_dir: Path | None = None,
) -> Path:
    """Step 辅助: dry-run 渲染 publish HTML(不调 draft/add)。

    用途:用户想看发布版 HTML 长什么样,但不想真发草稿。本函数:
    1. 上传所有图到素材库(必须,因为 publish html 里的 URL 要换成 WeChat CDN)
    2. 渲染 publish_xxx.html
    3. **不**调 draft/add
    4. 返回 publish html 路径 + 草稿箱链接(用户决定是否真发)

    下一步真发: 再调 `step_publish_draft(job_id, template_id=...)` 一行就行。
    """
    cfg = get_config()
    work_root = data_dir or cfg.data_dir
    work_dir = work_root / job_id
    sb = _load_storyboard(work_dir / "storyboard.json")

    if template_id is None:
        template_id = sb.recommended_template or "e"

    image_paths = _current_images(work_dir)
    if not image_paths:
        raise RuntimeError(f"No images in {work_dir}/pages. Run step_gen_images first.")

    # Step 1: 上传所有图片
    uploaded = []
    wechat_urls = []
    for i, path in enumerate(image_paths, start=1):
        print(f"  [{i}/{len(image_paths)}] uploading {path.name}", end=" ... ", flush=True)
        result = pub_mod.add_permanent_image(path)
        uploaded.append({"page": i, "media_id": result["media_id"], "url": result["url"]})
        wechat_urls.append(result["url"])
        print("OK")

    # Step 2: 渲染 publish html
    publish_html = article_mod.render_publish_article(sb, wechat_urls, template=template_id)
    publish_path = work_dir / f"publish_{template_id}.html"
    publish_path.write_text(publish_html, encoding="utf-8")
    print(f"[dry-publish] rendered: {publish_path}")
    print(f"[dry-publish] next step: step_publish_draft(job_id='{job_id}', template_id='{template_id}') to actually create draft")
    return publish_path


def step_preflight(
    job_id: str,
    template_id: str | None = None,
    data_dir: Path | None = None,
) -> dict:
    """Step 辅助:发布前自检(不发布)。

    检查项:
    1. storyboard.json 存在且完整(>= 6 页)
    2. 所有 pages/*.png 存在且 < 2MB(公众号素材库上限)
    3. 推荐模板存在(article.py:render_publish_article 支持 a/c/e)
    4. access_token 通(测一次,不缓存)
    5. WECHAT_APPID / WECHAT_APPSECRET 已配

    Returns:
        {"ok": bool, "checks": [{"name": ..., "ok": bool, "detail": ...}, ...]}

    Mavis 用途:调 step_publish_draft 前先调本函数,避免跑到一半才发现图太大/IP 没加白名单。
    """
    cfg = get_config()
    work_root = data_dir or cfg.data_dir
    work_dir = work_root / job_id
    sb_path = work_dir / "storyboard.json"

    checks = []

    # Check 1: storyboard.json 存在
    if not sb_path.exists():
        checks.append({"name": "storyboard.json", "ok": False, "detail": f"missing: {sb_path}"})
        return {"ok": False, "checks": checks}
    checks.append({"name": "storyboard.json", "ok": True, "detail": str(sb_path)})

    raw = json.loads(sb_path.read_text(encoding="utf-8"))

    # Check 2: storyboard 完整(>= 6 页)
    pages = raw.get("pages", [])
    if len(pages) < 6:
        checks.append({"name": "page_count", "ok": False, "detail": f"only {len(pages)} pages"})
    else:
        checks.append({"name": "page_count", "ok": True, "detail": f"{len(pages)} pages"})

    # Check 3: 所有图片存在 + < 2MB
    pages_dir = work_dir / "pages"
    image_paths = sorted(pages_dir.glob("*.png")) if pages_dir.exists() else []
    if not image_paths:
        checks.append({"name": "images", "ok": False, "detail": "no images found"})
    else:
        over_limit = []
        for p in image_paths:
            size_mb = p.stat().st_size / 1024 / 1024
            if size_mb > 2:
                over_limit.append(f"{p.name}={size_mb:.1f}MB")
        if over_limit:
            checks.append({
                "name": "image_size",
                "ok": False,
                "detail": f"over 2MB: {', '.join(over_limit)}. 公众号素材库上限 2MB.",
            })
        else:
            sizes = ", ".join(f"{p.name}={p.stat().st_size/1024/1024:.1f}MB" for p in image_paths)
            checks.append({"name": "image_size", "ok": True, "detail": sizes})

    # Check 4: 推荐模板存在
    tpl = template_id or raw.get("recommended_template", "e")
    if tpl not in ("a", "c", "e"):
        checks.append({"name": "template", "ok": False, "detail": f"unknown: {tpl}"})
    else:
        checks.append({"name": "template", "ok": True, "detail": f"template_id={tpl}"})

    # Check 5: WECHAT_APPID / SECRET 已配
    if not cfg.wechat_appid or not cfg.wechat_appsecret:
        checks.append({"name": "wechat_creds", "ok": False, "detail": "WECHAT_APPID/WECHAT_APPSECRET missing in .env"})
    else:
        checks.append({
            "name": "wechat_creds",
            "ok": True,
            "detail": f"APPID={cfg.wechat_appid[:8]}... SECRET={'*' * 8}",
        })

    # Check 6: access_token 通(测一次,不缓存)
    try:
        token = pub_mod.get_access_token(force=True)
        checks.append({"name": "access_token", "ok": True, "detail": f"got token (len={len(token)})"})
    except Exception as e:
        checks.append({"name": "access_token", "ok": False, "detail": str(e)[:200]})

    overall_ok = all(c["ok"] for c in checks)
    return {"ok": overall_ok, "checks": checks}


# ============ 内部工具函数 ============

def _load_storyboard(sb_path: Path) -> Storyboard:
    raw = json.loads(sb_path.read_text(encoding="utf-8"))
    return Storyboard(
        topic=raw["topic"],
        style_id=raw["style_id"],
        title=raw.get("title", raw["topic"]),
        subtitle=raw.get("subtitle", ""),
        summary=raw.get("summary", ""),
        preface=raw.get("preface", ""),
        epigraph=raw.get("epigraph", ""),
        postscript=raw.get("postscript", ""),
        recommended_template=raw.get("recommended_template", ""),
        pages=[StoryPage(**p) for p in raw["pages"]],
    )


def _current_images(work_dir: Path) -> list[Path]:
    pages_dir = work_dir / "pages"
    if not pages_dir.exists():
        return []
    return sorted(pages_dir.glob("*.png"))


# ============ CLI 兼容入口（one-shot / 单步） ============

def _cli_main() -> int:
    parser = argparse.ArgumentParser(description="knowledge-comic · step runner")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # all: 一键跑通
    p_all = sub.add_parser("all", help="一键跑完整链路（plan→gen→render→publish）")
    p_all.add_argument("topic")
    p_all.add_argument("--bullets", "-b", nargs="+", required=True)
    p_all.add_argument("--style", "-s", default=None)
    p_all.add_argument("--template", "-t", default=None)
    p_all.add_argument("--dry-run", action="store_true")
    p_all.add_argument("--data-dir", default=None)

    # 单步
    p_plan = sub.add_parser("plan", help="只跑 plan 步骤")
    p_plan.add_argument("topic")
    p_plan.add_argument("--bullets", "-b", nargs="+", required=True)
    p_plan.add_argument("--style", "-s", default=None)
    p_plan.add_argument("--template", "-t", default=None)
    p_plan.add_argument("--data-dir", default=None)

    p_gen = sub.add_parser("gen", help="只跑 gen 步骤")
    p_gen.add_argument("--job-id", required=True)
    p_gen.add_argument("--regenerate-pages", nargs="*", type=int, default=None)
    p_gen.add_argument("--data-dir", default=None)

    p_render = sub.add_parser("render", help="只跑 render 步骤")
    p_render.add_argument("--job-id", required=True)
    p_render.add_argument("--template", "-t", default=None)
    p_render.add_argument("--data-dir", default=None)

    p_publish = sub.add_parser("publish", help="只跑 publish 步骤")
    p_publish.add_argument("--job-id", required=True)
    p_publish.add_argument("--template", "-t", default=None)
    p_publish.add_argument("--dry-run", action="store_true")
    p_publish.add_argument("--data-dir", default=None)

    args = parser.parse_args()
    data_dir = Path(args.data_dir) if args.data_dir else None

    if args.cmd == "all":
        sb, job_id, work_dir = step_plan(args.topic, args.bullets, args.style, args.template, data_dir=data_dir)
        style_id = args.style or sb.style_id
        template_id = args.template or "e"
        image_paths = step_gen_images(job_id, data_dir=data_dir)
        step_render_article(job_id, template_id, image_paths, data_dir=data_dir)
        result = step_publish_draft(job_id, template_id, image_paths, data_dir=data_dir, dry_run=args.dry_run)
        if not args.dry_run:
            print(f"\nDONE  draft_media_id={result['draft_media_id']}")
        return 0

    if args.cmd == "plan":
        sb, job_id, work_dir = step_plan(args.topic, args.bullets, args.style, args.template, data_dir=data_dir)
        print(f"job_id={job_id}  work_dir={work_dir}")
        return 0

    if args.cmd == "gen":
        paths = step_gen_images(args.job_id, data_dir=data_dir, regenerate_pages=args.regenerate_pages)
        for p in paths:
            print(f"  - {p.name}")
        return 0

    if args.cmd == "render":
        html = step_render_article(args.job_id, args.template, data_dir=data_dir)
        print(f"html={html}")
        return 0

    if args.cmd == "publish":
        result = step_publish_draft(args.job_id, args.template, data_dir=data_dir, dry_run=args.dry_run)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(_cli_main())