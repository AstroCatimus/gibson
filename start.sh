#!/bin/zsh
# Gibson — start backend + mobile dev server

ROOT="$(cd "$(dirname "$0")" && pwd)"

# ── Backend ──────────────────────────────────────────────────────
echo "\n🔧  Starting Gibson API..."
osascript -e "
  tell application \"Terminal\"
    do script \"cd '$ROOT' && source .venv/bin/activate && python3 -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000\"
  end tell
"

# ── Mobile ───────────────────────────────────────────────────────
echo "📱  Starting Expo..."
osascript -e "
  tell application \"Terminal\"
    do script \"cd '$ROOT/mobile' && npx expo start --clear\"
  end tell
"

echo "\n✅  Both servers launching in new Terminal windows."
