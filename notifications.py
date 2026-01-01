# notifications.py (исправленная версия)
import asyncio
import json
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

class NotificationService:
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self.running = False
        self.broadcast_running = False
        self.queue = asyncio.Queue()
        self.worker_running = False

    async def add(self, user_id: int, text: str, buttons=None):
        """Добавляет задачу на отправку уведомления конкретному пользователю"""
        buttons_json = self._serialize_buttons(buttons)
        
        # Создаем запись в notifications (упрощенная версия)
        try:
            await self._send_to_user(user_id, text, buttons)
            return True
        except Exception as e:
            print(f"[NOTIFICATION ERROR sending to {user_id}]: {e}")
            return False

    async def add_broadcast(self, text: str, buttons=None):
        """Добавляет задачу на глобальную рассылку"""
        buttons_json = self._serialize_buttons(buttons)
        
        # Получаем общее количество подписанных пользователей
        users_count = await self.db.fetchval(
            "SELECT COUNT(*) FROM users WHERE is_subscribed = TRUE"
        )
        
        # Создаем запись в notifications
        notification_id = await self.db.fetchval("""
            INSERT INTO notifications (title, message, notification_type, buttons, is_sent, created_at)
            VALUES ($1, $2, $3, $4, FALSE, NOW())
            RETURNING notification_id
        """, "Глобальная рассылка", text, "broadcast", buttons_json)
        
        if notification_id:
            # Создаем задачу рассылки
            await self.db.execute("""
                INSERT INTO broadcast_jobs (notification_id, total_users, status, created_at)
                VALUES ($1, $2, 'pending', NOW())
            """, notification_id, users_count)
            
        return notification_id

    def _serialize_buttons(self, buttons):
        """Конвертирует кнопки в JSON строку"""
        if not buttons:
            return None
        
        try:
            buttons_list = []
            for row in buttons:
                row_list = []
                if isinstance(row, list):
                    for button in row:
                        if isinstance(button, InlineKeyboardButton):
                            row_list.append({
                                'text': button.text,
                                'url': button.url
                            })
                        elif isinstance(button, dict):
                            row_list.append(button)
                elif isinstance(row, dict):
                    row_list.append(row)
                
                if row_list:
                    buttons_list.append(row_list)
            
            if buttons_list:
                return json.dumps(buttons_list)
        except Exception as e:
            print(f"[ERROR serializing buttons]: {e}")
        
        return None

    def _deserialize_buttons(self, buttons_json):
        """Конвертирует JSON строку обратно в кнопки"""
        if not buttons_json:
            return None
        
        try:
            buttons_data = json.loads(buttons_json)
            keyboard_buttons = []
            
            for row in buttons_data:
                row_buttons = []
                if isinstance(row, list):
                    for btn_data in row:
                        if isinstance(btn_data, dict) and 'text' in btn_data:
                            # Создаем кнопку с правильным синтаксисом для Aiogram 3.x
                            if 'url' in btn_data:
                                row_buttons.append(
                                    InlineKeyboardButton(
                                        text=btn_data['text'],
                                        url=btn_data['url']
                                    )
                                )
                            elif 'callback_data' in btn_data:
                                row_buttons.append(
                                    InlineKeyboardButton(
                                        text=btn_data['text'],
                                        callback_data=btn_data['callback_data']
                                    )
                                )
                elif isinstance(row, dict) and 'text' in row:
                    if 'url' in row:
                        row_buttons.append(
                            InlineKeyboardButton(
                                text=row['text'],
                                url=row['url']
                            )
                        )
                
                if row_buttons:
                    keyboard_buttons.append(row_buttons)
            
            if keyboard_buttons:
                return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
                
        except Exception as e:
            print(f"[ERROR deserializing buttons]: {e}")
        
        return None

    async def _send_to_user(self, user_id: int, text: str, buttons=None):
        """Отправляет сообщение пользователю"""
        reply_markup = None
        
        if buttons:
            # Если кнопки уже в формате InlineKeyboardMarkup
            if isinstance(buttons, InlineKeyboardMarkup):
                reply_markup = buttons
            # Если кнопки в формате списка списков
            elif isinstance(buttons, list):
                keyboard_buttons = []
                for row in buttons:
                    row_buttons = []
                    if isinstance(row, list):
                        for button in row:
                            if isinstance(button, InlineKeyboardButton):
                                row_buttons.append(button)
                            elif isinstance(button, dict):
                                # Конвертируем dict в InlineKeyboardButton
                                if 'text' in button and 'url' in button:
                                    row_buttons.append(
                                        InlineKeyboardButton(
                                            text=button['text'],
                                            url=button['url']
                                        )
                                    )
                    if row_buttons:
                        keyboard_buttons.append(row_buttons)
                
                if keyboard_buttons:
                    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        await self.bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=reply_markup
        )

    async def broadcast_worker(self):
        """Фоновый воркер для глобальных рассылок"""
        if self.broadcast_running:
            return
        self.broadcast_running = True

        while True:
            try:
                # Находим задачу рассылки в статусе pending
                job = await self.db.fetchrow("""
                    SELECT bj.job_id, bj.notification_id, bj.total_users,
                           n.message, n.buttons, n.notification_type
                    FROM broadcast_jobs bj
                    JOIN notifications n ON bj.notification_id = n.notification_id
                    WHERE bj.status = 'pending'
                    ORDER BY bj.job_id
                    LIMIT 1
                """)

                if not job:
                    await asyncio.sleep(1)
                    continue

                job_id = job["job_id"]
                notification_id = job["notification_id"]
                text = job["message"]
                buttons_json = job["buttons"]

                # Обновляем статус задачи
                await self.db.execute("""
                    UPDATE broadcast_jobs
                    SET status = 'running', started_at = NOW()
                    WHERE job_id = $1
                """, job_id)

                # Получаем пользователей (подписанных)
                users = await self.db.fetch(
                    "SELECT telegram_id FROM users WHERE is_subscribed = TRUE"
                )

                # Подготавливаем клавиатуру
                reply_markup = self._deserialize_buttons(buttons_json)

                success = 0
                fail = 0

                # Отправляем сообщения всем пользователям
                for user in users:
                    try:
                        await self.bot.send_message(
                            chat_id=user["telegram_id"],
                            text=text,
                            reply_markup=reply_markup
                        )
                        success += 1
                    except Exception as e:
                        fail += 1
                        print(f"[BROADCAST ERROR to {user['telegram_id']}]: {e}")

                    # Небольшая задержка для защиты от флуда
                    await asyncio.sleep(0.05)

                # Обновляем статистику задачи и помечаем уведомление как отправленное
                await self.db.execute("""
                    UPDATE broadcast_jobs
                    SET status = 'completed',
                        completed_at = NOW(),
                        sent_users = $1,
                        failed_users = $2
                    WHERE job_id = $3
                """, success, fail, job_id)
                
                await self.db.execute("""
                    UPDATE notifications 
                    SET is_sent = TRUE, sent_at = NOW()
                    WHERE notification_id = $1
                """, notification_id)

                print(f"[BROADCAST FINISHED] job={job_id}, ok={success}, fail={fail}")
                
            except Exception as e:
                print(f"[BROADCAST WORKER ERROR]: {e}")
                await asyncio.sleep(5)

    
    async def add_to_queue(self, user_id: int, text: str, **kwargs):
        """Добавить уведомление в быструю очередь (не блокирует)"""
        await self.queue.put((user_id, text, kwargs))
    
    # ДОБАВИТЬ НОВЫЙ МЕТОД:
    async def add_bulk_to_queue(self, notifications: list):
        """Добавить несколько уведомлений в очередь
        notifications = [(user_id, text, kwargs), ...]
        """
        for user_id, text, kwargs in notifications:
            await self.queue.put((user_id, text, kwargs))

    async def add_bulk_optimized(self, notifications: list):
        """
        Батчинг уведомлений - добавить много за раз
        notifications = [(user_id, text, buttons), ...]
        """
        for user_id, text, buttons in notifications:
            await self.queue.put((user_id, text, {"reply_markup": buttons} if buttons else {}))
    

    async def queue_worker(self):
        """Воркер с батчингом (обрабатывает до 5 уведомлений за раз)"""
        self.worker_running = True
        
        while self.worker_running:
            batch = []
            
            try:
                # Собираем батч до 5 уведомлений или таймаут 0.5 сек
                for _ in range(5):
                    try:
                        item = await asyncio.wait_for(self.queue.get(), timeout=0.5)
                        batch.append(item)
                    except asyncio.TimeoutError:
                        break
                
                # Отправляем батч
                for user_id, text, kwargs in batch:
                    try:
                        await self.bot.send_message(user_id, text, **kwargs)
                        await asyncio.sleep(0.05)  # Защита от flood
                    except Exception as e:
                        print(f"[QUEUE ERROR to {user_id}]: {e}")
                    
                    self.queue.task_done()
                
            except Exception as e:
                print(f"[QUEUE WORKER ERROR]: {e}")
    
    async def start(self):
        """Запуск всех воркеров"""
        asyncio.create_task(self.broadcast_worker())
        # ДОБАВИТЬ: Запускаем queue_worker
        asyncio.create_task(self.queue_worker())
        
        print("[NOTIFICATION SERVICE] Workers started")

    async def get_stats(self):
        """Получить статистику уведомлений"""
        stats = {}
        
        # Статистика по уведомлениям
        notification_stats = await self.db.fetchrow("""
            SELECT 
                COUNT(*) as total_notifications,
                SUM(CASE WHEN is_sent THEN 1 ELSE 0 END) as sent_notifications,
                SUM(CASE WHEN NOT is_sent THEN 1 ELSE 0 END) as pending_notifications
            FROM notifications
        """)
        
        if notification_stats:
            stats['notifications'] = notification_stats
        
        # Статистика по рассылкам
        broadcast_stats = await self.db.fetchrow("""
            SELECT 
                COUNT(*) as total_jobs,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_jobs,
                SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) as running_jobs,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending_jobs,
                COALESCE(SUM(sent_users), 0) as total_sent,
                COALESCE(SUM(failed_users), 0) as total_failed
            FROM broadcast_jobs
        """)
        
        if broadcast_stats:
            stats['broadcasts'] = broadcast_stats
        
        return stats