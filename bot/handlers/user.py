from datetime import UTC, datetime
from typing import Any
import logging
from functools import wraps

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.commands import export_commands_file
from bot.diagnostics.error_tracker import get_error_tracker
from bot.integrations.webhook import send_webhook
from bot.keyboards import get_survey_list_keyboard
from bot.roles import get_role_manager_instance
from bot.states import TakeSurveyStates
from config import get_settings
from database import (
    complete_response,
    create_response,
    get_active_surveys,
    get_questions,
    get_response_notification_payload,
    get_survey_title,
    save_answer,
)

router = Router()
logger = logging.getLogger("surveybot.handlers.user")


def safe_user_handler(fn):
    @wraps(fn)
    async def wrapper(event, *args, **kwargs):
        try:
            return await fn(event, *args, **kwargs)
        except Exception as error:
            logger.exception("User handler error in %s: %s", fn.__name__, error)
            get_error_tracker().add_error("user_handler", str(error), "")
            if isinstance(event, Message):
                await event.answer("Внутренняя ошибка. Попробуйте позже.")
            elif isinstance(event, CallbackQuery):
                await event.answer("Внутренняя ошибка", show_alert=True)
            return None

    return wrapper


@router.message(CommandStart())
@safe_user_handler
async def cmd_start(message: Message):
    send_webhook(
        "user_started",
        {
            "user_id": message.from_user.id if message.from_user else None,
            "username": message.from_user.username if message.from_user else None,
        },
    )
    try:
        surveys = await get_active_surveys()
    except Exception:
        await message.answer("Не удалось загрузить анкеты. Попробуйте чуть позже.")
        return

    if not surveys:
        await message.answer("Сейчас нет активных анкет.")
        return

    await message.answer(
        "Привет! Выберите анкету для прохождения:",
        reply_markup=get_survey_list_keyboard(surveys),
    )


@router.message(Command("help"))
@safe_user_handler
async def cmd_help(message: Message):
    await message.answer(
        "Доступные команды:\n"
        "/start - Запустить бота\n"
        "/help - Помощь\n"
        "/demo - Демо-анкеты для ознакомления\n"
        "/create_survey - Создать анкету (owner/admin)\n"
        "/list_surveys - Список анкет (owner/admin)\n"
        "/health - Состояние системы (owner/admin)\n"
        "/diagnostics - Диагностика стабильности (owner/admin)\n"
        "/export_commands - Выгрузить commands.txt для BotFather"
    )


@router.message(Command("export_commands"))
@safe_user_handler
async def cmd_export_commands(message: Message):
    file_path = export_commands_file("commands.txt")
    await message.answer_document(
        document=FSInputFile(str(file_path)),
        caption="Сгенерирован файл commands.txt для BotFather",
    )


async def _send_current_question(message: Message, state: FSMContext) -> None:
    """Отправляет пользователю текущий вопрос из состояния FSM."""

    data = await state.get_data()
    questions: list[dict[str, Any]] = data.get("questions", [])
    current_index: int = data.get("current_index", 0)

    if current_index >= len(questions):
        if data.get("demo_mode"):
            await message.answer(
                "✅ Демо завершено! Для покупки полной версии свяжитесь с нами: @your_username"
            )
        else:
            await message.answer("Спасибо, ваши ответы сохранены")
        response_id = int(data["response_id"])
        await complete_response(response_id=response_id)
        if not data.get("demo_mode"):
            await _notify_admins_about_response(
                message=message,
                survey_id=int(data.get("survey_id", 0)),
                response_id=response_id,
                questions_count=len(questions),
            )
        await state.clear()
        return

    question = questions[current_index]
    text = f"Вопрос {current_index + 1}/{len(questions)}:\n{question['question_text']}"

    if question.get("question_type") == "choice" and question.get("choices"):
        choices_str = ", ".join(question["choices"])
        text += f"\nВарианты: {choices_str}"

    await message.answer(text)


