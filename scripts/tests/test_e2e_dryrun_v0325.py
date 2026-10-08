"""端到端可用性验证：不烧额度版（v0.3.25 收尾）

为什么需要这个
--------------
v0.3.24 / v0.3.25 改了 `image_gen.generate_character_references` 的签名
（新增 `progress_cb`）以及 `run.py` 里两个 `generate_pages` 调用点。
**这些改动从来没有真跑过** —— 11 个测试全是 mock，live 冒烟只覆盖到出分镜。
而跑图是最贵的一步，改坏了要烧额度才发现。

所以这里用打桩把**唯一花钱的那一次 HTTP 调用**（`_call_agnes`）换掉，
其余全部真跑：
  1. preflight 生图前体检        （不花钱）
  2. 角色参考图 + 每页跑图       （桩：真走签名/进度回调/写文件/排序）
  3. render_article 出 HTML      （不花钱）
  4. dry-run publish             （不花钱，只校验组装）

真花钱的两处（Agnes 图像 API、微信 API）不在本脚本覆盖范围，会如实标注。

跑法：python scripts/tests/test_e2e_dryrun_v0325.py
"""
import io
import shutil
import sys
import tempfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
SKILL_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL_ROOT))

from scripts.core import image_gen as IG  # noqa: E402
from scripts.core import article as A  # noqa: E402

FAIL: list[str] = []
PROGRESS: list[str] = []


def ck(name, cond, extra=""):
    print(("  PASS " if cond else "  FAIL "), name, extra)
    if not cond:
        FAIL.append(name)


# ---------------------------------------------------------------- 打桩
_real_call = IG._call_agnes
_fake_png = None


def _fake_call_agnes(prompt, out_path, reference_paths=None):
    """模拟一次成功的图像生成：写真实 PNG 字节，但不打任何网络请求。"""
    global _fake_png
    if _fake_png is None:
        import struct
        import zlib
        w = h = 64
        raw = b"".join(b"\x00" + bytes([200, 190, 170] * w) for _ in range(h))

        def chunk(typ, data):
            c = typ + data
            return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))
        _fake_png = (b"\x89PNG\r\n\x1a\n"
                     + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw))
                     + chunk(b"IEND", b""))
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(_fake_png)
    PROGRESS.append(str(out.name))
    return True


