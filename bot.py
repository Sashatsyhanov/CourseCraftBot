import logging
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from handlers import course
from dotenv import load_dotenv
import os
import aiosqlite
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor

# Загружаем переменные из .env
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    bot = Bot(token=os.getenv("TELEGRAM_TOKEN"))
except Exception as e:
    logger.error(f"Ошибка при создании бота: {e}")
    exit(1)

storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

DB_NAME = "course_progress.db"

# Кнопка для донатов
donate_button = types.InlineKeyboardMarkup().add(
    types.InlineKeyboardButton("Поддержать проект", url="https://yoomoney.ru/to/4100119062540797")  # Замени на свой счёт
)

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_courses (
                user_id INTEGER PRIMARY KEY,
                course TEXT,
                current_day INTEGER,
                chat_id INTEGER,
                progress INTEGER,
                skill TEXT,
                current_question INTEGER,
                experience TEXT,
                goal TEXT,
                preferences TEXT
            )
        """)
        await db.commit()

async def load_user_courses():
    user_courses = {}
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT * FROM user_courses") as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                user_id = row[0]
                user_courses[user_id] = {
                    "course": eval(row[1]) if row[1] else [],
                    "current_day": row[2],
                    "chat_id": row[3],
                    "progress": row[4],
                    "skill": row[5],
                    "current_question": row[6],
                    "experience": row[7],
                    "goal": row[8],
                    "preferences": row[9]
                }
    return user_courses

async def save_user_course(user_id, course_data):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT OR REPLACE INTO user_courses (
                user_id, course, current_day, chat_id, progress, skill, current_question, experience, goal, preferences
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, str(course_data.get("course", [])), course_data.get("current_day", 0), course_data.get("chat_id", 0),
            course_data.get("progress", 0), course_data.get("skill", ""), course_data.get("current_question", 0),
            course_data.get("experience", ""), course_data.get("goal", ""), course_data.get("preferences", "")
        ))
        await db.commit()

# Функция для создания клавиатуры возврата
def get_return_keyboard(user_id):
    keyboard = types.InlineKeyboardMarkup()
    if user_id in course.user_courses and course.user_courses[user_id].get("course"):
        keyboard.add(types.InlineKeyboardButton("Вернуться к курсу", callback_data="return_to_lesson"))
    else:
        keyboard.add(types.InlineKeyboardButton("Начать курс", callback_data="start_course"))
    return keyboard

# Обработчик /start
@dp.message_handler(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    logger.info(f"Команда /start от {message.from_user.id}")
    await state.finish()
    await course.start(message, None)

# Обработчик /help
@dp.message_handler(Command("help"))
async def cmd_help(message: types.Message, state: FSMContext):
    logger.info(f"Команда /help от {message.from_user.id}")
    await state.finish()
    help_text = (
        "Привет! Я CourseCraftBot — твой помощник в обучении! 🚀\n\n"
        "<b>Команды:</b>\n"
        "/start — начать новый курс\n"
        "/feedback — оставить отзыв\n"
        "/donate — поддержать проект\n"
        "/help — показать эту справку\n\n"
        "<b>Кнопки под уроками:</b>\n"
        "Следующий урок — перейти к следующему дню\n"
        "Завершить курс — закончить курс на 7-м дне\n"
        "Ты непонятно объясняешь — упростить текущий урок\n"
        "Задать вопрос — спросить что-то по уроку\n"
        "Пожелания по генерации — улучшить текущий урок\n"
        "Отказаться от курса — выйти из курса\n\n"
        "По любому поводу пиши мне — я помогу! 🎯"
    )
    keyboard = get_return_keyboard(message.from_user.id)
    await message.reply(help_text, reply_markup=keyboard, parse_mode="HTML")

# Состояния для отзывов
class FeedbackState(StatesGroup):
    waiting_for_feedback = State()

# Команда /feedback
@dp.message_handler(Command("feedback"))
async def start_feedback(message: types.Message, state: FSMContext):
    logger.info(f"Команда /feedback от {message.from_user.id}")
    await state.finish()
    keyboard = get_return_keyboard(message.from_user.id)
    await message.reply("Напиши свой отзыв о курсе! Что понравилось, что улучшить?", reply_markup=keyboard)
    await FeedbackState.waiting_for_feedback.set()

@dp.message_handler(state=FeedbackState.waiting_for_feedback)
async def process_feedback(message: types.Message, state: FSMContext):
    feedback = message.text
    await bot.send_message(795056847, f"Новый отзыв от {message.from_user.id}:\n{feedback}")
    keyboard = get_return_keyboard(message.from_user.id)
    await message.reply("Спасибо за отзыв!", reply_markup=keyboard)
    await state.finish()

# Команда /donate
@dp.message_handler(Command("donate"))
async def send_donate(message: types.Message, state: FSMContext):
    logger.info(f"Команда /donate от {message.from_user.id}")
    await state.finish()
    keyboard = get_return_keyboard(message.from_user.id)
    await message.reply("Спасибо за желание помочь! Поддержи проект здесь:", reply_markup=donate_button)
    await message.reply("Выбери действие:", reply_markup=keyboard)

async def on_startup(_):
    await init_db()
    global user_courses
    user_courses = await load_user_courses()
    course.register_course_handlers(dp, user_courses)
    logger.info("Бот запущен!")

async def on_shutdown(_):
    logger.info("Бот завершает работу...")

# Обработчик для кнопки "Начать курс"
async def start_course_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await state.finish()
    await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)
    await course.start(callback_query.message, None)
    await callback_query.answer()

# Обработчик для кнопки "Вернуться к курсу"
async def return_to_lesson_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await state.finish()
    user_id = callback_query.from_user.id
    logger.info(f"Возврат к курсу для user_id={user_id}")
    if user_id in course.user_courses and course.user_courses[user_id].get("course"):
        logger.info(f"Найден курс: {course.user_courses[user_id]}")
        await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)
        await course.send_lesson(user_id, callback_query.message, bot)
    else:
        logger.info(f"Курс не найден для {user_id}, запускаем новый")
        await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)
        await course.start(callback_query.message, None)
    await callback_query.answer()

if __name__ == "__main__":
    dp.register_callback_query_handler(start_course_callback, lambda c: c.data == "start_course")
    dp.register_callback_query_handler(return_to_lesson_callback, lambda c: c.data == "return_to_lesson")
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup, on_shutdown=on_shutdown)