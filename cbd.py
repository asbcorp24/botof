import sqlite3
def create_users_table():
    conn = sqlite3.connect("bot_buttons.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL  )
    ''')

    conn.commit()
    conn.close()
    print("table users")
def create_survey():
    """
    Удаляет таблицу user_survey_progress, если существует, и создаёт её заново.
    """
    conn = sqlite3.connect("bot_buttons.db")
    cursor = conn.cursor()

    try:

        # Создаём таблицу заново
        cursor.execute(
            '''
            CREATE TABLE user_survey_progress (
                user_id INTEGER PRIMARY KEY,
                survey_name TEXT,
                current_index INTEGER,
                answers TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                questions TEXT
            );
            '''
        )
        conn.commit()
        print("Таблица user_survey_progress успешно пересоздана!")
    except sqlite3.Error as e:
        print(f"Ошибка при создании таблицы: {e}")
    finally:
        conn.close()   
def create_event():
	conn = sqlite3.connect("bot_buttons.db")
	cursor = conn.cursor()
	cursor.execute("""
        CREATE TABLE IF NOT EXISTS processed_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT UNIQUE
     )""")
	conn.commit()
	print(f"Эвенты созданы")
def get_parent_id(user_id):
    """
    Возвращает parent_id для текущего пользователя.
    """
    query = """
        SELECT parent_id 
        FROM buttons 
        WHERE id = (
            SELECT MAX(id) 
            FROM user_survey_progress
            WHERE user_id = ?
        )
    """
    result = execute_query(query, (user_id,), fetchone=True)
    return result[0] if result else 0
def create_database():
    conn = sqlite3.connect("bot_buttons.db")
    cursor = conn.cursor()

    # Таблица для кнопок
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS buttons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,            -- Текст вопроса или кнопки
            response TEXT NOT NULL,            -- Ответ на кнопку
            parent_id INTEGER DEFAULT 0,       -- Родительский ID
            request_type INTEGER DEFAULT 0,    -- Тип запроса (0 = стандартный, 1 = анкета)
            dop TEXT DEFAULT NULL,             -- Дополнительные данные (JSON для анкеты)
            media_url TEXT DEFAULT NULL        -- Ссылка на медиа (картинка или документ)
        )
    ''')

    # Таблица для результатов анкет
    cursor.execute('DROP TABLE IF EXISTS survey_results')

    # Создание таблицы survey_results с новыми изменениями
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS survey_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,          -- ID пользователя, заполнившего анкету
            answers TEXT NOT NULL,             -- Ответы в формате JSON
            file_url TEXT DEFAULT NULL,        -- Ссылка на загруженный файл (если есть)
            survey_name TEXT DEFAULT NULL,     -- Название анкеты
            can_repeat INTEGER DEFAULT 1,     -- Можно ли повторно проходить анкету (1 = да, 0 = нет)
            created_at TEXT DEFAULT CURRENT_TIMESTAMP -- Дата и время заполнения анкеты
        )
    ''')

    conn.commit()
    conn.close()
    print("База данных успешно создана!")

def seed_database():
    conn = sqlite3.connect("bot_buttons.db")
    cursor = conn.cursor()

    # Пример стандартных кнопок
    buttons = [
        (1, "Главное меню", "Выберите опцию:", 0, 0, None, None),
        (2, "Расписание", "Вот ваше расписание:\n1. Математика\n2. Физика", 1, 0, None, None),
        (3, "Контакты", "Контакты школы:\nТелефон: 123-456-789\nE-mail: school@example.com", 1, 0, None, None),
        (4, "Анкета", "Пожалуйста, заполните анкету:", 1, 1, '''
        [
            {"text": "Ваше имя?", "answer_type": 1},
            {"text": "Введите вашу дату рождения (YYYY-MM-DD):", "answer_type": 2},
            {"text": "Введите ваш возраст:", "answer_type": 3},
            {"text": "Загрузите ваше фото:", "answer_type": 4},
            {"text": "Загрузите документ в формате PDF:", "answer_type": 5}
        ]
        ''', None)
    ]

    cursor.executemany('''
        INSERT INTO buttons (id, question, response, parent_id, request_type, dop, media_url)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', buttons)

    conn.commit()
    conn.close()
    print("Демо-данные успешно добавлены!")
def create_users_table():
    conn = sqlite3.connect("bot_buttons.db")
    cursor = conn.cursor()

    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,   -- Логин пользователя
            password TEXT NOT NULL          -- Пароль (в зашифрованном виде)
        )
    ''')

    # Добавление демо-данных
    demo_users = [
        ("admin", "admin123"),  # Логин: admin, Пароль: admin123
        ("user", "user123")  # Логин: user, Пароль: user123
    ]

    try:
        cursor.executemany("INSERT INTO users (username, password) VALUES (?, ?)", demo_users)
    except sqlite3.IntegrityError:
        print("Демо-данные уже существуют.")

    conn.commit()
    conn.close()
    print("Таблица users успешно создана и заполнена демо-данными!")




if __name__ == "__main__":
 # create_database()
 # seed_database()
 # create_users_table()
 # create_survey()
 #create_event()
 create_database();
  