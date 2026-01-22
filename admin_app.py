import asyncio
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from functools import wraps
import database.database as db
from datetime import datetime
from notifications import NotificationService
from bot_instance import bot_instance
import os
from werkzeug.security import check_password_hash, generate_password_hash
import threading
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Инициализация notification_service
notification_service = None

# Конфигурация
ADMIN_USERNAME = "admin"
# Get admin password from environment, fall back to default
ADMIN_PASSWORD_HASH = generate_password_hash(os.getenv("ADMIN_PASSWORD", "admin123"))

# Глобальный event loop для async операций в отдельном потоке
loop = None
loop_thread = None

def start_event_loop():
    """Запустить event loop в отдельном потоке"""
    global loop
    def run_loop():
        global loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_forever()
    
    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()
    
    # Ждём пока loop инициализируется
    import time
    while loop is None:
        time.sleep(0.01)
    
    return thread

def init_async():
    """Инициализация async компонентов"""
    global loop, notification_service, loop_thread
    try:
        # Запускаем event loop в отдельном потоке если еще не запущен
        if loop is None:
            loop_thread = start_event_loop()
            import time
            time.sleep(0.1)  # Даём время на инициализацию
        
        # Инициализация БД в loop
        future = asyncio.run_coroutine_threadsafe(db.init_db(), loop)
        future.result(timeout=10)
        
        # Инициализация notification service
        notification_service = NotificationService(bot_instance, db)
        print("✅ Async components initialized")
    except Exception as e:
        print(f"❌ Failed to initialize async components: {e}")
        import traceback
        traceback.print_exc()
        raise

# Декоратор для проверки авторизации
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def run_async(coro):
    """Запустить async функцию в главном event loop"""
    global loop
    
    # Инициализируем loop если еще не готов
    if loop is None:
        init_async()
    
    try:
        # Убедимся, что БД инициализирована
        async def _ensure_and_run():
            if db.pool is None or not db._db_initialized:
                await db.init_db()
            return await coro
        
        # Запускаем в главном loop используя run_coroutine_threadsafe
        future = asyncio.run_coroutine_threadsafe(_ensure_and_run(), loop)
        return future.result(timeout=60)
    except Exception as e:
        print(f"Error in run_async: {e}")
        import traceback
        traceback.print_exc()
        raise

# ==================== АВТОРИЗАЦИЯ ====================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session['logged_in'] = True
            session['username'] = username
            flash('Успешный вход!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Неверные учетные данные', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('login'))

# ==================== HEALTHCHECK ====================

@app.route('/health')
def health():
    """Healthcheck endpoint for monitoring"""
    try:
        # Check database connection
        run_async(db.fetchval("SELECT 1"))
        return jsonify({'status': 'healthy'}), 200
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

# ==================== ГЛАВНАЯ ====================

@app.route('/')
@login_required
def dashboard():
    try:
        stats = run_async(get_dashboard_stats())
        return render_template('dashboard.html', stats=stats)
    except Exception as e:
        print(f"Dashboard error: {e}")
        flash(f'Ошибка загрузки статистики: {e}', 'danger')
        return render_template('dashboard.html', stats={})

