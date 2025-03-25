from database import init_db, add_resource

def load_resources_from_file(filename):
    init_db()  # Убеждаемся, что база создана
    
    with open(filename, 'r', encoding='utf-8') as file:
        lines = [line.strip() for line in file.readlines() if line.strip()]
        
        # Разбиваем на блоки по 5 строк (title, author, type, content, tags)
        for i in range(0, len(lines), 5):
            if i + 4 < len(lines):  # Проверяем, что блок полный
                title = lines[i]
                author = lines[i + 1]
                resource_type = lines[i + 2]
                content = lines[i + 3]
                tags = lines[i + 4]
                
                # Проверка формата
                if resource_type not in ["book", "article"]:
                    print(f"Ошибка: '{title}' имеет неверный тип '{resource_type}'. Пропускаем.")
                    continue
                if len(content) > 500:
                    print(f"Ошибка: '{title}' имеет содержание длиннее 500 символов. Обрезаем.")
                    content = content[:500]
                
                # Добавляем в базу
                add_resource(title, author, resource_type, content, tags)
                print(f"Добавлен ресурс: {title}")
            else:
                print("Ошибка: файл содержит неполный блок данных. Проверьте формат.")

if __name__ == "__main__":
    try:
        load_resources_from_file("resources.txt")
        print("Все ресурсы успешно загружены в базу!")
    except FileNotFoundError:
        print("Ошибка: файл 'resources.txt' не найден. Создайте его и добавьте книги.")
    except Exception as e:
        print(f"Ошибка при загрузке: {str(e)}")