import logging
from aiogram import types
from aiogram.dispatcher import FSMContext
from states import CourseForm
from database import get_resources_by_tags
from gemini_service import generate_plan, generate_course, answer_question, generate_course_suggestions, update_lesson
import asyncio
from bot import save_user_course

logger = logging.getLogger(__name__)

user_courses = {}

async def start(message: types.Message, state: FSMContext):
    # Отправляем приветственное сообщение и сохраняем его ID
    welcome_msg = await message.reply(
        "Привет! Я CourseCraftAI — твой личный помощник в обучении. "
        "Я создам для тебя курс по любому навыку за 7 дней! "
        "Просто скажи, чему хочешь научиться, и я подготовлю персональный план."
    )
    # Сразу отправляем вопрос и удаляем приветственное сообщение
    await message.reply("Чему хотите научиться?")
    await message.bot.delete_message(chat_id=message.chat.id, message_id=welcome_msg.message_id)
    await CourseForm.skill.set()

async def process_skill(message: types.Message, state: FSMContext):
    if message.text.startswith('/'):
        return
    skill = message.text.strip()
    if not skill:
        await message.reply("Пожалуйста, укажи навык!")
        return
    user_id = message.from_user.id
    if user_id not in user_courses:
        user_courses[user_id] = {"completed_lessons": []}
    await state.update_data(skill=skill)
    await message.reply("Какой результат вы хотите достичь?")
    await CourseForm.goal.set()

async def process_goal(message: types.Message, state: FSMContext):
    if message.text.startswith('/'):
        return
    goal = message.text.strip()
    if not goal:
        await message.reply("Пожалуйста, укажи цель!")
        return
    await state.update_data(goal=goal)
    await message.reply("Что вы уже знаете об этом навыке?")
    await CourseForm.experience.set()

async def process_experience(message: types.Message, state: FSMContext):
    if message.text.startswith('/'):
        return
    experience = message.text.strip()
    if not experience:
        await message.reply("Пожалуйста, опишите свой опыт!")
        return
    await state.update_data(experience=experience)
    keyboard = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("Пропустить", callback_data="skip_preferences"))
    await message.reply(
        "Расскажи о себе? что хочешь видеть в курсе?\nЭтот вопрос нужен для большей персонализации курса. (Можно пропустить)",
        reply_markup=keyboard
    )
    await CourseForm.preferences.set()

async def process_preferences(message: types.Message, state: FSMContext, bot):
    if message.text.startswith('/'):
        return
    preferences = message.text.strip()
    await state.update_data(preferences=preferences)
    await generate_and_show_plan(message, state, bot)

async def skip_preferences(callback_query: types.CallbackQuery, state: FSMContext, bot):
    await state.update_data(preferences="Не указано")
    await generate_and_show_plan(callback_query.message, state, bot)
    await callback_query.answer()

async def generate_and_show_plan(message, state: FSMContext, bot):
    user_data = await state.get_data()
    skill = user_data["skill"]
    goal = user_data["goal"]
    experience = user_data["experience"]
    plan = generate_plan(skill, experience, goal)
    if not plan or len(plan) != 7:
        logger.error(f"Не удалось создать план для навыка '{skill}', цели '{goal}'")
        await message.reply("Не удалось создать план курса. Попробуй ещё раз!")
        return
    
    plan_text = "<b>Вот план твоего курса:</b>\n\n" + "\n".join([f"День {i+1}: {title}" for i, title in enumerate(plan)])
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton("Утвердить план", callback_data="approve_plan"),
        types.InlineKeyboardButton("Что добавить в план", callback_data="edit_plan"),
        types.InlineKeyboardButton("Вернуться в начало", callback_data="restart")
    )
    logger.info(f"Показан план для пользователя {message.from_user.id}: {plan_text}")
    await message.reply(plan_text, reply_markup=keyboard, parse_mode="HTML")
    await state.update_data(plan=plan)
    await CourseForm.plan.set()