@router.callback_query(F.data.startswith("take_"))
@safe_user_handler
async def take_survey(callback: CallbackQuery, state: FSMContext):
    if callback.message is None or callback.from_user is None:
        await callback.answer("Не удалось начать анкету.")
        return

    survey_id_str = callback.data.replace("take_", "", 1)
    if not survey_id_str.isdigit():
        await callback.answer("Некорректный идентификатор анкеты.", show_alert=True)
        return

    survey_id = int(survey_id_str)
    try:
        questions = await get_questions(survey_id=survey_id)
        if not questions:
            await callback.answer("В анкете пока нет вопросов.", show_alert=True)
            return

        response_id = await create_response(
            survey_id=survey_id,
            user_id=callback.from_user.id,
        )
    except Exception:
        await callback.answer("Ошибка БД. Попробуйте позже.", show_alert=True)
        return

    await state.update_data(
        survey_id=survey_id,
        response_id=response_id,
        questions=questions,
        current_index=0,
    )
    await state.set_state(TakeSurveyStates.answering)
    await callback.answer()
    await _send_current_question(callback.message, state)


@router.message(TakeSurveyStates.answering)
@safe_user_handler
async def process_answer(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Пожалуйста, отправьте ответ текстовым сообщением.")
        return

    data = await state.get_data()
    questions: list[dict[str, Any]] = data.get("questions", [])
    current_index: int = data.get("current_index", 0)
    response_id = data.get("response_id")

    if response_id is None or current_index >= len(questions):
        await message.answer("Сессия анкеты не найдена. Запустите /start заново.")
        await state.clear()
        return

    current_question = questions[current_index]
    try:
        await save_answer(
            response_id=int(response_id),
            question_id=int(current_question["id"]),
            answer_text=message.text.strip(),
        )
        send_webhook(
            "new_response",
            {
                "response_id": int(response_id),
                "survey_id": int(data.get("survey_id", 0)),
                "user_id": message.from_user.id if message.from_user else None,
                "question_id": int(current_question["id"]),
                "answer_text": message.text.strip(),
            },
        )
    except Exception:
        await message.answer("Не удалось сохранить ответ. Попробуйте еще раз.")
        return

    await state.update_data(current_index=current_index + 1)
    await _send_current_question(message, state)


async def _notify_admins_about_response(
    message: Message,
    survey_id: int,
    response_id: int,
    questions_count: int,
) -> None:
    settings = get_settings()
    if not settings.NOTIFY_ON_RESPONSE:
        return

    role_manager = get_role_manager_instance()
    if role_manager is None:
        return

    payload = await get_response_notification_payload(response_id)
    survey_title = payload.get("survey_title") or await get_survey_title(survey_id)
    telegram_user_id = payload.get("telegram_id") or (message.from_user.id if message.from_user else "unknown")
    completed_at = payload.get("completed_at") or datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
    answers_count = int(payload.get("answers_count") or 0)
    total_questions = int(payload.get("questions_count") or questions_count)

    started_raw = payload.get("started_at")
    completed_raw = payload.get("completed_at")
    duration_minutes = 0
    try:
        if started_raw and completed_raw:
            started_dt = datetime.fromisoformat(str(started_raw).replace("Z", ""))
            completed_dt = datetime.fromisoformat(str(completed_raw).replace("Z", ""))
            duration_minutes = max(int((completed_dt - started_dt).total_seconds() // 60), 0)
    except Exception:
        duration_minutes = 0

    text = (
        "Новый ответ на анкету!\n\n"
        f"📋 Анкета: {survey_title}\n"
        f"👤 Пользователь: {telegram_user_id}\n"
        f"🕐 Время: {completed_at}\n"
        f"⏱️ Длительность: {duration_minutes} мин\n"
        f"✅ Ответов: {answers_count} из {total_questions}"
    )
    link = f"{settings.WEB_ADMIN_BASE_URL.rstrip('/')}/survey/{survey_id}"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔗 Просмотреть в админке", url=link)]]
    )

    admin_ids = await role_manager.get_all_admins()
    for admin_id in admin_ids:
        try:
            await message.bot.send_message(chat_id=admin_id, text=text, reply_markup=keyboard)
        except Exception:
            continue
