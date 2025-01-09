import os
import json
import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from werkzeug.utils import secure_filename
from datetime import datetime
import sqlite3
from dotenv import load_dotenv
import uuid
import re
import requests
# Загрузка переменных окружения из .env файла
load_dotenv()

# Получение токена из переменной окружения
VK_TOKEN = os.getenv("VK_TOKEN")

# Конфигурация
UPLOAD_FOLDER = "uploads"
USER_FOLDER = os.path.join(UPLOAD_FOLDER, "user")
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}

# Убедитесь, что папка uploads/user существует
if not os.path.exists(USER_FOLDER):
    os.makedirs(USER_FOLDER)

user_survey_progress = {}  # Временное хранилище для анкет
DB_FILE = "bot_buttons.db"

# Проверка допустимого расширения

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

def get_buttons_by_parent_id(parent_id):
    return execute_query("SELECT id, question, request_type, dop, media_url FROM buttons WHERE parent_id = ?", (parent_id,))

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
    return save_path

def handle_user_attachment(vk, event):
    """Обрабатывает вложения пользователя и сохраняет их в папку user."""
    attachment = event.attachments
    if attachment and "attach1_type" in attachment:
        attach_type = attachment["attach1_type"]
        attach_key = attachment["attach1"]

        if attach_type == "photo":
            message_id = event.message_id
            message_data = vk.messages.getById(message_ids=message_id)["items"][0]
            photo_data = message_data["attachments"][0]["photo"]["sizes"][-1]["url"]
            response = requests.get(photo_data)
            file_path = save_user_file(response.content, "jpg")
            return file_path

        elif attach_type == "doc":
            message_id = event.message_id
            message_data = vk.messages.getById(message_ids=message_id)["items"][0]
            document = message_data["attachments"][0]["doc"]
            if document["ext"] in ALLOWED_EXTENSIONS:
                response = requests.get(document["url"])
                file_path = save_user_file(response.content, document["ext"])
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
        random_id=0,
        attachment=attachment
    )

def send_message_with_keyboard(vk, user_id, message, buttons):
    """Отправляет сообщение с кнопками и обрабатывает media_url."""
    keyboard = VkKeyboard(one_time=True)
    for i, (button_id, button_text, request_type, dop, media_url) in enumerate(buttons):
        keyboard.add_button(button_text, color=VkKeyboardColor.PRIMARY)
        if i < len(buttons) - 1:
            keyboard.add_line()

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
        random_id=0,
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
    """
    Обрабатывает ответы пользователя в анкете.
    Проверяет ответ в зависимости от типа вопроса.
    """
    current_question = survey["questions"][survey["current_index"]]
    question_text = current_question["text"]
    answer_type = current_question["answer_type"]

    if event.attachments:
        if "photo" == event.attachments.get('attach1_type') and answer_type == 4:
            # Обработка фото
            photo_url = get_attachment_photo_url(vk, event)
            photo_url=handle_user_attachment(vk, event)
            survey["answers"].append({"question": question_text, "answer": photo_url})
        elif "doc" == event.attachments.get('attach1_type') and answer_type == 5:
            # Обработка PDF
            message_id = event.message_id
            message_data = vk.messages.getById(message_ids=message_id)["items"][0]

            document = message_data["attachments"][0]["doc"]
            if document["ext"] == "pdf":
                pdf_url = document["url"]
                photo_url=handle_user_attachment(vk, event)
                survey["answers"].append({"question": question_text, "answer": photo_url})
            else:
                vk.messages.send(user_id=user_id, message="Пожалуйста, загрузите корректный PDF-документ.", random_id=0)
                return
        else:
            vk.messages.send(user_id=user_id, message="Неверный тип вложения.", random_id=0)
            return
    else:
        # Текстовые ответы
        user_answer = event.text
        if validate_answer(user_answer, answer_type):
            survey["answers"].append({"question": question_text, "answer": user_answer})
        else:
            vk.messages.send(user_id=user_id, message=f"Неверный формат ответа. Повторите вопрос: {question_text}", random_id=0)
            return

    # Переход к следующему вопросу
    survey["current_index"] += 1
    if survey["current_index"] < len(survey["questions"]):
        next_question = survey["questions"][survey["current_index"]]["text"]
        vk.messages.send(user_id=user_id, message=next_question, random_id=0)
    else:
        # Завершение анкеты

        save_survey_result(user_id, survey["answers"], survey["survey_name"])
        del user_survey_progress[user_id]
        vk.messages.send(user_id=user_id, message="Спасибо за ответы! Анкета завершена.", random_id=0)

def main():
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    longpoll = VkLongPoll(vk_session)

    print("Бот запущен...")

    for event in longpoll.listen():
        if event.type == VkEventType.MESSAGE_NEW and event.to_me:
            user_id = event.user_id

            # Если пользователь в процессе анкеты
            if user_id in user_survey_progress:
                survey = user_survey_progress[user_id]
                handle_survey_response(vk, user_id, survey, event)
                continue

            # Обработка кнопок
            response = get_response_by_text(event.text)
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
                        "survey_name": survey_name
                    }
                    vk.messages.send(user_id=user_id, message=questions[0]["text"], random_id=0)
                else:
                    buttons = get_buttons_by_parent_id(response_id)
                    if buttons:
                        send_message_with_keyboard(vk, user_id, "Выберите следующий шаг:", buttons)
                    else:
                        vk.messages.send(user_id=user_id, message="На этом всё!", random_id=0)
                        buttons = get_buttons_by_parent_id(0)  # Главное меню
                        send_message_with_keyboard(vk, user_id, "Возвращаемся в главное меню:", buttons)
            else:
                # Показываем главное меню
                buttons = get_buttons_by_parent_id(0)
                send_message_with_keyboard(vk, user_id, "Я вас не понял. Вот главное меню:", buttons)

if __name__ == "__main__":
    main()
