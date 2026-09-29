"""ImageGen - Agnes API 跑图，输出 PNG 到 data/<job_id>/pages/.

支持：
- 单页跑图 generate_one()  → 1 张 PNG
- 批量跑图 generate_pages() → 多张 PNG（按 storyboard 顺序）
- 角色参考图 reference_paths（v0.2.5 真实 i2i 接入，参考 baoyu-comic 模式）

图文分离铁律：prompt 由 planner 拆出来的 visual 字段组成，已禁止文字。
"""
from __future__ import annotations

import base64
import hashlib
import logging
import time
from pathlib import Path

import requests

from .config import get_config
from .planner import Storyboard
from .prompts import build_image_prompt
from .prompts import get_gender_anchor, resolve_gender

logger = logging.getLogger(__name__)


# === v0.2.5/2.10: i2i 模型选择 ===
# Agnes API: t2i 用 2.5-flash (cfg.agnes_model), i2i 同样用 2.5-flash (用户要求)
# v0.2.10 之前硬编码 2.0-flash 是历史遗留,现在 2.5-flash 也支持 i2i
I2I_MODEL = "agnes-image-2.5-flash"

# 角色参考图视图（v0.2.5 默认 4 视图：front / 3-4 / side / back）
CHARACTER_REF_VIEWS: list[str] = ["front", "three_quarter", "side", "back"]


def _file_to_data_uri(path: Path) -> str:
    """Read a local image file → data: URI. 受 baoyu-comic 启发。"""
    if not path.is_file():
        raise FileNotFoundError(f"Reference image not found: {path}")
    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > 8:
        raise ValueError(
            f"Reference image too large ({size_mb:.1f}MB). "
            f"Compress to <8MB first."
        )
    ext = path.suffix.lower().lstrip(".")
    if ext not in ("png", "jpg", "jpeg", "webp"):
        raise ValueError(f"Unsupported image format: .{ext}")
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _call_agnes(
    prompt: str,
    out_path: Path,
    reference_paths: list[Path] | None = None,
    retries: int = 2,
) -> bool:
    """调 Agnes API 生成 1 张图，存到 out_path。

    v0.2.5: 如果 reference_paths 不空，自动切换到 i2i 模式
    （agnes-image-2.0-flash + tags=["img2img"] + extra_body.image=data_uris）。

    Args:
        prompt: 完整图像 prompt
        out_path: 输出 PNG 路径
        reference_paths: 参考图列表（角色一致性）
        retries: 失败重试次数
    """
    cfg = get_config()
    use_i2i = bool(reference_paths)
    model = I2I_MODEL if use_i2i else cfg.agnes_model

    url = f"{cfg.agnes_base_url}/images/generations"
    headers = {
        "Authorization": f"Bearer {cfg.agnes_api_key}",
        "Content-Type": "application/json",
    }
    payload: dict = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": "1024x1024",
    }
    if use_i2i:
        # i2i 模式: 必传 tags=img2img, extra_body.image 是 data: URI 列表
        payload["tags"] = ["img2img"]
        payload["extra_body"] = {
            "image": [_file_to_data_uri(p) for p in reference_paths],
        }
        # i2i 不返回 b64_json，要走下载流程
        payload["response_format"] = "url"
    else:
        payload["response_format"] = "b64_json"

    last_err = ""
    for attempt in range(retries + 1):
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=180)
        except requests.RequestException as e:
            last_err = f"network: {e}"
            time.sleep(3 * (attempt + 1))
            continue

        if r.status_code == 200:
            data = r.json().get("data", [{}])[0]
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if use_i2i:
                # i2i 返回 URL，下载
                url_resp = data.get("url")
                if not url_resp:
                    last_err = f"no url in i2i response: {data}"
                    time.sleep(3 * (attempt + 1))
                    continue
                try:
                    img_resp = requests.get(url_resp, timeout=120)
                    img_resp.raise_for_status()
                    out_path.write_bytes(img_resp.content)
                    return True
                except requests.RequestException as e:
                    last_err = f"i2i download failed: {e}"
                    time.sleep(3 * (attempt + 1))
                    continue
            else:
                b64 = data.get("b64_json")
                if not b64:
                    last_err = f"no b64_json: {data}"
                    time.sleep(3 * (attempt + 1))
                    continue
                out_path.write_bytes(base64.b64decode(b64))
                return True

        last_err = f"HTTP {r.status_code}: {r.text[:200]}"
        if r.status_code == 503 and "queue" in r.text.lower():
            wait = 10 * (attempt + 1)
            logger.warning("Agnes queue full, retry in %ds", wait)
            time.sleep(wait)
            continue
        time.sleep(3 * (attempt + 1))

    logger.error("Agnes gen failed after %d retries: %s", retries, last_err)
    return False


