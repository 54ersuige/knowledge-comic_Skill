"""Mavis 风格推荐 CLI

用法:
  python scripts/recommend.py "Transformer"
  python scripts/recommend.py "中世纪黑死病"
"""
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from scripts.core.prompts import recommend_style_rationale, list_styles  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python recommend.py "<topic>"")
        print()
        print("All available styles:")
        for s in list_styles():
            print(f"  - {s['id']:25s}  {s['name_zh']}  ({s['use_cases']})")
        return 1

    topic = " ".join(sys.argv[1:])
    print(recommend_style_rationale(topic))
    return 0


if __name__ == "__main__":
    sys.exit(main())