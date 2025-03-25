import google.generativeai as genai
import logging
import os
from dotenv import load_dotenv
import hashlib
from database import get_resources_by_tags  # Импортируем функцию поиска

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

logger = logging.getLogger(__name__)

def generate_plan(skill, experience, goal, edit_request=""):
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = (
            f"Ты — эксперт в обучении с 20-летним опытом. "
            f"Создай план курса из 7 уроков для навыка '{skill}'. "
            f"Уровень опыта: '{experience}'. Цель: '{goal}'. {edit_request}. "
            f"Применяй закон 80/20: фокус на 20% тем, дающих 80% результата. "
            f"Каждый урок — заголовок (50-70 символов). "
            f"Возвращай только 7 строк без нумерации и лишнего текста."
        )
        response = model.generate_content(prompt).text.strip().split("\n")
        lessons = [line.strip() for line in response if line.strip()]
        if len(lessons) != 7:
            logger.warning(f"План содержит {len(lessons)} уроков вместо 7, корректируем")
            return lessons[:7] if len(lessons) > 7 else lessons + ["Дополнительный урок"] * (7 - len(lessons))
        return lessons
    except Exception as e:
        logger.error(f"Ошибка генерации плана: {str(e)}")
        return None

def generate_course(skill, experience, goal, preferences, plan, generated_lessons=None):
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        plan_str = "\n".join([f"День {i+1}: {title}" for i, title in enumerate(plan)])
        exclude_lessons = ""
        if generated_lessons:
            exclude_lessons = (
                "Не повторяй следующие уроки (хеши):\n" +
                "\n".join([f"- {hashlib.md5(lesson.encode()).hexdigest()}" for lesson in generated_lessons]) +
                "\nГенерируй новый уникальный контент для каждого дня."
            )
        
        # Проверяем базу данных
        resources = get_resources_by_tags(skill.lower())
        resource_content = ""
        if resources:
            resource_content = "Используй следующий материал из базы данных:\n"
            for title, author, res_type, content in resources:
                resource_content += f"- {res_type.capitalize()} '{title}' от {author}: {content[:200]}...\n"
            resource_content += "Интегрируй этот материал в уроки, адаптируя под структуру.\n"
        
        prompt = (
            f"Ты — эксперт в обучении с 20-летним опытом, создающий вдохновляющие курсы. "
            f"Разработай 7-дневный курс по навыку '{skill}' для цели '{goal}'. "
            f"Уровень опыта: {experience}. Предпочтения: {preferences}.\n\n"
            f"### Принцип 80/20\n"
            f"- Дай 20% знаний, которые обеспечат 80% результата.\n"
            f"- Убери всё лишнее, оставь только самое важное.\n\n"
            f"### Длительность\n"
            f"- Курс длится 7 дней. Используй план:\n{plan_str}\n\n"
            f"### Структура урока\n"
            f"- Каждый урок должен быть в точном формате:\n"
            f"  <b>День X: [Название урока]</b>\n"
            f"  <b>Краткое введение 🎯</b>: 3-4 предложения (почему это важно, с мотивацией).\n"
            f"  <b>Основной шаг 🚀</b>: Ключевая идея, 3-4 совета. В конце ОБЯЗАТЕЛЬНО добавь: 'Не уверен? Задай мне вопрос!'.\n"
            f"  <b>Практический пример 🌟</b>: Реальная ситуация с деталями.\n"
            f"  <b>Практическое задание 1 ✍️</b>: Простое задание для практики.\n"
            f"  <b>Практическое задание 2 ✍️</b>: Задание для закрепления.\n"
            f"  💡 Полезный совет: Короткий и практичный.\n"
            f"  Не стесняйся задавать вопросы — я здесь, чтобы помочь!\n"
            f"  По любому поводу можешь задать мне вопрос! 🚀\n"
            f"  <b>Спрашивай обо всём! 🤓</b>\n"
            f"- Не дублируй заголовки, используй ТОЛЬКО указанный формат.\n"
            f"### Персонализация\n"
            f"- Для новичков: простые основы. Для среднего: больше практики. Для продвинутых: сложные задачи.\n"
            f"- Учитывай предпочтения ({preferences}) в примерах и стиле.\n"
            f"- Если программирование — используй Python, если язык не указан.\n\n"
            f"### Формат\n"
            f"- Длина урока: 1800-2400 символов (строго соблюдай этот диапазон).\n"
            f"- Используй <b>жирный текст</b> с <b></b> только для заголовков.\n"
            f"- Никаких ** или * в тексте.\n"
            f"- Добавляй смайлики (🎯, 🚀, 🌟, ✍️) к заголовкам.\n"
            f"- Пиши вдохновляюще, дружелюбно, как наставник.\n"
            f"- Разделяй уроки символом '---'.\n"
            f"- Не указывай время выполнения заданий.\n"
            f"{resource_content if resource_content else 'Если материала нет, создай курс с нуля.'}\n"
            f"{exclude_lessons}"
        )
        response = model.generate_content(prompt).text.strip()
        logger.info(f"Сырой ответ Gemini для курса: {response[:500]}...")
        lessons = [lesson.strip() for lesson in response.split("---") if lesson.strip()]
        if len(lessons) != 7:
            logger.warning(f"Сгенерировано {len(lessons)} уроков вместо 7, корректируем")
            while len(lessons) < 7:
                lessons.append(
                    f"<b>День {len(lessons) + 1}: Дополнительный шаг к '{skill}'</b>\n"
                    f"<b>Краткое введение 🎯</b>: Ты близок к цели '{goal}' — продолжай!\n"
                    f"<b>Основной шаг 🚀</b>: Практикуй '{skill}' каждый день. Не уверен? Задай мне вопрос!\n"
                    f"<b>Практический пример 🌟</b>: Примени '{skill}' в жизни.\n"
                    f"<b>Практическое задание 1 ✍️</b>: Сделай простой шаг.\n"
                    f"<b>Практическое задание 2 ✍️</b>: Закрепи результат.\n"
                    f"💡 Полезный совет: Постоянство — ключ к успеху.\n"
                    f"Не стесняйся задавать вопросы — я здесь, чтобы помочь!\n"
                    f"По любому поводу можешь задать мне вопрос! 🚀\n"
                    f"<b>Спрашивай обо всём! 🤓</b>"
                )
            lessons = lessons[:7]
        return lessons
    except Exception as e:
        logger.error(f"Ошибка генерации курса: {str(e)}")
        return None

