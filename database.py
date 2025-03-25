import sqlite3
from datetime import datetime

def init_db():
    conn = sqlite3.connect('course_craft.db')
    c = conn.cursor()
    # Существующие таблицы
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    skill TEXT,
                    experience TEXT,
                    goal TEXT,
                    preferences TEXT,
                    current_lesson INTEGER DEFAULT 0,
                    course_plan TEXT,
                    course_content TEXT,
                    last_interaction TEXT)''')
    
    # Таблица для книг и статей
    c.execute('''CREATE TABLE IF NOT EXISTS resources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    author TEXT,
                    type TEXT CHECK(type IN ('book', 'article')),
                    content TEXT,
                    tags TEXT)''')
    
    conn.commit()
    conn.close()

def add_resource(title, author, resource_type, content, tags):
    conn = sqlite3.connect('course_craft.db')
    c = conn.cursor()
    c.execute("INSERT INTO resources (title, author, type, content, tags) VALUES (?, ?, ?, ?, ?)",
              (title, author, resource_type, content, tags))
    conn.commit()
    conn.close()

def get_resources_by_tags(tags):
    conn = sqlite3.connect('course_craft.db')
    c = conn.cursor()
    c.execute("SELECT title, author, type, content FROM resources WHERE tags LIKE ?", (f"%{tags}%",))
    results = c.fetchall()
    conn.close()
    return results

def add_user(user_id, skill, experience, goal, preferences):
    conn = sqlite3.connect('course_craft.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, skill, experience, goal, preferences, last_interaction) VALUES (?, ?, ?, ?, ?, ?)",
              (user_id, skill, experience, goal, preferences, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('course_craft.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()
    conn.close()
    return user

def update_user_lesson(user_id, lesson_index, course_plan, course_content):
    conn = sqlite3.connect('course_craft.db')
    c = conn.cursor()
    c.execute("UPDATE users SET current_lesson = ?, course_plan = ?, course_content = ?, last_interaction = ? WHERE user_id = ?",
              (lesson_index, course_plan, course_content, datetime.now().isoformat(), user_id))
    conn.commit()
    conn.close()

def update_user_interaction(user_id):
    conn = sqlite3.connect('course_craft.db')
    c = conn.cursor()
    c.execute("UPDATE users SET last_interaction = ? WHERE user_id = ?",
              (datetime.now().isoformat(), user_id))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()