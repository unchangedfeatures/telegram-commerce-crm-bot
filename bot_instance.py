# bot_instance.py
from aiogram import Bot
from config import TOKEN

# Создаем единственный экземпляр бота
bot_instance = Bot(token=TOKEN)

# notification_service будет инициализирован позже в bot.py
notification_service = None

def set_notification_service(service):
    """Установить notification_service после его создания"""
    global notification_service
    notification_service = service