"""Publisher - WeChat MP API wrapper.

完整链路：
  1. get_access_token()              - access_token with local cache (7150s TTL)
  2. add_permanent_image(path)       - 上传永久素材，返回 (media_id, url)
  3. create_draft(title, html, ...)  - 创建图文草稿，返回 draft media_id

WeChat API endpoints:
  GET  /cgi-bin/token
  POST /cgi-bin/material/add_material?access_token=&type=image
  POST /cgi-bin/draft/add?access_token=
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

from .config import get_config

# access_token 缓存（2 小时过期，留 5 分钟余量）
_token_cache: dict[str, tuple[str, float]] = {}
_TOKEN_TTL = 60 * 60 - 5 * 60


def get_access_token(force: bool = False) -> str:
    """获取 access_token，本地缓存 7150 秒。

    Raises RuntimeError on API error (invalid AppID/Secret, IP not whitelisted,
    quota exhausted).
    """
    cfg = get_config()
    cache_key = cfg.wechat_appid

    if not force and cache_key in _token_cache:
        token, expires_at = _token_cache[cache_key]
        if time.time() < expires_at:
            return token

    url = f"{cfg.wechat_api_base}/cgi-bin/token"
    params = {
        "grant_type": "client_credential",
        "appid": cfg.wechat_appid,
        "secret": cfg.wechat_appsecret,
    }

    r = requests.get(url, params=params, timeout=30)
    data = r.json()

    if "access_token" not in data:
        errcode = data.get("errcode", "unknown")
        errmsg = data.get("errmsg", "unknown")
        raise RuntimeError(
            f"WeChat get_access_token failed: errcode={errcode}, errmsg={errmsg}. "
            f"Common causes: invalid AppID/Secret, IP not whitelisted in "
            f"公众号后台 -> 开发 -> 基本配置 -> IP 白名单."
        )

    token = data["access_token"]
    _token_cache[cache_key] = (token, time.time() + _TOKEN_TTL)
    return token


def add_permanent_image(image_path: Path) -> dict:
    """上传图片到永久素材库。

    Returns:
        {"media_id": "...", "url": "https://..."}

    Raises:
        RuntimeError on API error.
    """
    cfg = get_config()
    token = get_access_token()

    url = f"{cfg.wechat_api_base}/cgi-bin/material/add_material"
    params = {"access_token": token, "type": "image"}

    # multipart/form-data 上传文件
    with open(image_path, "rb") as f:
        files = {"media": (image_path.name, f, "image/png")}
        r = requests.post(url, params=params, files=files, timeout=60)

    if r.status_code != 200:
        raise RuntimeError(f"add_material HTTP {r.status_code}: {r.text[:300]}")

    data = r.json()

    if "media_id" not in data:
        errcode = data.get("errcode", "unknown")
        errmsg = data.get("errmsg", "unknown")
        raise RuntimeError(
            f"add_material failed: errcode={errcode}, errmsg={errmsg}. "
            f"Note: 公众号素材库上限 5000 个素材。"
        )

    return {"media_id": data["media_id"], "url": data.get("url", "")}


def create_draft(
    title: str,
    content_html: str,
    thumb_media_id: str,
    author: str = "",
    digest: str = "",
    content_source_url: str = "",
) -> str:
    """创建图文草稿，返回 draft media_id（用户可在公众号后台草稿箱看到）。

    Args:
        title: 草稿标题（公众号文章标题）
        content_html: 文章 HTML（图用 WeChat 图床 URL）
        thumb_media_id: 封面图 media_id（通常用第一张图的 media_id）
        author: 作者（可选）
        digest: 摘要（可选，留空 WeChat 自动取 content 前 54 字）
        content_source_url: 原文链接（可选）

    Returns:
        draft media_id（草稿 ID）

    Raises:
        RuntimeError on API error.
    """
    cfg = get_config()
    token = get_access_token()

    url = f"{cfg.wechat_api_base}/cgi-bin/draft/add"
    params = {"access_token": token}

    article = {
        "title": title,
        "content": content_html,
        "content_source_url": content_source_url,
        "thumb_media_id": thumb_media_id,
    }
    if author:
        article["author"] = author
    if digest:
        article["digest"] = digest

    body = {"articles": [article]}

    # 关键：requests.post(json=) 默认 ensure_ascii=True，公众号后台会把 \uXXXX 字面量当真字符串存。
    # 自己 json.dumps(ensure_ascii=False) + 显式 charset=UTF-8。
    import json
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    r = requests.post(url, params=params, data=raw, headers=headers, timeout=60)

    if r.status_code != 200:
        raise RuntimeError(f"draft/add HTTP {r.status_code}: {r.text[:300]}")

    data = r.json()

    if "media_id" not in data:
        errcode = data.get("errcode", "unknown")
        errmsg = data.get("errmsg", "unknown")
        raise RuntimeError(
            f"draft/add failed: errcode={errcode}, errmsg={errmsg}. "
            f"Common causes: content 含违规词 / 图片超过 1MB / thumb_media_id 失效."
        )

    return data["media_id"]


def _post_json_no_ascii_escape(url: str, params: dict, body: dict, timeout: int = 60) -> dict:
    """requests.post json= 默认 ensure_ascii=True 会把中文转成 \\uXXXX 字面量，
    公众号草稿存的是 ASCII 字面字符串（不会反解析），导致整篇文章乱码。

    自己 json.dumps 后用 data= + UTF-8 charset 传，保留原字符。
    """
    import json
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    r = requests.post(url, params=params, data=raw, headers=headers, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"{url} HTTP {r.status_code}: {r.text[:300]}")
    return r.json()


def publish_draft(job_id: str, title: str, content_html: str, image_paths: list[Path]) -> dict:
    """完整发布流程：上传所有图片 → 创建草稿。

    Returns:
        {
            "draft_media_id": "...",
            "uploaded_images": [{"page": 1, "media_id": "...", "url": "..."}],
            "title": "...",
        }
    """
    # Step 1: 上传所有图片到素材库
    uploaded: list[dict] = []
    wechat_urls: list[str] = []

    for i, path in enumerate(image_paths, start=1):
        if not path.exists():
            raise RuntimeError(f"Image not found: {path}")
        result = add_permanent_image(path)
        uploaded.append({
            "page": i,
            "filename": path.name,
            "media_id": result["media_id"],
            "url": result["url"],
        })
        wechat_urls.append(result["url"])
        print(f"  uploaded page {i}: media_id={result['media_id'][:18]}...")

    # Step 2: 替换 article_html 里的本地 src 为 WeChat URL
    # （article 在 render_publish_article 时已经用 WeChat URL，但占位支持两种模式）
    published_html = content_html

    # Step 3: 创建草稿（thumb 用第一张图）
    thumb_media_id = uploaded[0]["media_id"]
    digest = ""  # 让 WeChat 自动取前 54 字

    draft_media_id = create_draft(
        title=title,
        content_html=published_html,
        thumb_media_id=thumb_media_id,
        digest=digest,
    )

    return {
        "draft_media_id": draft_media_id,
        "uploaded_images": uploaded,
        "title": title,
        "wechat_urls": wechat_urls,
    }