from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.states import TakeSurveyStates
from database import create_response, get_demo_surveys, get_questions

router = Router()


@router.message(Command("demo"))
async def cmd_demo(message: Message) -> None:
    surveys = await get_demo_surveys()
    if not surveys:
        await message.answer("Демо-анкеты сейчас недоступны.")
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=survey["title"],
                    callback_data=f"demo_take_{survey['id']}",
                )
            ]
            for survey in surveys
        ]
    )
    await message.answer("Выберите демо-анкету:", reply_markup=keyboard)


@router.callback_query(F.data.startswith("demo_take_"))
async def callback_demo_take(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer("Не удалось начать демо.")
        return

    survey_id_raw = callback.data.replace("demo_take_", "", 1)
    if not survey_id_raw.isdigit():
        await callback.answer("Некорректный ID демо-анкеты", show_alert=True)
        return

    survey_id = int(survey_id_raw)
    questions = await get_questions(survey_id)
    if not questions:
        await callback.answer("В демо-анкете пока нет вопросов", show_alert=True)
        return

    response_id = await create_response(survey_id=survey_id, user_id=callback.from_user.id)
    await state.update_data(
        survey_id=survey_id,
        response_id=response_id,
        questions=questions,
        current_index=0,
        demo_mode=True,
    )
    await state.set_state(TakeSurveyStates.answering)
    await callback.answer()
    question = questions[0]
    text = f"Вопрос 1/{len(questions)}:\n{question['question_text']}"
    if question.get("question_type") == "choice" and question.get("choices"):
        text += "\nВарианты: " + ", ".join(question["choices"])
    await callback.message.answer(text)
