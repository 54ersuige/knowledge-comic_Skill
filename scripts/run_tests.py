"""run_tests.py — 一次跑完全部测试，退出码即结论。

为什么需要这个（v0.3.24）
------------------------
`scripts/tests/test_*.py` 全部是 **standalone 脚本**：模块顶层用 `assert`
自检、结尾 `sys.exit(0)`。这套写法单跑没问题（`python test_x.py` → rc=0），
但 `pytest scripts/tests` 会 **INTERNALERROR 退出码 3** —— pytest 在收集阶段
执行模块顶层代码，撞上 `SystemExit`，整个 session 直接崩，连已收集的用例
都不跑。实测 7 个文件只能一个一个手敲。

所以不做「把 7 个文件改写成 pytest 风格」（改动面大、易碰坏已验证的断言），
改为**用子进程逐个跑并汇总**：
  - 隔离 —— 一个文件崩不影响其它文件
  - 兼容 —— 不动现有测试代码
  - 可读 —— 末尾一张汇总表 + 明确的退出码，能直接进 CI / pre-commit

用法
----
    python scripts/run_tests.py              # 跑全部（跳过需要真 LLM 的 live 用例）
    python scripts/run_tests.py --live       # 连 test_live_smoke.py 一起跑（烧额度）
    python scripts/run_tests.py -k preflight # 只跑文件名含 preflight 的
    python scripts/run_tests.py -v           # 透传每个测试文件的完整输出
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = SKILL_ROOT / "scripts" / "tests"

# 需要真 LLM / 真额度的用例，默认不跑。
LIVE_TESTS = {"test_live_smoke.py"}


def _force_utf8_stdout() -> None:
    """测试输出里有大量中文 + ✅ emoji，GBK 控制台会 UnicodeEncodeError。

    事故先例：v0.3.23 `test_preflight_v0315.py` 里一个损坏字符导致
    「逻辑 93/93 全过但退出码 1」。这里统一 errors="replace" 兜底，
    让**编码问题永远不会伪装成测试失败**。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def discover(include_live: bool, pattern: str | None) -> list[Path]:
    files = sorted(TESTS_DIR.glob("test_*.py"))
    if not include_live:
        files = [f for f in files if f.name not in LIVE_TESTS]
    if pattern:
        files = [f for f in files if pattern in f.name]
    return files


def run_one(path: Path, verbose: bool) -> tuple[bool, float, str]:
    """跑一个测试文件。返回 (是否通过, 耗时秒, 失败摘要)。"""
    t0 = time.time()
    proc = subprocess.run(
        [sys.executable, str(path)],
        cwd=str(SKILL_ROOT),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    took = time.time() - t0
    ok = proc.returncode == 0

    if verbose:
        print(f"\n----- {path.name} (rc={proc.returncode}) -----")
        sys.stdout.write(proc.stdout or "")
        if proc.returncode != 0:
            sys.stdout.write(proc.stderr or "")
        sys.stdout.flush()

    if not ok:
        tail = [ln for ln in (proc.stdout or "").strip().splitlines() if ln.strip()]
        stderr_tail = [ln for ln in (proc.stderr or "").strip().splitlines() if ln.strip()]
        summary = " / ".join((tail[-3:] or stderr_tail[-3:]) or [f"rc={proc.returncode}"])
        return False, took, summary[:300]
    return True, took, ""


def main() -> int:
    ap = argparse.ArgumentParser(description="跑 knowledge-comic 全部测试")
    ap.add_argument("--live", dest="include_live", action="store_true",
                    help="连需要真 LLM 的 live 冒烟测试一起跑（烧额度）")
    ap.add_argument("-k", dest="pattern", default=None,
                    help="只跑文件名含该子串的测试")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="透传每个测试文件的完整输出")
    args = ap.parse_args()

    _force_utf8_stdout()

    files = discover(args.include_live, args.pattern)
    if not files:
        print(f"[tests] 没有匹配的测试文件 (dir={TESTS_DIR}, -k={args.pattern})")
        return 1

    skipped = [f.name for f in sorted(TESTS_DIR.glob("test_*.py")) if f.name in LIVE_TESTS]
    print(f"[tests] {len(files)} 个测试文件"
          + (f"，跳过 live: {', '.join(skipped)}（加 --live 可跑）" if skipped and not args.include_live else ""))
    print("-" * 68)

    results: list[tuple[str, bool, float, str]] = []
    for i, path in enumerate(files, start=1):
        print(f"[tests] ({i}/{len(files)}) {path.name} ...", flush=True)
        ok, took, summary = run_one(path, args.verbose)
        results.append((path.name, ok, took, summary))
        print(f"[tests]   -> {'PASS' if ok else 'FAIL'} ({took:.1f}s)", flush=True)

    passed = sum(1 for _, ok, _, _ in results if ok)
    failed = len(results) - passed
    total_time = sum(t for _, _, t, _ in results)

    print("-" * 68)
    print(f"[tests] 汇总: {passed}/{len(results)} 通过, {failed} 失败, 共 {total_time:.1f}s")
    if failed:
        print()
        for name, ok, _, summary in results:
            if not ok:
                print(f"  FAIL {name}: {summary}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
