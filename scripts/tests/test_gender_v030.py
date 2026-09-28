"""v0.3.0 smoke test: 验证中性脸 + 性别分支 anchor + 自动检测。

跑法(任意目录): python scripts/tests/test_gender_v030.py
"""
import sys
from pathlib import Path

# 自解析 skill 根目录（原写法 `sys.path.insert(0, '.')` 只在 skill 根目录下有效）
SKILL_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL_ROOT))

from scripts.core.prompts import (
    CHARACTER_CN_LIANHUANHUA_FACE,
    CHARACTER_CN_LIANHUANHUA_GENDER_FEMALE,
    CHARACTER_CN_LIANHUANHUA_GENDER_MALE,
    CHARACTER_CN_LIANHUANHUA_MODERN,
    CHARACTER_CN_LIANHUANHUA_ANCESTOR,
    CHARACTER_ANCHORS,
    build_image_prompt,
    _resolve_cn_lianhuanhua_anchor,
)

# 1. 子块存在
assert CHARACTER_CN_LIANHUANHUA_FACE
assert CHARACTER_CN_LIANHUANHUA_GENDER_FEMALE
assert CHARACTER_CN_LIANHUANHUA_GENDER_MALE
assert 'willow-leaf' in CHARACTER_CN_LIANHUANHUA_GENDER_FEMALE
assert 'NO pink blush' in CHARACTER_CN_LIANHUANHUA_GENDER_MALE
# 注意:男性描述里有"NOT 步摇 — too feminine",包含步摇字面,
# 但有"too feminine"明确否定,所以检查 must not be present as positive styling
import re as _re
male_positive = _re.search(r'\(d\) Hair:[^(]*jade or gold hairpin[^(]*', CHARACTER_CN_LIANHUANHUA_GENDER_MALE)
assert male_positive and '玉簪/金簪' in male_positive.group(0)
assert 'NO 花钿' in CHARACTER_CN_LIANHUANHUA_GENDER_MALE
assert 'NO 簪花' in CHARACTER_CN_LIANHUANHUA_GENDER_MALE
print('PASS: 中性脸 + 性别分支 子块就位')

# 2. 默认 anchor = FACE + FEMALE (历史典故默认偏女性主角,但 build_image_prompt 会按 gender 重选)
assert 'willow-leaf' in CHARACTER_CN_LIANHUANHUA_MODERN
assert 'FEMALE-GENDER STYLING (must apply to all female leads in the scene)' in CHARACTER_CN_LIANHUANHUA_MODERN
# 默认 MODERN 不含 MALE-STYLING(那由 _resolve_cn_lianhuanhua_anchor 按 gender 动态拼)
assert 'MALE-GENDER STYLING (must apply to all male leads in the scene)' not in CHARACTER_CN_LIANHUANHUA_MODERN
assert CHARACTER_ANCHORS['chinese_lianhuanhua_classic'] == CHARACTER_CN_LIANHUANHUA_MODERN
print('PASS: 默认 anchor = 中性脸 + 女性妆发 (历史典故默认偏女性主角)')

# 3. ANCESTOR 保留
assert CHARACTER_CN_LIANHUANHUA_ANCESTOR
assert 'square jaw' in CHARACTER_CN_LIANHUANHUA_ANCESTOR
print('PASS: CHARACTER_CN_LIANHUANHUA_ANCESTOR 古典脸保留')

