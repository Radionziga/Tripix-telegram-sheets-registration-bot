import logging
import os # Импортируем модуль os для работы с переменными окружения
import json # Импортируем json для парсинга ключа сервисного аккаунта

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import asyncio # Импортируем asyncio для run_until_disconnected, хотя для long polling не всегда нужно явно, но полезно

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# Отключаем логирование для google-auth-library, чтобы избежать излишнего вывода в консоль
logging.getLogger('google_auth_httplib2').setLevel(logging.WARNING)
logging.getLogger('google_auth_oauthlib.flow').setLevel(logging.WARNING)

# --- КОНФИГУРАЦИЯ ---
# Получаем токен Telegram-бота из переменной окружения
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен в переменных окружения!")

# Получаем ID Google Sheet из переменной окружения
SPREADSHEET_ID = os.getenv('GOOGLE_SHEET_ID')
if not SPREADSHEET_ID:
    raise ValueError("GOOGLE_SHEET_ID не установлен в переменных окружения!")

# Получаем JSON-строку сервисного аккаунта из переменной окружения
GOOGLE_CREDENTIALS_JSON = os.getenv('GOOGLE_CREDENTIALS_JSON')
if not GOOGLE_CREDENTIALS_JSON:
    raise ValueError("GOOGLE_CREDENTIALS_JSON не установлен в переменных окружения!")

# Константы для Google Sheets
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
RANGE_NAME = 'Sheet1!A:C'  # Диапазон для записи (измените, если нужно)

# Инициализация учетных данных для Google Sheets API
try:
    # Декодируем JSON-строку в Python-словарь
    service_account_info = json.loads(GOOGLE_CREDENTIALS_JSON)
    credentials = Credentials.from_service_account_info(
        service_account_info, scopes=SCOPES)
    service = build('sheets', 'v4', credentials=credentials)
    sheet = service.spreadsheets()
    print("Google Sheets API успешно инициализирован.")
except Exception as e:
    print(f"Ошибка инициализации Google Sheets API: {e}")
    print("Убедитесь, что GOOGLE_CREDENTIALS_JSON корректно установлен и имеет корректные права доступа к таблице.")
    # Критическая ошибка, если API не инициализирован
    exit(1) # Завершаем выполнение скрипта, если не можем подключиться к Sheets

# Состояния для ConversationHandler
NAME, EMAIL = range(2)

# Настройка логирования для Telegram-бота
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинает диалог регистрации."""
    await update.message.reply_text("Привет! Давай зарегистрируемся. Как тебя зовут?")
    return NAME

async def name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ввод имени пользователя."""
    context.user_data['name'] = update.message.text
    await update.message.reply_text("Отлично! Теперь введи свой email.")
    return EMAIL

async def email_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ввод email и записывает данные в Google Sheets."""
    context.user_data['email'] = update.message.text

    # Записываем данные в Google Sheets
    values = [[
        context.user_data.get('name'),
        context.user_data.get('email'),
        update.message.from_user.id  # Добавляем ID пользователя Telegram
    ]]

    body = {'values': values}
    try:
        sheet.values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=RANGE_NAME,
            valueInputOption='RAW',
            body=body
        ).execute()
        await update.message.reply_text("Спасибо, ты зарегистрирован!")
        logger.info(f"Пользователь {context.user_data.get('name')} ({update.message.from_user.id}) успешно зарегистрирован.")
    except Exception as e:
        logger.error(f"Ошибка при записи в Google Sheets: {e}")
        await update.message.reply_text("Произошла ошибка при регистрации. Пожалуйста, попробуй еще раз.")
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменяет процесс регистрации."""
    await update.message.reply_text("Регистрация отменена.")
    return ConversationHandler.END

if __name__ == '__main__':
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_handler)],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, email_handler)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(conv_handler)

    print("Бот запущен. Ожидание сообщений...")
    # Используем run_polling() для получения обновлений
    application.run_polling()