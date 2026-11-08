#!/usr/bin/env bash
# Keep this computer on the Key Ring: awake, bridge running, tunnel reachable.
# When the quick tunnel's URL changes, update SWC_MACHINES on Vercel and redeploy.
# Usage: machine/keep_alive.sh   (from the repo root, with .env holding SWC_MACHINE_KEY)
set -u
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a

DEFAULT_LABEL="Anton's Mac, Codex on ChatGPT plan"
LABEL="${SWC_MACHINE_LABEL:-$DEFAULT_LABEL}"
STATE=/tmp/swc-machine
mkdir -p "$STATE"
caffeinate -dims -w $$ &

start_bridge() {
  nohup .venv/bin/python machine/codex_bridge.py >> "$STATE/bridge.log" 2>&1 &
  echo $! > "$STATE/bridge.pid"
  sleep 3
}

start_tunnel() {
  [ -f "$STATE/tunnel.pid" ] && kill "$(cat "$STATE/tunnel.pid")" 2>/dev/null
  : > "$STATE/tunnel.log"
  nohup cloudflared tunnel --url http://127.0.0.1:8790 >> "$STATE/tunnel.log" 2>&1 &
  echo $! > "$STATE/tunnel.pid"
  for _ in $(seq 30); do
    url=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$STATE/tunnel.log" | head -1)
    [ -n "$url" ] && break
    sleep 1
  done
  echo "$url" > "$STATE/url"
  value="$LABEL=$url/v1"
  vercel env rm SWC_MACHINES production --yes >/dev/null 2>&1
  printf '%s' "$value" | vercel env add SWC_MACHINES production >/dev/null 2>&1
  vercel deploy --prod --yes >> "$STATE/deploy.log" 2>&1
  echo "$(date) tunnel $url, Vercel updated" >> "$STATE/watchdog.log"
}

while true; do
  if ! lsof -t -iTCP:8790 -sTCP:LISTEN >/dev/null; then
    echo "$(date) bridge down, restarting" >> "$STATE/watchdog.log"
    start_bridge
  fi
  url=$(cat "$STATE/url" 2>/dev/null)
  code=$(curl -s -o /dev/null -m 15 -w '%{http_code}' "$url/v1/models")
  if [ "$code" != "200" ]; then
    sleep 20
    code=$(curl -s -o /dev/null -m 15 -w '%{http_code}' "$url/v1/models")
    if [ "$code" != "200" ]; then
      echo "$(date) tunnel check got $code, restarting tunnel" >> "$STATE/watchdog.log"
      start_tunnel
    fi
  fi
  sleep 60
done