def answer_question(question, context=""):
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = (
            f"Ты — наставник с 20-летним опытом. Контекст: {context}\n"
            f"Ответь на вопрос: '{question}'.\n"
            f"Применяй закон 80/20: 20% ключевой информации для 80% понимания.\n"
            f"Текст — 300-500 символов, вдохновляющий и дружелюбный.\n"
            f"Используй <b>жирный текст</b> с <b></b> для ключевых моментов, никаких ** или других символов.\n"
            f"Добавляй смайлики (🎯, 🚀, 🌟, ✍️). Не делай структуру урока, просто ответь."
        )
        response = model.generate_content(prompt).text.strip()
        logger.info(f"Сырой ответ Gemini на вопрос: {response}")
        return response
    except Exception as e:
        logger.error(f"Ошибка при ответе на вопрос: {str(e)}")
        return (
            f"<b>Ой, не переживай!</b> 🎯 Я помогу! Задай вопрос ещё раз, и мы разберёмся вместе. ✍️"
        )

def generate_course_suggestions(skill):
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = (
            f"Ты — эксперт в обучении. Предложи 3 идеи для курсов после '{skill}'. "
            f"Каждая идея — строка (30-50 символов). "
            f"Возвращай только 3 строки без лишнего текста."
        )
        response = model.generate_content(prompt).text.strip().split("\n")
        suggestions = [suggestion.strip() for suggestion in response if suggestion.strip()]
        if len(suggestions) != 3:
            logger.warning(f"Сгенерировано {len(suggestions)} предложений вместо 3, корректируем")
            return suggestions[:3] if len(suggestions) > 3 else suggestions + ["Дополнительный курс"] * (3 - len(suggestions))
        return suggestions
    except Exception as e:
        logger.error(f"Ошибка генерации предложений: {str(e)}")
        return None

