import asyncio
from typing import List, Tuple

class NotificationQueue:
    def __init__(self, bot):
        self.bot = bot
        self.queue = asyncio.Queue()
        self.running = False
    
    async def add(self, chat_id: int, text: str, **kwargs):
        """Добавить уведомление в очередь"""
        await self.queue.put((chat_id, text, kwargs))
    
    async def add_bulk(self, notifications: List[Tuple[int, str, dict]]):
        """Добавить несколько уведомлений"""
        for chat_id, text, kwargs in notifications:
            await self.queue.put((chat_id, text, kwargs))
    
    async def worker(self):
        """Воркер для обработки очереди"""
        while self.running:
            try:
                # Получаем уведомление с таймаутом
                chat_id, text, kwargs = await asyncio.wait_for(
                    self.queue.get(), 
                    timeout=1.0
                )
                
                try:
                    await self.bot.send_message(chat_id, text, **kwargs)
                    await asyncio.sleep(0.05)  # Защита от flood
                except Exception as e:
                    print(f"Ошибка отправки уведомления {chat_id}: {e}")
                
                self.queue.task_done()
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"Ошибка в воркере уведомлений: {e}")
    
    async def start(self):
        """Запустить воркер"""
        if not self.running:
            self.running = True
            asyncio.create_task(self.worker())
    
    async def stop(self):
        """Остановить воркер"""
        self.running = False
        await self.queue.join()