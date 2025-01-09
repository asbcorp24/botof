from vk_api.keyboard import VkKeyboard, VkKeyboardColor
import json
from werkzeug.utils import secure_filename
import os
from datetime import datetime
import sqlite3
from dotenv import load_dotenv
import uuid
import re
import requests
from flask import Flask, request, jsonify
import vk_api
import sys
import io
import logging
import time






sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
# Получаем директорию текущего файла
current_dir = os.path.dirname(os.path.abspath(__file__))

# Путь к лог-файлу в текущей директории проекта
log_path = os.path.join(current_dir, "app.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_path, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)

# Загрузка переменных окружения из .env файла
load_dotenv()

# Получение токена из переменной окружения
VK_TOKEN = os.getenv("VK_TOKEN","vk1.a.6XR1Ly_CiS3mmbmxf0KHW6sEF0EVJuuLUlXhL1G8CQb9sLlYbiCCIJa07r0ujtVdx2xen_Tv78E_rMB6VppJqJnjFAtaPgwxHl2j06kt3BHOokcjZAEE83aIJrdIgiubeSj6gzKRDJY0le3jsp5pVqAjsOcZd3uucFQg8YbJERGE1_WMIGO7dBlojQ2jjq15WWNF0FcPqJmbgSGSC2cdDg")
CONFIRMATION_TOKEN ="b1a46b98"# os.getenv("CONFIRMATION_TOKEN","bf734f61")
# Конфигурация
UPLOAD_FOLDER =  os.path.join(current_dir, "uploads")
USER_FOLDER = os.path.join(UPLOAD_FOLDER, "user")
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}
app = Flask(__name__)
app.secret_key =os.getenv("secret_key","your_secret_key")

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# Убедитесь, что папка uploads/user существует
if not os.path.exists(USER_FOLDER):
   os.makedirs(USER_FOLDER)

user_survey_progress = {}  # Временное хранилище для анкет
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_buttons.db")
#DB_FILE = "bot_buttons.db"


processed_events = set()

def is_event_processed(event_id):
    # Проверка на наличие события в таблице
    query = "SELECT 1 FROM processed_events WHERE event_id = ?"
    if execute_query(query, (event_id,), fetchone=True):
        return True
    
    # Вставка нового события
    execute_query("INSERT INTO processed_events (event_id) VALUES (?)", (event_id,), commit=True)
    
    # Удаление старых записей, если количество превышает 100
    count_query = "SELECT COUNT(*) FROM processed_events"
    count = execute_query(count_query, fetchone=True)[0]
    if count > 100:
        delete_query = """
        DELETE FROM processed_events
        WHERE id IN (
            SELECT id FROM processed_events
            ORDER BY id ASC
            LIMIT ?
        )
        """
        execute_query(delete_query, (count - 100,), commit=True)
    
    return False
#def is_event_processed(event_id):
	
#    logging.info(f"Processing event_id: {event_id}")
#    if event_id in processed_events:
#        return True
#    processed_events.add(event_id)
#    return False
# Проверка допустимого расширения

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS



def save_survey_progress(user_id, survey_name, current_index, answers,questions):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    execute_query("DELETE FROM user_survey_progress WHERE user_id = ?", (user_id,), commit=True)
    logging.info(f"SAVE CURRENT")
    execute_query(
        '''
        INSERT OR REPLACE INTO user_survey_progress (user_id, survey_name, current_index, answers,created_at,questions)
        VALUES (?, ?, ?, ?,?,?)
        ''',
        (user_id, survey_name, current_index, json.dumps(answers),current_time,json.dumps(questions)),
        commit=True
    )

def load_survey_progress(user_id):
    logging.info(f"uid:{user_id}")
    row = execute_query(
        """
        SELECT survey_name, current_index, answers, questions 
        FROM user_survey_progress 
        WHERE user_id = ?
        ORDER BY user_survey_progress.rowid DESC
		LIMIT 1;
        """,
        (user_id,), fetchone=True
    )
    if row:
        return {
            "survey_name": row[0],
            "current_index": row[1],
            "answers": json.loads(row[2]),
            "questions": json.loads(row[3])  # Восстанавливаем вопросы из колонки dop
        }
    return None