def update_lesson(skill, experience, goal, preferences, current_lesson, edit_request, day):
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        current_title = current_lesson.split('\n')[0].replace("<b>", "").replace("</b>", "").split(": ")[1].strip()
        
        # Проверяем базу данных
        resources = get_resources_by_tags(skill.lower())
        resource_content = ""
        if resources:
            resource_content = "Используй следующий материал из базы данных:\n"
            for title, author, res_type, content in resources:
                resource_content += f"- {res_type.capitalize()} '{title}' от {author}: {content[:200]}...\n"
            resource_content += "Интегрируй этот материал в урок, адаптируя под структуру.\n"
        
        prompt = (
            f"Ты — эксперт в обучении с 20-летним опытом. "
            f"Обнови урок по навыку '{skill}' с учётом пожелания: '{edit_request}'. "
            f"Уровень опыта: {experience}. Цель: {goal}. Предпочтения: {preferences}. "
            f"Текущий урок:\n{current_lesson}\n"
            f"Применяй закон 80/20: 20% знаний для 80% результата.\n"
            f"Сохрани заголовок урока: '<b>День {day + 1}: {current_title}</b>'.\n"
            f"### Структура урока\n"
            f"- Урок должен быть в точном формате:\n"
            f"  <b>День X: [Название урока]</b>\n"
            f"  <b>Краткое введение 🎯</b>: 2-3 предложения (почему это важно, с мотивацией).\n"
            f"  <b>Основной шаг 🚀</b>: Ключевая идея, 3-4 совета. В конце ОБЯЗАТЕЛЬНО добавь: 'Не уверен? Задай мне вопрос!'.\n"
            f"  <b>Практический пример 🌟</b>: Реальная ситуация с деталями.\n"
            f"  <b>Практическое задание 1 ✍️</b>: Простое задание с инструкциями.\n"
            f"  <b>Практическое задание 2 ✍️</b>: Задание для закрепления с инструкциями.\n"
            f"  💡 Полезный совет: Короткий и практичный.\n"
            f"  Не стесняйся задавать вопросы — я здесь, чтобы помочь!\n"
            f"  По любому поводу можешь задать мне вопрос! 🚀\n"
            f"  <b>Спрашивай обо всём! 🤓</b>\n"
            f"- Не дублируй заголовки, используй ТОЛЬКО указанный формат.\n"
            f"### Дополнительно\n"
            f"- Сделай акцент на практических шагах для '{edit_request}'.\n"
            f"- Длина: 1800-2400 символов (строго соблюдай этот диапазон).\n"
            f"- Используй <b>жирный текст</b> с <b></b> ТОЛЬКО для заголовков.\n"
            f"- Никаких ** или * в тексте.\n"
            f"- Пиши вдохновляюще и дружелюбно.\n"
            f"{resource_content if resource_content else 'Если материала нет, обнови урок с нуля.'}"
        )
        response = model.generate_content(prompt).text.strip()
        logger.info(f"Сырой ответ Gemini для обновления урока: {response[:500]}...")
        # Проверяем длину
        lesson_length = len(response)
        if lesson_length < 1800 or lesson_length > 2400:
            logger.warning(f"Длина обновлённого урока {lesson_length} символов, ожидалось 1800-2400")
        return response
    except Exception as e:
        logger.error(f"Ошибка обновления урока: {str(e)}")
        return current_lesson

__all__ = ["generate_plan", "generate_course", "answer_question", "generate_course_suggestions", "update_lesson"]