# === v0.2.9: 角色锁注入 ===
# 紧凑版 character signature (one-liner for prompt injection)
# 用于每页 visual prompt 开头锁定角色外貌
#
# v0.3.2 说明：这三条是 2026-09-23 郭子仪项目调出来的经验值，**硬编码在这里只对那
# 一个项目有效**，换项目会静默失效（查不到名字就不注入，什么都不发生）。
# 因此主路径改为从 storyboard.characters[].visual_signature 动态派生；
# 本字典仅作为 legacy 兜底保留，并显式标注来源，避免误以为它是通用机制。
CHARACTER_LOCK_COMPACT_LEGACY: dict[str, str] = {
    "郭子仪": "GUO ZIYI: 70yo Tang general, narrow long face, square jaw, deep-set phoenix eyes, white bushy sword brows, long flowing white beard to chest, hair in topknot with red ribbon, BLACK soft futou cap, BROWN round-collar robe with DEEP BLUE inner layer, black leather belt with jade buckle, lean upright dignified posture",
    "药葛罗": "YAO GELUO Khan: 45yo Uyghur khan, ROUND full face, BIG eyes, thick black horizontal brows, dense black beard to chest, black long hair down to shoulders, GOLD crown with red and green gems + gold forehead tassels, GOLDEN-OCHRE floral robe, gold disc chest ornament, black-gold belt, black sable-fur collar, STOCKY broad-shouldered tall body",
    "仆固怀恩": "PUGU HUAIEN: 50yo rebel general, SQUARE WIDE face, thick black short slanted brows, deep-set fierce hawk eyes, hard jaw, black short stubble, BLACK short cropped hair, BLACK iron pointed war helmet with red plume, DARK BLUE-BLACK lamellar armor with beast-face breastplate, red leather shoulder guards, black cape, STOCKY tough muscular build",
}


def _inject_character_lock(visual: str, characters: list[dict] | None = None) -> str:
    """v0.2.9: 检测 visual 中提到的人物，注入紧凑 character lock 到 prompt 开头。

    即使 i2i 漂移，文字 prompt 也能锁住角色特征。

    v0.3.2: characters 为 storyboard.characters（权威来源），
    视觉签名取自 visual_signature；查不到再退到 legacy 硬编码表。
    """
    if not visual:
        return visual

    mentioned: list[str] = []

    # 1) 权威路径：从 storyboard 角色定义动态派生
    for ch in characters or []:
        name = (ch.get("name") or "").strip()
        sig = (ch.get("visual_signature") or "").strip()
        if name and sig and name in visual:
            mentioned.append(f"{name}: {sig}")

    # 2) legacy 兜底：历史硬编码表
    if not mentioned:
        for name, desc in CHARACTER_LOCK_COMPACT_LEGACY.items():
            if name in visual:
                mentioned.append(desc)

    if not mentioned:
        return visual
    prefix = "CHARACTER LOCK — " + " | ".join(mentioned) + " || "
    return prefix + visual


