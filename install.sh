#!/usr/bin/env bash
# install.sh — knowledge-comic skill 一键安装到本地 MiniMax Code (macOS / Linux)
#
# 用法（在新设备上）:
#   curl -fsSL https://raw.githubusercontent.com/54ersuige/knowledge-comic_Skill/main/install.sh | bash
#
# 或手动:
#   wget -O install.sh https://raw.githubusercontent.com/54ersuige/knowledge-comic_Skill/main/install.sh
#   chmod +x install.sh && ./install.sh

set -e

REPO_URL="https://github.com/54ersuige/knowledge-comic_Skill.git"
TARGET_DIR="$HOME/.minimax/skills/knowledge-comic"

echo -e "\033[0;36m[install] knowledge-comic skill installer\033[0m"
echo ""

# 1. 备份 + 清理旧版
if [ -d "$TARGET_DIR" ]; then
    echo -e "\033[0;33m[install] existing dir found: $TARGET_DIR\033[0m"
    backup_dir="${TARGET_DIR}.backup-$(date +%Y%m%d-%H%M%S)"
    echo -e "\033[0;33m[install] backing up to: $backup_dir\033[0m"
    mv "$TARGET_DIR" "$backup_dir"
fi

# 2. 克隆
echo -e "\033[0;36m[install] cloning from $REPO_URL\033[0m"
mkdir -p "$(dirname "$TARGET_DIR")"
git clone "$REPO_URL" "$TARGET_DIR"

# 3. 装依赖
echo -e "\033[0;36m[install] installing python deps via pip\033[0m"
python3 -m pip install -r "$TARGET_DIR/requirements.txt" || echo -e "\033[0;33m[install] pip install failed (continue anyway)\033[0m"

# 4. 配 .env
ENV_FILE="$TARGET_DIR/.env"
ENV_EXAMPLE="$TARGET_DIR/.env.example"
if [ ! -f "$ENV_FILE" ]; then
    if [ -f "$ENV_EXAMPLE" ]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        echo -e "\033[0;32m[install] copied .env.example → .env\033[0m"
        echo -e "\033[0;33m[install] ⚠️  请编辑 $ENV_FILE 填入你的凭证:\033[0m"
        echo -e "\033[0;33m          - AGNES_API_KEY\033[0m"
        echo -e "\033[0;33m          - LLM_API_KEY\033[0m"
        echo -e "\033[0;33m          - WECHAT_APPID + WECHAT_APPSECRET\033[0m"
        echo ""
        echo -e "\033[0;33m[install] 公众号 IP 白名单: 把本机公网 IP 加到\033[0m"
        echo -e "\033[0;33m          https://mp.weixin.qq.com → 设置与开发 → IP 白名单\033[0m"
        echo ""
        echo -e "\033[0;33m          本机公网 IP:\033[0m"
        PUBLIC_IP=$(curl -s https://api.ipify.org || echo "(无法自动获取)")
        echo -e "\033[0;37m          $PUBLIC_IP\033[0m"
    else
        echo -e "\033[0;33m[install] ⚠️  .env.example not found\033[0m"
    fi
else
    echo -e "\033[0;33m[install] .env 已存在, 跳过\033[0m"
fi

# 5. 自检
echo ""
echo -e "\033[0;36m[install] running smoke test...\033[0m"
python3 "$TARGET_DIR/guide.py" || true

# 6. 完成
echo ""
echo -e "\033[0;32m[install] ✅ knowledge-comic skill installed at $TARGET_DIR\033[0m"
echo ""
echo -e "\033[0;36m[install] 下一步:\033[0m"
echo -e "  1. 编辑 .env 填凭证: nano $ENV_FILE"
echo -e "  2. 公众号加 IP 白名单: https://mp.weixin.qq.com"
echo -e "  3. 重启 MiniMax Code (新 session 才能识别 skill)"
echo -e "  4. 在对话里: /knowledge-comic"