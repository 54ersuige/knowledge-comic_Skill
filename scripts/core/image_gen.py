"""ImageGen - Agnes API 跑图，输出 PNG 到 data/<job_id>/pages/.

支持：
- 单页跑图 generate_one()  → 1 张 PNG
- 批量跑图 generate_pages() → 多张 PNG（按 storyboard 顺序）
- 角色参考图 reference_paths（首期占位：把 ref 描述拼到 prompt，等 Phase-2D 真实接入）

图文分离铁律：prompt 由 planner 拆出来的 visual 字段组成，已禁止文字。
"""
from __future__ import annotations

import base64
import logging
import time
from pathlib import Path

import requests

from .config import get_config
from .planner import Storyboard
from .prompts import build_image_prompt

logger = logging.getLogger(__name__)


def _call_agnes(prompt: str, out_path: Path, retries: int = 2) -> bool:
    """调 Agnes API 生成 1 张图，存到 out_path。"""
    cfg = get_config()
    url = f"{cfg.agnes_base_url}/images/generations"
    headers = {
        "Authorization": f"Bearer {cfg.agnes_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": cfg.agnes_model,
        "prompt": prompt,
        "n": 1,
        "size": "1024x1024",
        "response_format": "b64_json",
    }

    last_err = ""
    for attempt in range(retries + 1):
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=180)
        except requests.RequestException as e:
            last_err = f"network: {e}"
            time.sleep(3 * (attempt + 1))
            continue

        if r.status_code == 200:
            data = r.json()
            b64 = data.get("data", [{}])[0].get("b64_json")
            if not b64:
                last_err = f"no b64_json: {data}"
                time.sleep(3 * (attempt + 1))
                continue
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(base64.b64decode(b64))
            return True

        last_err = f"HTTP {r.status_code}: {r.text[:200]}"
        # 队列满的话退避
        if r.status_code == 503 and "queue" in r.text.lower():
            wait = 10 * (attempt + 1)
            logger.warning("Agnes queue full, retry in %ds", wait)
            time.sleep(wait)
            continue
        time.sleep(3 * (attempt + 1))

    logger.error("Agnes gen failed after %d retries: %s", retries, last_err)
    return False


def generate_one(
    visual: str,
    style_id: str,
    out_path: Path,
    reference_paths: list[Path] | None = None,
) -> bool:
    """单页跑图。reference_paths 首期占位（拼 prompt），后续接真实 i2i。"""
    prompt = build_image_prompt(style_id, visual)
    if reference_paths:
        # 占位：列出参考图路径，让模型"参考这些图的视觉风格"
        ref_desc = ", ".join(f"reference image {i+1}" for i in range(len(reference_paths)))
        prompt += f" Maintain visual consistency with: {ref_desc}."
    return _call_agnes(prompt, out_path)


def generate_pages(
    storyboard: Storyboard,
    job_id: str,
    reference_paths: list[Path] | None = None,
    progress_cb=None,
) -> list[Path]:
    """批量跑图，返回每页 PNG 路径列表。

    progress_cb(done: int, total: int, page: int) → 用于前端轮询进度。
    """
    cfg = get_config()
    out_dir = cfg.data_dir / job_id / "pages"
    out_dir.mkdir(parents=True, exist_ok=True)

    results: list[Path] = []
    total = len(storyboard.pages)
    for i, page in enumerate(storyboard.pages):
        out = out_dir / f"{page.page:02d}-page.png"
        logger.info("[job=%s] gen page %d/%d: %s", job_id, i + 1, total, page.caption[:30])
        ok = generate_one(
            visual=page.visual,
            style_id=storyboard.style_id,
            out_path=out,
            reference_paths=reference_paths,
        )
        if not ok:
            # 占位：失败时写一个空 PNG + warning，前端能看到
            placeholder = out_dir / f"{page.page:02d}-page.png"
            placeholder.parent.mkdir(parents=True, exist_ok=True)
            from PIL import Image
            img = Image.new("RGB", (1024, 1024), color=(240, 230, 215))
            img.save(placeholder)
        results.append(out)
        if progress_cb:
            progress_cb(i + 1, total, page.page)
    return results