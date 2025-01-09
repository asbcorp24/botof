from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, CallbackQueryHandler
import os
import json
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN", "your_telegram_token")
DB_FILE = "bot_buttons.db"
UPLOAD_FOLDER = "uploads"

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

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

def start(update: Update, context: CallbackContext):
    buttons = get_buttons_by_parent_id(0)
    keyboard = [
        [InlineKeyboardButton(button[1], callback_data=str(button[0]))] for button in buttons
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Добро пожаловать! Выберите действие:", reply_markup=reply_markup)

def handle_button_click(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    button_id = int(query.data)
    response = execute_query("SELECT response, request_type, dop, media_url FROM buttons WHERE id = ?", (button_id,), fetchone=True)

    if response:
        response_text, request_type, dop, media_url = response
        query.message.reply_text(response_text)

        if request_type == 1:  # Анкета
            questions = json.loads(dop)
            context.user_data['survey'] = {
                'questions': questions,
                'current_index': 0,
                'answers': []
            }
            ask_question(update, context)
        elif media_url:
            context.bot.send_document(chat_id=query.message.chat_id, document=media_url)

        buttons = get_buttons_by_parent_id(button_id)
        if buttons:
            keyboard = [[InlineKeyboardButton(button[1], callback_data=str(button[0]))] for button in buttons]
            query.message.reply_text("Выберите следующий шаг:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        query.message.reply_text("На этом всё!")

def ask_question(update: Update, context: CallbackContext):
    survey = context.user_data['survey']
    question = survey['questions'][survey['current_index']]
    text = question['text']
    options = question.get('sp', '').split(',')

    if options:
        keyboard = [[KeyboardButton(option.strip())] for option in options]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        update.message.reply_text(text, reply_markup=reply_markup)
    else:
        update.message.reply_text(text)

def handle_message(update: Update, context: CallbackContext):
    survey = context.user_data.get('survey')

    if survey:
        answer = update.message.text
        survey['answers'].append(answer)
        survey['current_index'] += 1

        if survey['current_index'] < len(survey['questions']):
            ask_question(update, context)
        else:
            save_survey_result(update.message.chat_id, survey['answers'], "Survey")
            del context.user_data['survey']
            update.message.reply_text("Спасибо за ответы! Анкета завершена.")
    else:
        update.message.reply_text("Я вас не понял. Пожалуйста, используйте меню.")

def save_survey_result(user_id, answers, survey_name):
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    execute_query(
        '''INSERT INTO survey_results (user_id, answers, survey_name, created_at) VALUES (?, ?, ?, ?)''',
        (user_id, json.dumps(answers), survey_name, created_at),
        commit=True
    )

def main():
    updater = Updater(TOKEN)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(handle_button_click))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