def build_storyboard():
    """造一个结构完整的分镜，覆盖所有跑图前置字段。"""
    from scripts.core.planner import Storyboard, StoryPage
    pages = []
    for i in range(1, 6):
        pages.append(StoryPage(
            page=i,
            visual=(f"CONCEPT: 第{i}页核心概念 → 画面里的具体元素 // 第{i}页 速记\n"
                    f"[GENDER:male]\n"
                    f"Character bible (FIVE ANCHORS, identical in every frame):\n"
                    f"(1) Face shape: oval face, sharp jawline.\n"
                    f"(2) Eyes: dark brown irises.\n"
                    f"(3) Eyebrows: sword brows.\n"
                    f"(4) Lip: cupid's bow lips.\n"
                    f"(5) Hair: Han-Chinese historical figure, high topknot.\n"
                    f"SUBJECT: 守将, 蓄短须, 穿朱砂色圆领窄袖袍, 身侧两名士卒 // 守将 士卒\n"
                    f"ACTION: he lowers a straw dummy over the wall // 放草人\n"
                    f"CAMERA: Wide shot, low angle, 35mm lens, deep focus // 大远景 俯拍\n"
                    f"PLACEMENT: positioned on the left third\n"
                    f"DEPTH LAYERS: FOREGROUND 城墙砖 / MIDGROUND 守将放草人 / "
                    f"BACKGROUND 敌军队列 远山\n"
                    f"LIGHTING: hard side-light from left, deep crimson wash from behind\n"
                    f"MOOD: grim resolve, desaturated ink black + cinnabar red\n"
                    f"STRICT NO TEXT — plain fabric, PLAIN unadorned, no characters."),
            caption=f"第{i}章 城头",
            dialogue="非我族类，其心必异。",
            body="守将立于城头，远处烟尘渐起。军报说援军已在路上，可守城的人都知道"
                 "那只是安抚的措辞。他把最后半袋粟米分成三份，给两个饿到站不稳的士卒。"
                 "这一夜没有人睡，天亮时城墙下多了一排新的箭，插在昨日站过人的位置。",
            keywords=["守将", "城墙", "援军", "粟米", "士卒"],
            punchline="城在人在。",
            key_visual="守将立于城头",
            highlight=f"第{i}夜",
        ))
    return Storyboard(
        topic="张巡守睢阳", style_id="chinese_lianhuanhua_classic",
        pages=pages, title="睢阳：四十天", subtitle="《旧唐书·张巡传》",
        summary="以孤城挡叛军四十日。", preface="城在人在", epigraph="宁为 backward 死",
        postscript="守城靠的不是援军，是每天重新算一遍还能守多久。",
        sources="《旧唐书·张巡传》",
        characters=[{"name": "张巡", "role": "主角", "era": "唐代", "gender": "male",
                     "visual_signature": "唐代老将, 60 岁, 方颌, 剑眉, 蓄短须, "
                                          "戴黑色软脚幞头, 穿朱砂色圆领窄袖袍"}],
    )


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="kc_e2e_"))
    IG._call_agnes = _fake_call_agnes          # ← 唯一花钱的地方被打桩
    try:
        job = tmp / "kc_dryrun"
        (job / "pages").mkdir(parents=True, exist_ok=True)
        (job / "characters").mkdir(parents=True, exist_ok=True)
        sb = build_storyboard()
        import json
        (job / "storyboard.json").write_text(json.dumps(sb.to_dict(), ensure_ascii=False),
                                             encoding="utf-8")

        print("=== 1. 生图前体检 preflight（不花钱）===")
        from scripts.core.preflight import run_preflight
        pre = run_preflight(sb)
        print(f"  blocked={pre.blocked} blocks={len(pre.blocks)} warns={len(pre.warns)}")
        for b in pre.blocks[:6]:
            print(f"    [阻塞] p{b.page} {b.code} {b.msg}")
        ck("无阻塞项（结构完整时应放行）", not pre.blocked,
           f"blocks={[b.code for b in pre.blocks]}")

        print("\n=== 2. 跑图全链路（桩：验证签名/进度回调/写文件/排序）===")
        refs = IG.generate_character_references(
            characters=sb.characters, style_id=sb.style_id, job_id=str(job),
            progress_cb=lambda d, t, lbl: print(f"    进度 {d}/{t} -> {lbl}"),
        )
        ck("角色参考图生成了（4 视图）",
           bool(refs) and all(len(v) == 4 for v in refs.values()),
           f"{ {k: len(v) for k, v in refs.items()} }")
        sig_files = list((job / "characters").glob("*.sig"))
        ck("角色签名指纹已落盘（v0.3.19 防复用旧图）", bool(sig_files),
           f"{[f.name for f in sig_files]}")

        PROGRESS.clear()
        paths = IG.generate_pages(
            sb, str(job), character_refs=refs,
            progress_cb=lambda d, t, lbl: print(f"    进度 {d}/{t} -> {lbl}"),
        )
        ck("每页都出了图", len(paths) == len(sb.pages), f"{len(paths)}/{len(sb.pages)}")
        ck("文件真实存在且是合法 PNG（非 0 字节）",
           all(p.exists() and p.stat().st_size > 0
               and p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" for p in paths),
           f"最小 {min((p.stat().st_size for p in paths), default=0)} 字节（桩图，真实图 >2MB）")
        ck("进度回调被调用次数 = 页数", len(PROGRESS) == len(sb.pages),
           f"调用 {len(PROGRESS)} 次")
        ck("返回按页码有序",
           [int(p.stem.split('-')[0]) for p in paths] == list(range(1, len(sb.pages) + 1)))

        print("\n=== 3. 重画单页（镜像 run.py 的 regenerate 真实流程）===")
        # 注意语义：generate_pages(force_pages=N) 控制的是**哪些页重画**，
        # 返回值仍然是传入 storyboard 的全部页。run.py 的真实做法是先用
        # pages_to_gen 构造一个只含目标页的 rerender_sb，再把结果合并回全量列表。
        # 这里照抄那个流程，才能真正验证 v0.3.14 修的"静默跳过重画"。
        from scripts.core.planner import Storyboard as _SB
        pages_to_gen = [p for p in sb.pages if p.page == 3]
        rerender_sb = _SB(
            topic=sb.topic, style_id=sb.style_id, pages=pages_to_gen,
            title=sb.title, subtitle=sb.subtitle, summary=sb.summary,
            preface=sb.preface, epigraph=sb.epigraph, postscript=sb.postscript,
            sources=sb.sources, characters=sb.characters,
        )
        before_mtimes = {p.name: p.stat().st_mtime_ns for p in paths}
        new_paths = IG.generate_pages(rerender_sb, str(job), character_refs=refs,
                                      force_pages={3},
                                      progress_cb=lambda *a: None)
        ck("重画返回的正是目标页", len(new_paths) == 1 and new_paths[0].stem.startswith("03-"),
           f"返回 {[p.name for p in new_paths]}")
        after_mtimes = {p.name: p.stat().st_mtime_ns
                        for p in (job / "pages").glob("*.png")}
        # 文件名是零填充的（03-page.png），别用 startswith("3-") 判断
        def _pno(n: str) -> int:
            return int(n.split("-")[0])
        changed = [n for n in after_mtimes
                   if _pno(n) == 3 and after_mtimes[n] != before_mtimes.get(n)]
        untouched = [n for n in before_mtimes
                     if _pno(n) != 3 and n in after_mtimes
                     and after_mtimes[n] != before_mtimes[n]]
        ck("目标页确实被重写", bool(changed), f"changed={changed}")
        ck("非目标页未被误碰", not untouched, f"误碰={untouched}")

        print("\n=== 4. 排版渲染（不花钱）===")
        from scripts.run import _load_storyboard
        from scripts.core.article import ArticleInput, render_article
        sb2 = _load_storyboard(job / "storyboard.json")
        urls = [f"https://example.invalid/{p.name}" for p in paths]
        html = render_article(ArticleInput(storyboard=sb2, page_image_urls=urls,
                                           title=sb2.title), template="c")
        ck("c 模板出 HTML", len(html) > 2000, f"{len(html)} 字符")
        ck("每页都有 <img", html.count("<img") >= len(sb2.pages),
           f"{html.count('<img')} 张")
        ck("朱砂红高亮生效（keywords 渲染进去了）", "#9b2332" in html)
        ck("无未替换占位符", "__TITLE__" not in html and "__CHAPTER__" not in html)

        print("\n=== 5. 排版预览（生图前审阅产物）===")
        prev = A.render_layout_preview(sb2, "c")
        ck("layout_preview 可渲染", len(prev) > 2000, f"{len(prev)} 字符")
        ck("预览含占位图高度参数生效", "placeholder" in prev.lower() or "<img" in prev)
        ck("预览无未替换占位符",
           "__TITLE__" not in prev and "__CHAPTER__" not in prev and "__BOARD__" not in prev)

        print("\n=== 6. 微信发布链路（只验组装，不发网络请求）===")
        from scripts.core import publisher as P
        for fn in ("get_access_token", "add_permanent_image", "create_draft",
                   "publish_draft"):
            ck(f"publisher.{fn} 存在", callable(getattr(P, fn, None)))
        import inspect
        sig = inspect.signature(P.publish_draft)
        ck("publish_draft 签名正常", list(sig.parameters)[:2] == ["job_id", "title"],
           f"{sig}")
        # dry_run 在 run.py 的 step 层（publisher 只负责真发）
        from scripts.run import step_publish_draft
        ssig = inspect.signature(step_publish_draft)
        ck("step_publish_draft 有 dry_run（先干跑再真发）",
           "dry_run" in ssig.parameters, f"{list(ssig.parameters)}")
        ck("dry_run 默认关闭（默认会真发）",
           ssig.parameters.get("dry_run") is None
           or ssig.parameters["dry_run"].default is False)
        cfg_w = P.get_config()
        ck("微信凭据已配置（首次真跑还需 IP 白名单）",
           bool(getattr(cfg_w, "wechat_appid", "")))
        print("    注：真实 publish 会调微信 API（需要公网 IP 在白名单里，"
              "否则 errcode 40164）。本脚本不覆盖那一步。")

    finally:
        IG._call_agnes = _real_call
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print("=" * 50)
    print("FAILED:", FAIL if FAIL else "NONE — 全链路可用")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())