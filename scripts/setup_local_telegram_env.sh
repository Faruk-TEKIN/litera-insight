#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"

if [[ -z "${TELEGRAM_BOT_TOKEN:-}" ]]; then
  echo "TELEGRAM_BOT_TOKEN is required. Get it from @BotFather." >&2
  exit 1
fi

if [[ -z "${TELEGRAM_BOT_USERNAME:-}" ]]; then
  echo "TELEGRAM_BOT_USERNAME is required. Use the bot username without @." >&2
  exit 1
fi

if [[ -z "${NGROK_AUTHTOKEN:-}" ]]; then
  echo "NGROK_AUTHTOKEN is required. Get it from https://dashboard.ngrok.com/get-started/your-authtoken" >&2
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  cp .env.example "${ENV_FILE}"
fi

if [[ -z "${TELEGRAM_WEBHOOK_SECRET:-}" ]]; then
  TELEGRAM_WEBHOOK_SECRET="$(openssl rand -hex 32)"
fi

set_env_value() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" "${ENV_FILE}"; then
    python - "$ENV_FILE" "$key" "$value" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
lines = path.read_text().splitlines()
path.write_text("\n".join(f"{key}={value}" if line.startswith(f"{key}=") else line for line in lines) + "\n")
PY
  else
    printf '%s=%s\n' "${key}" "${value}" >> "${ENV_FILE}"
  fi
}

set_env_value TELEGRAM_BOT_TOKEN "${TELEGRAM_BOT_TOKEN}"
set_env_value TELEGRAM_BOT_USERNAME "${TELEGRAM_BOT_USERNAME}"
set_env_value TELEGRAM_WEBHOOK_SECRET "${TELEGRAM_WEBHOOK_SECRET}"
set_env_value NGROK_AUTHTOKEN "${NGROK_AUTHTOKEN}"
set_env_value PUBLIC_APP_URL "${PUBLIC_APP_URL:-http://localhost:5173}"

echo "Telegram local env is ready in ${ENV_FILE}."
echo "TELEGRAM_BOT_USERNAME=${TELEGRAM_BOT_USERNAME}"
echo "TELEGRAM_WEBHOOK_SECRET=<generated-or-set>"
echo "NGROK_AUTHTOKEN=<set>"