def delete_survey_progress(user_id):
    execute_query("DELETE FROM user_survey_progress WHERE user_id = ?", (user_id,), commit=True)


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

def get_buttons_by_parent_id(parent_id):
    return execute_query("SELECT id, question, request_type, dop, media_url,parent_id FROM buttons WHERE parent_id = ?", (parent_id,))

def get_response_by_text(user_text):
    return execute_query("SELECT id, response, request_type, dop, media_url FROM buttons WHERE question LIKE ?", (f"%{user_text}%",), fetchone=True)

# Загрузка файлов в VK

def upload_photo(vk, user_id, file_path):
    upload = vk_api.VkUpload(vk)
    photo = upload.photo_messages(file_path)[0]
    return f"photo{photo['owner_id']}_{photo['id']}"

def upload_document(vk, user_id, file_path):
    """Загружает документ в сообщения VK."""
    upload = vk_api.VkUpload(vk)
    try:
        response = upload.document_message(file_path, peer_id=user_id)
        print(response)  # Отладочный вывод для проверки структуры
        doc = response.get('doc', {})  # Извлекаем вложенный объект 'doc'
        return f"doc{doc['owner_id']}_{doc['id']}"  # Формируем идентификатор документа
    except KeyError as e:
        print(f"Ошибка загрузки документа: {e}")
        return None

# Обработка вложений

def save_user_file(file_data, file_extension):
    """Сохраняет вложение пользователя в папку user с уникальным именем."""
    unique_filename = f"{uuid.uuid4()}.{file_extension}"
    save_path = os.path.join(USER_FOLDER, unique_filename)
    with open(save_path, "wb") as f:
        f.write(file_data)
    return unique_filename

def handle_user_attachment(vk, event):
    """Обрабатывает вложения пользователя и сохраняет их в папку user."""
    attachments = event.get("attachments", [])
    if attachments:
        attachment = attachments[0]  # Берем первое вложение
        attach_type = attachment.get("type")
        
        if attach_type == "photo":
            photo = attachment.get("photo", {})
            sizes = photo.get("sizes", [])
            if sizes:
                # Берем URL самого большого изображения
                photo_url = sizes[-1].get("url")
                if photo_url:
                    response = requests.get(photo_url)
                    file_path = save_user_file(response.content, "jpg")
                    return file_path

        elif attach_type == "doc":
            document = attachment.get("doc", {})
            if document.get("ext") in ALLOWED_EXTENSIONS:
                doc_url = document.get("url")
                if doc_url:
                    response = requests.get(doc_url)
                    file_path = save_user_file(response.content, document.get("ext"))
                    return file_path

    return None
# Отправка сообщений

def send_message(vk, user_id, message, media_url=None):
    """Отправляет сообщение с вложением, если media_url не пустой."""
    attachment = None
    if media_url:
        if media_url.startswith("http"):
            attachment = media_url
        else:
            file_path = os.path.join(UPLOAD_FOLDER, os.path.basename(media_url))
            if os.path.exists(file_path):
                if media_url.endswith(('.png', '.jpg', '.jpeg', '.gif')):
                    attachment = upload_photo(vk, user_id, file_path)
                elif media_url.endswith('.pdf'):
                    attachment = upload_document(vk, user_id, file_path)

    vk.messages.send(
        user_id=user_id,
        message=message,
        random_id=int(time.time()),
        attachment=attachment
    )

