"""Quick mock v3 现代极简风 - 用占位 div 快速呈现设计。

不依赖真实图片。给你看完整排版结构。
"""
from __future__ import annotations

import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from scripts.core import article as article_mod
from scripts.core.planner import Storyboard, StoryPage


# Mock 黑死病 storyboard（用之前生成的真实数据，但显式构造以避免依赖）
def build_mock_sb() -> Storyboard:
    pages = [
        StoryPage(page=1, visual="", caption="1347年，墨西拿港口的清晨笼罩在死寂中", dialogue="", narration="", body="历史往往被宏大叙事包裹，但真相通常藏在细节里。1347年10月，一艘来自东方的商船缓缓驶入西西里岛墨西拿港。船员身上布满黑色肿块，眼神空洞。当地官员起初认为这是战争所致，直至发现死者身上的黑斑。这是鼠疫大流行抵达欧洲的第一个确切时间点。", key_visual="停靠的商船与尸体", highlight="1347"),
        StoryPage(page=2, visual="", caption="传播链的核心：从老鼠到人类的微观视角", dialogue="", narration="", body="流行病学的追踪揭示了一个残酷的机制：鼠疫杆菌通过寄生在棕色大鼠身上的跳蚤传播。当老鼠因感染死亡或跳蚤因宿主消失而饥饿时，它们会转向叮咬人类。这一过程在拥挤的城市贫民窟中加速爆发。", key_visual="跳蚤的特写", highlight="跳蚤"),
        StoryPage(page=3, visual="", caption="数据背后的社会断层：三分之一人口蒸发", dialogue="", narration="", body="在1347至1351年间，死亡人数惊人地稳定在欧洲总人口的30%至60%之间，通常被概括为三分之一。这不仅是一场灾难，更是一次剧烈的人口统计学冲击。劳动力骤减导致土地价值暴跌，而幸存者的工资需求激增。", key_visual="空荡的市场与数字1/3", highlight="三分"),
        StoryPage(page=4, visual="", caption="从被动承受转向主动防御的卫生革命", dialogue="", narration="", body="面对死亡的常态化，威尼斯和热那亚率先实施了现代意义上的隔离措施。来自疫区的船只必须在海上停留40天（意大利语quaranta giorni，即quarantine词源）。这种集体性的卫生行为标志着欧洲公共卫生体系的雏形诞生。", key_visual="被锚链固定的隔离船只", highlight="隔离"),
        StoryPage(page=5, visual="", caption="死亡之后的经济重构与权力转移", dialogue="", narration="", body="黑死病后，幸存的劳动力拥有前所未有的议价能力。农民开始拒绝沉重的劳役，要求现金工资。为了留住人手，领主不得不降低租金，甚至允许农民购买土地。这一过程加速了农奴制的解体，推动了西欧向资本主义早期形态过渡。", key_visual="荒芜的田野与单个劳动者", highlight="余波"),
    ]
    return Storyboard(
        topic="中世纪黑死病", style_id="new_yorker",
        title="1347", subtitle="西西里港口的黑旗与欧洲的三分之一",
        summary="当一艘来自东方的商船驶入墨西拿，欧洲失去了近半数劳动力，也重塑了现代社会的底层逻辑。",
        preface="死亡，是历史最昂贵的货币。", epigraph="",
        postscript="黑死病，是工资体系的催化剂。",
        pages=pages,
    )


def main():
    sb = build_mock_sb()
    html = article_mod.render_mock_preview_v3(sb, template="c_v3")
    out = Path("data/_mock_v3.html")
    out.parent.mkdir(exist_ok=True, parents=True)
    out.write_text(html, encoding="utf-8")
    print(f"saved: {out.absolute()}  ({len(html)} chars)")
    print("open in browser to review")


if __name__ == "__main__":
    main()