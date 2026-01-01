import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

class CacheManager:
    def __init__(self):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.ttl: Dict[str, datetime] = {}
    
    def get(self, key: str) -> Optional[Any]:
        """Получить значение из кэша"""
        if key in self.cache:
            # Проверяем TTL
            if key in self.ttl and datetime.now() > self.ttl[key]:
                # Кэш устарел
                del self.cache[key]
                del self.ttl[key]
                return None
            return self.cache[key]
        return None
    
    def set(self, key: str, value: Any, ttl_seconds: int = 300):
        """Сохранить значение в кэш с TTL"""
        self.cache[key] = value
        self.ttl[key] = datetime.now() + timedelta(seconds=ttl_seconds)
    
    def delete(self, key: str):
        """Удалить значение из кэша"""
        if key in self.cache:
            del self.cache[key]
        if key in self.ttl:
            del self.ttl[key]
    
    def clear_pattern(self, pattern: str):
        """Очистить все ключи, содержащие паттерн"""
        keys_to_delete = [key for key in self.cache.keys() if pattern in key]
        for key in keys_to_delete:
            self.delete(key)
    
    def clear_all(self):
        """Очистить весь кэш"""
        self.cache.clear()
        self.ttl.clear()

# Глобальный экземпляр кэша
cache = CacheManager()