def send_message_with_keyboard(vk, user_id, message, buttons):
    """Отправляет сообщение с кнопками и обрабатывает media_url."""
    keyboard = VkKeyboard(one_time=True)
    logging.info(f"message keyb: {message}")
    for i, (button_id, button_text, request_type, dop, media_url,parent_id) in enumerate(buttons):
        keyboard.add_button(button_text, color=VkKeyboardColor.PRIMARY)
        if i < len(buttons) - 1:
            keyboard.add_line()
    if buttons and buttons[0][-1] > 0:  # Предполагается, что parent_id — последний элемент в кортеже
        keyboard.add_line()  # Размещаем кнопку 'Назад' на новой строке
        keyboard.add_button("Назад", color=VkKeyboardColor.NEGATIVE,payload=[buttons[0][-1]])
    attachment = None
    if media_url:
        if media_url.startswith("http"):
            attachment = media_url
        else:
            file_path = os.path.join(UPLOAD_FOLDER, os.path.basename(media_url))
            if os.path.exists(file_path):
                if media_url.endswith(('.png', '.jpg', '.jpeg', '.gif')):
                    attachment = upload_photo(vk, user_id, file_path)
                elif media_url.endswith('.pdf'):
                    attachment = upload_document(vk, user_id, file_path)

    vk.messages.send(
        user_id=user_id,
        message=message,
        random_id=0,#int(time.time()),
        keyboard=keyboard.get_keyboard(),
        attachment=attachment
    )
  
def get_attachment_photo_url(vk, event):
        """
        Извлекает URL фото из вложений сообщения через messages.getById.
        """
        try:
            message_id = event.message_id
            message_data = vk.messages.getById(message_ids=message_id)["items"][0]
            attachment = message_data["attachments"][0]
            if attachment["type"] == "photo":
                # Получаем URL самого крупного размера
                photo_url = attachment["photo"]["sizes"][-1]["url"]
                return photo_url
        except Exception as e:
            print(f"Ошибка получения фото: {e}")
            return None


def save_survey_result(user_id, answers, survey_name, file_url=None):
    """
    Сохраняет результаты анкеты. Сохраняет вопросы и ответы в формате JSON.
    """
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    execute_query(
        '''
        INSERT INTO survey_results (user_id, answers, file_url, survey_name, created_at)
        VALUES (?, ?, ?, ?, ?)
        ''',
        (user_id, json.dumps(answers), file_url, survey_name, created_at),
        commit=True
    )
def validate_answer(answer, answer_type):
    """
    Проверяет ответ пользователя в зависимости от ожидаемого типа.
    """
    if answer_type == 1:  # Текст
        return isinstance(answer, str) and len(answer) > 0
    elif answer_type == 2:  # Дата (формат YYYY-MM-DD)
        return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", answer))
    elif answer_type == 3:  # Число
        return answer.isdigit()
    elif answer_type == 4:  # Рисунок
        return answer.startswith("photo")  # Проверяем формат ID фото
    elif answer_type == 5:  # PDF
        return answer.endswith(".pdf")  # Проверяем формат URL
    return False