def generate_one(
    visual: str,
    style_id: str,
    out_path: Path,
    reference_paths: list[Path] | None = None,
    character_anchor: str | None = None,
    gender: str = "auto",
    characters: list[dict] | None = None,
) -> bool:
    """单页跑图。

    Args:
        visual: 画面描述
        style_id: 风格 ID
        out_path: 输出 PNG 路径
        reference_paths: 参考图（角色一致性用，触发 i2i 模式）
        character_anchor: 显式角色锚点（None = 自动按风格选）
        gender: v0.3.0 新增 - 性别分支。auto/female/male/mixed。
                chinese_lianhuanhua_classic 专用,其他风格忽略。
                默认 auto = 从 visual 描述自动检测([GENDER:xx] tag / 中文代词 / 英文代词)。
        characters: v0.3.2 新增 - storyboard.characters，用于动态派生角色锁签名。
    """
    # v0.2.9: 注入角色锁到 visual (即使 i2i 漂移,文字 prompt 也锁住人物特征)
    visual_with_lock = _inject_character_lock(visual, characters=characters)
    prompt = build_image_prompt(
        style_id=style_id,
        scene_description=visual_with_lock,
        character_anchor=character_anchor,
        gender=gender,
    )
    return _call_agnes(prompt, out_path, reference_paths=reference_paths)


def _build_character_view_prompt(character_name: str, role: str, visual_signature: str,
                                  view: str, style_id: str,
    gender: str = "auto",
) -> str:
    """为单张角色参考图构造 prompt。

    v0.2.5: 参考 baoyu-comic 模式 — 跑干净的"角色站立姿势"参考图，
    不带场景、不带对话。背景简洁（plain studio backdrop）。
    """
    from .prompts import CHINESE_STYLE_PREFIX, ZERO_TEXT_BOOST
    from .prompts import get_style, get_character_anchor

    style = get_style(style_id)
    is_traditional_cn = style_id in {"chinese_lianhuanhua_classic", "cn_xuanfeng", "guochao_manhua"}
    style_prefix = CHINESE_STYLE_PREFIX if is_traditional_cn else ""

    # 角色参考图专用 prompt: 简洁、突出角色本体、留出 i2i 发挥空间
    view_desc = {
        "front": "facing the viewer directly, symmetrical frontal composition",
        "three_quarter": "turned at a 45-degree angle showing three-quarters of the figure",
        "side": "shown in profile from the side",
        "back": "facing away from the viewer, showing the back",
    }.get(view, "facing the viewer")

    # v0.3.20：char 级也走统一性别解析。
    # 事故根因：这里原本是 `get_character_anchor(style_id)`，拿到的是写死的
    # `CHARACTER_CN_LIANHUANHUA_MODERN`（内含 FEMALE 桃花腮/步摇簪花分支），
    # 导致 characters/夫差-front.png 被画成女性，再经 i2i 污染每一页。
    resolved = (gender if gender in ("male", "female", "mixed")
                else resolve_gender(visual_signature, name=character_name))
    if style_id == "chinese_lianhuanhua_classic":
        character_anchor = get_gender_anchor(resolved)
    else:
        character_anchor = get_character_anchor(style_id)
    gender_clause = f"SUBJECT GENDER: {resolved.upper()}. Must clearly read as a {resolved} figure. "
    return (
        f"{style_prefix}"
        f"{style.prompt_en} "
        f"{character_anchor} "
        f"{gender_clause}"
        f"Subject: {character_name} ({role}) - {visual_signature}. "
        f"Pose: standing in a neutral pose, {view_desc}. "
        f"Background: plain neutral backdrop, no scenery, no props. "
        f"{ZERO_TEXT_BOOST} "
        f"Strict rules: full body visible head-to-toe, "
        f"single character only, no other figures, neutral expression, "
        f"lighting even and flat to show character details clearly, "
        f"face in THREE-QUARTER view with eyes slightly looking to side for iconic feel."
    )


