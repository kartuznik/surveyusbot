#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/opt/bots/SurveyBot"
ENV_FILE="${PROJECT_DIR}/.env"
SERVICE_NAME="surveybot"
HOSTNAME_VALUE="$(hostname)"
TIMESTAMP="$(date -u +"%Y-%m-%d %H:%M:%S UTC")"

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
fi

send_telegram_alert() {
  local text="$1"
  local ids_raw="${ADMIN_IDS:-}"
  local token="${BOT_TOKEN:-}"

  if [[ -z "${token}" || -z "${ids_raw}" ]]; then
    return 0
  fi

  ids_raw="${ids_raw// /}"
  IFS=',' read -r -a ids_array <<< "${ids_raw}"
  for admin_id in "${ids_array[@]}"; do
    [[ -z "${admin_id}" ]] && continue
    curl -sS -X POST "https://api.telegram.org/bot${token}/sendMessage" \
      -d "chat_id=${admin_id}" \
      --data-urlencode "text=${text}" >/dev/null || true
  done
}

if systemctl is-active --quiet "${SERVICE_NAME}"; then
  exit 0
fi

systemctl restart "${SERVICE_NAME}"
ALERT_TEXT="WARNING: ${SERVICE_NAME} was down on ${HOSTNAME_VALUE} at ${TIMESTAMP}. Restart command executed."
send_telegram_alert "${ALERT_TEXT}"