# 4. _resolve_cn_lianhuanhua_anchor 测试
cases = [
    ('SUBJECT: Zhang Xun', 'auto', 'male'),     # auto mode: Zhang Xun 触发 "Zhang" 男性名 + 内容语境 → male
    ('SUBJECT: Wang Zhaojun', 'auto', 'female'),
    ('[GENDER:male] SUBJECT:...', 'auto', 'male'),
    ('[GENDER:female] SUBJECT:...', 'auto', 'female'),
    ('[GENDER:mixed] SUBJECT:...', 'auto', 'mixed'),
    ('SUBJECT: Zhang Xun', 'female', 'female'),  # explicit female override
    ('SUBJECT: Wang Zhaojun', 'male', 'male'),  # explicit male override
    ('He is a commander', 'auto', 'male'),
    ('She is a noble lady', 'auto', 'female'),
    ('He is with his wife', 'auto', 'mixed'),
    ('他和妻子坐在桌旁', 'auto', 'mixed'),
]
def _detect_gender(anchor_text):
    """检查 anchor 包含哪个 gender 妆发分支。"""
    has_m = 'MALE-GENDER STYLING (must apply to all male leads in the scene)' in anchor_text
    has_f = 'FEMALE-GENDER STYLING (must apply to all female leads in the scene)' in anchor_text
    if has_m and has_f: return 'mixed'
    if has_m: return 'male'
    if has_f: return 'female'
    return 'unknown'
for scene, g_param, want in cases:
    got = _detect_gender(_resolve_cn_lianhuanhua_anchor(g_param, scene))
    if got != want:
        print(f'FAIL: {scene!r} gender={g_param!r} want={want} got={got}')
        sys.exit(1)
print(f'PASS: _resolve_cn_lianhuanhua_anchor {len(cases)} cases')

# 5. build_image_prompt 集成测试 - 显式 gender 参数优先
p_male = build_image_prompt('chinese_lianhuanhua_classic', 'SUBJECT: Zhang Xun', gender='male')
assert 'MALE-GENDER STYLING (must apply to all male leads in the scene)' in p_male
assert 'FEMALE-GENDER STYLING (must apply to all female leads in the scene)' not in p_male
print('PASS: build_image_prompt 显式 gender=male → 只用 MALE-STYLING')

p_female = build_image_prompt('chinese_lianhuanhua_classic', 'SUBJECT: someone', gender='female')
assert 'FEMALE-GENDER STYLING (must apply to all female leads in the scene)' in p_female
assert 'MALE-GENDER STYLING (must apply to all male leads in the scene)' not in p_female
print('PASS: build_image_prompt 显式 gender=female → 只用 FEMALE-STYLING')

p_mixed = build_image_prompt('chinese_lianhuanhua_classic', 'Zhang Xun and his wife', gender='mixed')
assert 'MALE-GENDER STYLING (must apply to all male leads in the scene)' in p_mixed
assert 'FEMALE-GENDER STYLING (must apply to all female leads in the scene)' in p_mixed
print('PASS: build_image_prompt 显式 gender=mixed → FEMALE + MALE 都有')

# 6. auto mode: Zhang Xun 应该被自动判断为 male
p_auto = build_image_prompt('chinese_lianhuanhua_classic', 'SUBJECT: Zhang Xun, 40yo Tang general. ACTION: holds a sword', gender='auto')
assert 'MALE-GENDER STYLING (must apply to all male leads in the scene)' in p_auto
print('PASS: build_image_prompt auto mode 正确识别 Zhang Xun 为男性')

# 7. auto mode: Zhang Xun + his wife → mixed
p_auto2 = build_image_prompt('chinese_lianhuanhua_classic', 'Zhang Xun and his wife sitting in a room', gender='auto')
assert 'MALE-GENDER STYLING (must apply to all male leads in the scene)' in p_auto2
assert 'FEMALE-GENDER STYLING (must apply to all female leads in the scene)' in p_auto2
print('PASS: build_image_prompt auto mode "Zhang Xun and his wife" → mixed')

# 8. 非 chinese_lianhuanhua_classic 风格不受影响
p_other = build_image_prompt('cn_xuanfeng', 'SUBJECT: Zhang Xun', gender='auto')
assert 'CHARACTER_ANCIENT_CN' in p_other or 'Han-Chinese historical person' in p_other
print('PASS: cn_xuanfeng 风格不受 v0.3.0 性别分支影响')

print()
print('=== v0.3.0 全部 8 项验证通过 ===')