async def process_plan(callback_query: types.CallbackQuery, state: FSMContext, bot):
    global user_courses
    user_id = callback_query.from_user.id
    action = callback_query.data
    
    if action == "approve_plan":
        user_data = await state.get_data()
        skill = user_data["skill"]
        experience = user_data["experience"]
        goal = user_data["goal"]
        preferences = user_data["preferences"]
        plan = user_data["plan"]
        course_content = generate_course(skill, experience, goal, preferences, plan)
        if not course_content or len(course_content) != 7:
            logger.error(f"Не удалось создать курс для пользователя {user_id}: {course_content}")
            await callback_query.message.reply("Не удалось создать курс. Попробуй ещё раз!")
            return
        
        user_courses[user_id] = {
            "course": course_content,
            "current_day": 0,
            "chat_id": callback_query.message.chat.id,
            "progress": 0,
            "skill": skill,
            "current_question": 0,
            "experience": experience,
            "goal": goal,
            "preferences": preferences,
            "completed_lessons": user_courses.get(user_id, {}).get("completed_lessons", [])
        }
        await save_user_course(user_id, user_courses[user_id])
        await send_lesson(user_id, callback_query.message, bot)
        asyncio.create_task(schedule_reminders(user_id, bot))
        await state.finish()
    
    elif action == "edit_plan":
        await callback_query.message.reply("Напиши, что ты хочешь добавить или изменить в плане:")
        await CourseForm.edit_plan.set()
    
    elif action == "restart":
        await callback_query.message.reply("Давай начнём заново. Чему хотите научиться?")
        await CourseForm.skill.set()
    
    await callback_query.answer()

async def process_edit_plan(message: types.Message, state: FSMContext):
    if message.text.startswith('/'):
        return
    edit_request = message.text.strip()
    if not edit_request:
        await message.reply("Пожалуйста, укажи, что добавить или изменить!")
        return
    user_data = await state.get_data()
    skill = user_data["skill"]
    experience = user_data["experience"]
    goal = user_data["goal"]
    updated_plan = generate_plan(skill, experience, goal, edit_request)
    if not updated_plan or len(updated_plan) != 7:
        logger.error(f"Не удалось обновить план для навыка '{skill}' с запросом '{edit_request}'")
        await message.reply("Не удалось обновить план. Попробуй ещё раз!")
        return
    
    plan_text = "<b>Обновлённый план твоего курса:</b>\n\n" + "\n".join([f"День {i+1}: {title}" for i, title in enumerate(updated_plan)])
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton("Утвердить план", callback_data="approve_plan"),
        types.InlineKeyboardButton("Что добавить в план", callback_data="edit_plan"),
        types.InlineKeyboardButton("Вернуться в начало", callback_data="restart")
    )
    logger.info(f"Обновлён план для пользователя {message.from_user.id}: {plan_text}")
    await message.reply(plan_text, reply_markup=keyboard, parse_mode="HTML")
    await state.update_data(plan=updated_plan)
    await CourseForm.plan.set()

async def send_lesson(user_id, message_or_chat_id, bot):
    global user_courses
    if user_id not in user_courses:
        await bot.send_message(message_or_chat_id.chat.id, "Сначала начни курс с помощью /start!")
        return
    day = user_courses[user_id]["current_day"]
    lesson = user_courses[user_id]["course"][day]
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    if day < 6:
        keyboard.add(types.InlineKeyboardButton("Следующий урок", callback_data="next_lesson"))
    elif day == 6:
        keyboard.add(types.InlineKeyboardButton("Завершить курс", callback_data="finish_course"))
    keyboard.add(
        types.InlineKeyboardButton("Ты непонятно объясняешь", callback_data="simplify_lesson"),
        types.InlineKeyboardButton("Задать вопрос", callback_data="custom_question"),
        types.InlineKeyboardButton("Пожелания по генерации", callback_data="change_plan"),
        types.InlineKeyboardButton("Отказаться от курса", callback_data="cancel_course")
    )
    await bot.send_message(
        user_courses[user_id]["chat_id"],
        lesson,
        reply_markup=keyboard,
        parse_mode="HTML"
    )

