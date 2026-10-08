"""thresholds.py — 全项目内容阈值的**唯一真源**（v0.3.24 新增）

为什么要有这个模块
------------------
项目里有 5 道检查层（preflight / visual_qa / review_page / check_alignment /
story_script），每层各自定义"正文多少字算长""几个 keywords 算够"。2026-10-08
审计实测已经漂移：

| 规则            | preflight（阻塞关卡）        | review_page（体检报告）   | 后果 |
|-----------------|------------------------------|--------------------------|------|
| body > 150      | BODY_LONG_SOFT **warn**      | **error**                | 同一次跑，preflight 放行 + review_page 报错，结论自相矛盾 |
| body > 170      | BODY_LONG **block**          | 无此档（150 就 error 了） | 阻塞线比报告线还松 |
| body < 90       | BODY_SHORT **warn**          | 无此档                   | 90 字正文被报告判「低于下限」 |
| body < 100      | 放行                         | **warn**                 | 同上 |
| keywords < 3    | **无检查**                   | warn                     | preflight 放行 1 个关键词的页 |
| keywords > 6    | warn                         | 无此档                   | — |
| punchline > 22  | 实际按 30 放行，但**报错文案写 22** | 无检查          | 代码与自己的提示自相矛盾 |
| dialogue > 50   | 实际按 90 放行（文案未写上限）| 无检查                   | 同上 |

**根因不是某个值定错了，而是同一个值被复制了 2~3 份。** 修一份漏一份正是本项目
反复踩的坑（keywords 解析层漏字段 v0.3.3、CONCEPT 段漏加黑名单 v0.3.18、
prompt 拼装双路径 v0.3.21）—— 同一个失效模式第 4 次出现。

所以这里只放**数值**，各检查层 import，不允许再自己写死字面量。

取值原则（与 planner prompt 铁律一致）
--------------------------------------
用户的「100-150 字」是**目标带**，不是硬边界。preflight v0.3.15 的修正记录写得很
清楚：初版把 100-150 当硬边界，结果 93/95/154 字全被判不合格；用户的真实诉求是
「文字不能过多、别压过画面」，不是「必须够 150 字」。

**关卡拦"方向错"，不拦"没到理想值"** —— 这条原则决定了下面每一档的宽严。
"""
from __future__ import annotations

# --- 正文 body -----------------------------------------------------------
# 目标带：planner 照此写，报告层照此建议
BODY_TARGET_LO = 100
BODY_TARGET_HI = 150
# 阻塞线：超过就真的「文字压过画面」了
BODY_HARD_HI = 170
# 建议线：低于此值内容偏薄（比目标带下沿更宽松，避免误伤短页）
BODY_WARN_LO = 90

# --- keywords（朱砂红高亮）-----------------------------------------------
KEYWORDS_MIN = 3       # 少于 3 个 → 高亮链路的价值撑不起来
KEYWORDS_IDEAL = 5     # 5-8 个/人名/地名/朝代/事件
KEYWORDS_MAX = 6       # 超过 6 个 → 正文里碎成一片，反而看不清重点

# --- punchline（「定格瞬间」白话金句）------------------------------------
PUNCH_MIN = 10
PUNCH_MAX = 22         # 与 planner prompt §2 字段表 punchline 行一致

# --- dialogue（文言原文引句，叠图下缘蒙版）------------------------------
QUOTE_MIN = 8
QUOTE_MAX = 50         # 与 planner prompt §3.4 dialogue 上限一致

# --- visual（画面描述）---------------------------------------------------
VISUAL_MIN = 300       # 太短说明七要素没写全
# 连环画（chinese_lianhuanhua_classic）单页主人物下限。planner §4.4 铁律是
# 「主人物 ≥ 3 个 + 背景 2-3 个配角活动」；review_page._check_multi_figure 的
# 提示文案引用这个数，不要再在消息里另写一个 "3+"，否则又是一份复制品。
MULTI_FIGURE_MIN = 3

# --- caption / highlight -------------------------------------------------
CAPTION_MIN = 10
CAPTION_MAX = 20
HIGHLIGHT_MIN = 4
HIGHLIGHT_MAX = 8


def describe_body_policy() -> str:
    """给报告/提示文案用的单行口径说明，保证所有层说法一致。"""
    return (f"目标 {BODY_TARGET_LO}-{BODY_TARGET_HI} 字/页；"
            f"超过 {BODY_HARD_HI} 字阻塞，{BODY_WARN_LO} 字以下偏薄")
