# states.py
from aiogram.dispatcher.filters.state import State, StatesGroup

class CourseForm(StatesGroup):
    skill = State()
    goal = State()
    experience = State()
    preferences = State()
    plan = State()
    edit_plan = State()
    custom_question = State()
    change_plan = State()