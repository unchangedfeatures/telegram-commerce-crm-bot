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

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Инициализация notification_service
notification_service = None

# Конфигурация
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD_HASH = generate_password_hash("YOUR PASSWORD")  # Измените пароль!

# Глобальный event loop для async операций
loop = None

def init_async():
    """Инициализация async компонентов"""
    global loop, notification_service
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Инициализация БД
    loop.run_until_complete(db.init_db())
    
    # Инициализация notification service
    notification_service = NotificationService(bot_instance, db)

# Декоратор для проверки авторизации
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Хелпер для async функций
def run_async(coro):
    """Безопасный запуск async функций"""
    global loop
    if loop is None:
        init_async()
    
    try:
        # Если loop уже запущен в другом потоке, создаем новый
        if loop.is_running():
            new_loop = asyncio.new_event_loop()
            try:
                return new_loop.run_until_complete(coro)
            finally:
                new_loop.close()
        else:
            return loop.run_until_complete(coro)
    except Exception as e:
        print(f"Error in run_async: {e}")
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
        
        expires_at = data.get('expires_at') if data.get('expires_at') else None
        
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
                description, is_active, created_at
            ) VALUES ($1, $2, $3, $4, $5, TRUE, NOW())
        """,
        int(data['brand_id']),
        data['product_name'],
        float(data['price']),
        int(data['stock_quantity']),
        data.get('description', '')))
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ==================== УВЕДОМЛЕНИЯ ====================

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
        
        # Отправка
        run_async(notification_service.add(telegram_id, message))
        
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
        page = request.args.get('page', 1, type=int)
        per_page = 50
        offset = (page - 1) * per_page
        
        query = """
            SELECT o.*, u.username, u.phone 
            FROM orders o
            LEFT JOIN users u ON o.telegram_id = u.telegram_id
        """
        
        if status_filter != 'all':
            query += f" WHERE o.status = '{status_filter}'"
        
        query += f" ORDER BY o.created_at DESC LIMIT {per_page} OFFSET {offset}"
        
        orders_data = run_async(db.fetch(query))
        
        count_query = "SELECT COUNT(*) FROM orders"
        if status_filter != 'all':
            count_query += f" WHERE status = '{status_filter}'"
        
        total = run_async(db.fetchval(count_query)) or 0
        
        return render_template('orders.html',
                             orders=[dict(o) for o in orders_data] if orders_data else [],
                             status_filter=status_filter,
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
        
        run_async(db.execute("""
            UPDATE orders 
            SET status = $1, updated_at = NOW()
            WHERE order_id = $2
        """, status, order_id))
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    
@app.route('/analytics')
@login_required
def analytics():
    try:
        analytics_data = run_async(get_marketing_analytics())
        return render_template('analytics.html', data=analytics_data)
    except Exception as e:
        flash(f'Ошибка загрузки аналитики: {e}', 'danger')
        return render_template('analytics.html', data={})
    
@app.route('/segments')
@login_required
def user_segments():
    segments = run_async(get_user_segments())
    return render_template('segments.html', segments=segments)

async def get_user_segments():
    return {
        'new_users': await db.fetch("""
            SELECT * FROM users 
            WHERE created_at >= NOW() - INTERVAL '7 days'
        """),
        'active_buyers': await db.fetch("""
            SELECT u.* FROM users u
            JOIN orders o ON u.telegram_id = o.telegram_id
            WHERE o.created_at >= NOW() - INTERVAL '30 days'
            GROUP BY u.user_id
            HAVING COUNT(o.order_id) >= 2
        """),
        'churned': await db.fetch("""
            SELECT u.* FROM users u
            LEFT JOIN orders o ON u.telegram_id = o.telegram_id 
                AND o.created_at >= NOW() - INTERVAL '60 days'
            WHERE u.total_orders > 0 AND o.order_id IS NULL
        """),
        'high_value': await db.fetch("""
            SELECT * FROM users 
            WHERE total_spent > 50
            ORDER BY total_spent DESC
        """)
    }

# Рассылка по сегментам
@app.route('/broadcast-segment', methods=['POST'])
@login_required
def broadcast_to_segment():
    data = request.json
    segment = data.get('segment')
    message = data.get('message')
    
    # Получить пользователей сегмента и отправить
    users = run_async(get_user_segments (segment))
    
    for user in users:
        run_async(notification_service.add(user['telegram_id'], message))
    
    return jsonify({'success': True, 'sent': len(users)})

async def get_marketing_analytics():
    # Конверсия по воронке
    funnel = await db.fetchrow("""
        SELECT 
            COUNT(DISTINCT u.telegram_id) as total_users,
            COUNT(DISTINCT CASE WHEN o.order_id IS NOT NULL THEN u.telegram_id END) as users_with_orders,
            COUNT(DISTINCT CASE WHEN o.status = 'completed' THEN u.telegram_id END) as completed_buyers,
            COUNT(o.order_id) as total_orders,
            COALESCE(AVG(o.final_amount), 0) as avg_order_value,
            COALESCE(SUM(CASE WHEN o.status = 'completed' THEN o.final_amount ELSE 0 END), 0) as total_revenue
        FROM users u
        LEFT JOIN orders o ON u.telegram_id = o.telegram_id
    """)
    
    # LTV по когортам
    cohorts = await db.fetch("""
        SELECT 
            DATE_TRUNC('week', u.created_at) as cohort_week,
            COUNT(DISTINCT u.telegram_id) as users,
            COALESCE(SUM(o.final_amount), 0) as revenue,
            COALESCE(AVG(o.final_amount), 0) as avg_ltv
        FROM users u
        LEFT JOIN orders o ON u.telegram_id = o.telegram_id AND o.status = 'completed'
        GROUP BY cohort_week
        ORDER BY cohort_week DESC
        LIMIT 12
    """)
    
    # Эффективность промокодов
    promo_stats = await db.fetch("""
        SELECT 
            pc.code,
            pc.current_uses,
            pc.max_uses,
            COUNT(o.order_id) as orders_count,
            COALESCE(SUM(o.final_amount), 0) as revenue_generated,
            COALESCE(SUM(o.discount_amount), 0) as discount_given
        FROM promo_codes pc
        LEFT JOIN orders o ON o.promo_code_used = pc.code
        WHERE pc.created_at >= NOW() - INTERVAL '30 days'
        GROUP BY pc.promo_id
        ORDER BY revenue_generated DESC
    """)
    
    # Реферальная программа
    referral_stats = await db.fetchrow("""
        SELECT 
            COUNT(DISTINCT referred_by) as active_referrers,
            COUNT(*) as total_referrals,
            COALESCE(SUM(rd.discount_amount), 0) as total_bonuses_paid
        FROM users u
        LEFT JOIN referral_discounts rd ON u.telegram_id = rd.referred_telegram_id
        WHERE u.referred_by IS NOT NULL
    """)
    
    # Популярные товары
    top_products = await db.fetch("""
        SELECT 
            p.product_name,
            COUNT(oi.order_item_id) as times_ordered,
            SUM(oi.quantity) as units_sold,
            COALESCE(SUM(oi.total_price), 0) as revenue
        FROM products p
        JOIN order_items oi ON p.product_id = oi.product_id
        JOIN orders o ON oi.order_id = o.order_id
        WHERE o.created_at >= NOW() - INTERVAL '30 days'
        GROUP BY p.product_id
        ORDER BY revenue DESC
        LIMIT 10
    """)
    
    # Активность по дням недели и часам
    activity = await db.fetch("""
        SELECT 
            EXTRACT(DOW FROM created_at) as day_of_week,
            EXTRACT(HOUR FROM created_at) as hour,
            COUNT(*) as orders_count
        FROM orders
        WHERE created_at >= NOW() - INTERVAL '30 days'
        GROUP BY day_of_week, hour
        ORDER BY day_of_week, hour
    """)
    
    return {
        'funnel': dict(funnel),
        'cohorts': [dict(c) for c in cohorts],
        'promo_stats': [dict(p) for p in promo_stats],
        'referral_stats': dict(referral_stats),
        'top_products': [dict(p) for p in top_products],
        'activity': [dict(a) for a in activity]
    }


@app.route('/api/realtime-stats')
@login_required
def realtime_stats():
    """API для реал-тайм дашборда"""
    stats = run_async(get_realtime_stats())
    return jsonify(stats)

async def get_realtime_stats():
    return {
        'online_now': await db.fetchval("""
            SELECT COUNT(*) FROM users 
            WHERE last_active >= NOW() - INTERVAL '5 minutes'
        """),
        'orders_today': await db.fetchval("""
            SELECT COUNT(*) FROM orders 
            WHERE DATE(created_at) = CURRENT_DATE
        """),
        'revenue_today': await db.fetchval("""
            SELECT COALESCE(SUM(final_amount), 0) FROM orders 
            WHERE DATE(created_at) = CURRENT_DATE AND status = 'completed'
        """),
        'cart_value_avg': await db.fetchval("""
            SELECT AVG(
                (SELECT SUM((value->>'price')::numeric * (value->>'quantity')::int) 
                 FROM jsonb_each(items_json::jsonb))
            ) FROM cart WHERE items_json != '{}'
        """)
    }
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
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)
