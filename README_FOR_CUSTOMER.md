# SurveyBot - Customer Guide / Руководство для клиента

## RU: Быстрый старт

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

Дополнительно:
- `DB_PATH` - путь к БД (по умолчанию `data/surveybot.db`)
- `ADMIN_WEB_PASSWORD` - пароль веб-админки
- `FLASK_SECRET` - секрет Flask

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
- `/create_survey` - создать анкету
- `/list_surveys` - список анкет
- `/health` - состояние системы (админ)
- `/setadmin` - инструкция по настройке команд
- `/export_commands` - выгрузка команд для BotFather

### 5) Как добавить вопросы в анкету
1. Выполните `/create_survey`
2. Укажите название и описание
3. Добавьте вопросы:
   - текстовые
   - с вариантами ответа (через запятую)
4. Для завершения отправьте `Готово` или `/done`

---

## EN: Quick start

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

Optional:
- `DB_PATH` - database path (default `data/surveybot.db`)
- `ADMIN_WEB_PASSWORD` - web admin password
- `FLASK_SECRET` - Flask secret key

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
- `/create_survey` - create survey
- `/list_surveys` - list surveys
- `/health` - system health (admin)
- `/setadmin` - setup instructions
- `/export_commands` - export commands for BotFather

### 5) How to add survey questions
1. Run `/create_survey`
2. Enter title and description
3. Add questions:
   - free-text
   - choice questions (comma-separated options)
4. Finish with `Готово` or `/done`