async def get_dashboard_stats():
    try:
        # Общая статистика
        total_users = await db.fetchval("SELECT COUNT(*) FROM users") or 0
        total_orders = await db.fetchval("SELECT COUNT(*) FROM orders") or 0
        pending_orders = await db.fetchval("SELECT COUNT(*) FROM orders WHERE status = 'pending'") or 0
        total_revenue = await db.fetchval("SELECT COALESCE(SUM(final_amount), 0) FROM orders WHERE status = 'completed'") or 0
        
        # Статистика за сегодня
        today_orders = await db.fetchval(
            "SELECT COUNT(*) FROM orders WHERE DATE(created_at) = CURRENT_DATE"
        ) or 0
        today_revenue = await db.fetchval(
            "SELECT COALESCE(SUM(final_amount), 0) FROM orders WHERE DATE(created_at) = CURRENT_DATE"
        ) or 0
        
        # Топ товары
        top_products = await db.fetch("""
            SELECT product_name, times_chosen, stock_quantity
            FROM products
            WHERE is_active = TRUE
            ORDER BY times_chosen DESC
            LIMIT 5
        """)
        
        return {
            'total_users': total_users,
            'total_orders': total_orders,
            'pending_orders': pending_orders,
            'total_revenue': float(total_revenue) if total_revenue else 0,
            'today_orders': today_orders,
            'today_revenue': float(today_revenue) if today_revenue else 0,
            'top_products': [dict(p) for p in top_products] if top_products else []
        }
    except Exception as e:
        print(f"Error in get_dashboard_stats: {e}")
        return {
            'total_users': 0,
            'total_orders': 0,
            'pending_orders': 0,
            'total_revenue': 0,
            'today_orders': 0,
            'today_revenue': 0,
            'top_products': []
        }

# ==================== ПРОМОКОДЫ ====================

@app.route('/promocodes')
@login_required
def promocodes():
    try:
        promos = run_async(db.fetch("""
            SELECT * FROM promo_codes 
            ORDER BY created_at DESC
        """))
        return render_template('promocodes.html', promocodes=[dict(p) for p in promos] if promos else [])
    except Exception as e:
        print(f"Promocodes error: {e}")
        flash(f'Ошибка загрузки промокодов: {e}', 'danger')
        return render_template('promocodes.html', promocodes=[])

