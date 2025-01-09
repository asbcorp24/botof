from flask import Flask, request, render_template, redirect, url_for, send_from_directory
import sqlite3
import json
import os
from math import ceil
from werkzeug.utils import secure_filename
from flask import session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
# Конфигурация
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}
DB_FILE = os.path.join(os.path.dirname(__file__), "bot_buttons.db")
load_dotenv()
SUPERADMIN_USERNAME = os.getenv("SUPERADMIN_USERNAME", "superadmin")
SUPERADMIN_PASSWORD = os.getenv("SUPERADMIN_PASSWORD", "superpassword")
# Получение токена из переменной окружения
VK_TOKEN = os.getenv("VK_TOKEN")

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = os.getenv("SECRET_KEY", "your_default_secret_key")  # Убедитесь, что секретный ключ задан
# Проверка разрешённого расширения файла
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Работа с базой данных
def execute_query(query, args=(), fetchone=False, commit=False):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(query, args)
    data = cursor.fetchone() if fetchone else cursor.fetchall()
    if commit:
        conn.commit()
    conn.close()
    return data
@app.route("/delete_survey_progress/<int:user_id>", methods=["POST"])
def delete_survey_progress(user_id):
    execute_query("DELETE FROM user_survey_progress WHERE user_id = ?", (user_id,), commit=True)
    flash("Запись успешно удалена.", "success")
    return redirect(url_for("view_user_survey_progress"))
    
@app.route("/processed_events")
def view_processed_events():
    """
    Отображает содержимое таблицы processed_events.
    """
    query = "SELECT id, event_id FROM processed_events"
    rows = execute_query(query)

    data = [{"id": row[0], "event_id": row[1]} for row in rows]

    return render_template("processed_events.html", events=data)

@app.route("/user_survey_progress")
def view_user_survey_progress():
    """
    Отображает содержимое таблицы user_survey_progress.
    """
    query = "SELECT user_id, survey_name, current_index, answers,created_at,questions FROM user_survey_progress"
    rows = execute_query(query)

    data = []
    for row in rows:
        answers = json.loads(row[3]) if row[3] else []  # Декодируем JSON-ответы
        data.append({
            "user_id": row[0],
            "survey_name": row[1],
            "current_index": row[2],
            "answers": answers,
            "created_at":row[4],
            "questions":row[5]
        })

    return render_template("user_survey_progress.html", surveys=data)

# Выход из системы
@app.route("/logout")
def logout():
    session.clear()
    flash("Вы вышли из системы.", "info")
    return redirect(url_for("login"))
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        
        if username == SUPERADMIN_USERNAME and password == SUPERADMIN_PASSWORD:
             session["user_id"] = -1
             session["username"] = SUPERADMIN_USERNAME
             flash("Вы вошли как суперадмин!", "success")
             return redirect(url_for("index"))

        user = execute_query("SELECT * FROM users WHERE username = ?", (username,), fetchone=True)
        if user:
           session["user_id"] = user[0]
           session["username"] = user[1]
           flash("Вы успешно вошли в систему!", "success")
           return redirect(url_for("index"))
        else:
           flash("Неверный логин или пароль.", "danger")

    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("username") != SUPERADMIN_USERNAME:
        flash("Доступ запрещён.", "danger")
        return redirect(url_for("login"))

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        hashed_password = generate_password_hash(password)

        try:
            execute_query(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, hashed_password),
                commit=True
            )
            flash("Пользователь успешно добавлен.", "success")
            return redirect(url_for("manage_users"))
        except sqlite3.IntegrityError:
            flash("Пользователь с таким логином уже существует.", "danger")

    return render_template("register.html")

# Управление пользователями (только для суперадмина)
@app.route("/manage_users", methods=["GET", "POST"])
def manage_users():
    if session.get("username") != SUPERADMIN_USERNAME:
        flash("Доступ запрещён.", "danger")
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        try:
            execute_query(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, password),
                commit=True
            )
            flash("Пользователь успешно добавлен.", "success")
        except sqlite3.IntegrityError:
            flash("Пользователь с таким логином уже существует.", "danger")

    users = execute_query("SELECT id, username,password FROM users")
    return render_template("manage_users.html", users=users)

# Удаление пользователя (только для суперадмина)
@app.route("/delete_user/<int:user_id>", methods=["POST"])
def delete_user(user_id):
    if session.get("username") != SUPERADMIN_USERNAME:
        flash("Доступ запрещён.", "danger")
        return redirect(url_for("login"))

    execute_query("DELETE FROM users WHERE id = ?", (user_id,), commit=True)
    flash("Пользователь успешно удалён.", "success")
    return redirect(url_for("manage_users"))





@app.before_request
def require_login():
    app.jinja_env.globals['SUPERADMIN_USERNAME'] = SUPERADMIN_USERNAME
    allowed_routes = ["login", "register", "get_uploaded_file"]
    if "user_id" not in session and request.endpoint not in allowed_routes:
        return redirect(url_for("login"))

