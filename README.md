# SurveyBot - Telegram бот для создания анкет

SurveyBot - многофункциональный Telegram-бот для опросов с веб-админкой, самодиагностикой и авто-лечением. Проект подходит для использования в командах, образовательных проектах и бизнес-опросах.

## Ключевые возможности

- Создание анкет и вопросов прямо в Telegram
- Поддержка текстовых и выборочных вопросов
- Веб-админка на Flask для просмотра ответов и экспорта CSV
- Система самодиагностики (`/health`) и авто-лечения
- Рассылка `/broadcast` с предпросмотром и подтверждением
- Статистика `/stats` и графики активности
- Контроль целостности SQLite и резервное копирование БД
- Автозапуск и восстановление через systemd
- Мультиязычный вывод состояния (`ru`/`en`)
- PDF/CSV экспорт из веб-админки и тёмная тема интерфейса

## Быстрый старт

```bash
git clone <your-repo-url> SurveyBot
cd SurveyBot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # если есть, иначе создайте .env вручную
```

Запуск вручную:

```bash
python -m bot.main
python web/app.py
```

Запуск через systemd:

```bash
systemctl daemon-reload
systemctl enable --now surveybot
systemctl enable --now surveybot-web
```

## Настройка `.env`

Обязательные переменные:

- `BOT_TOKEN` - токен Telegram-бота
- `ADMIN_IDS` - список Telegram ID администраторов через запятую
- `LANGUAGE` - язык интерфейса (`ru` или `en`)
- `FLASK_SECRET` - секрет Flask для сессий

Рекомендуемые:

- `DB_PATH` - путь к SQLite БД (по умолчанию `data/surveybot.db`)
- `ADMIN_WEB_PASSWORD` - пароль входа в веб-админку

## Команды бота

| Команда | Описание | Доступ |
|---|---|---|
| `/start` | Запустить бота | Все |
| `/help` | Справка по командам | Все |
| `/demo` | Демо-анкеты для покупателей | Все |
| `/create_survey` | Создать анкету | Owner, Admin |
| `/list_surveys` | Показать анкеты | Owner, Admin |
| `/health` | Состояние системы | Owner, Admin |
| `/stats` | Статистика | Owner, Admin |
| `/broadcast` | Рассылка | Owner, Admin |
| `/setadmin <user_id>` | Назначить администратора | Owner |
| `/removeadmin <user_id>` | Отозвать права администратора | Owner |
| `/admins` | Список owner/admin | Owner |
| `/transferowner <user_id>` | Передать роль владельца | Owner |
| `/setadmin` | Инструкция по BotFather | Все |
| `/export_commands` | Выгрузить `commands.txt` | Все |

## Система ролей

В боте используются 3 роли:

- `owner` - владелец системы, полный контроль прав
- `admin` - администратор, рабочие команды управления ботом
- `user` - обычный пользователь

Роли хранятся в таблице `roles` в SQLite (`user_id`, `role`, `granted_by`, `granted_at`).

### Примеры управления ролями

- Назначить администратора:
  - `/setadmin 123456789`
- Убрать администратора:
  - `/removeadmin 123456789`
- Посмотреть список:
  - `/admins`

Владелец может отозвать права у администратора в любой момент (например, если сотрудник уволен).

## Демо-режим

- Включается через `DEMO_MODE=true` в `.env`
- На старте бот создаёт демо-анкеты
- Команда `/demo` доступна всем пользователям
- Демо-анкеты не попадают в обычный список активных анкет для пользователей

## Веб-админка

- URL: `http://<server-ip>:5000/login`
- Логин: пароль из `ADMIN_WEB_PASSWORD`
- Возможности:
  - список анкет и количество ответов
  - просмотр ответов по анкете
  - экспорт ответов в CSV

## Система самодиагностики

- Команда `/health` показывает:
  - онлайн/офлайн статус бота
  - время последней проверки БД
  - свободное место на диске
  - аптайм и критические ошибки
- Фоновый монитор:
  - `check_bot_alive` каждые 30 секунд
  - `check_database` каждые 60 секунд
  - `check_resources` каждые 5 минут
- Авто-лечение:
  - переподключение сессии Telegram API
  - уведомления админам `WARNING`/`RECOVERED`
  - безопасный аварийный рестарт с checkpoint и pre-crash backup

## Архитектура проекта

```text
SurveyBot/
├── bot/
│   ├── handlers/
│   ├── commands.py
│   ├── health.py
│   ├── locales.py
│   └── main.py
├── web/
│   ├── app.py
│   └── templates/
├── data/
├── scripts/
├── config.py
├── database.py
└── README.md
```

## Деплой на VPS

Проект использует systemd-юниты:

- `surveybot.service` - Telegram-бот
- `surveybot-web.service` - Flask-админка
- `surveybot-check.timer` + `surveybot-check.service` - периодическая проверка и авто-рекавери

Проверка:

```bash
systemctl status surveybot
systemctl status surveybot-web
systemctl status surveybot-check.timer
```

## Мониторинг и диагностика

- Логи бота:
  - `journalctl -u surveybot -f`
- Логи веб-админки:
  - `journalctl -u surveybot-web -f`
- Логи health-монитора:
  - `bot_health.log`

## Устранение проблем

| Проблема | Возможная причина | Решение |
|---|---|---|
| Не видны команды при вводе `/` | Команды не перерегистрированы | `systemctl restart surveybot`, затем `journalctl -u surveybot -n 50` |
| Нет кнопки меню | Telegram-клиент не обновил UI | Написать боту `/start`, перезапустить клиент |
| Ошибка входа в веб-админку | Неверный `ADMIN_WEB_PASSWORD` | Проверить `.env`, перезапустить `surveybot-web` |
| Бот не стартует | Неверный `BOT_TOKEN` или повреждена БД | Проверить токен, посмотреть `journalctl`, проверить backup БД |
| Нет доступа к `/health` | Пользователь не в `ADMIN_IDS` | Добавить ID в `.env`, перезапустить сервис |

## Лицензия

MIT License.
