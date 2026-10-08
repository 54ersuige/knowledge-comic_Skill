"""check_drift.py — Skill 真源 ↔ dev 只读镜像的一致性校验（v0.3.24）

为什么需要这个脚本
------------------
`AGENTS.md` 定的规矩是：改动**只在 Skill 侧做**（`~/.minimax/skills/knowledge-comic/`），
`src/core/` 是它的**只读镜像**，用于离线阅读和 code review。规矩里也写了
"同步完必须跑漂移校验"，但那条校验是一条**要人手动敲的 PowerShell**。

于是它从来没被稳定执行过。2026-10-08 实测：`article.py` 真源 1727 行、
镜像 1721 行 —— **镜像缺 v0.3.18 的双层蒙版修复**，一直没人发现。
AGENTS.md 顶部那段"声明与现实不符且无校验机制，是这次漂移烂了好几天的原因"
说的就是它自己。**纯人工约定 = 不会执行。**

本脚本把那条约定变成可执行、可进 CI、退出码有意义的检查：
逐文件比对行数 + SHA-256，列出镜像缺文件 / 多文件 / 内容不一致三类漂移。

用法
----
    python scripts/check_drift.py            # 校验，漂移则 exit 1
    python scripts/check_drift.py --sync     # 先校验，把真源复制到镜像，再复校
    python scripts/check_drift.py --path D:\\other\\src\\core   # 指定镜像路径

镜像路径解析顺序：环境变量 KNOWLEDGE_COMIC_DEV_ENV > 默认 D 盘路径。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
SKILL_CORE = SKILL_ROOT / "scripts" / "core"
DEV_ROOT = Path(r"D:\minimax-agent_cn-project\知识漫画微信公众号")
DEFAULT_DEV_CORE = DEV_ROOT / "src" / "core"

# 只同步/校验真正的模块。__init__.py 是空文件且镜像本来就有，忽略。
IGNORE = {"__init__.py"}


def _safe_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def resolve_dev_core() -> Path:
    env = os.environ.get("KNOWLEDGE_COMIC_DEV_ENV")
    if env:
        p = Path(env)
        return (p / "src" / "core") if (p / "src" / "core").is_dir() else p
    return DEFAULT_DEV_CORE


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def scan(dev_core: Path) -> tuple[list[str], list[str], list[tuple[str, str, str, str]]]:
    """返回 (缺失, 多余, 内容不一致)。不一致项为 (name, 源行数, 镜像行数, 哈希说明)。"""
    src_files = {f.name: f for f in sorted(SKILL_CORE.glob("*.py")) if f.name not in IGNORE}
    if not dev_core.is_dir():
        return sorted(src_files), [], []

    dev_files = {f.name: f for f in sorted(dev_core.glob("*.py")) if f.name not in IGNORE}

    missing = sorted(set(src_files) - set(dev_files))
    extra = sorted(set(dev_files) - set(src_files))
    mismatch = []
    for name in sorted(set(src_files) & set(dev_files)):
        s, d = src_files[name], dev_files[name]
        if sha256(s) != sha256(d):
            mismatch.append((name, str(len(s.read_text(encoding="utf-8").splitlines())),
                             str(len(d.read_text(encoding="utf-8").splitlines())),
                             f"{sha256(s)} != {sha256(d)}"))
    return missing, extra, mismatch


def report(dev_core: Path, missing, extra, mismatch) -> None:
    total = len([f for f in SKILL_CORE.glob("*.py") if f.name not in IGNORE])
    print(f"[drift] 真源: {SKILL_CORE}")
    print(f"[drift] 镜像: {dev_core}")
    print(f"[drift] 应同步 {total} 个模块")
    print("-" * 66)
    if not dev_core.is_dir():
        print(f"[drift] 镜像目录不存在 —— 视为全部缺失（{len(missing)} 个）")
    for n in missing:
        print(f"  [缺失]   {n}")
    for n in extra:
        print(f"  [多余]   {n}  (镜像有、真源已删)")
    for name, sl, dl, h in mismatch:
        print(f"  [不一致] {name}  真源 {sl} 行 / 镜像 {dl} 行   {h}")
    print("-" * 66)
    ok = not (missing or extra or mismatch)
    print(f"[drift] {'一致，无漂移' if ok else f'发现漂移 {len(missing)+len(extra)+len(mismatch)} 处'}")


def do_sync(dev_core: Path) -> bool:
    dev_core.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted(SKILL_CORE.glob("*.py")):
        if f.name in IGNORE:
            continue
        shutil.copy2(f, dev_core / f.name)
        n += 1
    # 清掉镜像里真源已删的模块
    for f in sorted(dev_core.glob("*.py")):
        if f.name not in IGNORE and not (SKILL_CORE / f.name).exists():
            f.unlink()
            print(f"[sync] 删除镜像多余文件 {f.name}")
    print(f"[sync] 已复制 {n} 个模块到 {dev_core}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="校验/同步 Skill 真源与 dev 只读镜像")
    ap.add_argument("--sync", action="store_true",
                    help="先把真源复制到镜像，再复校（AGENTS.md 第 2 步）")
    ap.add_argument("--path", default=None, help="镜像 src/core 路径")
    args = ap.parse_args()

    _safe_stdout()
    dev_core = Path(args.path) if args.path else resolve_dev_core()

    if args.sync:
        do_sync(dev_core)

    missing, extra, mismatch = scan(dev_core)
    report(dev_core, missing, extra, mismatch)
    return 1 if (missing or extra or mismatch) else 0


if __name__ == "__main__":
    raise SystemExit(main())
