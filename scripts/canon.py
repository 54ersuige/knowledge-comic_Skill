"""Canon loader - load data/canon.md and inject into planner prompt.

让 planner 在生成 storyboard 前加载 canon，确保术语/数字/角色一致。
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

CANON_PATH = SKILL_ROOT / "data" / "canon.md"


@dataclass
class CanonTerm:
    category: str
    candidates: list[str]
    selected: str = ""


@dataclass
class CanonFact:
    label: str
    value: str
    source: str = ""


@dataclass
class CanonCharacter:
    id: str
    name: str
    description: str = ""
    visual_anchor: str = ""


@dataclass
class Canon:
    """跨文章一致性追踪的内存表示。"""
    terms: dict[str, CanonTerm] = field(default_factory=dict)
    facts: list[CanonFact] = field(default_factory=list)
    characters: dict[str, CanonCharacter] = field(default_factory=dict)
    timelines: dict[str, list[str]] = field(default_factory=dict)

    def to_planner_injection(self) -> str:
        """生成给 planner 的 cannon 注入文本。"""
        lines = []
        if self.terms:
            lines.append("## Canon 术语表（必须遵守）")
            for term in self.terms.values():
                if term.selected:
                    lines.append(f"- {term.category}: 用「{term.selected}」（不要用 {'/'.join(t for t in term.candidates if t != term.selected)}）")
                else:
                    lines.append(f"- {term.category}: {'/'.join(term.candidates)}")
            lines.append("")

        if self.facts:
            lines.append("## Canon 关键数字（必须一致）")
            for fact in self.facts:
                lines.append(f"- {fact.label}: {fact.value}")
            lines.append("")

        if self.characters:
            lines.append("## Canon 角色（视觉锚点统一）")
            for char in self.characters.values():
                if char.visual_anchor:
                    lines.append(f"- {char.id}: {char.visual_anchor}")
            lines.append("")

        if self.timelines:
            lines.append("## Canon 时间线（按时间顺序展开）")
            for topic, events in self.timelines.items():
                lines.append(f"### {topic}")
                for ev in events:
                    lines.append(f"- {ev}")
            lines.append("")

        return "\n".join(lines)


def _parse_terms(text: str) -> dict[str, CanonTerm]:
    """解析 §2 术语统一表。"""
    terms = {}
    in_section = False
    for line in text.split("\n"):
        if "## 2. 术语统一表" in line:
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if not in_section or not line.startswith("|"):
            continue
        # 表格行：| 类别 | 候选词 | 当前选定 | 备注 |
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 4 or "---" in cells[0] or cells[0] == "类别":
            continue
        category, candidates_str, selected, _note = cells[:4]
        candidates = [c.strip() for c in candidates_str.split("/") if c.strip()]
        terms[category] = CanonTerm(
            category=category,
            candidates=candidates,
            selected=selected,
        )
    return terms


def _parse_facts(text: str) -> list[CanonFact]:
    """解析 §3 关键数字库。"""
    facts = []
    in_section = False
    for line in text.split("\n"):
        if "## 3. 关键数字库" in line:
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if not in_section or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3 or "---" in cells[0] or cells[0] == "数据":
            continue
        label, value, source = cells[:3]
        facts.append(CanonFact(label=label, value=value, source=source))
    return facts


def _parse_characters(text: str) -> dict[str, CanonCharacter]:
    """解析 §1 角色表。"""
    chars = {}
    # 简单解析：基于 ID + visual_anchor 行的"- id: visual_anchor"模式
    in_section = False
    for line in text.split("\n"):
        if "## 1. 角色表" in line or "### 1." in line:
            in_section = True
            continue
        if in_section and (line.startswith("## ") or line.startswith("### 2.")):
            break
        if not in_section:
            continue
        m = re.match(r"^\s*-\s*ID\s*[:：]\s*`?([\w_]+)`?", line)
        if m:
            chars[m.group(1)] = CanonCharacter(
                id=m.group(1),
                name="",
                visual_anchor="",
            )
    return chars


def _parse_timelines(text: str) -> dict[str, list[str]]:
    """解析 §4 时间线模板（### 主题 后是 - 时间：事件）。"""
    timelines = {}
    in_section = False
    current_topic = None
    for line in text.split("\n"):
        if "## 4. 时间线模板" in line:
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if not in_section:
            continue
        if line.startswith("### "):
            current_topic = line[4:].strip()
            timelines[current_topic] = []
        elif current_topic and line.startswith("- "):
            timelines[current_topic].append(line[2:].strip())
    return timelines


def load_canon() -> Canon:
    """从 data/canon.md 加载 Canon。"""
    if not CANON_PATH.exists():
        # Canon 文件不存在时返回空 Canon（不阻塞）
        return Canon()
    text = CANON_PATH.read_text(encoding="utf-8")
    return Canon(
        terms=_parse_terms(text),
        facts=_parse_facts(text),
        characters=_parse_characters(text),
        timelines=_parse_timelines(text),
    )


def get_canon_injection() -> str:
    """快捷：直接拿 canon 注入文本。"""
    canon = load_canon()
    return canon.to_planner_injection()


if __name__ == "__main__":
    # CLI: 看 canon 解析结果
    canon = load_canon()
    print(f"Terms: {len(canon.terms)}")
    for k, v in list(canon.terms.items())[:3]:
        print(f"  {k}: {v.candidates} (selected: {v.selected})")
    print(f"\nFacts: {len(canon.facts)}")
    for f in canon.facts[:3]:
        print(f"  {f.label}: {f.value}")
    print(f"\nCharacters: {len(canon.characters)}")
    print(f"\nTimelines: {list(canon.timelines.keys())}")
    print("\n--- Planner injection ---")
    print(canon.to_planner_injection())