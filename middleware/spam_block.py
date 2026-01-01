import asyncio
from datetime import datetime, timedelta
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery

class SpamBlockMiddleware(BaseMiddleware):
    def __init__(self, first_warning_seconds=3, block_seconds=5):
        super().__init__()
        self.first_warning_seconds = first_warning_seconds
        self.block_seconds = block_seconds
        self.user_last_message = {}  # user_id -> datetime
        self.user_warning_sent = {}  # user_id -> bool
        self.user_blocked_until = {}  # user_id -> datetime

    async def __call__(self, handler, event, data):
        user_id = None
        if isinstance(event, Message):
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id

        if user_id is None:
            return await handler(event, data)

        now = datetime.now()

        # Проверка блокировки
        blocked_until = self.user_blocked_until.get(user_id)
        if blocked_until and now < blocked_until:
            return  # просто игнорируем

        last_time = self.user_last_message.get(user_id)

        # Проверяем спам (любые события подряд меньше 1 секунды)
        if last_time and (now - last_time).total_seconds() < 0.1:
            if not self.user_warning_sent.get(user_id):
                # Первое нарушение: предупреждение
                self.user_warning_sent[user_id] = True
                self.user_last_message[user_id] = now
                if isinstance(event, Message):
                    await event.answer(f"⚠️ Пожалуйста, не спамьте. Подождите {self.first_warning_seconds} секунд.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("⚠️ Не спамьте!", show_alert=True)
                await asyncio.sleep(self.first_warning_seconds)
                return
            else:
                # Второе нарушение: блок на 5 секунд
                self.user_blocked_until[user_id] = now + timedelta(seconds=self.block_seconds)
                if isinstance(event, Message):
                    await event.answer(f"❌ Вы заблокированы на {self.block_seconds} секунд за спам.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("❌ Вы заблокированы на 5 секунд за спам.", show_alert=True)
                return  # дальше не пускаем
        else:
            # Все ок, сбрасываем предупреждение
            self.user_warning_sent[user_id] = False

        self.user_last_message[user_id] = now
        return await handler(event, data)
