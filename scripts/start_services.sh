#!/usr/bin/env bash
# Start the local services cc-router uses. Today that is only the Laya server.
# The port comes from config/ladder.json, so the server and route.py always agree.
set -euo pipefail

skill_dir=$(cd "$(dirname "$0")/.." && pwd)
default_config=$skill_dir/config/ladder.json
[ ! -f "$skill_dir/config/router.json" ] || default_config=$skill_dir/config/router.json
config=${CC_ROUTER_CONFIG:-$default_config}
log_dir=${XDG_STATE_HOME:-$HOME/.local/state}/cc-router
log=$log_dir/laya.log

#-----------------------------------------------------------
# Checks
#-----------------------------------------------------------
python3 -c 'import laya, fastapi, uvicorn' 2>/dev/null \
    || { echo 'Laya is not installed. Run: python3 -m pip install "laya[serve]"' >&2; exit 1; }

port=$(python3 - "$config" <<'EOF'
import sys, json
from urllib.parse import urlparse
config = json.load(open(sys.argv[1], encoding='utf-8'))
ports = {urlparse(url).port or 80 for url in [config['laya_url'], *config.get('laya_urls', {}).values()]}
if len(ports) > 1: sys.exit(f'laya_url and laya_urls in {sys.argv[1]} use different ports: {sorted(ports)}')
print(ports.pop())
EOF
)

auth=()
[ -n "${LAYA_API_KEY:-}" ] && auth=(-H "Authorization: Bearer $LAYA_API_KEY")
# ${auth[@]+...} keeps bash 3.2 (macOS) from failing on an empty array under set -u
health() { curl -s --max-time 2 ${auth[@]+"${auth[@]}"} "http://127.0.0.1:$port/health" || true; }

# --check only reports; the router asks the user before starting the model
if [ "${1:-}" = --check ]; then
    [[ $(health) == *'"loaded"'* ]] && { echo "Laya is running on port $port."; exit 0; }
    echo "Laya is not running on port $port." >&2
    exit 1
fi

# Laya's /health lists the loaded checkpoints
if [[ $(health) == *'"loaded"'* ]]; then
    echo "Laya is already running on port $port."
    exit 0
fi

# first port from $1 upward that nothing listens on; SO_REUSEADDR ignores TIME_WAIT, as uvicorn does
free=$(python3 - "$port" <<'EOF'
import sys, socket
for port in range(int(sys.argv[1]), 65536):
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(('127.0.0.1', port))
        except OSError:
            continue
        print(port)
        break
else:
    sys.exit('No free port found')
EOF
)

# another service owns the port: offer the next free one and save it so route.py follows
if [ "$free" != "$port" ]; then
    echo "Port $port is already used by another service." >&2
    printf 'Use port %s? [y/N] ' "$free" >&2
    read -r reply || reply=
    [ -t 0 ] || echo >&2
    if [[ ! $reply =~ ^[YySs] ]]; then
        echo "Not started. Answer y, or set a free port in laya_url and laya_urls in $config." >&2
        exit 1
    fi
    python3 - "$config" "$free" <<'EOF'
import sys, json
from pathlib import Path
from urllib.parse import urlparse
path, port = Path(sys.argv[1]), sys.argv[2]
text = path.read_text(encoding='utf-8')
config = json.loads(text)
# replace the URL strings in place, so the file keeps its layout
for url in {config['laya_url'], *config.get('laya_urls', {}).values()}:
    parts = urlparse(url)
    text = text.replace(f'"{url}"', f'"{parts._replace(netloc=f"{parts.hostname}:{port}").geturl()}"')
from datetime import datetime, timezone
backup = path.with_name(path.name + '.' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f') + '.bak')
backup.write_bytes(path.read_bytes())
path.write_text(text, encoding='utf-8')
EOF
    port=$free
    echo "Saved port $port in $config."
fi

#-----------------------------------------------------------
# Laya
#-----------------------------------------------------------
mkdir -p "$log_dir"
LAYA_PORT=$port nohup python3 "$skill_dir/scripts/serve_laya.py" >"$log" 2>&1 &
pid=$!
echo "Starting Laya on port $port (PID $pid, log: $log). The first run downloads the checkpoint."

# the server listens only after the checkpoint is loaded
for _ in $(seq 600); do
    if [[ $(health) == *'"loaded"'* ]]; then
        echo "Laya is ready at http://127.0.0.1:$port/v1/systemone. Stop it with: kill $pid"
        exit 0
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
        echo "Laya exited during startup. Last lines of $log:" >&2
        tail -n 20 "$log" >&2
        exit 1
    fi
    sleep 1
done
echo "Laya is still loading after 10 minutes; it keeps running in the background. Follow $log." >&2
