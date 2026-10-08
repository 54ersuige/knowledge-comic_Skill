"""check_drift.py — Skill 真源 ↔ dev 只读镜像的一致性校验（v0.3.24）

为什么需要这个脚本
------------------
本 skill 的同步规矩是：改动**只在 Skill 侧做**（`~/.minimax/skills/knowledge-comic/`），
`src/core/` 是它的**只读镜像**，用于离线阅读和 code review。规矩里也写了
"同步完必须跑漂移校验"，但那条校验过去只是一条**要人手动敲的 PowerShell**。

于是它从来没被稳定执行过。2026-10-08 实测：`article.py` 真源 1727 行、
镜像 1721 行 —— **镜像缺 v0.3.18 的双层蒙版修复**，一直没人发现。
**"声明与现实不符且无校验机制，是这次漂移烂了好几天的原因"** ——
这句话说的就是只靠人工约定本身。**纯人工约定 = 不会执行。**

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


def _read_norm(p: Path) -> bytes:
    """读文件并**归一化行尾符 + 去 BOM**。

    为什么必须归一化（v0.3.24 实测踩到的坑）
    --------------------------------------
    最初这里直接 `sha256(read_bytes())` 比原始字节，结果在
    `git checkout main` 之后误报 3 处漂移：真源 CRLF、镜像 LF，
    **每一行的内容完全一致**（行数也一致），只差一个 \\r。
    根因是 git 的 `core.autocrlf` 会在 checkout 时按平台重新检出，
    而两边的检出状态不同。

    这个误报比"没有校验"更糟 —— 报几次假警报之后，人就不看这个工具了。
    所以改成比对**归一化后的内容**（这才是"两边是不是同一份代码"的语义），
    同时把"仅行尾符不同"单独作为提示报出来，不当成漂移。
    """
    raw = p.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):      # UTF-8 BOM
        raw = raw[3:]
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def sha256(p: Path) -> str:
    """**归一化后**的 SHA-256（见 _read_norm 的说明）。"""
    return hashlib.sha256(_read_norm(p)).hexdigest()[:16]


def raw_sha256(p: Path) -> str:
    """原始字节哈希，仅用于诊断"仅行尾符不同"的情况。"""
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def scan(dev_core: Path) -> tuple[list[str], list[str], list[tuple], list[str]]:
    """返回 (缺失, 多余, 内容不一致, 仅行尾符不同)。

    不一致项为 (name, 源行数, 镜像行数, 哈希说明)。
    「仅行尾符不同」不计入漂移 —— 归一化后内容一样就是同一份代码。
    """
    src_files = {f.name: f for f in sorted(SKILL_CORE.glob("*.py")) if f.name not in IGNORE}
    if not dev_core.is_dir():
        return sorted(src_files), [], [], []

    dev_files = {f.name: f for f in sorted(dev_core.glob("*.py")) if f.name not in IGNORE}

    missing = sorted(set(src_files) - set(dev_files))
    extra = sorted(set(dev_files) - set(src_files))
    mismatch = []
    eol_only = []
    for name in sorted(set(src_files) & set(dev_files)):
        s, d = src_files[name], dev_files[name]
        if sha256(s) == sha256(d):
            if raw_sha256(s) != raw_sha256(d):
                eol_only.append(name)
            continue
        mismatch.append((name, str(len(s.read_text(encoding="utf-8").splitlines())),
                         str(len(d.read_text(encoding="utf-8").splitlines())),
                         f"{sha256(s)} != {sha256(d)}"))
    return missing, extra, mismatch, eol_only


def report(dev_core: Path, missing, extra, mismatch, eol_only) -> None:
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
    if eol_only:
        print(f"  [行尾符] {len(eol_only)} 个文件归一化后一致、原始字节不同"
              f"（CRLF/LF 差异，不算漂移）: {', '.join(eol_only)}")
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
                    help="先把真源复制到镜像，再复校（同步流程第 2 步）")
    ap.add_argument("--path", default=None, help="镜像 src/core 路径")
    args = ap.parse_args()

    _safe_stdout()
    dev_core = Path(args.path) if args.path else resolve_dev_core()

    if args.sync:
        do_sync(dev_core)

    missing, extra, mismatch, eol_only = scan(dev_core)
    report(dev_core, missing, extra, mismatch, eol_only)
    return 1 if (missing or extra or mismatch) else 0


if __name__ == "__main__":
    raise SystemExit(main())
