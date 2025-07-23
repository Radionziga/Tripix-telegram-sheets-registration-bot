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
# !!! ИСПРАВЛЕНИЕ ДИАПАЗОНА: УКАЗЫВАЕМ ТОЛЬКО ИМЯ ЛИСТА ДЛЯ ОПЕРАЦИИ APPEND !!!
# Убедитесь, что ваш лист в Google Sheets действительно называется "Sheet1".
# Если нет, измените "Sheet1" на точное название вашего листа (например, "Регистрации").
RANGE_NAME = 'Sheet1'

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
    # Критическая ошибка, если API не инициализирован, завершаем выполнение скрипта
    exit(1)

# Состояния для ConversationHandler
# Переименовал NAME в AGENCY_NAME для ясности, так как теперь это название турагентства
# Изменил EMAIL на PHONE_NUMBER
AGENCY_NAME, PHONE_NUMBER = range(2)

# Настройка логирования для Telegram-бота
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Начинает диалог регистрации с приветственным сообщением
    и запросом названия турагентства.
    """
    welcome_message = "Это бот для регистрации Tripix Parser — расширения, которое помогает удобно собирать данные о турах.\nЧтобы начать, пожалуйста, введите название вашего турагентства."
    await update.message.reply_text(welcome_message)
    return AGENCY_NAME # Переходим в состояние AGENCY_NAME, чтобы получить название агентства

async def agency_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает ввод названия турагентства и запрашивает номер телефона.
    """
    context.user_data['agency_name'] = update.message.text # Сохраняем название турагентства
    # Изменил запрос на номер телефона
    await update.message.reply_text("Отлично! Теперь введите ваш номер телефона.")
    return PHONE_NUMBER # Переходим в состояние PHONE_NUMBER, чтобы получить номер телефона

async def phone_number_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает ввод номера телефона и записывает данные (Название турагентства, Номер телефона, ID пользователя Telegram)
    в Google Sheets.
    """
    context.user_data['phone_number'] = update.message.text # Сохраняем номер телефона

    # Записываем данные в Google Sheets: Название турагентства, Номер телефона, ID пользователя Telegram
    values = [[
        context.user_data.get('agency_name'), # Используем сохраненное название турагентства
        context.user_data.get('phone_number'), # Используем сохраненный номер телефона
        update.message.from_user.id  # Добавляем ID пользователя Telegram
    ]]

    body = {'values': values}
    try:
        sheet.values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=RANGE_NAME, # Используем исправленный RANGE_NAME (только имя листа)
            valueInputOption='RAW',
            body=body
        ).execute()
        await update.message.reply_text("Спасибо, вы зарегистрированы!")
        logger.info(f"Пользователь {update.message.from_user.id} успешно зарегистрирован. Агентство: {context.user_data.get('agency_name')}, Телефон: {context.user_data.get('phone_number')}")
    except Exception as e:
        logger.error(f"Ошибка при записи в Google Sheets: {e}")
        await update.message.reply_text("Произошла ошибка при регистрации. Пожалуйста, попробуйте еще раз.")
    
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
            # Теперь AGENCY_NAME - это первое состояние после /start
            AGENCY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, agency_name_handler)],
            # Изменил EMAIL на PHONE_NUMBER
            PHONE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_number_handler)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(conv_handler)

    print("Бот запущен. Ожидание сообщений...")
    # Используем run_polling() для получения обновлений
    application.run_polling()
