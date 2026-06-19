from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from bot.commands import export_commands_file
from bot.keyboards import get_survey_list_keyboard
from bot.states import TakeSurveyStates
from database import complete_response, create_response, get_active_surveys, get_questions, save_answer

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
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
async def cmd_help(message: Message):
    await message.answer(
        "Доступные команды:\n"
        "/start - Запустить бота\n"
        "/help - Помощь\n"
        "/create_survey - Создать анкету (для админов)\n"
        "/list_surveys - Список анкет (для админов)\n"
        "/setadmin - Инструкция по активации админ-панели\n"
        "/export_commands - Выгрузить commands.txt для BotFather"
    )


@router.message(Command("setadmin"))
async def cmd_setadmin(message: Message):
    await message.answer(
        "Для активации админ-панели выполните:\n"
        "1. Откройте @BotFather\n"
        "2. Выберите вашего бота\n"
        "3. Commands -> Edit Commands\n"
        "4. Скопируйте команды из файла commands.txt"
    )


@router.message(Command("export_commands"))
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
        await message.answer("Спасибо, ваши ответы сохранены")
        await complete_response(response_id=int(data["response_id"]))
        await state.clear()
        return

    question = questions[current_index]
    text = f"Вопрос {current_index + 1}/{len(questions)}:\n{question['question_text']}"

    if question.get("question_type") == "choice" and question.get("choices"):
        choices_str = ", ".join(question["choices"])
        text += f"\nВарианты: {choices_str}"

    await message.answer(text)


@router.callback_query(F.data.startswith("take_"))
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
    except Exception:
        await message.answer("Не удалось сохранить ответ. Попробуйте еще раз.")
        return

    await state.update_data(current_index=current_index + 1)
    await _send_current_question(message, state)