async def schedule_reminders(user_id, bot):
    global user_courses
    while user_courses.get(user_id) and user_courses[user_id]["current_day"] < 6:
        await asyncio.sleep(24 * 60 * 60)  # 24 часа
        if user_id in user_courses:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("Следующий урок", callback_data="next_lesson"))
            await bot.send_message(
                user_courses[user_id]["chat_id"],
                "Готов к новому уроку?",
                reply_markup=keyboard
            )

async def next_lesson(callback_query: types.CallbackQuery, bot):
    global user_courses
    user_id = callback_query.from_user.id
    if user_id not in user_courses:
        await callback_query.message.reply("Сначала начни курс с помощью /start!")
        return
    current_day = user_courses[user_id]["current_day"]
    skill = user_courses[user_id]["skill"]
    if "completed_lessons" not in user_courses[user_id]:
        user_courses[user_id]["completed_lessons"] = []
    if current_day < 6:
        if (skill, current_day) not in user_courses[user_id]["completed_lessons"]:
            user_courses[user_id]["completed_lessons"].append((skill, current_day))
        user_courses[user_id]["current_day"] += 1
        current_day = user_courses[user_id]["current_day"]
        user_courses[user_id]["progress"] = min(100, (current_day + 1) * 14)
        await save_user_course(user_id, user_courses[user_id])
        await callback_query.message.reply(f"Твой прогресс: {user_courses[user_id]['progress']}%")
        await send_lesson(user_id, callback_query.message, bot)
    await callback_query.answer()

async def simplify_lesson(callback_query: types.CallbackQuery, state: FSMContext):
    global user_courses
    user_id = callback_query.from_user.id
    if user_id not in user_courses:
        await callback_query.message.reply("Сначала начни курс с помощью /start!")
        return
    day = user_courses[user_id]["current_day"]
    lesson = user_courses[user_id]["course"][day]
    context = f"Пользователь проходит курс по '{user_courses[user_id]['skill']}'. Текущий урок:\n{lesson}"
    simpler_lesson = answer_question("Объясни этот урок проще", context)
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    if day < 6:
        keyboard.add(types.InlineKeyboardButton("Следующий урок", callback_data="next_lesson"))
    elif day == 6:
        keyboard.add(types.InlineKeyboardButton("Завершить курс", callback_data="finish_course"))
    keyboard.add(
        types.InlineKeyboardButton("Ты непонятно объясняешь", callback_data="simplify_lesson"),
        types.InlineKeyboardButton("Задать вопрос", callback_data="custom_question"),
        types.InlineKeyboardButton("Пожелания по генерации", callback_data="change_plan"),
        types.InlineKeyboardButton("Отказаться от курса", callback_data="cancel_course")
    )
    await callback_query.message.reply(
        f"<b>Простое объяснение</b>:\n{simpler_lesson}",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback_query.answer()

async def custom_question(callback_query: types.CallbackQuery, state: FSMContext):
    keyboard = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton("Вернуться к уроку", callback_data="return_to_lesson")
    )
    await callback_query.message.reply("Какой у тебя вопрос?", reply_markup=keyboard)
    await CourseForm.custom_question.set()
    await callback_query.answer()

