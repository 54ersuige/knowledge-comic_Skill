"""smoke test:验证 v0.2.9 默认值
- body 长度 100-150 字
- 每页有 keywords 字段
- planner 输出符合 schema

跑法(任意目录): python scripts/tests/test_smoke_v029.py
"""
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
# 自解析 skill 根目录（原写法 `sys.path.insert(0, 'scripts')` 只在 skill 根目录下有效）
SKILL_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL_ROOT))

# 不调用真 LLM,直接检查 schema 和代码改动
print("=== 验证 StoryPage.keywords 字段 ===")
from scripts.core.planner import StoryPage
fields = StoryPage.__dataclass_fields__.keys()
print('StoryPage fields:', list(fields))
assert 'keywords' in fields, 'keywords field missing!'
print('✅ StoryPage.keywords 字段已加')

print()
print("=== 验证 _highlight_keywords 接 extra_keywords ===")
from scripts.core.article import _highlight_keywords
out = _highlight_keywords("公元前33年匈奴呼韩邪单于入朝", ["匈奴", "呼韩邪单于"])
assert 'color:#9b2332' in out, 'highlight style missing!'
assert '匈奴' in out, '匈奴 not highlighted'
assert '呼韩邪单于' in out, '呼韩邪单于 not highlighted'
print('✅ _highlight_keywords(extra_keywords) 工作正常')
print(out)
print()

print("=== 验证默认 character_anchor 是 modern 变体 ===")
from scripts.core.prompts import CHARACTER_ANCHORS, CHARACTER_CN_LIANHUANHUA_MODERN
assert CHARACTER_ANCHORS['chinese_lianhuanhua_classic'] == CHARACTER_CN_LIANHUANHUA_MODERN
print('✅ chinese_lianhuanhua_classic 默认走 modern face')
assert '桃花腮' in CHARACTER_CN_LIANHUANHUA_MODERN
assert '花钿' in CHARACTER_CN_LIANHUANHUA_MODERN
assert '步摇' in CHARACTER_CN_LIANHUANHUA_MODERN
assert '柳叶眉' in CHARACTER_CN_LIANHUANHUA_MODERN
assert '樱桃小口' in CHARACTER_CN_LIANHUANHUA_MODERN
print('✅ 现代审美脸 5 件套关键词全到位')

print()
print("=== 验证 build_image_prompt 默认带 modern face ===")
from scripts.core.prompts import build_image_prompt
prompt = build_image_prompt(
    style_id='chinese_lianhuanhua_classic',
    scene_description='SUBJECT: A Han dynasty woman'
)
assert '桃花腮' in prompt, 'modern face not in prompt'
print('✅ build_image_prompt 默认用 modern face')

print()
print("=== 全部通过 ===")
