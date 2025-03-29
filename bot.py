import logging
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor
import os
import aiosqlite
from aiohttp import web
from handlers import course  # Импортируем модуль course из папки handlers

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Получаем переменные окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

# Проверяем, что переменные окружения заданы
if not TELEGRAM_TOKEN:
    logger.error("TELEGRAM_TOKEN не задан в переменных окружения")
    exit(1)
if not GEMINI_API_KEY:
    logger.error("GEMINI_API_KEY не задан в переменных окружения")
    exit(1)
if not DATABASE_URL:
    logger.error("DATABASE_URL не задан в переменных окружения")
    exit(1)

try:
    bot = Bot(token=TELEGRAM_TOKEN)
except Exception as e:
    logger.error(f"Ошибка при создании бота: {e}")
    exit(1)

storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Устанавливаем путь к базе данных
DB_NAME = DATABASE_URL.replace("sqlite:///", "")  # Убираем префикс для SQLite

# Кнопка для донатов
donate_button = types.InlineKeyboardMarkup().add(
    types.InlineKeyboardButton("Поддержать проект", url="https://yoomoney.ru/to/4100119062540797")
)

# Инициализация базы данных
async def init_db():
    logger.info(f"Инициализация базы данных: {DB_NAME}")
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

# Загрузка данных из базы
async def load_user_courses():
    user_courses = {}
    logger.info("Загрузка данных из базы...")
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
    logger.info(f"Загружено {len(user_courses)} записей из базы")
    return user_courses

# Сохранение данных в базу
async def save_user_course(user_id, course_data):
    logger.info(f"Сохранение данных для user_id={user_id}")
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

# Клавиатура для возврата к курсу
def get_return_keyboard(user_id):
    keyboard = types.InlineKeyboardMarkup()
    if user_id in user_courses and user_courses[user_id].get("course"):
        keyboard.add(types.InlineKeyboardButton("Вернуться к курсу", callback_data="return_to_lesson"))
    else:
        keyboard.add(types.InlineKeyboardButton("Начать курс", callback_data="start_course"))
    return keyboard

# Команда /start
@dp.message_handler(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    logger.info(f"Команда /start от {message.from_user.id}")
    await state.finish()  # Сбрасываем состояние
    await message.reply("Привет! Я CourseCraftBot — твой помощник в обучении! 🚀 Напиши /help, чтобы узнать, что я умею.")
    try:
        await course.start(message, None)  # Вызываем функцию start из course.py
    except Exception as e:
        logger.error(f"Ошибка в course.start: {e}")
        await message.reply("Произошла ошибка при запуске курса. Попробуй снова или напиши /help.")

# Команда /help
@dp.message_handler(Command("help"))
async def cmd_help(message: types.Message, state: FSMContext):
    logger.info(f"Команда /help от {message.from_user.id}")
    await state.finish()  # Сбрасываем состояние
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

# Состояние для обратной связи
class FeedbackState(StatesGroup):
    waiting_for_feedback = State()

# Команда /feedback
@dp.message_handler(Command("feedback"))
async def start_feedback(message: types.Message, state: FSMContext):
    logger.info(f"Команда /feedback от {message.from_user.id}")
    await state.finish()  # Сбрасываем состояние
    keyboard = get_return_keyboard(message.from_user.id)
    await message.reply("Напиши свой отзыв о курсе! Что понравилось, что улучшить?", reply_markup=keyboard)
    await FeedbackState.waiting_for_feedback.set()

# Обработка отзыва
@dp.message_handler(state=FeedbackState.waiting_for_feedback)
async def process_feedback(message: types.Message, state: FSMContext):
    logger.info(f"Получен отзыв от {message.from_user.id}")
    feedback = message.text
    await bot.send_message(795056847, f"Новый отзыв от {message.from_user.id}:\n{feedback}")
    keyboard = get_return_keyboard(message.from_user.id)
    await message.reply("Спасибо за отзыв!", reply_markup=keyboard)
    await state.finish()

# Команда /donate
@dp.message_handler(Command("donate"))
async def send_donate(message: types.Message, state: FSMContext):
    logger.info(f"Команда /donate от {message.from_user.id}")
    await state.finish()  # Сбрасываем состояние
    keyboard = get_return_keyboard(message.from_user.id)
    await message.reply("Спасибо за желание помочь! Поддержи проект здесь:", reply_markup=donate_button)
    await message.reply("Выбери действие:", reply_markup=keyboard)

# Callback для начала курса
async def start_course_callback(callback_query: types.CallbackQuery, state: FSMContext):
    logger.info(f"Callback start_course от {callback_query.from_user.id}")
    await state.finish()
    await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)
    await callback_query.message.reply("Начинаем курс! 🚀")
    try:
        await course.start(callback_query.message, None)  # Вызываем функцию start из course.py
    except Exception as e:
        logger.error(f"Ошибка в course.start (callback): {e}")
        await callback_query.message.reply("Произошла ошибка при запуске курса. Попробуй снова или напиши /help.")
    await callback_query.answer()

