import asyncpg
import json
from datetime import datetime
from cache_helpers import cached

pool: asyncpg.Pool | None = None


async def init_db():
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(
            user="postgres",
            password="pewpuff_admin",
            database="pewpuff",
            host="localhost",
            port=5432,
            min_size=2, 
            max_size=20,  
            command_timeout=60,  
            max_queries=50000,  
            max_cached_statement_lifetime=300,  
            max_cacheable_statement_size=1024 * 15,  
            max_inactive_connection_lifetime=300
        )

async def close_db():
    """Закрыть все подключения к базе данных"""
    global pool
    if pool:
        await pool.close()
        pool = None

async def get_products_cached(brand_id: int = None, use_cache: bool = True):
    """Получить товары с кэшированием"""
    from cache_manager import cache
    
    cache_key = f"products_brand_{brand_id}" if brand_id else "products_all"
    
    if use_cache:
        cached = cache.get(cache_key)
        if cached:
            return cached
    
    if brand_id:
        products = await fetch("""
            SELECT product_id, product_name, brand_id, price, 
                   stock_quantity, description, image_url, times_chosen, is_active
            FROM products 
            WHERE brand_id = $1 AND is_active = TRUE
            ORDER BY times_chosen DESC, product_name
        """, brand_id)
    else:
        products = await fetch("""
            SELECT product_id, product_name, brand_id, price, 
                   stock_quantity, description, image_url, times_chosen, is_active
            FROM products 
            WHERE is_active = TRUE
            ORDER BY times_chosen DESC, product_name
        """)
    
    # Кэшируем на 5 минут
    cache.set(cache_key, products, ttl_seconds=300)
    return products

async def get_user_cart_with_products(telegram_id: int):
    """Получить корзину вместе с информацией о товарах за один запрос"""
    result = await fetchrow("""
        SELECT 
            c.items_json,
            c.applied_discounts,
            c.delivery_discount_applied,
            json_agg(
                json_build_object(
                    'product_id', p.product_id,
                    'product_name', p.product_name,
                    'price', p.price,
                    'stock_quantity', p.stock_quantity
                )
            ) as products_info
        FROM cart c
        LEFT JOIN LATERAL (
            SELECT DISTINCT jsonb_object_keys(c.items_json::jsonb)::int as product_id
        ) as cart_products ON true
        LEFT JOIN products p ON p.product_id = cart_products.product_id
        WHERE c.telegram_id = $1
        GROUP BY c.cart_id, c.items_json, c.applied_discounts, c.delivery_discount_applied
    """, telegram_id)
    
    return result


async def get_order_full_info(order_id: int):
    """Получить полную информацию о заказе за один запрос"""
    return await fetchrow("""
        SELECT 
            o.*,
            u.username,
            u.phone,
            u.first_name,
            u.referred_by,
            json_agg(
                json_build_object(
                    'product_id', oi.product_id,
                    'product_name', p.product_name,
                    'quantity', oi.quantity,
                    'unit_price', oi.unit_price,
                    'total_price', oi.total_price
                )
            ) as items
        FROM orders o
        LEFT JOIN users u ON o.telegram_id = u.telegram_id
        LEFT JOIN order_items oi ON o.order_id = oi.order_id
        LEFT JOIN products p ON oi.product_id = p.product_id
        WHERE o.order_id = $1
        GROUP BY o.order_id, u.user_id
    """, order_id)


async def get_pending_orders_batch():
    """Получить все pending/delivery заказы с товарами за один запрос"""
    return await fetch("""
        SELECT 
            o.order_id,
            o.status,
            o.final_amount,
            o.created_at,
            o.delivery_address,
            u.username,
            u.phone,
            json_agg(
                json_build_object(
                    'product_id', oi.product_id,
                    'quantity', oi.quantity
                )
            ) as items
        FROM orders o
        JOIN users u ON o.telegram_id = u.telegram_id
        LEFT JOIN order_items oi ON o.order_id = oi.order_id
        WHERE o.status IN ('pending', 'delivery')
        GROUP BY o.order_id, u.user_id
        ORDER BY o.created_at DESC
    """)


