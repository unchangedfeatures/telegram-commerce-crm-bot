
from aiogram import Bot
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.strategy import FSMStrategy
from aiogram.client.default import DefaultBotProperties

# Инициализация бота (токен берется из переменных окружения или config.json)
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
CHAT_ID = os.getenv("CHAT_ID")
USERNAME = os.getenv("USERNAME")
SUPPORT = os.getenv("SUPPORT")


# Создаем бота с настройками по умолчанию
bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode="Markdown")
)

# Хранилище для FSM
storage = MemoryStorage()