@app.route('/promocodes/create', methods=['POST'])
@login_required
def create_promocode():
    try:
        data = request.json
        
        # Валидация
        if not data.get('code'):
            return jsonify({'success': False, 'error': 'Код обязателен'})
        
        # Проверка уникальности
        existing = run_async(db.fetchval(
            "SELECT 1 FROM promo_codes WHERE code = $1",
            data['code'].upper()
        ))
        
        if existing:
            return jsonify({'success': False, 'error': 'Промокод уже существует'})
        
        # Создание
        discount_percent = float(data.get('discount_percent', 0)) if data.get('type') == 'percent' else None
        discount_amount = float(data.get('discount_amount', 0)) if data.get('type') == 'amount' else None
        
        # Преобразуем expires_at из строки в datetime
        expires_at = None
        if data.get('expires_at'):
            from dateutil import parser as date_parser
            try:
                expires_at = date_parser.parse(data.get('expires_at'))
                # Отправляем только date часть (без timezone), PostgreSQL сам добавит правильный timezone
                if hasattr(expires_at, 'date'):
                    expires_at = expires_at.date()
            except Exception as e:
                return jsonify({'success': False, 'error': f'Ошибка парсинга даты: {e}'})
        
        run_async(db.execute("""
            INSERT INTO promo_codes (
                code, discount_percent, discount_amount, 
                min_order_amount, max_uses, current_uses,
                expires_at, is_active, created_at
            ) VALUES ($1, $2, $3, $4, $5, 0, $6, TRUE, NOW())
        """,
        data['code'].upper(),
        discount_percent,
        discount_amount,
        float(data.get('min_order', 0)),
        int(data.get('max_uses', 0)),
        expires_at))
        
        return jsonify({'success': True})
    except Exception as e:
        print(f"Create promo error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/promocodes/delete/<int:promo_id>', methods=['POST'])
@login_required
def delete_promocode(promo_id):
    try:
        run_async(db.execute("DELETE FROM promo_codes WHERE promo_id = $1", promo_id))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/promocodes/toggle/<int:promo_id>', methods=['POST'])
@login_required
def toggle_promocode(promo_id):
    try:
        run_async(db.execute("""
            UPDATE promo_codes 
            SET is_active = NOT is_active 
            WHERE promo_id = $1
        """, promo_id))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ==================== ТОВАРЫ ====================

@app.route('/products')
@login_required
def products():
    try:
        brands = run_async(db.fetch("SELECT * FROM brands ORDER BY brand_name"))
        products_data = []
        
        for brand in brands:
            brand_products = run_async(db.fetch("""
                SELECT * FROM products 
                WHERE brand_id = $1 
                ORDER BY product_name
            """, brand['brand_id']))
            
            products_data.append({
                'brand': dict(brand),
                'products': [dict(p) for p in brand_products] if brand_products else []
            })
        
        return render_template('products.html', products_data=products_data)
    except Exception as e:
        print(f"Products error: {e}")
        flash(f'Ошибка загрузки товаров: {e}', 'danger')
        return render_template('products.html', products_data=[])

@app.route('/products/<int:product_id>/details')
@login_required
def product_details(product_id):
    try:
        product = run_async(db.fetchrow(
            "SELECT * FROM products WHERE product_id = $1",
            product_id
        ))
        
        if not product:
            return jsonify({'error': 'Товар не найден'}), 404
        
        return jsonify(dict(product))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/products/<int:product_id>/update', methods=['POST'])
@login_required
def update_product(product_id):
    try:
        data = request.json
        
        run_async(db.execute("""
            UPDATE products
            SET brand_id = $1,
                product_name = $2,
                price = $3,
                stock_quantity = $4,
                description = $5,
                image_url = $6,
                is_active = $7
            WHERE product_id = $8
        """,
        int(data['brand_id']),
        data['product_name'],
        float(data['price']),
        int(data['stock_quantity']),
        data.get('description', ''),
        data.get('image_url', ''),
        data.get('is_active', 'true') == 'true',
        product_id))
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/products/<int:product_id>/delete', methods=['POST'])
@login_required
def delete_product(product_id):
    try:
        run_async(db.execute(
            "DELETE FROM products WHERE product_id = $1",
            product_id
        ))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/products/update-stock', methods=['POST'])
@login_required
def update_stock():
    try:
        data = request.json
        product_id = data.get('product_id')
        quantity = int(data.get('quantity', 0))
        
        run_async(db.execute(
            "UPDATE products SET stock_quantity = $1 WHERE product_id = $2",
            quantity, product_id
        ))
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/products/create', methods=['POST'])
@login_required
def create_product():
    try:
        data = request.json
        
        run_async(db.execute("""
            INSERT INTO products (
                brand_id, product_name, price, stock_quantity, 
                description, image_url, is_active, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, TRUE, NOW())
        """,
        int(data['brand_id']),
        data['product_name'],
        float(data['price']),
        int(data['stock_quantity']),
        data.get('description', ''),
        data.get('image_url', '')))
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ==================== РЕФЕРАЛЫ ====================

@app.route('/referrals')
@login_required
def referrals():
    try:
        filter_type = request.args.get('filter', 'all')
        
        # Статистика
        stats = run_async(get_referral_stats())
        
        # Список рефереров
        referrers = run_async(get_referrers_list(filter_type))
        
        return render_template('referrals.html', 
                             stats=stats, 
                             referrers=referrers,
                             filter=filter_type)
    except Exception as e:
        print(f"Referrals error: {e}")
        flash(f'Ошибка загрузки рефералов: {e}', 'danger')
        return render_template('referrals.html', stats={}, referrers=[], filter='all')

async def get_referral_stats():
    """Получить общую статистику по рефералам"""
    # Всего начислено
    total_earned = await db.fetchval("""
        SELECT COALESCE(SUM(discount_amount), 0)
        FROM referral_discounts
    """) or 0
    
    # Текущий баланс (к выплате)
    pending_payment = await db.fetchval("""
        SELECT COALESCE(SUM(discount_amount), 0)
        FROM referral_discounts
        WHERE discount_amount > 0
    """) or 0
    
    # Выплачено (было начислено, но сейчас 0)
    total_paid = float(total_earned) - float(pending_payment)
    
    # Активных рефереров (у кого есть баланс)
    active_referrers = await db.fetchval("""
        SELECT COUNT(DISTINCT referrer_telegram_id)
        FROM referral_discounts
        WHERE discount_amount > 0
    """) or 0
    
    return {
        'total_earned': float(total_earned),
        'total_paid': float(total_paid),
        'pending_payment': float(pending_payment),
        'active_referrers': active_referrers
    }

async def get_referrers_list(filter_type='all'):
    """Получить список рефереров с балансами"""
    
    query = """
        SELECT 
            u.telegram_id,
            u.username,
            COUNT(DISTINCT ref_users.telegram_id) as total_referrals,
            COUNT(DISTINCT ref_orders.order_id) as referral_orders,
            COALESCE(SUM(CASE WHEN rd.discount_amount IS NOT NULL THEN rd.discount_amount ELSE 0 END), 0) as total_earned,
            COALESCE(SUM(CASE WHEN rd.discount_amount > 0 THEN rd.discount_amount ELSE 0 END), 0) as current_balance,
            MAX(rd.created_at) as last_bonus_date
        FROM users u
        LEFT JOIN users ref_users ON ref_users.referred_by = u.telegram_id
        LEFT JOIN orders ref_orders ON ref_orders.telegram_id = ref_users.telegram_id 
            AND ref_orders.status = 'completed'
        LEFT JOIN referral_discounts rd ON rd.referrer_telegram_id = u.telegram_id
        WHERE EXISTS (
            SELECT 1 FROM users WHERE referred_by = u.telegram_id
        )
    """
    
    if filter_type == 'with_balance':
        query += " AND rd.discount_amount > 0"
    elif filter_type == 'paid':
        query += " AND rd.discount_amount = 0 AND rd.created_at IS NOT NULL"
    
    query += """
        GROUP BY u.telegram_id, u.username
        ORDER BY current_balance DESC, total_earned DESC
    """
    
    referrers = await db.fetch(query)
    return [dict(r) for r in referrers] if referrers else []

@app.route('/referrals/finance/summary')
@login_required
def referral_finance_summary():
    """Страница с финансовой информацией по реферралам"""
    try:
        # Общая статистика по доходам
        total_earned = run_async(db.fetchval("""
            SELECT COALESCE(SUM(discount_amount), 0)
            FROM referral_discounts
        """)) or 0
        
        # Детальная статистика
        stats = run_async(get_referral_stats())
        
        # История выплат
        payments = run_async(db.fetch("""
            SELECT 
                rpl.referrer_telegram_id,
                u.username,
                rpl.amount,
                rpl.paid_at,
                rpl.notes
            FROM referral_payments_log rpl
            LEFT JOIN users u ON rpl.referrer_telegram_id = u.telegram_id
            ORDER BY rpl.paid_at DESC
            LIMIT 50
        """))
        
        # Активные бонусы (не выплаченные)
        active_bonuses = run_async(db.fetch("""
            SELECT 
                referrer_telegram_id,
                SUM(discount_amount) as total_bonus
            FROM referral_discounts
            WHERE discount_amount > 0
            GROUP BY referrer_telegram_id
            ORDER BY total_bonus DESC
        """))
        
        return render_template('referral_finance.html',
                             stats=stats,
                             payments=[dict(p) for p in payments] if payments else [],
                             active_bonuses=[dict(b) for b in active_bonuses] if active_bonuses else [])
    except Exception as e:
        print(f"Referral finance error: {e}")
        flash(f'Ошибка загрузки финансовой информации: {e}', 'danger')
        return render_template('referral_finance.html', stats={}, payments=[], active_bonuses=[])

@app.route('/referrals/<int:telegram_id>/details')
@login_required
def referral_details(telegram_id):
    try:
        # История бонусов
        bonuses = run_async(db.fetch("""
            SELECT 
                rd.*,
                u.username as referred_username
            FROM referral_discounts rd
            LEFT JOIN users u ON rd.referred_telegram_id = u.telegram_id
            WHERE rd.referrer_telegram_id = $1
            ORDER BY rd.created_at DESC
        """, telegram_id))
        
        # Список рефералов
        referrals = run_async(db.fetch("""
            SELECT 
                u.telegram_id,
                u.username,
                COUNT(o.order_id) as orders_count,
                COALESCE(SUM(o.final_amount), 0) as total_spent
            FROM users u
            LEFT JOIN orders o ON u.telegram_id = o.telegram_id 
                AND o.status = 'completed'
            WHERE u.referred_by = $1
            GROUP BY u.telegram_id, u.username
        """, telegram_id))
        
        return jsonify({
            'bonuses': [dict(b) for b in bonuses] if bonuses else [],
            'referrals': [dict(r) for r in referrals] if referrals else []
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/referrals/mark-paid', methods=['POST'])
@login_required
def mark_referral_paid():
    try:
        data = request.json
        telegram_id = int(data.get('telegram_id'))
        amount = float(data.get('amount'))
        
        # Обнуляем бонусы (списываем)
        run_async(db.execute("""
            UPDATE referral_discounts
            SET discount_amount = 0
            WHERE referrer_telegram_id = $1 AND discount_amount > 0
        """, telegram_id))
        
        # Логируем выплату
        run_async(db.execute("""
            INSERT INTO referral_payments_log (
                telegram_id, amount, payment_type, created_at, created_by
            ) VALUES ($1, $2, 'paid', NOW(), $3)
        """, telegram_id, amount, session.get('username', 'admin')))
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/referrals/reset-balance', methods=['POST'])
@login_required
def reset_referral_balance():
    """Обнуление реферального баланса без выплаты"""
    try:
        data = request.json
        telegram_id = int(data.get('telegram_id'))
        amount = float(data.get('amount'))
        reason = data.get('reason', 'Не указана')
        
        # Получаем информацию о пользователе для логирования
        user = run_async(db.fetchrow(
            "SELECT username FROM users WHERE telegram_id = $1",
            telegram_id
        ))
        
        # Обнуляем бонусы
        run_async(db.execute("""
            UPDATE referral_discounts
            SET discount_amount = 0
            WHERE referrer_telegram_id = $1 AND discount_amount > 0
        """, telegram_id))
        
        # Логируем обнуление
        run_async(db.execute("""
            INSERT INTO referral_payments_log (
                telegram_id, amount, payment_type, reason, created_at, created_by
            ) VALUES ($1, $2, 'reset', $3, NOW(), $4)
        """, telegram_id, amount, reason, session.get('username', 'admin')))
        
        # Отправляем уведомление пользователю
        try:
            run_async(bot_instance.send_message(
                chat_id=telegram_id,
                text=f"ℹ️ Ваш реферальный баланс ({amount:.2f}€) был обнулен администратором.\n\n"
                     f"Причина: {reason}\n\n"
                     f"По всем вопросам обращайтесь в поддержку.",
                parse_mode="Markdown"
            ))
        except Exception as e:
            print(f"Не удалось отправить уведомление: {e}")
        
        print(f"✅ Баланс пользователя @{user.get('username', telegram_id)} обнулен: {amount}€. Причина: {reason}")
        
        return jsonify({'success': True})
    except Exception as e:
        print(f"Ошибка обнуления баланса: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/referrals/payments-history')
@login_required
def referral_payments_history():
    """История выплат и обнулений"""
    try:
        type_filter = request.args.get('type', 'all')
        page = request.args.get('page', 1, type=int)
        per_page = 50
        offset = (page - 1) * per_page
        
        # Статистика
        stats = run_async(get_payments_stats())
        
        # Список операций
        query = """
            SELECT 
                rpl.*,
                u.username
            FROM referral_payments_log rpl
            LEFT JOIN users u ON rpl.telegram_id = u.telegram_id
            WHERE 1=1
        """
        
        if type_filter != 'all':
            query += f" AND rpl.payment_type = '{type_filter}'"
        
        query += f" ORDER BY rpl.created_at DESC LIMIT {per_page} OFFSET {offset}"
        
        payments = run_async(db.fetch(query))
        
        # Подсчет для пагинации
        count_query = "SELECT COUNT(*) FROM referral_payments_log WHERE 1=1"
        if type_filter != 'all':
            count_query += f" AND payment_type = '{type_filter}'"
        
        total = run_async(db.fetchval(count_query)) or 0
        
        return render_template('referral_payments_history.html',
                             payments=[dict(p) for p in payments] if payments else [],
                             stats=stats,
                             type_filter=type_filter,
                             page=page,
                             total_pages=max(1, (total + per_page - 1) // per_page))
    except Exception as e:
        print(f"Payments history error: {e}")
        flash(f'Ошибка загрузки истории: {e}', 'danger')
        return render_template('referral_payments_history.html', 
                             payments=[], stats={}, type_filter='all', page=1, total_pages=1)

async def get_payments_stats():
    """Статистика по выплатам"""
    # Всего выплачено
    total_paid = await db.fetchval("""
        SELECT COALESCE(SUM(amount), 0)
        FROM referral_payments_log
        WHERE payment_type = 'paid'
    """) or 0
    
    # Всего обнулено
    total_reset = await db.fetchval("""
        SELECT COALESCE(SUM(amount), 0)
        FROM referral_payments_log
        WHERE payment_type = 'reset'
    """) or 0
    
    # Операций за месяц
    this_month_count = await db.fetchval("""
        SELECT COUNT(*)
        FROM referral_payments_log
        WHERE DATE_TRUNC('month', created_at) = DATE_TRUNC('month', NOW())
    """) or 0
    
    return {
        'total_paid': float(total_paid),
        'total_reset': float(total_reset),
        'this_month_count': this_month_count
    }


@app.route('/notifications')
@login_required
def notifications():
    return render_template('notifications.html')

@app.route('/notifications/send-user', methods=['POST'])
@login_required
def send_notification_to_user():
    try:
        data = request.json
        telegram_id = int(data.get('telegram_id'))
        message = data.get('message')
        
        # Проверка пользователя
        user = run_async(db.fetchrow(
            "SELECT telegram_id FROM users WHERE telegram_id = $1",
            telegram_id
        ))
        
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
        
        # Отправка через Markdown
        run_async(bot_instance.send_message(
            chat_id=telegram_id,
            text=message,
            parse_mode="Markdown"
        ))
        
        return jsonify({'success': True})
    except Exception as e:
        print(f"Send notification error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/notifications/broadcast', methods=['POST'])
@login_required
def send_broadcast():
    try:
        data = request.json
        message = data.get('message')
        
        # Создание рассылки
        run_async(notification_service.add_broadcast(message))
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ==================== ДОСТАВКА ====================

@app.route('/delivery-settings')
@login_required
def delivery_settings():
    try:
        settings = run_async(db.get_delivery_settings())
        return render_template('delivery_settings.html', settings=settings)
    except Exception as e:
        print(f"Delivery settings error: {e}")
        flash(f'Ошибка загрузки настроек доставки: {e}', 'danger')
        return render_template('delivery_settings.html', settings={})

@app.route('/delivery-settings/update', methods=['POST'])
@login_required
def update_delivery_settings():
    try:
        data = request.form
        
        # Получаем и конвертируем значения
        updates = {
            'free_delivery_threshold': int(data.get('free_delivery_threshold', 3)),
            'standard_delivery_cost': float(data.get('standard_delivery_cost', 2.0)),
        }
        
        # Пытаемся обновить в БД
        result = run_async(db.update_delivery_settings(**updates))
        
        if result:
            flash('✅ Настройки доставки обновлены!', 'success')
        else:
            flash('⚠️ Настройки доставки не обновлены (возможно, таблица не создана)', 'warning')
        
        return redirect(url_for('delivery_settings'))
    except Exception as e:
        print(f"Update delivery settings error: {e}")
        flash(f'Ошибка обновления настроек: {e}', 'danger')
        return redirect(url_for('delivery_settings'))

# ==================== ПОЛЬЗОВАТЕЛИ ====================

@app.route('/users')
@login_required
def users():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 50
        offset = (page - 1) * per_page
        
        users_data = run_async(db.fetch(f"""
            SELECT * FROM users 
            ORDER BY created_at DESC 
            LIMIT {per_page} OFFSET {offset}
        """))
        
        total = run_async(db.fetchval("SELECT COUNT(*) FROM users")) or 0
        
        return render_template('users.html', 
                             users=[dict(u) for u in users_data] if users_data else [],
                             page=page,
                             total_pages=max(1, (total + per_page - 1) // per_page))
    except Exception as e:
        print(f"Users error: {e}")
        flash(f'Ошибка загрузки пользователей: {e}', 'danger')
        return render_template('users.html', users=[], page=1, total_pages=1)

@app.route('/users/<int:telegram_id>')
@login_required
def user_detail(telegram_id):
    try:
        user = run_async(db.fetchrow(
            "SELECT * FROM users WHERE telegram_id = $1",
            telegram_id
        ))
        
        if not user:
            flash('Пользователь не найден', 'danger')
            return redirect(url_for('users'))
        
        orders = run_async(db.fetch("""
            SELECT * FROM orders 
            WHERE telegram_id = $1 
            ORDER BY created_at DESC
        """, telegram_id))
        
        return render_template('user_detail.html', 
                             user=dict(user),
                             orders=[dict(o) for o in orders] if orders else [])
    except Exception as e:
        print(f"User detail error: {e}")
        flash(f'Ошибка загрузки пользователя: {e}', 'danger')
        return redirect(url_for('users'))

# ==================== ЗАКАЗЫ ====================

@app.route('/orders')
@login_required
def orders():
    try:
        status_filter = request.args.get('status', 'all')
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        min_amount = request.args.get('min_amount', type=float)
        max_amount = request.args.get('max_amount', type=float)
        page = request.args.get('page', 1, type=int)
        per_page = 50
        offset = (page - 1) * per_page
        
        query = """
            SELECT o.*, u.username, u.phone 
            FROM orders o
            LEFT JOIN users u ON o.telegram_id = u.telegram_id
            WHERE 1=1
        """
        params = []
        param_count = 1
        
        # Фильтр по статусу
        if status_filter != 'all':
            query += f" AND o.status = ${param_count}"
            params.append(status_filter)
            param_count += 1
        
        # Фильтр по дате (от)
        if date_from:
            query += f" AND DATE(o.created_at) >= ${param_count}"
            params.append(date_from)
            param_count += 1
        
        # Фильтр по дате (до)
        if date_to:
            query += f" AND DATE(o.created_at) <= ${param_count}"
            params.append(date_to)
            param_count += 1
        
        # Фильтр по минимальной сумме
        if min_amount is not None:
            query += f" AND o.final_amount >= ${param_count}"
            params.append(min_amount)
            param_count += 1
        
        # Фильтр по максимальной сумме
        if max_amount is not None:
            query += f" AND o.final_amount <= ${param_count}"
            params.append(max_amount)
            param_count += 1
        
        query += f" ORDER BY o.created_at DESC LIMIT {per_page} OFFSET {offset}"
        
        orders_data = run_async(db.fetch(query, *params))
        
        # Подсчет общего количества для пагинации
        count_query = "SELECT COUNT(*) FROM orders o WHERE 1=1"
        count_params = []
        count_param_count = 1
        
        if status_filter != 'all':
            count_query += f" AND o.status = ${count_param_count}"
            count_params.append(status_filter)
            count_param_count += 1
        
        if date_from:
            count_query += f" AND DATE(o.created_at) >= ${count_param_count}"
            count_params.append(date_from)
            count_param_count += 1
        
        if date_to:
            count_query += f" AND DATE(o.created_at) <= ${count_param_count}"
            count_params.append(date_to)
            count_param_count += 1
        
        if min_amount is not None:
            count_query += f" AND o.final_amount >= ${count_param_count}"
            count_params.append(min_amount)
            count_param_count += 1
        
        if max_amount is not None:
            count_query += f" AND o.final_amount <= ${count_param_count}"
            count_params.append(max_amount)
            count_param_count += 1
        
        total = run_async(db.fetchval(count_query, *count_params)) or 0
        
        return render_template('orders.html',
                             orders=[dict(o) for o in orders_data] if orders_data else [],
                             status_filter=status_filter,
                             date_from=date_from,
                             date_to=date_to,
                             min_amount=min_amount,
                             max_amount=max_amount,
                             page=page,
                             total_pages=max(1, (total + per_page - 1) // per_page))
    except Exception as e:
        print(f"Orders error: {e}")
        flash(f'Ошибка загрузки заказов: {e}', 'danger')
        return render_template('orders.html', orders=[], status_filter='all', page=1, total_pages=1)

@app.route('/orders/<int:order_id>')
@login_required
def order_detail(order_id):
    try:
        order = run_async(db.fetchrow("""
            SELECT o.*, u.username, u.phone, u.telegram_id
            FROM orders o
            LEFT JOIN users u ON o.telegram_id = u.telegram_id
            WHERE o.order_id = $1
        """, order_id))
        
        if not order:
            flash('Заказ не найден', 'danger')
            return redirect(url_for('orders'))
        
        items = run_async(db.fetch("""
            SELECT oi.*, p.product_name
            FROM order_items oi
            JOIN products p ON oi.product_id = p.product_id
            WHERE oi.order_id = $1
        """, order_id))
        
        return render_template('order_detail.html',
                             order=dict(order),
                             items=[dict(i) for i in items] if items else [])
    except Exception as e:
        print(f"Order detail error: {e}")
        flash(f'Ошибка загрузки заказа: {e}', 'danger')
        return redirect(url_for('orders'))

@app.route('/orders/<int:order_id>/update-status', methods=['POST'])
@login_required
def update_order_status(order_id):
    try:
        data = request.json
        status = data.get('status')
        
        # Если заказ отклоняется, вернуть используемые промокоды
        if status == 'declined':
            # Получаем информацию о заказе
            order = run_async(db.fetchrow("""
                SELECT telegram_id, promo_code_used
                FROM orders
                WHERE order_id = $1
            """, order_id))
            
            if order and order['promo_code_used'] and order['promo_code_used'] != 'referral':
                # Получаем promo_id по коду
                promo = run_async(db.fetchrow("""
                    SELECT promo_id FROM promo_codes WHERE code = $1
                """, order['promo_code_used']))
                
                if promo:
                    # Возвращаем промокод (отмечаем как неиспользованный)
                    run_async(db.execute("""
                        UPDATE user_promocodes
                        SET is_used = FALSE, used_at = NULL
                        WHERE telegram_id = $1 AND promo_id = $2
                    """, order['telegram_id'], promo['promo_id']))
                    
                    print(f"✅ Промокод вернён пользователю {order['telegram_id']} при отклонении заказа #{order_id}")
        
        # Обновляем статус заказа
        run_async(db.execute("""
            UPDATE orders 
            SET status = $1, updated_at = NOW()
            WHERE order_id = $2
        """, status, order_id))
        
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error updating order status: {e}")
        return jsonify({'success': False, 'error': str(e)})

# ==================== API ====================

@app.route('/api/stats')
@login_required
def api_stats():
    try:
        stats = run_async(get_dashboard_stats())
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== ФИЛЬТРЫ ДЛЯ ШАБЛОНОВ ====================

@app.context_processor
def inject_now():
    """Добавляет datetime в контекст всех шаблонов"""
    return {'now': datetime.now, 'datetime': datetime}

@app.template_filter('strftime')
def strftime_filter(date, fmt='%d.%m.%Y %H:%M'):
    """Форматирование даты"""
    if date is None:
        return ''
    if isinstance(date, str):
        return date
    return date.strftime(fmt)

# ==================== ЗАПУСК ====================

if __name__ == '__main__':
    # Инициализация async компонентов
    init_async()
    
    # Запуск Flask
    debug_mode = os.getenv('FLASK_DEBUG', '0') == '1'
    app.run(debug=debug_mode, host='0.0.0.0', port=5000, threaded=True)
