#!/usr/bin/env bash
# =====================================================================
# Kissne 低保真原型 · 批量页面截图
# ---------------------------------------------------------------------
# 用法：bash tools/make-previews.sh
# 依赖：本机 Chrome（或 Edge），以及带 Pillow 的 Python
#
# 原理：用 ?shot=1 让手机框固定在视口左上角（390×844），
#       以 2 倍缩放截图后裁切左上角 780×1688，得到精确的页面截图。
#       之所以要这样绕：Windows 上 headless Chrome 会把窗口宽度钳到
#       约 500px，直接按 390 宽截图会截到「500px 布局的左半部分」。
# =====================================================================
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"          # Git Bash 风格：/c/Users/...
OUT="$ROOT/previews"
# 临时文件（原始截图 / Chrome profile）放在**交付目录之外**，
# 这样即使清理失败也不会污染 previews/。这个临时区可以随时手动删。
TMP="$ROOT/../.workbuddy/tmp/ks-previews"
RAW="$TMP/raw"
# 每次跑用独立的 Chrome profile：残留/并发的 Chrome 会抢默认 profile 的单例锁，
# 导致截图调用**永久挂住**（不报错、不退出）。
PROF="$TMP/prof"

# Chrome 能认 Git Bash 风格路径，Windows 版 Python 不能，所以两套都备着
win () { cygpath -w "$1" 2>/dev/null || echo "$1"; }
OUT_W="$(win "$OUT")"
RAW_W="$(win "$RAW")"
PY="${PY:-C:/Users/lenovo/.workbuddy/binaries/python/envs/default/Scripts/python.exe}"
CHROME="${CHROME:-/c/Program Files/Google/Chrome/Application/chrome.exe}"
[ -f "$CHROME" ] || CHROME="/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"

mkdir -p "$OUT" "$RAW" "$PROF"
# 只按名字覆盖上一轮的原始截图，不做批量删除（避免触发批量删除护栏）
rm -f "$RAW"/*.png

# 页面名 | 路由
ROUTES=(
  "01_splash_logo|#/welcome?state=intro"
  "01_splash_characters|#/welcome?state=final"
  "02_connect_idle|#/connect"
  "02_connect_advanced|#/connect?state=advanced"
  "02_connect_incomplete|#/connect?state=incomplete"
  "02_connect_connecting|#/connect?state=connecting"
  "02_connect_success|#/connect?state=success"
  "02_connect_code-error|#/connect?state=code-error"
  "02_connect_key-error|#/connect?state=key-error"
  "02_connect_network-error|#/connect?state=network-error"
  "02_connect_device-unavailable|#/connect?state=device-unavailable"
  "03_connect_success|#/connect/success"
  "04_home_online|#/home"
  "04_home_offline|#/home?state=offline"
  "05_chat_empty|#/chat"
  "05_chat_sending|#/chat?state=sending"
  "05_chat_typing|#/chat?state=typing"
  "05_chat_thinking|#/chat?state=thinking"
  "05_chat_replying|#/chat?state=replying"
  "05_chat_failed|#/chat?state=failed"
  "05_chat_device-offline|#/chat?state=device-offline"
  "05_chat_network-lost|#/chat?state=network-lost"
  "06_universe_both-online|#/universe"
  "06_universe_earth-online|#/universe?state=earth-online"
  "06_universe_ai-connecting|#/universe?state=ai-connecting"
  "06_universe_unlit|#/universe?state=unlit"
  "06_universe_abnormal|#/universe?state=abnormal"
  "07_memory_list|#/memory"
  "07_memory_empty|#/memory?state=empty"
  "07_memory_syncing|#/memory?state=syncing"
  "07_memory_sync-ok|#/memory?state=sync-ok"
  "07_memory_sync-fail|#/memory?state=sync-fail"
  "07_memory_detail|#/memory?state=detail"
  "07_memory_edit|#/memory?state=edit"
  "07_memory_delete-confirm|#/memory?state=delete-confirm"
  "08_device_normal|#/device"
  "08_device_offline|#/device?state=offline"
  "08_device_reconnecting|#/device?state=reconnecting"
  "08_device_disconnect-confirm|#/device?state=disconnect-confirm"
  "09_settings|#/settings"
  "10_notifications|#/notifications"
  "11_assets|#/assets"
)

for item in "${ROUTES[@]}"; do
  name="${item%%|*}"; route="${item#*|}"
  timeout 60 "$CHROME" --headless=new --disable-gpu --hide-scrollbars --no-sandbox \
    --user-data-dir="$(win "$PROF")" \
    --force-device-scale-factor=2 --window-size=520,900 --virtual-time-budget=2500 \
    --screenshot="$(win "$RAW")/$name.png" \
    "file:///$(cygpath -m "$ROOT")/index.html?shot=1$route" >/dev/null 2>&1
  echo "  shot $name"
done

# 全部页面总览（宽屏，带侧栏）
timeout 90 "$CHROME" --headless=new --disable-gpu --hide-scrollbars --no-sandbox \
  --user-data-dir="$(win "$PROF")" \
  --window-size=1620,1620 --virtual-time-budget=5000 \
  --screenshot="$(win "$OUT")/00_overview.png" \
  "file:///$(cygpath -m "$ROOT")/index.html#/overview" >/dev/null 2>&1
echo "  shot 00_overview"

# 裁切
"$PY" - "$RAW_W" "$OUT_W" <<'PYEOF'
import glob, os, sys
from PIL import Image
raw, out = sys.argv[1], sys.argv[2]
n = 0
for p in sorted(glob.glob(os.path.join(raw, '*.png'))):
    Image.open(p).convert('RGB').crop((0, 0, 780, 1688)).save(
        os.path.join(out, os.path.basename(p)), optimize=True)
    n += 1
print(f'cropped {n} screenshots -> {out}')
PYEOF