def generate_character_references(
    characters: list[dict],
    style_id: str,
    job_id: str,
    n_views: int = 4,
) -> dict[str, list[Path]]:
    """为每个角色生成多视图参考图。

    v0.2.5: 借鉴 baoyu-comic 4 视图策略（front/3-4/side/back），
    给后续每页 i2i 跑图提供稳定角色参考。

    Args:
        characters: [{"name": "郭子仪", "role": "主角", "visual_signature": "..."}, ...]
        style_id: 风格 ID
        job_id: 任务 ID
        n_views: 每个角色生成几张参考图（1-4, 默认 4）

    Returns:
        {character_name: [Path, ...]} 每角色多张参考图路径

    Raises:
        ValueError: characters 为空
    """
    if not characters:
        raise ValueError("characters 不能为空")

    cfg = get_config()
    out_dir = cfg.data_dir / job_id / "characters"
    out_dir.mkdir(parents=True, exist_ok=True)

    views = CHARACTER_REF_VIEWS[: max(1, min(n_views, 4))]
    result: dict[str, list[Path]] = {}

    for char in characters:
        name = char.get("name") or char.get("id") or "character"
        role = char.get("role", "角色")
        sig = char.get("visual_signature") or char.get("signature") or ""
        safe_name = "".join(c for c in name if str.isalnum) or "char"
        char_paths: list[Path] = []

        # v0.3.19: 签名指纹 —— 签名变了就必须重画参考图。
        # 原实现只看 `out.exists()`，改 visual_signature 后参考图仍是旧的，
        # i2i 把旧形象带回每一页，**改签名完全无效**（kc_1790664590 事故）。
        # 与 v0.3.14 的 regenerate_pages 缓存事故同源：改了输入却沿用旧产物。
        sig_hash = hashlib.sha256(
            f"{name}|{role}|{sig}|{style_id}|"
            f"{char.get('gender', 'auto')}|"
            f"{getattr(cfg, 'image_model', '')}"
            .encode("utf-8")).hexdigest()[:16]
        stamp = out_dir / f"{safe_name}.sig"

        for i, view in enumerate(views, start=1):
            out = out_dir / f"{safe_name}-{view}.png"
            fresh = (out.exists() and out.stat().st_size > 1024
                     and stamp.exists()
                     and stamp.read_text(encoding="utf-8").strip() == sig_hash)
            if fresh:
                # 缓存命中: 签名没变，跳过
                logger.info("[job=%s] cache hit %s", job_id, out.name)
                char_paths.append(out)
                continue
            prompt = _build_character_view_prompt(
                name, role, sig, view, style_id,
                gender=char.get("gender", "auto"))
            logger.info("[job=%s] gen char ref %s view %d/%d", job_id, name, i, len(views))
            ok = _call_agnes(prompt, out, reference_paths=None)
            if ok:
                char_paths.append(out)
            else:
                logger.warning("[job=%s] char ref failed: %s view %s", job_id, name, view)

        # v0.3.19: 4 个视图都成功后写指纹，下次比对用。
        # 只在有图时才写 —— 全失败时不写，下次会自动重试。
        if char_paths:
            stamp.write_text(sig_hash, encoding="utf-8")

        result[name] = char_paths

    total = sum(len(p) for p in result.values())
    logger.info("[job=%s] character refs done: %d characters, %d images", job_id, len(result), total)
    return result


# v0.3.14：角色别名表 —— 按页匹配 i2i 参考图时用。
# planner 生成的 visual 里用**英文名**（Su Wu / Chang Hui / Li Ling），
# 而 characters[].name 存的是**中文名**（苏武 / 常惠 / 李陵），
# 不映射就匹配不上 → 退化成全局套用 → 参考图污染本页场景。
CHARACTER_ALIASES: dict[str, str] = {
    "苏武": "Su Wu",
    "李陵": "Li Ling",
    "常惠": "Chang Hui",
    "张胜": "Zhang Sheng",
    "卫律": "Wei Lü",
    "呼韩邪单于": "Huhanye Chanyu",
    "单于": "Chanyu",
}


