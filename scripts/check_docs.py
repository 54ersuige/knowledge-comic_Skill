"""check_docs.py — 文档引用完整性校验（v0.3.27 新增）。

为什么需要这个
--------------
本项目**反复**栽在同一类坑上（CHANGELOG 里能数到 4 次）：文档里写着某个
路径 / 函数 / 脚本，而它其实已经被删掉或改名了。最近一次实测：

  - `README.md` 整体停在 v0.2.4，还推荐两个已被归档的 `diagnose_*.py`
  - `SKILL.md` 让 Mavis 调 `guide.show_intent()` —— 该函数**从未存在**
  - `style_guide.md` 的「总分 ≥90 / 重试 2 次」是一整套**没有实现的**死规格
  - `ruff.toml` / `check_drift.py` 以 `AGENTS.md` 为规矩来源，而 skill 里没有它

这些都不是运行时报错，而是**把下一个读文档的人引到不存在的地方**。靠人工
review 挡不住（已经漏了 4 次），所以做成可跑的检查。

检查三件事
----------
  1. 文档里反引号包起来的仓库内路径是否真的存在
  2. `SKILL.md` 提到的 `step_*` 是否都在 `scripts/run.py` 里有定义
  3. `references/*.md` 相互引用的文件是否存在

判为「可接受」的三种情况（不报错）
--------------------------------
  - 裸文件名（如 `run.py`）：仓库里存在同名文件即算命中，文档常省略路径
  - 同一行（或前两行）出现「已删除 / 已归档 / 原 / 原先 / 曾经 / 退役」：
    属于**有意为之的历史说明**，不是漂移
  - 同一窗口出现 `data/<job_id>`：那是运行时才生成的 job 产物，本就不该在仓库里

`references/CHANGELOG.md` 不参与校验 —— 它的职责就是记录历史，里面的路径
本来就可能是"当时存在、现在已删"。

跑法
----
    python scripts/check_docs.py        # 有悬空引用则退出码 1

用法建议：改完任何 `.md` 或删改脚本后跑一次。它和 `check_drift.py` 是一对 ——
后者管"真源 ↔ dev 镜像"的一致性，前者管"文档 ↔ 代码"的一致性。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BACKTICK = re.compile(r"`([^`\n]+)`")
PATHLIKE = re.compile(r"^[\w\-./]+\.(py|md|toml|txt|sh|ps1|json|example)$")
STEPFN = re.compile(r"\bstep_[a-z_]+\b")

ALLOW_IF_WINDOW_HAS = ("已删除", "已归档", "原 ", "原先", "曾经", "退役", "data/<job_id>")

problems: list[str] = []


def _basename_index() -> set[str]:
    return {p.name for p in ROOT.rglob("*") if p.is_file()}


def check_paths(md: Path, basenames: set[str]) -> None:
    lines = md.read_text(encoding="utf-8").splitlines()
    for idx, line in enumerate(lines):
        # 3 行窗口：Markdown 里一句话常被折行，关键词可能落在上一行
        window = "\n".join(lines[max(0, idx - 2): idx + 1])
        for raw in BACKTICK.findall(line):
            token = raw.strip()
            if not PATHLIKE.match(token):
                continue
            if (ROOT / token).exists():
                continue
            if token.endswith("/") and (ROOT / token).parent.exists():
                continue
            if "/" not in token and Path(token).name in basenames:
                continue
            if any(kw in window for kw in ALLOW_IF_WINDOW_HAS):
                continue
            problems.append(f"{md.relative_to(ROOT)}:{idx + 1}: 路径不存在 -> `{token}`")


def check_steps(md: Path, run_py_text: str) -> None:
    for fn in sorted(set(STEPFN.findall(md.read_text(encoding="utf-8")))):
        if f"def {fn}(" not in run_py_text:
            problems.append(f"{md.relative_to(ROOT)}: run.py 里没有 {fn}()")


def main() -> int:
    # 与 run.py 的 _safe_stdout() 同一课：中文 Windows 控制台是 cp936，
    # 编不出非 BMP 字符会直接抛 UnicodeEncodeError。退化成 '?' 好过崩。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            pass

    run_py = ROOT / "scripts" / "run.py"
    run_py_text = run_py.read_text(encoding="utf-8")
    basenames = _basename_index()

    docs = [ROOT / "SKILL.md"] + sorted((ROOT / "references").glob("*.md"))
    docs = [d for d in docs if d.name != "CHANGELOG.md"]

    for md in docs:
        check_paths(md, basenames)
        if md.name == "SKILL.md":
            check_steps(md, run_py_text)

    if problems:
        print(f"[docs] 发现 {len(problems)} 处悬空引用：")
        for p in problems:
            print(f"  [X] {p}")
        return 1

    print(f"[docs] 通过：{len(docs)} 份文档无悬空路径引用，"
          f"SKILL.md 的 step_* 全部存在于 run.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