async def bulk_update_stock(updates: list):
    """Массовое обновление остатков товаров"""
    if not updates:
        return
    
    # updates = [(product_id, quantity_change), ...]
    query = """
        UPDATE products 
        SET stock_quantity = stock_quantity + data.change
        FROM (VALUES {}) AS data(id, change)
        WHERE product_id = data.id
    """.format(
        ','.join([f"({pid}, {change})" for pid, change in updates])
    )
    
    await execute(query)



# ----------------------
# Основные методы для работы с БД
# ----------------------

async def fetch(query: str, *args):
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)

async def fetchrow(query: str, *args):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, *args)
        return dict(row) if row else None

async def fetchval(query: str, *args):
    async with pool.acquire() as conn:
        return await conn.fetchval(query, *args)

async def execute(query: str, *args):
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)

# ----------------------
# Пользователи
# ----------------------

async def create_user(
    username: str,
    telegram_id: int,
    referred_by: int | None = None,
    is_subscribed: bool = True
) -> int:
    async with pool.acquire() as conn:
        # Сначала проверяем, существует ли пользователь
        existing = await conn.fetchval(
            "SELECT user_id FROM users WHERE telegram_id = $1",
            telegram_id
        )
        
        if existing:
            # Обновляем существующего пользователя
            await conn.execute(
                """
                UPDATE users 
                SET username = $1, 
                    is_subscribed = $2,
                    updated_at = NOW()
                WHERE telegram_id = $3
                """,
                username,
                is_subscribed,
                telegram_id
            )
            return existing
        else:
            # Создаем нового пользователя
            user_id = await conn.fetchval(
                """
                INSERT INTO users (
                    telegram_id, username, first_name, 
                    referred_by, role, is_subscribed, 
                    created_at, updated_at
                ) VALUES ($1, $2, $3, $4, 'user', $5, NOW(), NOW())
                RETURNING user_id
                """,
                telegram_id,
                username,
                username,  # Используем username как first_name
                referred_by,
                is_subscribed
            )
            return user_id

async def get_user(user_id: int):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT * 
            FROM users
            WHERE user_id = $1
            """,
            user_id,
        )
    return dict(row) if row else None

async def get_user_by_telegram_id(telegram_id: int):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT * FROM users WHERE telegram_id = $1
            """,
            telegram_id
        )
    return dict(row) if row else None


# ----------------------
# Подписка на канал
# ----------------------
async def update_user_subscription(telegram_id: int, is_subscribed: bool):
    await execute(
        """
        UPDATE users 
        SET is_subscribed = $1, updated_at = NOW() 
        WHERE telegram_id = $2
        """,
        is_subscribed,
        telegram_id
    )

# ----------------------
# Баннер / Акции
# ----------------------
async def get_current_promotion():
    row = await fetchrow("""
        SELECT banner_url, description
        FROM promotions
        WHERE is_active = TRUE
          AND (start_date IS NULL OR start_date <= NOW())
          AND (end_date IS NULL OR end_date >= NOW())
        ORDER BY created_at DESC
        LIMIT 1
    """)
    return row

# ----------------------
# Корзина
# ----------------------

async def get_cart(telegram_id: int):
    """Получить корзину пользователя"""
    return await fetchrow(
        "SELECT * FROM cart WHERE telegram_id = $1",
        telegram_id
    )

async def update_cart(telegram_id: int, items_json: str):
    """Обновить корзину пользователя"""
    cart = await get_cart(telegram_id)
    
    if cart:
        await execute(
            """
            UPDATE cart 
            SET items_json = $1, last_updated = NOW()
            WHERE telegram_id = $2
            """,
            items_json,
            telegram_id
        )
    else:
        await execute(
            """
            INSERT INTO cart (telegram_id, items_json, applied_discounts, 
                            delivery_discount_applied, last_updated)
            VALUES ($1, $2, '[]', FALSE, NOW())
            """,
            telegram_id,
            items_json
        )

async def clear_cart(telegram_id: int):
    """Очистить корзину пользователя"""
    await execute("DELETE FROM cart WHERE telegram_id = $1", telegram_id)

# ----------------------
# Товары
# ----------------------

