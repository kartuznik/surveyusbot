from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards import get_question_type_keyboard
from bot.states import CreateSurveyStates
from database import add_question, create_survey, get_active_surveys

router = Router()


@router.message(Command("create_survey"))
async def cmd_create_survey(message: Message, state: FSMContext):
    await message.answer("Введите название анкеты:")
    await state.set_state(CreateSurveyStates.title)


@router.message(CreateSurveyStates.title)
async def process_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("Введите описание анкеты:")
    await state.set_state(CreateSurveyStates.description)


@router.message(CreateSurveyStates.description)
async def process_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await state.update_data(questions=[])
    await message.answer(
        "Введите текст первого вопроса.\n"
        "Когда вопросы закончатся, отправьте 'Готово' или команду /done."
    )
    await state.set_state(CreateSurveyStates.question_text)


@router.message(CreateSurveyStates.question_text, Command("done"))
@router.message(CreateSurveyStates.question_text, F.text.casefold() == "готово")
async def finish_survey_creation(message: Message, state: FSMContext):
    data = await state.get_data()
    title = data.get("title")
    description = data.get("description")
    questions: list[dict[str, Any]] = data.get("questions", [])

    if not title:
        await message.answer("Не найдено название анкеты. Начните заново: /create_survey")
        await state.clear()
        return

    if not questions:
        await message.answer("Добавьте хотя бы один вопрос перед завершением.")
        return

    try:
        survey_id = await create_survey(title=title, description=description)
        for question in questions:
            await add_question(
                survey_id=survey_id,
                text=question["text"],
                q_type=question["type"],
                choices=question.get("choices"),
            )
    except Exception:
        await message.answer("Ошибка при сохранении анкеты. Попробуйте снова чуть позже.")
        return

    await state.clear()
    await message.answer("Анкета успешно создана и сохранена")


@router.message(CreateSurveyStates.question_text)
async def process_question_text(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Введите текст вопроса обычным текстовым сообщением.")
        return

    await state.update_data(current_question_text=message.text.strip())
    await message.answer(
        "Выберите тип вопроса:",
        reply_markup=get_question_type_keyboard(),
    )
    await state.set_state(CreateSurveyStates.question_type)


@router.callback_query(
    CreateSurveyStates.question_type,
    F.data.in_({"type_text", "type_choice"}),
)
async def process_question_type(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    data = await state.get_data()
    question_text = data.get("current_question_text")
    if not question_text:
        await callback.message.answer("Не удалось определить текст вопроса. Повторите шаг.")
        await state.set_state(CreateSurveyStates.question_text)
        return

    if callback.data == "type_text":
        questions = data.get("questions", [])
        questions.append(
            {
                "text": question_text,
                "type": "text",
                "choices": None,
            }
        )
        await state.update_data(questions=questions, current_question_text=None)
        await callback.message.answer(
            "Вопрос добавлен. Отправьте текст следующего вопроса "
            "или напишите 'Готово' (/done), чтобы завершить."
        )
        await state.set_state(CreateSurveyStates.question_text)
        return

    await callback.message.answer("Введите варианты ответа через запятую:")
    await state.set_state(CreateSurveyStates.choices)


@router.message(CreateSurveyStates.choices)
async def process_question_choices(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Введите варианты ответа текстом через запятую.")
        return

    choices = [item.strip() for item in message.text.split(",") if item.strip()]
    if len(choices) < 2:
        await message.answer("Нужно минимум 2 варианта. Повторите ввод.")
        return

    data = await state.get_data()
    question_text = data.get("current_question_text")
    if not question_text:
        await message.answer("Не удалось определить вопрос. Добавьте его заново.")
        await state.set_state(CreateSurveyStates.question_text)
        return

    questions = data.get("questions", [])
    questions.append(
        {
            "text": question_text,
            "type": "choice",
            "choices": choices,
        }
    )
    await state.update_data(questions=questions, current_question_text=None)
    await message.answer(
        "Вопрос с вариантами добавлен. Отправьте следующий вопрос "
        "или напишите 'Готово' (/done)."
    )
    await state.set_state(CreateSurveyStates.question_text)


@router.message(Command("list_surveys"))
async def cmd_list_surveys(message: Message):
    try:
        surveys = await get_active_surveys(include_demo=True)
    except Exception:
        await message.answer("Не удалось получить список анкет. Попробуйте позже.")
        return

    if not surveys:
        await message.answer("Активных анкет пока нет.")
        return

    lines = ["Список активных анкет:"]
    for survey in surveys:
        lines.append(f"- #{survey['id']}: {survey['title']}")
    await message.answer("\n".join(lines))
