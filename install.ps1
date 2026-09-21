# install.ps1 — knowledge-comic skill 一键安装到本地 MiniMax Code
#
# 用法（在新设备上）:
#   1. 确保 git / python ≥3.10 / pip 都已装
#   2. PowerShell 里跑:
#      irm https://raw.githubusercontent.com/54ersuige/knowledge-comic_Skill/main/install.ps1 | iex
#
# 或手动:
#   iwr https://raw.githubusercontent.com/54ersuige/knowledge-comic_Skill/main/install.ps1 -OutFile install.ps1
#   .\install.ps1
#
# 装完后:
#   - SKILL 路径: $HOME\.minimax\skills\knowledge-comic
#   - 配置 .env: copy .env.example to .env + 填入凭证
#   - 公众号 IP 白名单: 把本机公网 IP 加到 mp.weixin.qq.com → IP 白名单

$ErrorActionPreference = 'Stop'
$REPO_URL = 'https://github.com/54ersuige/knowledge-comic_Skill.git'
$TARGET_DIR = Join-Path $HOME '.minimax\skills\knowledge-comic'

Write-Host "[install] knowledge-comic skill installer" -ForegroundColor Cyan
Write-Host ""

# 1. 备份 + 清理旧版（如果存在）
if (Test-Path $TARGET_DIR) {
    Write-Host "[install] existing dir found: $TARGET_DIR" -ForegroundColor Yellow
    $backupDir = "${TARGET_DIR}.backup-$(date +%Y%m%d-%H%M%S)"
    Write-Host "[install] backing up to: $backupDir" -ForegroundColor Yellow
    Move-Item -Path $TARGET_DIR -Destination $backupDir
}

# 2. 克隆
Write-Host "[install] cloning from $REPO_URL" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path (Split-Path $TARGET_DIR) | Out-Null
git clone $REPO_URL $TARGET_DIR
if ($LASTEXITCODE -ne 0) {
    Write-Host "[install] git clone failed" -ForegroundColor Red
    exit 1
}

# 3. 装依赖
Write-Host "[install] installing python deps via pip" -ForegroundColor Cyan
python -m pip install -r "$TARGET_DIR\requirements.txt"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[install] pip install failed (continue anyway — deps are optional)" -ForegroundColor Yellow
}

# 4. 配 .env
$envFile = Join-Path $TARGET_DIR '.env'
$envExample = Join-Path $TARGET_DIR '.env.example'
if (-not (Test-Path $envFile)) {
    if (Test-Path $envExample) {
        Copy-Item -Path $envExample -Destination $envFile
        Write-Host "[install] copied .env.example → .env" -ForegroundColor Green
        Write-Host "[install] ⚠️  请编辑 $envFile 填入你的凭证:" -ForegroundColor Yellow
        Write-Host "          - AGNES_API_KEY" -ForegroundColor Yellow
        Write-Host "          - LLM_API_KEY" -ForegroundColor Yellow
        Write-Host "          - WECHAT_APPID + WECHAT_APPSECRET" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "[install] 公众号 IP 白名单: 把本机公网 IP 加到" -ForegroundColor Yellow
        Write-Host "          https://mp.weixin.qq.com → 设置与开发 → IP 白名单" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "          本机公网 IP:" -ForegroundColor Yellow
        try {
            $ip = (Invoke-WebRequest -Uri 'https://api.ipify.org' -UseBasicParsing).Content.Trim()
            Write-Host "          $ip" -ForegroundColor White
        } catch {
            Write-Host "          (无法自动获取, 请手动访问 https://api.ipify.org)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "[install] ⚠️  .env.example not found, 请手动创建 .env" -ForegroundColor Yellow
    }
} else {
    Write-Host "[install] .env 已存在, 跳过" -ForegroundColor Yellow
}

# 5. 自检
Write-Host ""
Write-Host "[install] running smoke test..." -ForegroundColor Cyan
$testResult = python "$TARGET_DIR\guide.py" -- 2>&1
Write-Host $testResult

# 6. 完成
Write-Host ""
Write-Host "[install] ✅ knowledge-comic skill installed at $TARGET_DIR" -ForegroundColor Green
Write-Host ""
Write-Host "[install] 下一步:" -ForegroundColor Cyan
Write-Host "  1. 编辑 .env 填凭证: notepad `"$envFile`"" -ForegroundColor White
Write-Host "  2. 公众号加 IP 白名单: https://mp.weixin.qq.com" -ForegroundColor White
Write-Host "  3. 重启 MiniMax Code (新 session 才能识别 skill)" -ForegroundColor White
Write-Host "  4. 在对话里: /knowledge-comic" -ForegroundColor White