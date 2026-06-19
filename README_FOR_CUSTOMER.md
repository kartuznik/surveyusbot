# SurveyBot - Customer Guide / Руководство для клиента

## RU: Быстрый старт

### Новые возможности v1.1.0
- Dry-run режим для рассылки `/broadcast_dry`
- Авто backoff при rate-limit Telegram
- Экспорт в Google Sheets
- Webhook интеграция с CRM
- Экспорт статистики в PDF
- Страница `/about`
- Мониторинг стабильности `/diagnostics`

### 1) Установка
- Клонируйте проект в `/opt/bots/SurveyBot`
- Создайте и активируйте виртуальное окружение
- Установите зависимости: `pip install -r requirements.txt`
- Запустите сервисы:
  - `systemctl enable --now surveybot`
  - `systemctl enable --now surveybot-web`

### 2) Настройка `.env`
Минимальные переменные:
- `BOT_TOKEN` - токен Telegram-бота
- `ADMIN_IDS` - список ID админов через запятую (пример: `12345,67890`)
- `LANGUAGE` - язык интерфейса (`ru` или `en`)
- `OWNER_ID` - Telegram ID владельца (опционально, иначе первый из `ADMIN_IDS`)

Дополнительно:
- `DB_PATH` - путь к БД (по умолчанию `data/surveybot.db`)
- `ADMIN_WEB_PASSWORD` - пароль веб-админки
- `FLASK_SECRET` - секрет Flask
- `DEMO_MODE` - включение демо-анкет (`true/false`)
- `NOTIFY_ON_RESPONSE` - уведомлять админов о новых ответах
- `BROADCAST_DELAY` - базовая задержка в рассылке (например, `0.5`)
- `WEBHOOK_ENABLED`, `WEBHOOK_URL`, `WEBHOOK_SECRET` - интеграция с CRM
- `GOOGLE_SHEETS_ENABLED`, `GOOGLE_SHEETS_CREDENTIALS`, `GOOGLE_SHEETS_SPREADSHEET_ID` - экспорт в Google Sheets

### 3) Активация админ-панели
Вариант A: через BotFather
1. Откройте `@BotFather`
2. Выберите бота
3. `Commands -> Edit Commands`
4. Вставьте команды из `commands.txt`

Вариант B: через команду бота
1. В боте выполните `/export_commands`
2. Получите файл `commands.txt`
3. Скопируйте команды в BotFather

Кнопка меню слева от поля ввода появится автоматически после первого запуска.
Если не появилась — напишите боту `/start`.

### 4) Основные команды
- `/start` - запустить бота
- `/help` - справка
- `/create_survey` - создать анкету (owner/admin)
- `/list_surveys` - список анкет (owner/admin)
- `/health` - состояние системы (owner/admin)
- `/setadmin <user_id>` - назначить админа (owner)
- `/removeadmin <user_id>` - убрать админа (owner)
- `/admins` - список админов (owner)
- `/transferowner <user_id>` - передать права владельца (owner)
- `/setadmin` - инструкция по настройке команд
- `/export_commands` - выгрузка команд для BotFather

### 4.1) Система ролей
- `owner` - владелец бота, управляет правами
- `admin` - администратор с расширенными командами
- `user` - обычный пользователь

Владелец может в любой момент отозвать права у администратора (например, если сотрудник уволен):
- `/removeadmin 123456789`

### 4.2) Рассылка и dry-run
- `/broadcast` - реальная рассылка
- `/broadcast_dry` - проверка без отправки (покажет кому ушла бы рассылка)
- При лимитах Telegram бот автоматически делает backoff

### 4.3) Статистика и отчёты
- `/stats` - сводная статистика + графики
- В веб-админке доступны:
  - экспорт ответов CSV/PDF
  - экспорт статистики в PDF
  - экспорт в Google Sheets (если включено)

### 5) Как добавить вопросы в анкету
1. Выполните `/create_survey`
2. Укажите название и описание
3. Добавьте вопросы:
   - текстовые
   - с вариантами ответа (через запятую)
4. Для завершения отправьте `Готово` или `/done`

### 6) Демо-режим
- Включите `DEMO_MODE=true` в `.env`
- После перезапуска создадутся демо-анкеты
- Пользователь может пройти их через `/demo`
- После завершения показывается промо-сообщение для покупки полной версии

### 7) Интеграции
- CRM Webhook: см. `instructions/WEBHOOK_SETUP.md`
- Google Sheets: см. `instructions/GOOGLE_SHEETS_SETUP.md`

### 8) Мониторинг и диагностика
- Команда `/health` — базовое состояние
- Команда `/diagnostics` — расширенная диагностика (ошибки, память, БД)
- Логи:
  - `bot_health.log`
  - `error_log.json`
  - `journalctl -u surveybot -f`

---

## EN: Quick start

### New in v1.1.0
- Dry-run broadcast mode (`/broadcast_dry`)
- Automatic Telegram rate-limit backoff
- Google Sheets export
- CRM webhook integration
- Statistics PDF export
- Public `/about` page
- Stability diagnostics with `/diagnostics`

### 1) Installation
- Clone/copy project to `/opt/bots/SurveyBot`
- Create and activate a virtual environment
- Install dependencies: `pip install -r requirements.txt`
- Start services:
  - `systemctl enable --now surveybot`
  - `systemctl enable --now surveybot-web`

### 2) Configure `.env`
Required variables:
- `BOT_TOKEN` - Telegram bot token
- `ADMIN_IDS` - comma-separated admin IDs (example: `12345,67890`)
- `LANGUAGE` - interface language (`ru` or `en`)
- `OWNER_ID` - owner Telegram ID (optional, else first from `ADMIN_IDS`)

Optional:
- `DB_PATH` - database path (default `data/surveybot.db`)
- `ADMIN_WEB_PASSWORD` - web admin password
- `FLASK_SECRET` - Flask secret key
- `DEMO_MODE` - enable demo surveys (`true/false`)
- `NOTIFY_ON_RESPONSE` - notify admins about new responses

### 3) Enable admin panel
Option A: via BotFather
1. Open `@BotFather`
2. Select your bot
3. `Commands -> Edit Commands`
4. Paste commands from `commands.txt`

Option B: via bot command
1. Run `/export_commands` in bot chat
2. Receive `commands.txt`
3. Copy commands to BotFather

The menu button left of the input field appears automatically after first startup.
If it does not appear, send `/start` to the bot.

### 4) Main commands
- `/start` - start bot
- `/help` - help
- `/create_survey` - create survey (owner/admin)
- `/list_surveys` - list surveys (owner/admin)
- `/health` - system health (owner/admin)
- `/setadmin <user_id>` - grant admin role (owner)
- `/removeadmin <user_id>` - revoke admin role (owner)
- `/admins` - list admins (owner)
- `/transferowner <user_id>` - transfer owner role (owner)
- `/setadmin` - setup instructions
- `/export_commands` - export commands for BotFather

### 4.1) Role system
- `owner` - full control over role management
- `admin` - operational admin commands
- `user` - regular user

Owner can revoke admin rights at any time (for example, when staff changes):
- `/removeadmin 123456789`

### 5) How to add survey questions
1. Run `/create_survey`
2. Enter title and description
3. Add questions:
   - free-text
   - choice questions (comma-separated options)
4. Finish with `Готово` or `/done`

### 6) Demo mode
- Set `DEMO_MODE=true` in `.env`
- Restart bot to auto-create demo surveys
- Users can open demo flow with `/demo`
- After completion, bot shows a contact message for full version purchase
