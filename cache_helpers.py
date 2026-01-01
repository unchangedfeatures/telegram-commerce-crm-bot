import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable
import functools

class SmartCache:
    """Умный кэш с автоматической инвалидацией"""
    
    def __init__(self):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.ttl: Dict[str, datetime] = {}
    
    def get(self, key: str) -> Optional[Any]:
        """Получить из кэша"""
        if key in self.cache:
            if key in self.ttl and datetime.now() < self.ttl[key]:
                return self.cache[key]
            # Устарел
            self.delete(key)
        return None
    
    def set(self, key: str, value: Any, ttl_seconds: int = 300):
        """Сохранить в кэш"""
        self.cache[key] = value
        self.ttl[key] = datetime.now() + timedelta(seconds=ttl_seconds)
    
    def delete(self, key: str):
        """Удалить из кэша"""
        self.cache.pop(key, None)
        self.ttl.pop(key, None)
    
    def invalidate_pattern(self, pattern: str):
        """Инвалидировать по паттерну"""
        keys_to_delete = [k for k in self.cache.keys() if pattern in k]
        for key in keys_to_delete:
            self.delete(key)

# Глобальный кэш
smart_cache = SmartCache()


def cached(ttl_seconds: int = 300, key_prefix: str = ""):
    """Декоратор для кэширования async функций"""
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Формируем ключ кэша
            cache_key = f"{key_prefix}:{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # Проверяем кэш
            cached_value = smart_cache.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Вызываем функцию
            result = await func(*args, **kwargs)
            
            # Сохраняем в кэш
            smart_cache.set(cache_key, result, ttl_seconds)
            return result
        
        return wrapper
    return decorator