def inject_superadmin():
    app.jinja_env.globals['SUPERADMIN_USERNAME'] = SUPERADMIN_USERNAME
# Главная страница
@app.route("/")
def index():
    per_page = 10  # Количество записей на странице
    page = int(request.args.get("page", 1))
    # Подсчёт общего количества записей
    total_buttons = execute_query("SELECT COUNT(*) FROM buttons", fetchone=True)[0]
    total_pages = ceil(total_buttons / per_page)
   
    # Получение записей для текущей страницы
    offset = (page - 1) * per_page
   
    buttons = execute_query(
        "SELECT id, question, response, parent_id, request_type, dop, media_url FROM buttons LIMIT ? OFFSET ?",
        (per_page, offset)
    )
  
    return render_template("index.html", buttons=buttons, current_page=page, total_pages=total_pages)


# Добавление новой кнопки
@app.route("/add", methods=["GET", "POST"])
def add_button():
    if request.method == "POST":
        question = request.form["question"]
        response = request.form["response"]
        parent_id = int(request.form["parent_id"])
        request_type = int(request.form["request_type"])
        dop = request.form["dop"] if request.form["dop"] else None
        media_url = None

        # Обработка файла
        if 'file' in request.files:
            file = request.files['file']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
              # file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file_path = os.path.join(os.path.dirname(__file__), app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                media_url = f"/uploads/{filename}"

        execute_query(
            '''
            INSERT INTO buttons (question, response, parent_id, request_type, dop, media_url)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (question, response, parent_id, request_type, dop, media_url),
            commit=True
        )
        return redirect(url_for("index"))

    buttons = execute_query("SELECT id, question FROM buttons")
    return render_template("add_button.html", buttons=buttons)

# Получение файлов из папки uploads
@app.route("/uploads/<path:filename>")
def get_uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Редактирование кнопки
@app.route("/edit/<int:button_id>", methods=["GET", "POST"])
def edit_button(button_id):
    if request.method == "POST":
        question = request.form["question"]
        response = request.form["response"]
        parent_id = int(request.form["parent_id"])
        request_type = int(request.form["request_type"])
        dop = request.form["dop"] if request.form["dop"] else None
        media_url = request.form["media_url"]

        # Обработка нового файла
        if 'file' in request.files:
            file = request.files['file']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                media_url = f"/uploads/{filename}"

        execute_query(
            '''
            UPDATE buttons
            SET question = ?, response = ?, parent_id = ?, request_type = ?, dop = ?, media_url = ?
            WHERE id = ?
            ''',
            (question, response, parent_id, request_type, dop, media_url, button_id),
            commit=True
        )
        return redirect(url_for("index"))

    button = execute_query("SELECT * FROM buttons WHERE id = ?", (button_id,), fetchone=True)
    return render_template("edit_button.html", button=button)

# Удаление кнопки
@app.route("/delete/<int:button_id>")
def delete_button(button_id):
    execute_query("DELETE FROM buttons WHERE id = ?", (button_id,), commit=True)
    return redirect(url_for("index"))

# Просмотр результатов анкет
@app.route("/results", methods=["GET"])
def survey_results():
    survey_names = [row[0] for row in execute_query("SELECT DISTINCT survey_name FROM survey_results")]
    survey_name = request.args.get("survey_name", "").strip()
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()
    page = int(request.args.get("page", 1))
    per_page = 10  # Количество записей на страницу

    query = "SELECT id, user_id, answers, survey_name, created_at, file_url FROM survey_results WHERE 1=1"
    params = []

    if survey_name:
        query += " AND survey_name = ?"
        params.append(survey_name)
    if start_date:
        query += " AND created_at >= ?"
        params.append(start_date)
    if end_date:
        query += " AND created_at <= ?"
        params.append(end_date)

    # Выполнение основного запроса для подсчёта всех записей
    total_results = len(execute_query(query, params))
    total_pages = ceil(total_results / per_page)

    # Добавление LIMIT и OFFSET для пагинации
    query += " LIMIT ? OFFSET ?"
    params.extend([per_page, (page - 1) * per_page])

    raw_results = execute_query(query, params)

    results = []
    for row in raw_results:
        try:
            answers = json.loads(row[2]) if row[2] else []
        except json.JSONDecodeError:
            answers = []
        parsed_answers = [{"question": a.get("question", "Неизвестный вопрос"), "answer": a.get("answer", "")} for a in answers]
        results.append((row[0], row[1], parsed_answers, row[3], row[4], row[5]))

    return render_template(
        "survey_results.html",
        results=results,
        survey_names=survey_names,
        current_page=page,
        total_pages=total_pages
    )

# Удаление результата анкеты
@app.route("/delete_result/<int:result_id>", methods=["POST"])
def delete_result(result_id):
    execute_query("DELETE FROM survey_results WHERE id = ?", (result_id,), commit=True)
    return redirect(url_for("survey_results"))

# Запуск приложения
if __name__ == "__main__":
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    app.run(debug=True)

