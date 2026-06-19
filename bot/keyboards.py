from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Создать анкету", callback_data="create_survey")],
        [InlineKeyboardButton(text="Список анкет", callback_data="list_surveys")]
    ])


def get_question_type_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Текст", callback_data="type_text")],
        [InlineKeyboardButton(text="Варианты", callback_data="type_choice")]
    ])


def get_survey_list_keyboard(surveys):
    keyboard = []
    for survey in surveys:
        keyboard.append([InlineKeyboardButton(text=survey['title'], callback_data=f"take_{survey['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