# Callback для возврата к уроку
async def return_to_lesson_callback(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    logger.info(f"Callback return_to_lesson от user_id={user_id}")
    await state.finish()
    if user_id in user_courses and user_courses[user_id].get("course"):
        logger.info(f"Найден курс: {user_courses[user_id]}")
        await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)
        await callback_query.message.reply("Возвращаемся к твоему курсу! 📚")
        try:
            await course.send_lesson(user_id, callback_query.message, bot)  # Вызываем функцию send_lesson из course.py
        except Exception as e:
            logger.error(f"Ошибка в course.send_lesson: {e}")
            await callback_query.message.reply("Произошла ошибка при загрузке урока. Попробуй снова или напиши /help.")
    else:
        logger.info(f"Курс не найден для {user_id}, запускаем новый")
        await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)
        await callback_query.message.reply("Курс не найден, начинаем новый! 🚀")
        try:
            await course.start(callback_query.message, None)  # Вызываем функцию start из course.py
        except Exception as e:
            logger.error(f"Ошибка в course.start (callback): {e}")
            await callback_query.message.reply("Произошла ошибка при запуске курса. Попробуй снова или напиши /help.")
    await callback_query.answer()

# Обработчик всех текстовых сообщений (для отладки)
@dp.message_handler()
async def echo_all(message: types.Message, state: FSMContext):
    logger.info(f"Получено сообщение от {message.from_user.id}: {message.text}")
    current_state = await state.get_state()
    logger.info(f"Текущее состояние: {current_state}")
    await message.reply("Я получил твоё сообщение, но не знаю, что с ним делать. Попробуй команду, например, /help.")

# Функции on_startup и on_shutdown
async def on_startup(_):
    await init_db()
    global user_courses
    user_courses = await load_user_courses()
    logger.info("Бот запущен!")
    try:
        course.register_course_handlers(dp, user_courses)  # Регистрируем обработчики из course.py
    except Exception as e:
        logger.error(f"Ошибка в course.register_course_handlers: {e}")

async def on_shutdown(_):
    logger.info("Бот завершает работу...")

# HTTP-сервер для пинга UptimeRobot
app = web.Application()
app.router.add_get('/', lambda request: web.Response(text="Bot is alive!"))

async def start_app():
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.getenv("PORT", 8000)))
    await site.start()

# Запуск бота
if __name__ == "__main__":
    dp.register_callback_query_handler(start_course_callback, lambda c: c.data == "start_course")
    dp.register_callback_query_handler(return_to_lesson_callback, lambda c: c.data == "return_to_lesson")

    executor.start_polling(
        dp,
        skip_updates=True,
        on_startup=lambda _: start_app(),
        on_shutdown=on_shutdown
    )