async def get_product(product_id: int):
    """Получить информацию о товаре"""
    return await fetchrow(
        """
        SELECT product_id, product_name, brand_id, price, 
               stock_quantity, description, image_url, 
               times_chosen, is_active
        FROM products 
        WHERE product_id = $1
        """,
        product_id
    )

async def get_products_by_brand(brand_id: int):
    """Получить все товары определенного бренда"""
    return await fetch(
        """
        SELECT product_id, product_name, price, stock_quantity, 
               times_chosen, image_url
        FROM products 
        WHERE brand_id = $1 AND is_active = TRUE
        ORDER BY times_chosen DESC, product_name
        """,
        brand_id
    )

async def update_product_stock(product_id: int, quantity: int):
    """Обновить остаток + инвалидировать кэш"""
    await execute(
        "UPDATE products SET stock_quantity = $1 WHERE product_id = $2",
        quantity, product_id
    )
    # Инвалидируем кэш продуктов
    from cache_helpers import smart_cache
    smart_cache.invalidate_pattern("products")

async def add_to_cart_optimized(telegram_id: int, product_id: int, quantity: int):
    """Оптимизированное добавление в корзину"""
    # Получаем текущую корзину
    cart = await fetchrow("SELECT items_json FROM cart WHERE telegram_id = $1", telegram_id)
    
    if cart:
        items = json.loads(cart['items_json']) if cart['items_json'] else {}
    else:
        items = {}
    
    # Получаем продукт (используем кэш)
    product = await get_product(product_id)  # Эту функцию тоже можно закэшировать
    
    if not product or product['stock_quantity'] < quantity:
        return False
    
    # Обновляем
    if str(product_id) in items:
        items[str(product_id)]['quantity'] += quantity
    else:
        items[str(product_id)] = {
            'name': product['product_name'],
            'price': float(product['price']),
            'quantity': quantity
        }
    
    # Сохраняем
    if cart:
        await execute(
            "UPDATE cart SET items_json = $1, last_updated = NOW() WHERE telegram_id = $2",
            json.dumps(items), telegram_id
        )
    else:
        await execute(
            "INSERT INTO cart (telegram_id, items_json) VALUES ($1, $2)",
            telegram_id, json.dumps(items)
        )
    
    return True



# ----------------------
# Заказы
# ----------------------

async def create_order(
    telegram_id: int,
    total_amount: float,
    discount_amount: float,
    final_amount: float,
    delivery_address: str,
    customer_notes: str = None,
    payment_method: str = "cash",
    promo_code_used: str = None
) -> int:
    """Создать новый заказ"""
    order_number = f"ORD-{datetime.now().strftime('%Y%m%d')}-{telegram_id}"
    
    order_id = await fetchval(
        """
        INSERT INTO orders (
            telegram_id, order_number, total_amount, discount_amount,
            final_amount, delivery_address, customer_notes, 
            payment_method, promo_code_used, status, payment_status,
            created_at, updated_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'pending', 
                  'pending', NOW(), NOW())
        RETURNING order_id
        """,
        telegram_id,
        order_number,
        total_amount,
        discount_amount,
        final_amount,
        delivery_address,
        customer_notes,
        payment_method,
        promo_code_used
    )
    
    return order_id

async def add_order_item(
    order_id: int,
    product_id: int,
    quantity: int,
    unit_price: float,
    total_price: float
):
    """Добавить товар в заказ"""
    await execute(
        """
        INSERT INTO order_items (
            order_id, product_id, quantity, unit_price, total_price, created_at
        ) VALUES ($1, $2, $3, $4, $5, NOW())
        """,
        order_id,
        product_id,
        quantity,
        unit_price,
        total_price
    )

# ----------------------
# Промокоды
# ----------------------

async def get_promo_code(code: str):
    """Получить информацию о промокоде"""
    return await fetchrow(
        "SELECT * FROM promo_codes WHERE code = $1",
        code.upper()
    )

async def get_user_promocodes(telegram_id: int):
    """Получить промокоды пользователя"""
    return await fetch(
        """
        SELECT pc.*, up.is_used, up.received_at, up.used_at
        FROM user_promocodes up
        JOIN promo_codes pc ON up.promo_id = pc.promo_id
        WHERE up.telegram_id = $1
        ORDER BY pc.created_at DESC
        """,
        telegram_id
    )