# Основная логика бота
def handle_survey_response(vk, user_id, survey, event):
    current_question = survey["questions"][survey["current_index"]]
    question_text = current_question["text"]
    answer_type = current_question["answer_type"]

    # Обработка вложений
    attachments = event.get("attachments", [])
    logging.info(f"ptatt {attachments}")
    geo = event.get("geo")  # Получаем объект geo, если он есть
    geo = event.get("geo")
    if answer_type == 6:
        if not geo:  # Если геолокация отсутствует, отправляем кнопку для отправки местоположения
            keyboard = VkKeyboard(one_time=True)
            keyboard.add_location_button()  # Добавляем кнопку местоположения

            vk.messages.send(
                user_id=user_id,
                message=f"{question_text} (нажмите на кнопку, чтобы отправить координаты)",
                random_id=0,
                keyboard=keyboard.get_keyboard()  # Передаем клавиатуру
            )
            return "ok"  # Ждем от пользователя координаты через кнопку
        else:  # Если геолокация присутствует, обрабатываем её
            location = geo.get("coordinates", {})
            latitude = location.get("latitude")
            longitude = location.get("longitude")

            if latitude and longitude:
                # Сохраняем местоположение в ответы анкеты
                survey["answers"].append({
                    "question": question_text,
                    "answer": f"latitude: {latitude}, longitude: {longitude}"
                })
            else:
                vk.messages.send(user_id=user_id, message="Не удалось получить координаты. Попробуйте еще раз.", random_id=0)
                return "ok"
   
   
    if attachments:
        attach_type = attachments[0].get("type")
        logging.info(f"это {attach_type}")
        if attach_type == "photo" and answer_type == 4:
            photo_url = attachments[0]["photo"]["sizes"][-1]["url"]
            photo_url=handle_user_attachment(vk, event)
            survey["answers"].append({"question": question_text, "answer": photo_url})
        elif attach_type == "doc" and answer_type == 5:
            document = attachments[0].get("doc", {})
            if document.get("ext") == "pdf":
                photo_url=handle_user_attachment(vk, event)
                survey["answers"].append({"question": question_text, "answer": photo_url})
            else:
                vk.messages.send(user_id=user_id, message="Пожалуйста, загрузите корректный PDF-документ.", random_id=0)
                return "ok"
        else:
            vk.messages.send(user_id=user_id, message="Неверный тип вложения.", random_id=0)
            return "ok"
    if not geo and not attachments:
        # Обработка текстового ответа
        user_answer = event.get("text", "")
        logging.info(f"answer_type {answer_type}");
        if answer_type == 7:
            # Проверяем, является ли текст пользователя допустимым выбором из списка
           
            options = current_question.get("sp", "").split(",")
            if user_answer in [option.strip() for option in options]:
              survey["answers"].append({"question": question_text, "answer": user_answer})
            else:
               vk.messages.send(user_id=user_id, message=f"Неверный выбор. Пожалуйста, выберите один из доступных вариантов: {', '.join(options)}", random_id=0)
               return "ok"

        elif validate_answer(user_answer, answer_type):
            survey["answers"].append({"question": question_text, "answer": user_answer})
        else:
            vk.messages.send(user_id=user_id, message=f"Неверный формат ответа. Повторите вопрос: {question_text}", random_id=0)
            return "ok"

    # Переход к следующему вопросу
    survey["current_index"] += 1
    if survey["current_index"] < len(survey["questions"]):
        next_question = survey["questions"][survey["current_index"]]["text"]
        next_question2 = survey["questions"][survey["current_index"]]
        answer_type = next_question2["answer_type"]  
        if answer_type == 7:
           # Разбиваем содержимое "sp" на список кнопок
            options = next_question2.get("sp", "").split(",")
            keyboard = VkKeyboard(one_time=True)
            for i, option in enumerate(options):
              keyboard.add_button(option.strip(), color=VkKeyboardColor.PRIMARY)
           # После каждой 4-й кнопки добавляем новую строку
              if (i + 1) % 4 == 0 and i != len(options) - 1:
                 keyboard.add_line()

            vk.messages.send(
              user_id=user_id,
              message=f"{question_text} (выберите один из вариантов ниже)",
              random_id=0,
              keyboard=keyboard.get_keyboard()
              )
            save_survey_progress(user_id, survey["survey_name"], survey["current_index"], survey["answers"], survey["questions"])
            return "ok" 
        
        
        
        
        vk.messages.send(user_id=user_id, message=next_question, random_id=0)
        save_survey_progress(user_id, survey["survey_name"], survey["current_index"], survey["answers"], survey["questions"])
        return "ok"
    else:
        # Завершение анкеты
        save_survey_result(user_id, survey["answers"], survey["survey_name"])
        delete_survey_progress(user_id)
        #vk.messages.send(user_id=user_id, message="Спасибо за ответы! Анкета завершена.", random_id=0)
        buttons = get_buttons_by_parent_id(0)  # Главное меню
        send_message_with_keyboard(vk, user_id, "Спасибо за ответы! Анкета завершена.", buttons)
        return "ok"
