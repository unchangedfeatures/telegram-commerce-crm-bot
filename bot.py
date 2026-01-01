import asyncio
import logging
from aiogram import Dispatcher
from aiogram.types import Message
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware

from middleware.spam_block import SpamBlockMiddleware

# Импорты из наших папок
from config import TOKEN
import database.database as db
from notifications import NotificationService

# Импортируем bot_instance ИЗ НОВОГО ФАЙЛА
from bot_instance import bot_instance, set_notification_service

import handlers.orderHandlers as order_handlers
import handlers.AdminOrderHandlers as admin_order_handlers
from states import OrderStates

# Импорт обработчиков
import handlers.guestHandlers as guest_handlers
import handlers.commandHandlers as command_handlers
import handlers.cartHandlers as cart_handlers

# Включаем логирование, чтобы не пропустить важные сообщения
logging.basicConfig(level=logging.INFO)

# Middleware для инъекции зависимостей
class DependenciesMiddleware(BaseMiddleware):
    def __init__(self, db, notification_service):
        self.db = db
        self.notification_service = notification_service
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        # Добавляем зависимости в data
        data['db'] = self.db
        data['notification_service'] = self.notification_service
        return await handler(event, data)

# Main
dp = Dispatcher()

# Создаем notification_service
notification_service = NotificationService(bot_instance, db)

# Устанавливаем notification_service глобально
set_notification_service(notification_service)

# Регистрация middleware
spam_middleware = SpamBlockMiddleware()
dependencies_middleware = DependenciesMiddleware(db, notification_service)

dp.message.middleware.register(spam_middleware)
dp.callback_query.middleware.register(spam_middleware)
dp.message.middleware.register(dependencies_middleware)
dp.callback_query.middleware.register(dependencies_middleware)

# Запуск
async def main():
    try:
        # Инициализация базы данных
        await db.init_db()
        
        # Регистрируем роутеры
        dp.include_routers(
            guest_handlers.router, 
            command_handlers.router, 
            cart_handlers.router,
            order_handlers.router,
            admin_order_handlers.router
        )
        
        # Удаляем вебхук
        await bot_instance.delete_webhook(drop_pending_updates=True)
        
        # Запускаем воркер уведомлений
        asyncio.create_task(notification_service.start())
        # Рассылка общая
        asyncio.create_task(notification_service.broadcast_worker())
        
        # Запускаем поллинг
        await dp.start_polling(bot_instance)
    except Exception as e:
        logging.error(f"Ошибка при запуске бота: {e}")
    finally:
        await db.close_db()
        await bot_instance.session.close()

# Просто важная штука, я не уверен, за что она отвечает
if __name__ == "__main__":
    asyncio.run(main())

        