async def use_promo_code(telegram_id: int, promo_id: int, order_id: int, discount_received: float):
    """Использовать промокод"""
    await execute(
        """
        INSERT INTO used_promo_codes (telegram_id, promo_id, order_id, discount_received)
        VALUES ($1, $2, $3, $4)
        """,
        telegram_id,
        promo_id,
        order_id,
        discount_received
    )
    
    # Помечаем промокод как использованный
    await execute(
        "UPDATE user_promocodes SET is_used = TRUE, used_at = NOW() WHERE telegram_id = $1 AND promo_id = $2",
        telegram_id,
        promo_id
    )

# ----------------------
# Административные функции
# ----------------------

async def get_all_users():
    """Получить всех пользователей (для администратора)"""
    return await fetch(
        "SELECT user_id, telegram_id, username, role, total_orders, total_spent, created_at FROM users ORDER BY created_at DESC"
    )

async def get_all_orders():
    """Получить все заказы (для администратора)"""
    return await fetch(
        """
        SELECT o.*, u.username, u.phone 
        FROM orders o
        LEFT JOIN users u ON o.telegram_id = u.telegram_id
        ORDER BY o.created_at DESC
        """
    )

async def update_order_status(order_id: int, status: str, courier_telegram_id: int = None):
    """Обновить статус заказа"""
    if courier_telegram_id:
        await execute(
            """
            UPDATE orders 
            SET status = $1, courier_telegram_id = $2, updated_at = NOW()
            WHERE order_id = $3
            """,
            status,
            courier_telegram_id,
            order_id
        )
    else:
        await execute(
            "UPDATE orders SET status = $1, updated_at = NOW() WHERE order_id = $2",
            status,
            order_id
        )

# ----------------------
# Статистика
# ----------------------

async def get_user_stats(telegram_id: int):
    """Получить статистику пользователя"""
    return await fetchrow(
        """
        SELECT 
            total_orders,
            total_spent,
            (SELECT COUNT(*) FROM orders WHERE telegram_id = $1 AND status = 'completed') as completed_orders,
            (SELECT COUNT(*) FROM orders WHERE telegram_id = $1 AND status = 'pending') as pending_orders,
            created_at
        FROM users 
        WHERE telegram_id = $1
        """,
        telegram_id
    )

async def get_system_stats():
    """Получить системную статистику"""
    stats = {}
    
    # Общая статистика
    total_stats = await fetchrow(
        """
        SELECT 
            COUNT(*) as total_users,
            SUM(total_orders) as total_orders,
            SUM(total_spent) as total_revenue,
            AVG(total_spent) as avg_order_value
        FROM users
        """
    )
    
    if total_stats:
        stats.update(total_stats)
    
    # Статистика по дням
    daily_stats = await fetch(
        """
        SELECT 
            DATE(created_at) as date,
            COUNT(*) as new_users,
            SUM(total_orders) as daily_orders,
            SUM(total_spent) as daily_revenue
        FROM users
        GROUP BY DATE(created_at)
        ORDER BY date DESC
        LIMIT 7
        """
    )
    
    stats['daily_stats'] = [dict(row) for row in daily_stats]
    
    return stats

