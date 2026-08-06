# SurveyBot — Runbook

Операционное руководство для self-hosted деплоя. Секреты и публичные IP сюда не пишем — используйте `.env` и инфраструктуру окружения.

Деплой: **venv + systemd** (Docker Compose в репозитории нет). Веб-админка — порт **`:5000`**.

## Deploy (systemd)

1. Клонируйте репозиторий, создайте venv, установите `requirements.txt`.
2. Создайте `.env` с минимумом: `BOT_TOKEN`, `ADMIN_IDS`, `LANGUAGE`, `FLASK_SECRET`; рекомендуется `DB_PATH`, `ADMIN_WEB_PASSWORD`, при необходимости `DEMO_MODE`.
3. Убедитесь, что каталог для SQLite существует (родитель `DB_PATH`, обычно `data/`).
4. Установите/включите unit-ы:
   - `surveybot.service` — бот (`python -m bot.main`)
   - `surveybot-web.service` — Flask (`python web/app.py` или принятый ExecStart)
   - `surveybot-check.timer` + `surveybot-check.service` — периодическая проверка / авто-рекавери

```bash
systemctl daemon-reload
systemctl enable --now surveybot
systemctl enable --now surveybot-web
systemctl enable --now surveybot-check.timer
systemctl status surveybot
systemctl status surveybot-web
systemctl status surveybot-check.timer
```

Проверка:

- `/start` в Telegram; для админа — `/health`
- Админка: `http://<YOUR_HOST>:5000/login`

После docs-only изменений restart не нужен. После изменений кода:

```bash
systemctl restart surveybot
systemctl restart surveybot-web
```

Рекомендуется `Restart=` в unit бота, чтобы `sys.exit(1)` после неуспешного auto-heal поднимал процесс снова.

## Backup и restore (SQLite)

### Backup

```bash
systemctl stop surveybot surveybot-web
mkdir -p ./backups
cp -a data/surveybot.db ./backups/surveybot-$(date +%Y%m%d).db
# путь сверяйте с DB_PATH; при WAL при остановленных writers копируйте согласованно
systemctl start surveybot surveybot-web
```

Отдельно вне git храните `.env` и credentials интеграций (Sheets/webhook secrets).

Pre-crash backup при аварийном heal: файл вида `{DB_PATH}.pre_crash` (создаёт health-monitor).

### Restore

1. Остановить `surveybot` и `surveybot-web`.
2. Заменить файл БД из backup (или `.pre_crash` при необходимости).
3. Запустить сервисы.
4. Smoke: `/start`, `/health` (админ), вход в админку `:5000`.

## Ротация ключей

После любой ручной правки `.env`: `grep '^VAR=' .env` по каждой изменённой строке **до** restart (см. `/opt/standards/RULES.md` §4a).

| Секрет / параметр | Шаги |
|---|---|
| `BOT_TOKEN` | Новый токен в BotFather → `.env` → `systemctl restart surveybot` |
| `ADMIN_WEB_PASSWORD` / `FLASK_SECRET` | Обновить `.env` → restart `surveybot-web` |
| `ADMIN_IDS` / `OWNER_ID` | Обновить → restart `surveybot` |
| `WEBHOOK_SECRET` / Sheets credentials | Обновить по `instructions/` → restart бота при необходимости |

Секреты не вставлять в git, issues и чат.

## Инциденты

### Бот не отвечает

- `systemctl status surveybot`, `journalctl -u surveybot -f`, `bot_health.log`
- `/health` / `/diagnostics` от admin/owner
- Проверить `BOT_TOKEN`; дождаться auto-heal или restart unit

### Авто-лечение не помогло

- Health готовит checkpoint/backup и завершает процесс — systemd должен поднять сервис
- Проверить `Restart=` в unit и `surveybot-check.timer`

### Веб-админка

- `systemctl status surveybot-web`, порт `:5000`
- `ADMIN_WEB_PASSWORD` (не печатать в чат)
- При падении вебки опросы в Telegram продолжают работать

### Рассылки / интеграции

- 429 — встроенный backoff; dry-run: `/broadcast_dry`
- Sheets/CRM — см. `instructions/`; сбой интеграции не должен ронять весь бот

## Rollback

```bash
git log --oneline -5
git checkout <known-good-sha>
systemctl restart surveybot surveybot-web
```

При повреждении данных — restore SQLite из backup до smoke.