async def process_custom_question(message: types.Message, state: FSMContext):
    if message.text.startswith('/'):
        return
    user_id = message.from_user.id
    if user_id not in user_courses:
        await message.reply("Сначала начни курс с помощью /start!")
        return
    question = message.text.strip().lower()
    
    if "как отказаться" in question or "как пользоваться" in question or "что делать" in question:
        answer = (
            "Если хочешь отказаться от курса, нажми кнопку 'Отказаться от курса' под уроком. "
            "Чтобы задать вопрос, используй 'Задать вопрос'. "
            "Для изменения урока — 'Пожелания по генерации'. "
            "Если что-то непонятно, пиши мне!"
        )
    else:
        day = user_courses[user_id]["current_day"]
        lesson = user_courses[user_id]["course"][day]
        context = f"Пользователь проходит курс по '{user_courses[user_id]['skill']}'. Текущий урок:\n{lesson}"
        answer = answer_question(question, context)
    
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("Ещё вопрос", callback_data="custom_question"),
        types.InlineKeyboardButton("Вернуться к уроку", callback_data="return_to_lesson")
    )
    await message.reply(
        f"<b>Ответ</b>:\n{answer}",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await state.finish()

async def return_to_lesson(callback_query: types.CallbackQuery, bot):
    user_id = callback_query.from_user.id
    if user_id in user_courses:
        try:
            await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение: {e}")
        await send_lesson(user_id, callback_query.message, bot)
    else:
        try:
            await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение: {e}")
        await callback_query.message.reply("Сначала начни курс с помощью /start!")
    await callback_query.answer()

async def change_plan(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    if user_id not in user_courses:
        await callback_query.message.reply("Сначала начни курс с помощью /start!")
        return
    await callback_query.message.reply("Напиши пожелания по генерации уроков (например, 'Больше примеров'):")
    await CourseForm.change_plan.set()
    await callback_query.answer()

async def process_change_plan(message: types.Message, state: FSMContext, bot):
    if message.text.startswith('/'):
        return
    user_id = message.from_user.id
    edit_request = message.text.strip()
    if not edit_request:
        await message.reply("Пожалуйста, укажи пожелания!")
        return
    if user_id not in user_courses:
        await message.reply("Сначала начни курс с помощью /start!")
        return
    
    skill = user_courses[user_id]["skill"]
    experience = user_courses[user_id].get("experience", "Не указано")
    goal = user_courses[user_id].get("goal", "Не указано")
    preferences = user_courses[user_id].get("preferences", "Не указано")
    current_day = user_courses[user_id]["current_day"]
    current_course = user_courses[user_id]["course"]
    current_lesson = current_course[current_day]
    updated_lesson = update_lesson(skill, experience, goal, preferences, current_lesson, edit_request, current_day)
    user_courses[user_id]["course"][current_day] = updated_lesson
    await save_user_course(user_id, user_courses[user_id])
    await message.reply(f"<b>Пожелания учтены!</b> Урок {current_day + 1} обновлён!")
    await send_lesson(user_id, message, bot)
    await state.finish()

async def finish_course(callback_query: types.CallbackQuery):
    global user_courses
    user_id = callback_query.from_user.id
    if user_id not in user_courses:
        await callback_query.message.reply("Сначала начни курс с помощью /start!")
        return
    skill = user_courses[user_id]["skill"]
    completed_lessons = user_courses[user_id]["completed_lessons"]
    if (skill, 6) not in completed_lessons:
        completed_lessons.append((skill, 6))
    suggested_courses = generate_course_suggestions(skill)
    if not suggested_courses or len(suggested_courses) != 3:
        suggested_courses = [
            f"Продвинутый курс по {skill}",
            f"{skill} и маркетинг",
            f"Практика {skill} в реальных проектах"
        ]
    completed_skills = {s for s, d in completed_lessons if d == 6}
    suggested_courses = [course for course in suggested_courses if course not in completed_skills]
    if not suggested_courses:
        await callback_query.message.reply("Все предложенные курсы уже полностью пройдены. Выбери новый навык!")
        await CourseForm.skill.set()
        return
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    for i, course in enumerate(suggested_courses):
        keyboard.add(types.InlineKeyboardButton(course, callback_data=f"suggested_{i}"))
    keyboard.add(types.InlineKeyboardButton("Свой навык", callback_data="restart"))
    await callback_query.message.reply(
        f"<b>Вы молодец! 🎉 Завершили курс по '{skill}'!</b>\n"
        "Это большой шаг к твоей цели! Прогресс: 100%. Выбери, что дальше:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await save_user_course(user_id, user_courses[user_id])
    await callback_query.answer()

async def cancel_course(callback_query: types.CallbackQuery):
    global user_courses
    user_id = callback_query.from_user.id
    if user_id in user_courses:
        completed_lessons = user_courses[user_id]["completed_lessons"]
        del user_courses[user_id]
        await save_user_course(user_id, {"completed_lessons": completed_lessons})
        await callback_query.message.reply("Ты отказался от курса. Начни новый с помощью /start!")
    else:
        await callback_query.message.reply("У тебя нет активного курса!")
    await callback_query.answer()

async def process_suggested_course(callback_query: types.CallbackQuery, state: FSMContext):
    global user_courses
    user_id = callback_query.from_user.id
    if user_id not in user_courses:
        await callback_query.message.reply("Сначала начни курс с помощью /start!")
        return
    skill = user_courses[user_id]["skill"]
    completed_lessons = user_courses[user_id]["completed_lessons"]
    suggested_courses = generate_course_suggestions(skill)
    if not suggested_courses or len(suggested_courses) != 3:
        suggested_courses = [
            f"Продвинутый курс по {skill}",
            f"{skill} и маркетинг",
            f"Практика {skill} в реальных проектах"
        ]
    completed_skills = {s for s, d in completed_lessons if d == 6}
    suggested_courses = [course for course in suggested_courses if course not in completed_skills]
    if not suggested_courses:
        await callback_query.message.reply("Все предложенные курсы уже полностью пройдены. Выбери новый навык!")
        await CourseForm.skill.set()
        return
    course_index = int(callback_query.data.split("_")[1])
    if course_index >= len(suggested_courses):
        await callback_query.message.reply("Ошибка выбора курса. Попробуй ещё раз!")
        return
    selected_course = suggested_courses[course_index]
    await callback_query.message.reply(f"Ты выбрал '{selected_course}'. Какую цель ты хочешь достичь?")
    await state.update_data(skill=selected_course)
    await CourseForm.goal.set()
    completed_lessons = user_courses[user_id]["completed_lessons"]
    del user_courses[user_id]
    await save_user_course(user_id, {"completed_lessons": completed_lessons})
    await callback_query.answer()

def register_course_handlers(dp, user_courses_passed):
    global user_courses
    user_courses = user_courses_passed
    dp.register_message_handler(process_skill, state=CourseForm.skill)
    dp.register_message_handler(process_goal, state=CourseForm.goal)
    dp.register_message_handler(process_experience, state=CourseForm.experience)
    dp.register_message_handler(lambda message, state: process_preferences(message, state, dp.bot), state=CourseForm.preferences)
    dp.register_callback_query_handler(lambda cq, state: skip_preferences(cq, state, dp.bot), lambda c: c.data == "skip_preferences", state=CourseForm.preferences)
    dp.register_callback_query_handler(lambda cq, state: process_plan(cq, state, dp.bot), lambda c: c.data in ["approve_plan", "edit_plan", "restart"], state=CourseForm.plan)
    dp.register_message_handler(process_edit_plan, state=CourseForm.edit_plan)
    dp.register_callback_query_handler(lambda cq: next_lesson(cq, dp.bot), lambda c: c.data == "next_lesson")
    dp.register_callback_query_handler(custom_question, lambda c: c.data == "custom_question", state="*")
    dp.register_message_handler(process_custom_question, state=CourseForm.custom_question)
    dp.register_callback_query_handler(lambda cq: return_to_lesson(cq, dp.bot), lambda c: c.data == "return_to_lesson")
    dp.register_callback_query_handler(lambda cq: return_to_lesson(cq, dp.bot), lambda c: c.data == "return_to_lesson", state=CourseForm.custom_question)
    dp.register_callback_query_handler(change_plan, lambda c: c.data == "change_plan")
    dp.register_message_handler(lambda message, state: process_change_plan(message, state, dp.bot), state=CourseForm.change_plan)
    dp.register_callback_query_handler(simplify_lesson, lambda c: c.data == "simplify_lesson")
    dp.register_callback_query_handler(cancel_course, lambda c: c.data == "cancel_course")
    dp.register_callback_query_handler(lambda cq, state: process_suggested_course(cq, state), lambda c: c.data.startswith("suggested_"))
    dp.register_callback_query_handler(lambda cq, state: process_plan(cq, state, dp.bot), lambda c: c.data == "restart", state=None)
    dp.register_callback_query_handler(finish_course, lambda c: c.data == "finish_course")