import time
from functools import wraps
import logging

logger = logging.getLogger(__name__)

def measure_time(func_name: str = None):
    """Декоратор для измерения времени выполнения"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                elapsed = time.time() - start
                
                # Логируем медленные запросы (>1 сек)
                if elapsed > 1.0:
                    logger.warning(
                        f"SLOW QUERY: {func_name or func.__name__} "
                        f"took {elapsed:.2f}s"
                    )
                
                return result
            except Exception as e:
                elapsed = time.time() - start
                logger.error(
                    f"ERROR in {func_name or func.__name__} "
                    f"after {elapsed:.2f}s: {e}"
                )
                raise
        
        return wrapper
    return decorator