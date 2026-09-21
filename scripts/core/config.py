"""Config - load .env into typed dataclass.

Single source of truth for env vars. Throws KeyError if a required var
is missing so callers see the gap immediately.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
# 加载顺序：Skill 自带 .env 优先（如果有），否则尝试项目目录 .env（开发期共享）
load_dotenv(ROOT / ".env", override=False)

# 项目目录 fallback（让用户在 dev 阶段不用复制 .env）
_project_env = Path(r"D:/minimax-agent_cn-project/知识漫画微信公众号/.env")
if _project_env.exists():
    load_dotenv(_project_env, override=False)


@dataclass(frozen=True)
class Config:
    # Agnes (image gen)
    agnes_api_key: str
    agnes_base_url: str
    agnes_model: str

    # WeChat MP
    wechat_appid: str
    wechat_appsecret: str
    wechat_api_base: str

    # LLM
    llm_provider: str
    llm_api_key: str
    llm_base_url: str
    llm_model: str

    # Server
    host: str
    port: int
    data_dir: Path


def _req(name: str) -> str:
    val = os.getenv(name, "").strip()
    if not val:
        raise RuntimeError(
            f"Missing required env var: {name}. "
            f"Open {ROOT / '.env'} and fill it (copy from .env.example)."
        )
    return val


_cached: Config | None = None


def get_config() -> Config:
    global _cached
    if _cached is not None:
        return _cached
    _cached = Config(
        agnes_api_key=_req("AGNES_API_KEY"),
        agnes_base_url=os.getenv("AGNES_BASE_URL", "https://apihub.agnes-ai.cn/v1"),
        agnes_model=os.getenv("AGNES_MODEL", "agnes-image-2.5-flash"),
        wechat_appid=_req("WECHAT_APPID"),
        wechat_appsecret=_req("WECHAT_APPSECRET"),
        wechat_api_base=os.getenv("WECHAT_API_BASE", "https://api.weixin.qq.com"),
        llm_provider=os.getenv("LLM_PROVIDER", "minimax"),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_base_url=os.getenv("LLM_BASE_URL", "https://api.minimax.chat/v1"),
        llm_model=os.getenv("LLM_MODEL", "MiniMax-M3"),
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8765")),
        data_dir=Path(os.getenv("DATA_DIR", "./data")).resolve(),
    )
    return _cached


def reset_cache() -> None:
    """For tests: force re-read of .env."""
    global _cached
    _cached = None