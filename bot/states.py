from aiogram.fsm.state import State, StatesGroup


class CreateSurveyStates(StatesGroup):
    title = State()
    description = State()
    question_text = State()
    question_type = State()
    choices = State()


class TakeSurveyStates(StatesGroup):
    survey_selection = State()
    answering = State()


class BroadcastStates(StatesGroup):
    waiting_content = State()
    waiting_confirmation = State()
