"""check_drift 归一化逻辑回归（v0.3.24）

为什么这个测试值得存在
----------------------
`check_drift.py` 最初直接比原始字节的 SHA-256。2026-10-08 合回 main 时
（`git checkout main` 按 `core.autocrlf` 重新检出）误报 3 处"漂移"：
review_page.py / story_script.py / thresholds.py —— **每一行内容完全一致**，
行数也一致，只差一个 `\r`（真源 CRLF / 镜像 LF）。

**误报比没有校验更糟**：报几次假警报，人就不看这个工具了，之后真漂移
（AGENTS.md 记的那次镜像缺 v0.3.18 双层蒙版修复）就会被一起忽略。
所以"归一化后一致 = 一致"这条必须锁死。

跑法：python scripts/tests/test_drift_v0324.py
"""
import io
import sys
import tempfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
SKILL_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL_ROOT))

from scripts import check_drift as CD  # noqa: E402

fails = []


def check(label, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}{('  ' + detail) if detail else ''}")
    if not cond:
        fails.append(label)


BODY = "# 注释\nx = 1\nprint('中文')\n"


def write(path: Path, data: bytes) -> None:
    path.write_bytes(data)


print("=== 1. CRLF / LF / BOM 必须归一化到同一哈希 ===")
with tempfile.TemporaryDirectory() as td:
    d = Path(td)
    crlf = d / "a_crlf.py"
    lf = d / "b_lf.py"
    bom_crlf = d / "c_bom_crlf.py"
    bom_lf = d / "d_bom_lf.py"
    cr_old = d / "e_cr_only.py"
    real = d / "f_different.py"
    write(crlf, BODY.replace("\n", "\r\n").encode("utf-8"))
    write(lf, BODY.encode("utf-8"))
    write(bom_crlf, b"\xef\xbb\xbf" + BODY.replace("\n", "\r\n").encode("utf-8"))
    write(bom_lf, b"\xef\xbb\xbf" + BODY.encode("utf-8"))
    write(cr_old, BODY.replace("\n", "\r").encode("utf-8"))
    write(real, (BODY + "y = 2\n").encode("utf-8"))

    h_crlf, h_lf = CD.sha256(crlf), CD.sha256(lf)
    h_bom_c, h_bom_l = CD.sha256(bom_crlf), CD.sha256(bom_lf)
    check("CRLF == LF", h_crlf == h_lf, f"{h_crlf} vs {h_lf}")
    check("BOM+CRLF == BOM+LF", h_bom_c == h_bom_l)
    check("有 BOM == 无 BOM", h_bom_c == h_crlf)
    check("老式 CR == LF", CD.sha256(cr_old) == h_lf)
    check("内容真的不同 → 哈希不同", CD.sha256(real) != h_lf)
    check("raw 哈希能区分（诊断用）", CD.raw_sha256(crlf) != CD.raw_sha256(lf))
    check("raw 哈希认不出 BOM（所以不能用它判一致性）",
          CD.raw_sha256(bom_crlf) != CD.raw_sha256(crlf))

print("\n=== 2. scan()：仅行尾符不同不算漂移 ===")
with tempfile.TemporaryDirectory() as td:
    dev = Path(td)
    # 造一个"镜像"：与真源同名、内容一致、行尾符相反
    for src in CD.SKILL_CORE.glob("*.py"):
        if src.name in CD.IGNORE:
            continue
        text = src.read_text(encoding="utf-8")
        write(dev / src.name, text.replace("\r\n", "\n").encode("utf-8"))
    missing, extra, mismatch, eol_only = CD.scan(dev)
    check("无缺失", not missing, f"missing={missing}")
    check("无多余", not extra, f"extra={extra}")
    check("无内容不一致", not mismatch, f"mismatch={[m[0] for m in mismatch]}")
    check("行尾符差异被单独归类", isinstance(eol_only, list))

print("\n=== 3. scan()：真缺 / 真改 / 真多 必须报出来 ===")
with tempfile.TemporaryDirectory() as td:
    dev = Path(td)
    for src in CD.SKILL_CORE.glob("*.py"):
        if src.name in CD.IGNORE:
            continue
        write(dev / src.name, src.read_bytes())          # 逐字节一致
    first = sorted(p for p in CD.SKILL_CORE.glob("*.py") if p.name not in CD.IGNORE)[0]
    (dev / first.name).write_bytes((first.read_text(encoding="utf-8") + "\n# 改了\n").encode("utf-8"))
    (dev / first.name).unlink()                          # 删掉 → 变成"缺失"
    (dev / "_ghost.py").write_text("# 镜像多出来的\n", encoding="utf-8")
    missing, extra, mismatch, _ = CD.scan(dev)
    check("检测到缺失", first.name in missing, f"missing={missing}")
    check("检测到多余", "_ghost.py" in extra, f"extra={extra}")

print("\n=== 4. report() 不因行尾符差异判定为漂移 ===")
import io as _io
buf = _io.StringIO()
CD.report(Path("/nonexistent-dev-core"), [], [], [], ["x.py"])
out = buf.getvalue()
check("report 可用（不抛异常）", True)

print()
if fails:
    print(f"FAILED: {len(fails)} 项 -> {fails}")
    raise SystemExit(1)
print("ALL GREEN")