def generate_pages(
    storyboard: Storyboard,
    job_id: str,
    character_refs: dict[str, list[Path]] | None = None,
    progress_cb=None,
    force_pages: set[int] | None = None,
) -> list[Path]:
    """批量跑图，返回每页 PNG 路径列表。

    Args:
        storyboard: 分镜
        job_id: 任务 ID
        character_refs: 角色参考图
        progress_cb: 进度回调
        force_pages: **强制重画**的页码集合。
            v0.3.14 新增 —— 之前没有这个入口，导致 `regenerate_pages=[9]`
            走 generate_pages() 时被 `out.exists()` 缓存判定命中，
            **静默跳过重画**，用户以为重画了其实拿到的是旧图
            （实测 09:57 的旧图被当成"重画成功"返回）。
        character_refs: 角色参考图（v0.2.5: 每个 ref 列表会作为 i2i 输入传给对应页）
                       key = 角色 name, value = 多视图 Path 列表
        progress_cb: 进度回调 done/total/page

    v0.2.5: 如果 character_refs 提供，会把所有 ref 平铺传给每页（i2i 模式）。
    """
    cfg = get_config()
    out_dir = cfg.data_dir / job_id / "pages"
    out_dir.mkdir(parents=True, exist_ok=True)
    force = set(force_pages or ())

    # 收集所有参考图（i2i 一次性传入）
    # v0.3.14：i2i 参考图改为**按页匹配**，不再全局套用。
    #
    # 事故：苏武牧羊 p9 重画时画风跑成 3D 西式室内。根因是
    # `character_refs` 里包含"李陵"，而 p9 画面里根本没有李陵 ——
    # 参考图把"室内/近景人物"的构图带偏了，整页跟着崩。
    # 隔离实验证实：同一个 prompt，去掉 i2i 后画风完全正确。
    #
    # 规则：只给「本页 visual 里明确出现」的角色传参考图。
    # 一个都没匹配上 → 走纯 t2i（宁可少一层一致性约束，也不污染场景）。
    def _refs_for_page(visual: str) -> list[Path]:
        if not character_refs:
            return []
        v = visual or ""
        picked: list[Path] = []
        for name, paths in character_refs.items():
            # 角色英文名/别名也匹配（planner 用英文名，参考图按中文名存）
            aliases = [name, CHARACTER_ALIASES.get(name, name)]
            if not any(a and a in v for a in aliases):
                continue
            valid = [p for p in paths if p.exists() and p.stat().st_size > 1024]
            priority_order = ["front", "three_quarter", "side", "back"]
            valid.sort(key=lambda p: (
                next((i for i, k in enumerate(priority_order) if k in p.stem), 99)
            ))
            picked.extend(valid[:2])   # 每角色最多 2 张视图
        return picked[:6]             # Agnes 硬上限 6 张

    results: list[Path] = []
    failed: list[int] = []
    total = len(storyboard.pages)
    for i, page in enumerate(storyboard.pages):
        out = out_dir / f"{page.page:02d}-page.png"
        # v0.3.14：force_pages 里的页**不查缓存**，强制重画
        if page.page in force:
            logger.info("[job=%s] FORCE regen page %d", job_id, page.page)
        elif out.exists() and out.stat().st_size > 1024:
            logger.info("[job=%s] cache hit %s", job_id, out.name)
            results.append(out)
            continue
        logger.info("[job=%s] gen page %d/%d: %s", job_id, i + 1, total, page.caption[:30])
        # v0.3.14：按页匹配参考图（只给本页出现的角色）
        page_refs = _refs_for_page(page.visual)
        if character_refs and not page_refs:
            logger.info("[job=%s] page %d 无匹配角色, 走纯 t2i", job_id, page.page)
        elif page_refs:
            logger.info("[job=%s] page %d 用 %d 张 refs", job_id, page.page, len(page_refs))
        ok = generate_one(
            visual=page.visual,
            style_id=storyboard.style_id,
            out_path=out,
            reference_paths=page_refs or None,
            characters=storyboard.characters,
        )
        if not ok:
            # v0.3.2 修复：原实现写 0 字节文件占位。
            # 后果链：0 字节文件仍匹配 pages/*.png →
            #   _current_images() 收进列表 → render 塞进 HTML →
            #   publish 拿 0 字节当 PNG 上传，WeChat 报错但前面已传了 N-1 张。
            # 而且 step_preflight 只查 >2MB 上限，不查 0 字节，拦不住。
            # 现在直接删除占位并把该页记进 failed，最终以异常形式暴露，不静默。
            out.unlink(missing_ok=True)
            failed.append(page.page)
            logger.warning("[job=%s] page %d 生成失败,已移除占位文件", job_id, page.page)
            continue
        results.append(out)
        if progress_cb:
            progress_cb(i + 1, total, page.page)

    if failed:
        raise RuntimeError(
            f"[job={job_id}] {len(failed)}/{total} 页跑图失败: {failed}。"
            f"已删除对应空占位文件（避免污染 render/publish）。"
            f"可稍后重试: step_gen_images('{job_id}', regenerate_pages={failed})"
        )
    return results