async def execute_transaction(queries_and_params):
    """
    Выполняет несколько запросов в одной транзакции
    queries_and_params: список кортежей [(query1, params1), (query2, params2), ...]
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            results = []
            for query, params in queries_and_params:
                if query.strip().upper().startswith('SELECT'):
                    result = await conn.fetchval(query, *params) if 'RETURNING' in query.upper() else await conn.fetch(query, *params)
                else:
                    result = await conn.execute(query, *params) if 'RETURNING' not in query.upper() else await conn.fetchval(query, *params)
                results.append(result)
            return results
        
async def get_products_by_brand_cached(brand_id: int):
    """Получить товары бренда (для кэширования на уровне приложения)"""
    return await fetch("""
        SELECT product_id, product_name, brand_id, price, 
               stock_quantity, description, image_url, times_chosen, is_active
        FROM products 
        WHERE brand_id = $1 AND is_active = TRUE
        ORDER BY times_chosen DESC, product_name
    """, brand_id)


async def get_order_with_items(order_id: int):
    """Получить заказ со всеми товарами за один запрос"""
    return await fetchrow("""
        SELECT 
            o.order_id, o.telegram_id, o.status, o.payment_status,
            o.total_amount, o.discount_amount, o.final_amount,
            o.delivery_address, o.customer_notes, o.promo_code_used,
            o.created_at, o.updated_at,
            u.username, u.phone, u.first_name, u.referred_by,
            json_agg(
                json_build_object(
                    'product_id', oi.product_id,
                    'product_name', p.product_name,
                    'quantity', oi.quantity,
                    'unit_price', oi.unit_price,
                    'total_price', oi.total_price
                ) ORDER BY oi.order_item_id
            ) FILTER (WHERE oi.order_item_id IS NOT NULL) as items
        FROM orders o
        LEFT JOIN users u ON o.telegram_id = u.telegram_id
        LEFT JOIN order_items oi ON o.order_id = oi.order_id
        LEFT JOIN products p ON oi.product_id = p.product_id
        WHERE o.order_id = $1
        GROUP BY o.order_id, u.user_id
    """, order_id)


async def get_active_orders_with_items():
    """Получить все активные заказы с товарами за один запрос"""
    return await fetch("""
        SELECT 
            o.order_id, o.status, o.final_amount, o.created_at, 
            o.delivery_address, o.telegram_id,
            u.username, u.phone,
            json_agg(
                json_build_object(
                    'product_id', oi.product_id,
                    'quantity', oi.quantity
                ) ORDER BY oi.order_item_id
            ) FILTER (WHERE oi.order_item_id IS NOT NULL) as items
        FROM orders o
        JOIN users u ON o.telegram_id = u.telegram_id
        LEFT JOIN order_items oi ON o.order_id = oi.order_id
        WHERE o.status IN ('pending', 'delivery')
        GROUP BY o.order_id, u.user_id
        ORDER BY o.created_at DESC
    """)


async def check_admin_role(telegram_id: int) -> bool:
    """Быстрая проверка прав админа"""
    result = await fetchval(
        "SELECT role FROM users WHERE telegram_id = $1",
        telegram_id
    )
    return result == 'admin'

@cached(ttl_seconds=60, key_prefix="products")
async def get_products_by_brand_optimized(brand_id: int):
    """Кэшированное получение продуктов (1 минута)"""
    return await fetch("""
        SELECT product_id, product_name, brand_id, price, 
               stock_quantity, description, image_url, times_chosen, is_active
        FROM products 
        WHERE brand_id = $1 AND is_active = TRUE
        ORDER BY times_chosen DESC, product_name
    """, brand_id)


async def get_user_with_cart_optimized(telegram_id: int):
    """Получить пользователя + корзину за 1 запрос"""
    return await fetchrow("""
        SELECT 
            u.telegram_id, u.username, u.phone, u.address, 
            u.total_orders, u.referred_by,
            c.items_json, c.applied_discounts
        FROM users u
        LEFT JOIN cart c ON u.telegram_id = c.telegram_id
        WHERE u.telegram_id = $1
    """, telegram_id)


async def get_order_full_optimized(order_id: int):
    """Полная информация о заказе за 1 запрос (уже есть в вашем коде - отлично!)"""
    return await fetchrow("""
        SELECT 
            o.*, u.username, u.phone, u.first_name, u.referred_by,
            json_agg(
                json_build_object(
                    'product_id', oi.product_id,
                    'product_name', p.product_name,
                    'quantity', oi.quantity,
                    'unit_price', oi.unit_price,
                    'total_price', oi.total_price
                )
            ) as items
        FROM orders o
        LEFT JOIN users u ON o.telegram_id = u.telegram_id
        LEFT JOIN order_items oi ON o.order_id = oi.order_id
        LEFT JOIN products p ON oi.product_id = p.product_id
        WHERE o.order_id = $1
        GROUP BY o.order_id, u.user_id
    """, order_id)
