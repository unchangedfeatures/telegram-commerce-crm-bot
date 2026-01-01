import database.database as db
from functools import wraps

# Декоратор для проверки прав админа
def admin_required(func):
    """Декоратор для проверки прав администратора"""
    @wraps(func)
    async def wrapper(message, *args, **kwargs):
        user = await db.fetchrow(
            "SELECT role FROM users WHERE telegram_id = $1", 
            message.from_user.id
        )
        if not user or user['role'] != 'admin':
            await message.answer("❌ У вас нет прав для выполнения этой команды")
            return
        return await func(message, *args, **kwargs)
    return wrapper


# Кэш для проверки админов (чтобы не дергать БД каждый раз)
_admin_cache = {}
_admin_cache_ttl = {}

async def is_admin_cached(telegram_id: int) -> bool:
    """Проверка прав администратора с кэшированием"""
    from datetime import datetime, timedelta
    
    # Проверяем кэш
    if telegram_id in _admin_cache:
        if datetime.now() < _admin_cache_ttl.get(telegram_id, datetime.min):
            return _admin_cache[telegram_id]
    
    # Запрашиваем из БД
    user = await db.fetchrow(
        "SELECT role FROM users WHERE telegram_id = $1", 
        telegram_id
    )
    result = user and user['role'] == 'admin'
    
    # Кэшируем на 5 минут
    _admin_cache[telegram_id] = result
    _admin_cache_ttl[telegram_id] = datetime.now() + timedelta(minutes=5)
    
    return result


def format_order_status(status: str) -> tuple:
    """Возвращает (emoji, текст) для статуса заказа"""
    status_map = {
        'pending': ('⏳', 'Ожидает подтверждения'),
        'accepted': ('✅', 'Принят'),
        'delivery': ('🚚', 'В доставке'),
        'completed': ('💰', 'Завершен'),
        'declined': ('❌', 'Отклонен')
    }
    return status_map.get(status, ('❓', status))


def format_price(amount: float) -> str:
    """Форматирование цены"""
    return f"{amount:.2f}€"


def format_date(dt) -> str:
    """Форматирование даты"""
    if not dt:
        return "не указано"
    return dt.strftime('%d.%m.%Y %H:%M')