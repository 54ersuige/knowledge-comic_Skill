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
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent  # scripts/run.py → parent.parent = knowledge-comic/
sys.path.insert(0, str(SKILL_ROOT))


def _safe_stdout() -> None:
    """让 print() 在任何控制台编码下都不会崩。

    Windows 中文控制台默认 GBK(cp936)，编不了 🔴 🟡 这类非 BMP emoji。
    实测 v0.3.22：preflight 报告里一个 🔴 就让 `run.py all` 直接
    UnicodeEncodeError 挂掉 —— 而且是**阻塞分支**才触发，通关时不炸，
    所以很容易漏测。这里 errors='replace' 让编不出的字符退化成 '?'
    而不是抛异常；report() 本身已改用纯文本标记，正常路径不会有字符损失。

    Mavis 宿主里 stdout 已被重定向，reconfigure 不影响原有行为。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            # 旧 Python 或已被替换的流 —— 忽略，保持原有行为
            pass


_safe_stdout()

from scripts.core.config import get_config  # noqa: E402
from scripts.core.planner import plan_storyboard, Storyboard, StoryPage, recommend_pages  # noqa: E402
from scripts.core.preflight import run_preflight  # noqa: E402
from scripts.core.visual_qa import run_visual_qa  # noqa: E402
from scripts.core.image_gen import generate_pages, generate_character_references  # noqa: E402
from scripts.core import article as article_mod  # noqa: E402
from scripts.core import publisher as pub_mod  # noqa: E402
from scripts.core.review_page import check_quality, render_html, render_markdown  # noqa: E402
from scripts.core.prompts import (  # noqa: E402
    recommend_style,
    recommend_template,
)


# ============ Mavis 对话工作流 API（推荐入口） ============

def _progress_printer(label: str, t0: float | None = None):
    """v0.3.24: 生成 progress_cb，把跑图进度打到 stdout。

    为什么加这个：`image_gen.generate_pages` 一直有 `progress_cb` 形参，
    但 run.py 两个调用点都没传 —— 8~12 页每页 20~40s，整段 3~6 分钟
    **零输出**。用户既不知道在跑还是死了，也看不到跑到第几张。
    同一类事故还有角色参考图（2 角色 × 4 视图 = 8 张），一并补上。

    签名对齐 image_gen：`cb(done, total, page_or_label)`。
    """
    start = t0 if t0 is not None else time.time()

    def _cb(done: int, total: int, label_: object) -> None:
        elapsed = int(time.time() - start)
        eta = ""
        if done > 0 and total > done:
            eta = f", 约还需 {int(elapsed / done * (total - done))}s"
        print(f"[gen] {label} {done}/{total} done ({elapsed}s{eta}) -> {label_}", flush=True)

    return _cb


def step_plan(
    topic: str,
    bullets: list[str],
    style_id: str | None = None,
    template_id: str | None = None,
    num_pages: int | None = None,
    characters: list[dict] | None = None,
    use_llm: bool = True,
    data_dir: Path | None = None,
    allow_mock_fallback: bool = False,
) -> tuple[Storyboard, str, Path]:
    """Step 1: 主题 + 要点 → storyboard JSON + job_id + work_dir

    Args:
        topic: 主题
        bullets: 要点列表
        style_id: 风格 ID（None=自动推荐）
        template_id: 排版 ID（None=自动推荐）
        num_pages: 显式页数（None=按 recommend_pages 自动：≤3 bullets=8 / 4-6=10 / ≥7=12）
        characters: 人物列表（v0.2.5 人物故事专用；None=单角色锚点）。
                  格式: [{"name": "郭子仪", "role": "主角",
                         "visual_signature": "70+ 老年将军, 方颌 丹凤眼 剑眉, 蓄须, 唐代圆领袍+幞头"},
                        {"name": "药葛罗", "role": "回纥可汗", ...}, ...]
        use_llm: 是否调 LLM（False=mock）
        data_dir: 数据目录
        allow_mock_fallback: 配了 key 但 LLM 调用/解析失败时是否仍降级到 mock。
            **默认 False = 当场抛错**。v0.3.24 之前无条件降级，而 mock 分镜
            没有 keywords / [GENDER]，等于把朱砂高亮与性别锚点整条链路静默
            废掉 —— 2026-10-08 live 冒烟就是这样被坑了一次，10 页全空却
            "跑完了"。只有 CI / 离线批量场景才需要传 True。
            没配 LLM_API_KEY 不受此开关限制（那是合法离线模式，照样降级）。

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
    if num_pages is None:
        num_pages = recommend_pages(len(bullets))
        print(f"[auto-pages] 推荐 {num_pages} 页 (基于 {len(bullets)} 个 bullet)")

    # v0.3.24: 接入 canon 一致性约束。
    # 之前只有 scripts/run_plain.py 调 get_canon_injection()，**主流程 run.py
    # 从没接过** —— 特性看起来是活的（planner 签名里 canon_injection 参数一路
    # 传到 _build_planner_user_msg），实际上恒为 ""，data/canon.md 是死配置。
    # 现在接上；data/canon.md 是空模板 → 注入为 "" → 行为与之前完全一致，
    # 用户填了内容才会真正生效。
    canon_inj = ""
    try:
        from scripts.canon import get_canon_injection
        canon_inj = get_canon_injection()
    except Exception as e:  # pragma: no cover - canon 是可选增强，不该拖垮主流程
        print(f"[canon] 跳过（{e}）")
    if canon_inj:
        print(f"[canon] 已注入一致性约束 {len(canon_inj)} 字符")

    sb = plan_storyboard(topic, bullets, style_id, use_llm=use_llm, num_pages=num_pages,
                         canon_injection=canon_inj, allow_mock_fallback=allow_mock_fallback)

    # v0.2.5/0.2.6: 人物一致性 — characters 列表挂到 storyboard
    if characters:
        sb.characters = characters
    elif sb.characters:
        # v0.2.6: planner LLM 已经提取了 characters（话题是人物故事）
        characters = sb.characters
        print(f"[auto-characters] LLM 自动提取 {len(characters)} 个角色")
    elif _is_character_story(topic):
        # v0.2.6: 强制提示 — topic 看起来是人物故事但 LLM 没提取到
        print("[auto-characters] WARNING: topic 看起来是人物故事，但 planner 没提取 characters。"
              "建议手动传入 step_plan(..., characters=[...]) 启用 i2i 人物一致性")

    job_id = f"kc_{int(time.time())}"
    work_dir = work_root / job_id
    work_dir.mkdir(parents=True, exist_ok=True)

    # 把推荐 template 写到 storyboard.json 里（便于后续 render 步用）
    sb_dict = sb.to_dict()
    sb_dict["recommended_template"] = template_id
    if characters:
        sb_dict["characters"] = characters
    (work_dir / "storyboard.json").write_text(
        json.dumps(sb_dict, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"[plan] job_id={job_id}  style={style_id}  template={template_id}  pages={len(sb.pages)}  characters={len(characters or [])}")
    return sb, job_id, work_dir


def step_preflight_images(
    job_id: str,
    data_dir: Path | None = None,
) -> dict:
    """Step 辅助:生图前体检(不跑图)。

    v0.3.15 新增。step_gen_images 内部已内联同一道关卡,本函数把它单独暴露,
    用途是**改完 storyboard.json 先验一遍再决定要不要烧额度**。

    Returns:
        {"blocked": bool, "blocks": [...], "warns": [...], "report": str}
    """
    cfg = get_config()
    work_root = data_dir or cfg.data_dir
    sb_path = work_root / job_id / "storyboard.json"
    if not sb_path.exists():
        return {"blocked": True, "blocks": [], "warns": [],
                "report": f"storyboard.json 不存在: {sb_path}"}

    sb = _load_storyboard(sb_path)
    pre = run_preflight(sb)
    # v0.3.22：落盘 JSON 报告，方便复盘/对比/在 Mavis 对话里读
    try:
        rep = pre.to_dict()
        (work_root / job_id / "preflight_report.json").write_text(
            json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[preflight] 报告落盘失败（不影响体检结果）：{e}）")
    return {
        "blocked": pre.blocked,
        "blocks": [{"page": f.page, "code": f.code, "msg": f.msg, "hint": f.hint}
                   for f in pre.blocks],
        "warns": [{"page": f.page, "code": f.code, "msg": f.msg, "hint": f.hint}
                  for f in pre.warns],
        "report": pre.report(),
    }


def _run_visual_qa(job_id: str, data_dir: Path | None = None) -> None:
    """v0.3.15: 跑图后 LLM 视觉审核（图上出字 / 画风漂移 / 性别画反 / 图画不符）。

    **刻意不阻塞**：LLM 视觉判断有方差，审核还要烧 token 和时间。这里只打印
    报告，返工与否由用户看完图拍板。

    这与 preflight 的"阻塞"定位不同：preflight 拦的是**确定的**输入错误，
    视觉审核报的是**概率性**的输出问题 —— 后者只能提示，不能拦。

    审核失败（网络/超时/模型报错）只打印一行警告，绝不打断流程。

    v0.3.22：跑完落盘 `data/<job>/visual_qa_report.json`，方便复盘/对比。
    """
    cfg = get_config()
    work_root = data_dir or cfg.data_dir
    try:
        res = run_visual_qa(job_id, data_dir=data_dir)
    except Exception as e:
        print(f"[visual-qa] 审核异常（不影响已生成的图）：{e}")
        return
    # v0.3.22：落盘 JSON 报告
    try:
        rep = res.to_dict()
        (work_root / job_id / "visual_qa_report.json").write_text(
            json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[visual-qa] 报告落盘失败（不影响审核结果）：{e}")
    if res.error:
        print(f"[visual-qa] {res.error}")
    elif res.ok:
        print(f"[visual-qa] {res.report().strip()}")
    else:
        print(f"[visual-qa] {res.report()}")
        if res.blocks:
            print(f"[visual-qa] 建议复审/重画："
                  f"{sorted({f.page for f in res.blocks})}")


def step_visual_qa(
    job_id: str,
    pages: list[int] | None = None,
    data_dir: Path | None = None,
) -> dict:
    """Step 辅助:只做视觉审核,不跑图。返回结构化结果。

    v0.3.15 新增。典型用法：用户复审后只重看了某几页,单独再审一遍。
    """
    res = run_visual_qa(job_id, data_dir=data_dir, pages=pages)
    return {
        "checked": res.checked,
        "skipped": res.skipped,
        "error": res.error,
        "blocks": [{"page": f.page, "code": f.code, "msg": f.msg,
                    "confidence": f.confidence, "evidence": f.evidence}
                   for f in res.blocks],
        "warns": [{"page": f.page, "code": f.code, "msg": f.msg,
                   "confidence": f.confidence, "evidence": f.evidence}
                  for f in res.warns],
        "report": res.report(),
    }


def step_gen_images(
    job_id: str,
    data_dir: Path | None = None,
    regenerate_pages: list[int] | None = None,
    auto_char_refs: bool = True,
    skip_preflight: bool = False,
    auto_visual_qa: bool = True,
) -> list[Path]:
    """Step 2: 从 storyboard.json 跑图 → PNG 列表

    Args:
        job_id: job id
        regenerate_pages: 重画的页码列表（用户审核后给出）
        auto_char_refs: v0.2.5 人物故事自动跑角色参考图 + 用 i2i
        skip_preflight: v0.3.15 逃生阀。设 True 跳过生图前体检
            （体检有阻塞项但用户确认要硬跑时才用）
        auto_visual_qa: v0.3.15 跑完图后自动做 LLM 视觉审核，默认开。
            审核**不阻塞流程** —— 只打印报告，返工由用户拍板。
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

    # v0.3.15: 生图前硬关卡。
    # 放在这里（角色参考图之前）是因为**下面每一步都在烧额度** ——
    # 角色参考图 1 张 + 页面图 N 张，全是真金白银。
    # 关卡的作用是把静默失败（keywords 空 / 画字词 / 漏标性别）变成阻塞，
    # 第一次就拦住，而不是烧完图才发现。
    if not skip_preflight:
        pre = run_preflight(sb)
        if pre.blocked:
            print(pre.report())
            print(f"\n[gen] ABORT: 体检发现 {len(pre.blocks)} 个阻塞项，未跑图。"
                  f"\n     修完 storyboard.json 后重跑；"
                  f"\n     确认要硬跑可传 skip_preflight=True。")
            raise SystemExit(1)
        if pre.warns:
            print(pre.report())

    # v0.2.5: 人物故事自动跑角色参考图
    character_refs = None
    if auto_char_refs and sb.characters:
        print(f"[gen] 先跑 {len(sb.characters)} 个角色参考图 (i2i 模式)")
        character_refs = generate_character_references(
            characters=sb.characters,
            style_id=sb.style_id,
            job_id=job_id,
            progress_cb=_progress_printer("charref"),
        )

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
            sources=sb.sources,
            characters=sb.characters,
        )
        # v0.3.14：把 force_pages 传下去。
        # 之前漏传 → generate_pages 走 `out.exists()` 缓存判定 →
        # regenerate_pages=[N] **静默跳过重画**，返回的是旧图。
        new_paths = generate_pages(
            rerender_sb, job_id,
            character_refs=character_refs,
            force_pages=set(regenerate_pages),
            progress_cb=_progress_printer("regen"),
        )
        # 替换原路径
        existing = {int(p.stem.split("-")[0]): i for i, p in enumerate(_current_images(work_dir))}
        all_paths = _current_images(work_dir)
        for new_path in new_paths:
            page_no = int(new_path.stem.split("-")[0])
            if page_no in existing:
                all_paths[existing[page_no]] = new_path
        print(f"[gen] 重画 {len(new_paths)} 页,共 {len(all_paths)} 张")
        _run_alignment_check(sb_path)
        _run_visual_qa(job_id, data_dir=work_root)
        return all_paths
    else:
        paths = generate_pages(
            sb, job_id,
            character_refs=character_refs,
            progress_cb=_progress_printer("page"),
        )
        print(f"[gen] 生成 {len(paths)} 张")
        _run_alignment_check(sb_path)
        _run_visual_qa(job_id, data_dir=work_root)
        return paths


def _run_alignment_check(sb_path: Path) -> None:
    """v0.2.6: 自动跑视觉文字对齐审查 (scripts/check_alignment.py)。
    输出 HIGH/MEDIUM 风险的页号，让 Mavis 知道哪些页需要复审。
    """
    try:
        from scripts.check_alignment import check_storyboard, print_report
        report = check_storyboard(sb_path)
        if report["high_risk_pages"] or report["medium_risk_pages"]:
            print(f"\n[alignment] HIGH: {report['high_risk_pages']}  MEDIUM: {report['medium_risk_pages']}", flush=True)
            print_report(report)
        else:
            print(f"\n[alignment] OK ({report['ok_count']}/{report['total_pages']} 页通过)", flush=True)
    except Exception as e:
        print(f"[alignment] check failed: {e}", flush=True)


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
    thumb_page: int = 1,
) -> dict:
    """Step 4: 上传图片 + 创建草稿

    Args:
        job_id: job id
        template_id: 模板 ID
        image_paths: 图片路径列表
        data_dir: 数据根目录
        dry_run: True = 不实际发布,只生成 publish html
        thumb_page: v0.3.1 新增 - 封面图选第几张(1-based)。默认 1 = 第一张当封面。
                   公众号封面视觉冲击通常需要"人物主体 + 强动作",不一定等于第一张。
                   例如 p1 是开篇引子但人物占比小,做封面弱,可改 thumb_page=2 选 p2。
    Returns:
        {"draft_media_id": "...", "uploaded_count": N, "work_dir": "...",
         "thumb_media_id": "...", "thumb_page": N}

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
        print(f"[publish:DRY-RUN] job={job_id}  template={template_id}  pages={len(image_paths)}  thumb_page={thumb_page}")
        return {"dry_run": True, "job_id": job_id, "work_dir": str(work_dir)}

    # 上传图片到公众号素材库
    uploaded = []
    wechat_urls = []
    for i, path in enumerate(image_paths, start=1):
        print(f"  [{i}/{len(image_paths)}] uploading {path.name}", end=" ... ", flush=True)
        result = pub_mod.add_permanent_image(path)
        uploaded.append({"page": i, "media_id": result["media_id"], "url": result["url"]})
        wechat_urls.append(result["url"])
        print("OK")

    # v0.3.1: thumb_page 校验(1-based, 必须在 [1, len(uploaded)] 范围)
    if not (1 <= thumb_page <= len(uploaded)):
        raise ValueError(
            f"thumb_page={thumb_page} 越界, 有效范围 1..{len(uploaded)}"
        )
    thumb_media_id = uploaded[thumb_page - 1]["media_id"]
    print(f"  [thumb] using page {thumb_page} ({image_paths[thumb_page - 1].name}) as cover")

    # 用微信 URL 重渲染（图片走微信 CDN 才不会被删）
    publish_html = article_mod.render_publish_article(
        sb, wechat_urls, template=template_id
    )
    (work_dir / f"publish_{template_id}.html").write_text(publish_html, encoding="utf-8")

    draft_id = pub_mod.create_draft(
        title=sb.title,
        content_html=publish_html,
        thumb_media_id=thumb_media_id,
    )

    return {
        "draft_media_id": draft_id,
        "uploaded_count": len(uploaded),
        "work_dir": str(work_dir),
        "title": sb.title,
        "thumb_media_id": thumb_media_id,
        "thumb_page": thumb_page,
    }


def step_review_storyboard(
    job_id: str,
    data_dir: Path | None = None,
    write_files: bool = True,
) -> tuple[str, Path | None]:
    """Step 1.5（Checkpoint 1）：分镜审阅 —— 生图前定方向和内容的关卡。

    v0.3.4 新增。原本这一关只能让用户看 storyboard.json 原文，
    但那个文件有多层嵌套字段（keywords / body / visual / highlight），
    人很难快速判断"哪几页不合格"。本函数产出两份人可读产物：

      1. **Markdown 审阅卡**（返回值 str）—— 体检看板 + 问题页全文展开 +
         全页一览。设计成可直接贴进对话：先结论后细节，
         全部达标的页只给一行，不刷屏。
      2. **HTML 审阅页**（返回 Path）—— 浏览器打开，逐页详情 + 统计看板 +
         按「必修/建议」筛选。适合用户想自己安静看一遍的情况。

    跑图很贵，分镜错了后面全白费 —— 所以这一关必须让用户过目。

    Args:
        job_id: job id
        data_dir: 数据目录
        write_files: True=同时把 Markdown / HTML 落盘到 work_dir
    Returns:
        (markdown 文本, html 路径 或 None)

    Mavis 在对话里：
      1. 调本函数拿到 md + html_path
      2. 把 md 摘要贴给用户；如用户想细看，用 deliver-assets 送 html_path
      3. 用 ask_user 让用户拍板（接受 / 改某页 / 重跑分镜）
      4. 改某页用 review.set_page_field(job_id, page, field, value)
    """
    cfg = get_config()
    work_root = data_dir or cfg.data_dir
    work_dir = work_root / job_id
    sb_path = work_dir / "storyboard.json"
    if not sb_path.exists():
        raise FileNotFoundError(f"storyboard.json not found: {sb_path}")

    raw = json.loads(sb_path.read_text(encoding="utf-8"))
    health = check_quality(raw)
    md = render_markdown(raw, health)
    doc = render_html(raw, health)

    html_path = None
    if write_files:
        (work_dir / "storyboard_review.md").write_text(md, encoding="utf-8")
        html_path = work_dir / "storyboard_review.html"
        html_path.write_text(doc, encoding="utf-8")

    stats = health["stats"]
    print(
        f"[review] job={job_id}  pages={stats['pages']}  "
        f"error={stats['errors']}  warn={stats['warns']}  "
        f"body_ok={stats['body_ok']}/{stats['pages']}  "
        f"kw_ok={stats['kw_ok']}/{stats['pages']}"
    )
    if stats["errors"]:
        bad = sorted({i.page for i in health["issues"] if i.level == "error"})
        print(f"[review] 必修页: {bad} —— 生图前应先修")
    return md, html_path


def step_story_script(
    job_id: str,
    data_dir: Path | None = None,
) -> str:
    """图文对齐诊断（v0.3.6 起为**辅助工具**，主产物是 layout_preview.html）。

    用户在 layout_preview.html 里审阅排版 + 分镜时，如果发现某页图文对不上，
    调本函数定位到底是缺了哪个动作 / 哪个人物，避免人工比对 visual 原文。

    Args:
        job_id: job id
        data_dir: 数据目录
    Returns:
        对齐风险报告（Markdown）。无风险时返回「全部通过」一句话。
    """
    cfg = get_config()
    work_root = data_dir or cfg.data_dir
    work_dir = work_root / job_id
    sb_path = work_dir / "storyboard.json"
    if not sb_path.exists():
        raise FileNotFoundError(f"storyboard.json not found: {sb_path}")

    raw = json.loads(sb_path.read_text(encoding="utf-8"))
    health = check_quality(raw)

    from scripts.check_alignment import check_storyboard
    rep = check_storyboard(sb_path)
    pages = raw.get("pages", [])

    risky = [r for r in rep["results"] if r.get("severity") in ("high", "medium")]
    if not risky and not health["stats"]["errors"]:
        out = "✅ 全部页面图文相符，硬约束也全部通过。可以生图。"
    else:
        lines = []
        if health["stats"]["errors"]:
            bad = sorted({i.page for i in health["issues"] if i.level == "error"})
            lines.append(f"⚠️ 硬约束必修项涉及页 {bad}\n")
        for r in risky:
            no = r["page"]
            page = next((x for x in pages if x.get("page") == no), {})
            tag = "[阻塞]" if r["severity"] == "high" else "[建议]"
            lines.append(f"{tag} **p{no:02d}** {page.get('highlight', '')}")
            for label, key in (("caption 里的动作画面没画", "caption_missing_actions"),
                               ("caption 里的人物画面没画", "caption_missing_entities")):
                v = r.get(key) or []
                if v:
                    lines.append(f"　　{label}：**{'、'.join(v)}**")
            for label, key in (("正文提到但画面没画的动作", "body_missing_actions"),
                               ("正文提到但画面没画的人物", "body_missing_entities")):
                v = r.get(key) or []
                if len(v) >= 2:
                    lines.append(f"　　{label}：**{'、'.join(v)}**")
            lines.append("")
        out = "\n".join(lines).rstrip()

    (work_dir / "alignment_report.md").write_text(out + "\n", encoding="utf-8")
    print(f"[align] job={job_id}  HIGH={rep['high_risk_pages']} "
          f"MEDIUM={rep['medium_risk_pages']}  errors={health['stats']['errors']}")
    return out


def step_layout_preview(
    job_id: str,
    template_id: str | None = None,
    compare_templates: list[str] | None = None,
    data_dir: Path | None = None,
    placeholder_h: int = 420,
) -> Path | list[Path]:
    """Step 1.5（Checkpoint 1）：★ 生图前的排版 + 分镜审阅 ★

    **这是 Checkpoint 1 的唯一产物**：用户打开这一个 HTML 就能确认两件事：
      1. **文字排版效果** —— 标题/章节题/正文/朱砂红高亮/印章/收束段落的成品版式
      2. **每页分镜要画什么** —— 占位图下方直接列出主体/动作/配角/背景/景别/情绪

    确认「文字说的」和「画面画的」对得上，再跑 `step_gen_images` 生图。
    跑图很贵且常要重跑，所以这一关必须先过。

    不想开文件时，可调 `step_story_script(job_id)` 拿对话内的图文对齐诊断。

    Args:
        job_id: job id
        template_id: 模板 ID（None=用推荐模板）
        compare_templates: 同时渲染多个模板做对比（如 ["c","e"]），
                          返回 Path 列表；否则返回单个 Path
        placeholder_h: 占位图高度（px）
    Returns:
        html_path（单模板）或 html_paths（多模板对比）

    Mavis 在对话里：
      1. 调本函数拿到 html 路径
      2. 用 deliver-assets 送 html；或用 Browser 打开让用户看
      3. ask_user 拍板：图文相符 → 生图 / 换模板 / 改文案
      4. 用户发现某页图文不符 → 调 step_story_script 定位缺什么
    """
    cfg = get_config()
    work_root = data_dir or cfg.data_dir
    work_dir = work_root / job_id
    sb = _load_storyboard(work_dir / "storyboard.json")

    if template_id is None:
        template_id = sb.recommended_template or "e"

    if compare_templates:
        out: list[Path] = []
        for tpl in compare_templates:
            html = article_mod.render_layout_preview(
                sb, template=tpl, placeholder_h=placeholder_h)
            p = work_dir / f"layout_preview_{tpl}.html"
            p.write_text(html, encoding="utf-8")
            out.append(p)
            print(f"[preview] template={tpl}  html={p}  size={len(html)} chars")
        return out

    html = article_mod.render_layout_preview(
        sb, template=template_id, placeholder_h=placeholder_h)
    html_path = work_dir / f"layout_preview_{template_id}.html"
    html_path.write_text(html, encoding="utf-8")

    n = len(sb.pages)
    body_lens = [len((p.body or "").strip()) for p in sb.pages]
    kw_total = sum(len(p.keywords or []) for p in sb.pages)
    print(f"[preview] template={template_id}  html={html_path}  size={len(html)} chars")
    print("[preview] 含排版成品 + 每页分镜要素（主体/动作/配角/背景/景别/情绪）")
    print(f"[preview] {n} 页 · 正文平均 {sum(body_lens)//max(n,1)} 字 · "
          f"关键词共 {kw_total} 个（朱砂红高亮）")
    print("[preview] 确认图文相符后再跑 step_gen_images 生图")
    return html_path


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
    # v0.3.2 修复：step_gen_images(regenerate_pages=…) 返回的是**全部页面**的有序列表，
    # 原先直接 `return paths[0]` 会把 p1 的路径当成重画结果返回，必须按页码取。
    for p in paths:
        if int(p.stem.split("-")[0]) == page_no:
            return p
    raise RuntimeError(f"重画后未找到 page {page_no} 的图片（job={job_id}）")


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

    # Check 3: 所有图片存在 + 非空 + < 2MB
    pages_dir = work_dir / "pages"
    image_paths = sorted(pages_dir.glob("*.png")) if pages_dir.exists() else []
    if not image_paths:
        checks.append({"name": "images", "ok": False, "detail": "no images found"})
    else:
        # v0.3.2：先查 0 字节/损坏文件。跑图失败的旧版本会留 0 字节占位，
        # 这种文件能过 "<2MB" 检查，却会在上传时被 WeChat 拒掉。
        empty = [p.name for p in image_paths if p.stat().st_size == 0]
        over_limit = []
        for p in image_paths:
            size_mb = p.stat().st_size / 1024 / 1024
            if size_mb > 2:
                over_limit.append(f"{p.name}={size_mb:.1f}MB")
        if empty:
            checks.append({
                "name": "image_empty",
                "ok": False,
                "detail": f"0 字节(跑图失败占位): {', '.join(empty)}. "
                          f"重跑: step_gen_images(job_id, regenerate_pages=[页码])",
            })
        if over_limit:
            checks.append({
                "name": "image_size",
                "ok": False,
                "detail": f"over 2MB: {', '.join(over_limit)}. 公众号素材库上限 2MB.",
            })
        if not empty and not over_limit:
            sizes = ", ".join(
                f"{p.name}={p.stat().st_size/1024/1024:.1f}MB" for p in image_paths
            )
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

# v0.2.6: 人物故事检测 — 判断 topic 是否需要走 characters 一致性流程。
# v0.3.2: 删除未使用的 _CHARACTER_STORY_KEYWORDS（写进 _is_character_story
# 的 docstring 但从未被任何代码读取，纯死数据）。
# 人物典故 / 典故类关键词 (中文)
_CHARACTER_STORY_NAMES: list[str] = [
    "郭子仪", "药葛罗", "仆固怀恩", "岳飞", "项羽", "刘邦", "韩信",
    "诸葛亮", "刘备", "关羽", "张飞", "曹操", "赵云",
    "李世民", "武则天", "李靖", "霍去病", "卫青",
    "张巡", "许远", "文天祥", "辛弃疾", "戚继光", "郑成功",
    "孔子", "老子", "庄子", "孟子", "屈原", "司马迁",
]


def _is_character_story(topic: str) -> bool:
    """v0.2.6: 启发式判断 topic 是否是"人物故事"（需要 characters 一致性流程）。

    规则：
    - 含已知历史人物名（郭子仪/岳飞/...）→ True
    - 含"单骑/退/入/破/斩/救"等动作 + 人名模式 → True
    """
    # 1) 已知人物名
    for name in _CHARACTER_STORY_NAMES:
        if name in topic:
            return True
    # 2) topic 长度较短 + 含典故/故事/生平关键词
    if any(kw in topic for kw in ["典故", "故事", "生平", "事迹", "传"]):
        return True
    # 3) 含"人名 + 动作词"模式（如 "看石崇与王恺争豪"）
    import re
    if re.search(r"[\u4e00-\u9fff]{2,4}(与|单骑|退|入|破|斩|救|讨|伐|击|围)", topic):
        return True
    return False


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
        sources=raw.get("sources", ""),
        characters=raw.get("characters", []),
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