# Обработка Webhook
def get_parent_id(user_id):
    """
    Возвращает parent_id для текущего пользователя.
    """
    query = """
        SELECT parent_id 
        FROM buttons 
        WHERE id = ?
    """
    result = execute_query(query, (user_id,), fetchone=True)
    if result :
    	logging.info(f"parent {user_id}")
    return result[0] if result else 0


@app.route("/", methods=["GET","POST"])
def webhook():
    if request.method == "GET":
        return request.data, 200

    if request.method == "POST":
        data = request.get_json(force=True, silent=True)
        if not data:
            return "No data", 400

        event_id = data.get("event_id")
        if is_event_processed(event_id):
            return "ok"

        # Подтверждение сервера
        if data.get("type") == "confirmation":
            return CONFIRMATION_TOKEN, 200

        tp = data.get("type")
        if tp not in ["message_new"]:
            return "ok"

        logging.info(f"Body: {request.data.decode('utf-8')}")
        logging.info(f"type: {tp}")
        if tp == "message_new":
            vk_session = vk_api.VkApi(token=VK_TOKEN)
            vk = vk_session.get_api()

            event = data["object"]["message"]
            user_id = event["from_id"]
            text = event["text"]
            logging.info(f"text: {text}")

            survey = load_survey_progress(user_id)
            if survey:
                handle_survey_response(vk, user_id, survey, event)
                return "ok"

            attachments = event.get("attachments", [])
            if attachments:
                logging.info(f"Сообщение с вложением: {attachments}")
                return "ok"

            if text == "Назад":
                payload = event.get("payload")
                previous_parent_id = get_parent_id(payload)
                buttons = get_buttons_by_parent_id(previous_parent_id)
                if buttons:
                    send_message_with_keyboard(vk, user_id, "Выберите предыдущий шаг:", buttons)
                else:
                    buttons = get_buttons_by_parent_id(0)
                    send_message_with_keyboard(vk, user_id, "Выберите следующий шаг:", buttons)
            else:
                response = get_response_by_text(text)
                if response:
                    response_id, response_text, request_type, dop, media_url = response
                    send_message(vk, user_id, response_text, media_url)
                    if request_type == 1:  # Режим анкеты
                        questions = json.loads(dop)
                        survey_name = questions[0]["text"]
                        user_survey_progress[user_id] = {
                            "questions": questions,
                            "current_index": 0,
                            "answers": [],
                            "survey_name": survey_name,
                        }
                        save_survey_progress(user_id, survey_name, 0, [], questions)
                        atp = questions[0]["answer_type"]
                        if atp == 7:
                            options = questions[0].get("sp", "").split(",")
                            keyboard = VkKeyboard(one_time=True)
                            for i, option in enumerate(options):
                                keyboard.add_button(option.strip(), color=VkKeyboardColor.PRIMARY)
                                if (i + 1) % 4 == 0 and i != len(options) - 1:
                                    keyboard.add_line()

                            vk.messages.send(
                                user_id=user_id,
                                message=f"{questions[0]['text']} (выберите один из вариантов ниже)",
                                random_id=0,
                                keyboard=keyboard.get_keyboard(),
                            )
                            return "ok"
                        else:
                            vk.messages.send(
                                user_id=user_id,
                                message=questions[0]["text"],
                                random_id=0,
                            )
                            return "ok"
                    else:
                        buttons = get_buttons_by_parent_id(response_id)
                        if buttons:
                            send_message_with_keyboard(vk, user_id, "Выберите следующий шаг:", buttons)
                        else:
                            buttons = get_buttons_by_parent_id(0)
                            send_message_with_keyboard(vk, user_id, "На этом всё!", buttons)
                else:
                    buttons = get_buttons_by_parent_id(0)
                    send_message_with_keyboard(vk, user_id, "Я вас не понял. Вот главное меню:", buttons)
        return "ok"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
