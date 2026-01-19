from aiogram import Router, types, F
from aiogram.filters import Command
from datetime import datetime
from zoneinfo import ZoneInfo
from dateutil import parser as date_parser
import json
from aiogram.types import InlineKeyboardButton
import aiogram


router = Router()


# Вспомогательная функция для проверки роли администратора
async def is_admin(db, telegram_id: int) -> bool:
    try:
        user = await db.fetchrow("SELECT role FROM users WHERE telegram_id = $1", telegram_id)
        return user and user["role"] == "admin"
    except Exception:
        return False

@router.message(Command("promo"))
async def promo_register(message: types.Message, db):
    parts = message.text.split()
    
    # Проверяем регистрацию пользователя
    user = await db.fetchrow("SELECT telegram_id FROM users WHERE telegram_id = $1", message.from_user.id)
    if not user:
        return await message.answer("❌ Вы не зарегистрированы в системе.")
    
    if len(parts) < 2:
        return await message.answer("❗ Использование: /promo <код>")

    promo_code = parts[1].strip().upper()
    telegram_id = message.from_user.id

    # 1) Найти промокод
    promo = await db.fetchrow("""
        SELECT *
        FROM promo_codes
        WHERE code = $1
    """, promo_code)

    if not promo:
        return await message.answer("❌ Такого промокода не существует.")

    # 2) Проверка активности
    if not promo["is_active"]:
        return await message.answer("❌ Промокод не активен.")

    now = datetime.now()

    # 3) Проверка даты окончания (expires_at)
    if promo.get("expires_at"):
        expires_at = promo["expires_at"]
        if expires_at.tzinfo is not None:
            expires_at = expires_at.replace(tzinfo=None)
        if now > expires_at:
            return await message.answer("❌ Срок действия промокода истёк.")

    # 4) Проверка использований
    if promo.get("max_uses", 0) > 0 and promo.get("current_uses", 0) >= promo["max_uses"]:
        return await message.answer("❌ Превышен лимит использований промокода.")

    # 5) Проверка, есть ли у юзера этот промокод
    existing = await db.fetchrow("""
        SELECT 1
        FROM user_promocodes
        WHERE telegram_id = $1 AND promo_id = $2
    """, telegram_id, promo["promo_id"])

    if existing:
        return await message.answer("⚠️ Этот промокод уже привязан к вашему аккаунту.")

    # 6) Привязать промокод юзеру
    await db.execute("""
        INSERT INTO user_promocodes (telegram_id, promo_id)
        VALUES ($1, $2)
    """, telegram_id, promo["promo_id"])

    # 7) Увеличить current_uses
    await db.execute("""
        UPDATE promo_codes
        SET current_uses = current_uses + 1
        WHERE promo_id = $1
    """, promo["promo_id"])

    # 8) Формируем информацию о скидке
    discount_info = ""
    if promo.get("discount_percent"):
        discount_info = f"{promo['discount_percent']}% скидка"
    elif promo.get("discount_amount"):
        discount_info = f"{promo['discount_amount']}€ скидка"
    
    # 9) Отправить сообщение
    remaining = promo.get("max_uses", 0) - (promo.get("current_uses", 0) + 1) if promo.get("max_uses", 0) > 0 else "∞"
    
    await message.answer(
        f"🎉 *Промокод успешно активирован!* `{promo_code}`\n\n"
        f"💰 Тип скидки: *{discount_info}*\n"
        f"💵 Мин. заказ: *{promo.get('min_order_amount', 0)}€*\n\n"
        f"⏳ Действует до: *{promo.get('expires_at', 'Бессрочно')}*\n"
        f"♻️ Оставшееся количество использований: *{remaining}*\n",
        parse_mode="Markdown"
    )

@router.message(Command("createpromo"))
async def create_promo(message: types.Message, db):
    # Проверка роли
    if not await is_admin(db, message.from_user.id):
        return await message.answer("❌ У вас нет прав для создания промокода.")

    # Синтаксис команды:
    # /createpromo CODE PERCENT|AMOUNT VALUE MIN_ORDER MAX_USES EXPIRES_AT NOTE
    # PERCENT|AMOUNT = "percent" или "amount"
    # VALUE = число (процент или сумма)
    # MIN_ORDER = минимальная сумма заказа
    # MAX_USES = максимальное количество использований (0 = безлимит)
    # EXPIRES_AT = дата в формате YYYY-MM-DD
    # NOTE = текст, может быть в кавычках

    parts = message.text.split(maxsplit=7)
    if len(parts) < 8:
        return await message.answer(
            "❗ Использование:\n"
            "/createpromo CODE TYPE VALUE MIN_ORDER MAX_USES EXPIRES_AT NOTE\n\n"
            "Тип: percent (процент) или amount (фиксированная сумма)\n"
            "Пример:\n"
            "/createpromo NEWYEAR percent 10 20 100 2025-12-31 'Новогодняя акция'"
        )

    _, code, promo_type, value, min_order, max_uses, expires_at, note = parts

    try:
        value = float(value)
        min_order = float(min_order)
        max_uses = int(max_uses)
        expires_at = date_parser.parse(expires_at)
        
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=ZoneInfo("Europe/Vilnius"))
    except Exception as e:
        return await message.answer(f"❌ Ошибка парсинга данных: {e}")

    # Проверка уникальности кода
    exists = await db.fetchrow("SELECT 1 FROM promo_codes WHERE code = $1", code.upper())
    if exists:
        return await message.answer("❌ Промокод с таким названием уже существует.")

    # Определяем тип скидки
    discount_percent = None
    discount_amount = None
    
    if promo_type.lower() == "percent":
        discount_percent = value
    elif promo_type.lower() == "amount":
        discount_amount = value
    else:
        return await message.answer("❌ Тип скидки должен быть 'percent' или 'amount'")

    # Вставка в базу
    await db.execute("""
        INSERT INTO promo_codes (
            code, discount_percent, discount_amount, 
            min_order_amount, max_uses, current_uses,
            created_by, expires_at, is_active, created_at
        ) VALUES (
            $1, $2, $3, $4, $5, 0,
            $6, $7, TRUE, NOW()
        )
    """, code.upper(), discount_percent, discount_amount, 
         min_order, max_uses, message.from_user.id, expires_at)

    # Формируем информацию о скидке
    discount_info = ""
    if discount_percent:
        discount_info = f"{discount_percent}% скидка"
    else:
        discount_info = f"{discount_amount}€ скидка"

    await message.answer(
        f"🎉 *Промокод успешно создан!*\n\n"
        f"📄 *Описание:* {note or 'Нет'}\n"
        f"💰 Тип скидки: *{discount_info}*\n"
        f"💵 Мин. заказ: *{min_order}€*\n\n"
        f"⏳ Действует до: *{expires_at}*\n"
        f"♻️ Максимальное количество использований: *{max_uses if max_uses > 0 else 'безлимит'}*\n",
        parse_mode="Markdown"
    )

@router.message(Command("activepromos"))
async def active_promos(message: types.Message, db):
    if not await is_admin(db, message.from_user.id):
        return await message.answer("❌ У вас нет прав для просмотра.")
    
    rows = await db.fetch("""
        SELECT code, discount_percent, discount_amount, 
               expires_at, max_uses, current_uses
        FROM promo_codes 
        WHERE is_active = TRUE 
          AND (expires_at IS NULL OR expires_at > NOW()) 
        ORDER BY created_at DESC
    """)
    
    if not rows:
        return await message.answer("На данный момент активных промокодов нет.")
    
    promos_text = "🔥 Активные промокоды:\n\n"
    for row in rows:
        discount_info = ""
        if row["discount_percent"]:
            discount_info = f"{row['discount_percent']}%"
        elif row["discount_amount"]:
            discount_info = f"{row['discount_amount']}€"
        
        remaining = row["max_uses"] - row["current_uses"] if row["max_uses"] > 0 else "∞"
        expires = row["expires_at"].strftime("%Y-%m-%d") if row["expires_at"] else "Бессрочно"
        
        promos_text += f"• `{row['code']}` - {discount_info}\n"
        promos_text += f"  Использовано: {row['current_uses']}/{row['max_uses'] if row['max_uses'] > 0 else '∞'}\n"
        promos_text += f"  Действует до: {expires}\n\n"
    
    await message.answer(promos_text, parse_mode="Markdown")

@router.message(Command("disablepromo"))
async def disable_promo(message: types.Message, db):
    if not await is_admin(db, message.from_user.id):
        return await message.answer("❌ У вас нет прав для деактивации промокода.")

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer("❗ Использование: /disablepromo CODE")

    code = parts[1].upper()
    
    # Проверяем существует ли промокод
    promo = await db.fetchrow("SELECT promo_id FROM promo_codes WHERE code = $1", code)
    if not promo:
        return await message.answer("❌ Промокод не найден.")
    
    updated = await db.execute(
        "UPDATE promo_codes SET is_active = FALSE WHERE code = $1", 
        code
    )
    
    if updated:
        await message.answer(f"✅ Промокод {code} деактивирован и больше не может использоваться.")
    else:
        await message.answer("❌ Не удалось деактивировать промокод.")

# Остальные команды остаются аналогичными, но нужно обновить SQL запросы
@router.message(Command("createpromotion"))
async def create_promotion(message: types.Message, db):
    if not await is_admin(db, message.from_user.id):
        return await message.answer("❌ У вас нет прав для создания промо-акции.")

    # Синтаксис:
    # /createpromotion "Заголовок" banner_url "Описание" start_date end_date
    parts = message.text.split(maxsplit=5)
    if len(parts) < 6:
        return await message.answer(
            "❗ Использование:\n"
            "/createpromotion \"Заголовок\" banner_url \"Описание\" start_date end_date\n"
            "Пример:\n"
            '/createpromotion "Новый год" https://img.url "Супер акция" 2025-12-20 2025-12-31'
        )

    _, title, banner_url, description, start_date, end_date = parts
    try:
        start_date = date_parser.parse(start_date)
        end_date = date_parser.parse(end_date)
    except Exception as e:
        return await message.answer(f"❌ Ошибка парсинга даты: {e}")

    await db.execute("""
        INSERT INTO promotions (title, banner_url, description, is_active, start_date, end_date, created_at)
        VALUES ($1, $2, $3, TRUE, $4, $5, NOW())
    """, title, banner_url, description, start_date, end_date)

    await message.answer(f"✅ Промо-акция '{title}' успешно создана!")

@router.message(Command("deletepromotion"))
async def delete_promotion(message: types.Message, db):
    if not await is_admin(db, message.from_user.id):
        return await message.answer("❌ У вас нет прав для удаления промо-акции.")

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer("❗ Использование: /deletepromotion PROMOTION_ID")

    try:
        promotion_id = int(parts[1])
    except ValueError:
        return await message.answer("❌ PROMOTION_ID должен быть числом.")

    result = await db.execute("DELETE FROM promotions WHERE promotion_id = $1", promotion_id)
    await message.answer(f"✅ Промо-акция удалена." if result else "❌ Промо-акция не найдена.")

@router.message(Command("notify"))
async def notify_user_simple(message: types.Message, db, notification_service):
    """
    Использование:
    /notify <telegram_id> Текст уведомления
    Для кнопок используйте отдельную команду /notifybutton
    """
    if not await is_admin(db, message.from_user.id):
        return await message.answer("❌ У вас нет прав для этой команды.")

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        return await message.answer("❗ Использование: /notify <telegram_id> Текст")

    try:
        telegram_id = int(parts[1])
    except ValueError:
        return await message.answer("❌ telegram_id должен быть числом.")

    text = parts[2]
    
    try:
        await notification_service._send_to_user(telegram_id, text)
        await message.answer(f"✅ Уведомление для {telegram_id} отправлено.")
    except Exception as e:
        await message.answer(f"❌ Ошибка отправки уведомления: {e}")

@router.message(Command("broadcast"))
async def broadcast_simple(message: types.Message, db, notification_service):
    """
    Использование:
    /broadcast Текст уведомления
    """
    if not await is_admin(db, message.from_user.id):
        return await message.answer("❌ У вас нет прав для этой команды.")

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer("❗ Использование: /broadcast Текст")

    text = parts[1]
    
    try:
        await notification_service.add_broadcast(text)
        await message.answer(f"✅ Рассылка добавлена в очередь.")
    except Exception as e:
        await message.answer(f"❌ Ошибка создания рассылки: {e}")

@router.message(Command("notifybutton"))
async def notify_user_with_button(message: types.Message, db, notification_service):
    """
    Использование:
    Для URL кнопок: /notifybutton <telegram_id> Текст | КнопкаТекст | url:https://example.com
    Для callback кнопок: /notifybutton <telegram_id> Текст | КнопкаТекст | callback:действие_данные
    Примеры:
    /notifybutton 123456789 Привет! | Перейти | url:https://t.me/pewpuff_bot
    /notifybutton 123456789 Выберите действие | Профиль | callback:show_profile
    /notifybutton 123456789 Товары | Каталог | callback:catalogue
    """
    if not await is_admin(db, message.from_user.id):
        return await message.answer("❌ У вас нет прав для этой команды.")

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        return await message.answer(
            "❗ Использование:\n"
            "/notifybutton <telegram_id> Текст | КнопкаТекст | url:ссылка\n"
            "ИЛИ\n"
            "/notifybutton <telegram_id> Текст | КнопкаТекст | callback:действие"
        )

    try:
        telegram_id = int(parts[1])
    except ValueError:
        return await message.answer("❌ telegram_id должен быть числом.")

    payload = parts[2]
    
    # Парсим текст и кнопку
    if '|' in payload:
        split_parts = [part.strip() for part in payload.split('|', 2)]
        
        if len(split_parts) == 3:
            text, button_text, action = split_parts
            
            # Определяем тип кнопки
            if action.startswith('url:'):
                url = action[4:]  # Убираем 'url:'
                buttons = [[InlineKeyboardButton(text=button_text, url=url)]]
            elif action.startswith('callback:'):
                callback_data = action[9:]  # Убираем 'callback:'
                buttons = [[InlineKeyboardButton(text=button_text, callback_data=callback_data)]]
            else:
                # По умолчанию считаем callback
                buttons = [[InlineKeyboardButton(text=button_text, callback_data=action)]]
            
            try:
                await notification_service._send_to_user(telegram_id, text, buttons)
                await message.answer(f"✅ Уведомление с кнопкой для {telegram_id} отправлено.")
                return
            except Exception as e:
                await message.answer(f"❌ Ошибка отправки уведомления: {e}")
                return
    
    await message.answer(
        "❗ Использование:\n"
        "/notifybutton <telegram_id> Текст | КнопкаТекст | url:ссылка\n"
        "ИЛИ\n"
        "/notifybutton <telegram_id> Текст | КнопкаТекст | callback:действие"
    )

@router.message(Command("broadcastbutton"))
async def broadcast_with_button(message: types.Message, db, notification_service):
    """
    Использование:
    Для URL кнопок: /broadcastbutton Текст | КнопкаТекст | url:https://example.com
    Для callback кнопок: /broadcastbutton Текст | КнопкаТекст | callback:действие_данные
    Примеры:
    /broadcastbutton Новое обновление! | Подробнее | url:https://t.me/pewpuff_bot
    /broadcastbutton Выберите действие | Профиль | callback:show_profile
    /broadcastbutton Скидки! | Посмотреть | callback:promo
    """
    if not await is_admin(db, message.from_user.id):
        return await message.answer("❌ У вас нет прав для этой команды.")

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer(
            "❗ Использование:\n"
            "/broadcastbutton Текст | КнопкаТекст | url:ссылка\n"
            "ИЛИ\n"
            "/broadcastbutton Текст | КнопкаТекст | callback:действие"
        )

    payload = parts[1]
    
    # Парсим текст и кнопку
    if '|' in payload:
        split_parts = [part.strip() for part in payload.split('|', 2)]
        
        if len(split_parts) == 3:
            text, button_text, action = split_parts
            
            # Определяем тип кнопки
            if action.startswith('url:'):
                url = action[4:]  # Убираем 'url:'
                buttons = [[InlineKeyboardButton(text=button_text, url=url)]]
            elif action.startswith('callback:'):
                callback_data = action[9:]  # Убираем 'callback:'
                buttons = [[InlineKeyboardButton(text=button_text, callback_data=callback_data)]]
            else:
                # По умолчанию считаем callback
                buttons = [[InlineKeyboardButton(text=button_text, callback_data=action)]]
            
            try:
                await notification_service.add_broadcast(text, buttons)
                await message.answer(f"✅ Рассылка с кнопкой добавлена в очередь.")
                return
            except Exception as e:
                await message.answer(f"❌ Ошибка создания рассылки: {e}")
                return
    
    await message.answer(
        "❗ Использование:\n"
        "/broadcastbutton Текст | КнопкаТекст | url:ссылка\n"
        "ИЛИ\n"
        "/broadcastbutton Текст | КнопкаТекст | callback:действие"
    )
@router.message(Command("admincommands"))
async def admin_commands(message: types.Message, db):
    if not await is_admin(db, message.from_user.id):
        return await message.answer("❌ У вас нет прав для просмотра.")
    
    args = message.text.split()
    if len(args) > 1 and args[1].lower() == "full":
        commands_text = (
            "🛠️ Полный список команд администратора:\n\n"
            "ПРОМОКОДЫ:\n"
            "/createpromo CODE TYPE VALUE MIN_ORDER MAX_USES VALID_UNTIL NOTE - Создать промокод\n"
            "/deletepromo CODE - Удалить промокод\n"
            "/activepromos - Показать активные промокоды\n"
            "/disablepromo CODE - Деактивировать промокод\n"
            "/createpromotion \"Заголовок\" banner_url \"Описание\" start_date end_date - Создать промо-акцию\n"
            "/deletepromotion PROMOTION_ID - Удалить промо-акцию\n\n"
            "УВЕДОМЛЕНИЯ:\n"
            "/notify <telegram_id> \"Текст\" - Отправить уведомление пользователю\n"
            "/broadcast \"Текст\" - Создать глобальную рассылку\n"
            "/notifybutton <telegram_id> \"Текст | КнопкаТекст | url:ссылка/callback:действие\" - Отправить с кнопкой\n"
            "/broadcastbutton \"Текст | КнопкаТекст | url:ссылка/callback:действие\" - Рассылка с кнопкой\n\n"
            "ЗАКАЗЫ:\n"
            "/accept <order_id> - Принять заказ\n"
            "/decline <order_id> - Отклонить заказ\n"
            "/deliver <order_id> <мин> - Отметить как отправленный\n"
            "/confirm <order_id> - Подтвердить оплату и завершить\n"
            "/orders - Показать неподтвержденные заказы\n"
            "/pending_orders - Показать все активные заказы\n"
            "/look_order <id> - Показать конкретный заказ\n\n"
            "ТОВАРЫ:\n"
            "/stock - Просмотр продуктов\n"
            "/stock set <product_id> <qty> - Установить остаток\n"
            "/stock add <brand_id> <name> <price> <qty> - Добавить товар\n\n"
            "СТАТИСТИКА:\n"
            "/stats - Общая статистика бота\n"
            "/refstats - Статистика реферальной программы\n\n"
            "/users - Список пользователей"
        )
        await message.answer(commands_text)
    else:
        commands_text = (
            "🛠️ Краткий список команд:\n\n"
            "/createpromo - Создать промокод\n"
            "/activepromos - Активные промокоды\n"
            "/notify - Отправить уведомление\n"
            "/broadcast - Глобальная рассылка\n"
            "/accept - Принять заказ\n"
            "/orders - Неподтвержденные заказы\n"
            "/stock - Управление товарами\n"
            "/stats - Общая статистика\n"
            "/refstats - Статистика рефералки\n\n"
            "Используйте /admincommands full для полного списка."
        )
        await message.answer(commands_text)

@router.message(Command("stock"))
async def stock_manager(message: types.Message, db):
    if not await is_admin(db, message.from_user.id):
        return await message.answer("❌ У вас нет прав для этой команды.")
    
    args = message.text.split()
    
    if len(args) > 1:
        action = args[1].lower()

        # Изменение количества
        if action == "set" and len(args) == 4:
            try:
                product_id = int(args[2])
                qty = int(args[3])
                await db.execute(
                    "UPDATE products SET stock_quantity = $1 WHERE product_id = $2",
                    qty, product_id
                )
                await message.answer(f"✅ Остаток для {product_id} установлен на {qty} шт.")
            except ValueError:
                await message.answer("❌ Некорректный формат. Используй /stock set <product_id> <qty>")
            return

        # Добавление нового продукта
        if action == "add" and len(args) == 6:
            try:
                brand_id = int(args[2])
                product_name = args[3]
                price = float(args[4])
                qty = int(args[5])
                await db.execute("""
                    INSERT INTO products (brand_id, product_name, price, stock_quantity, is_active, created_at)
                    VALUES ($1, $2, $3, $4, TRUE, NOW())
                """, brand_id, product_name, price, qty)
                await message.answer(f"✅ Добавлен продукт '{product_name}' с остатком {qty} шт.")
            except Exception as e:
                await message.answer(f"❌ Ошибка: {str(e)}")
            return
        
        if action == "help":
            help_text = (
                "🛠️ *Команды управления остатками:*\n\n"
                "/stock - Просмотр остатков всех продуктов\n"
                "/stock set <product_id> <qty> - Установить остаток продукта\n"
                "/stock add <brand_id> <product_name> <price> <qty> - Добавить новый продукт\n"
            )
            await message.answer(help_text, parse_mode="Markdown")
            return
        
        await message.answer("❌ Неверная команда. Используй /stock, /stock set или /stock add")
        return

    # Просмотр остатков
    brands = await db.fetch("SELECT brand_id, brand_name FROM brands ORDER BY brand_name")
    if not brands:
        return await message.answer("❌ Нет брендов в базе.")

    response_lines = []

    for brand in brands:
        response_lines.append(f"📦 *{brand['brand_name']}*:")

        products = await db.fetch("""
            SELECT product_id, product_name, stock_quantity, price, times_chosen 
            FROM products 
            WHERE brand_id = $1 AND is_active = TRUE 
            ORDER BY product_name
        """, brand["brand_id"])
        
        if not products:
            response_lines.append("  Нет продуктов")
            continue

        for product in products:
            response_lines.append(
                f"  • {product['product_name']} (ID: {product['product_id']}): "
                f"{product['stock_quantity']} шт × {product['price']}€ "
                f"(выбрано {product['times_chosen']})"
            )

    if not response_lines:
        await message.answer("❌ Нет товаров на складе.")
    else:
        await message.answer("\n".join(response_lines), parse_mode="Markdown")

# В начале файла добавьте импорт
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


# Исправленный обработчик activate_promo_from_message:
@router.callback_query(F.data.startswith("activate_promo_"))
async def activate_promo_from_message(callback: types.CallbackQuery, db):
    """Обработчик активации промокода из рассылки"""
    promo_code = callback.data.replace("activate_promo_", "").strip()
    telegram_id = callback.from_user.id
    
    # Проверяем регистрацию пользователя
    user = await db.fetchrow("SELECT telegram_id FROM users WHERE telegram_id = $1", telegram_id)
    if not user:
        await callback.answer("❌ Вы не зарегистрированы в системе.", show_alert=True)
        return
    
    # Находим промокод
    promo = await db.fetchrow("""
        SELECT *
        FROM promo_codes
        WHERE code = $1
    """, promo_code)
    
    if not promo:
        await callback.answer("❌ Промокод не найден.", show_alert=True)
        return
    
    # Проверка активности
    if not promo["is_active"]:
        await callback.answer("❌ Промокод не активен.", show_alert=True)
        return
    
    now = datetime.now(ZoneInfo("Europe/Vilnius"))
    
    # Проверка срока действия (исправлено сравнение дат)
    if promo.get("expires_at"):
        # Приводим обе даты к одному типу (aware или naive)
        expires_at = promo["expires_at"]
        
        # Если expires_at не имеет таймзоны, добавляем UTC
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        
        # Если now не имеет таймзоны (маловероятно), добавляем
        if now.tzinfo is None:
            now = now.replace(tzinfo=ZoneInfo("Europe/Vilnius"))
        
        # Приводим к одной таймзоне для сравнения
        expires_at_local = expires_at.astimezone(ZoneInfo("Europe/Vilnius"))
        
        if now > expires_at_local:
            await callback.answer("❌ Срок действия промокода истёк.", show_alert=True)
            return
    
    # Проверка лимита использований
    if promo.get("max_uses", 0) > 0 and promo.get("current_uses", 0) >= promo["max_uses"]:
        await callback.answer("❌ Превышен лимит использований промокода.", show_alert=True)
        return
    
    # Проверяем, есть ли уже у пользователя
    existing = await db.fetchrow("""
        SELECT 1
        FROM user_promocodes
        WHERE telegram_id = $1 AND promo_id = $2
    """, telegram_id, promo["promo_id"])
    
    if existing:
        await callback.answer("⚠️ Этот промокод уже привязан к вашему аккаунту.", show_alert=True)
        return
    
    # Активируем промокод
    await db.execute("""
        INSERT INTO user_promocodes (telegram_id, promo_id)
        VALUES ($1, $2)
    """, telegram_id, promo["promo_id"])
    
    # Увеличиваем счетчик использований
    await db.execute("""
        UPDATE promo_codes
        SET current_uses = current_uses + 1
        WHERE promo_id = $1
    """, promo["promo_id"])
    
    # Формируем информацию
    discount_info = ""
    if promo.get("discount_percent"):
        discount_info = f"{promo['discount_percent']}% скидка"
    elif promo.get("discount_amount"):
        discount_info = f"{promo['discount_amount']}€ скидка"
    
    remaining = promo.get("max_uses", 0) - (promo.get("current_uses", 0) + 1) if promo.get("max_uses", 0) > 0 else "∞"
    
    # Форматируем дату
    expires_text = "Бессрочно"
    if promo.get("expires_at"):
        expires_at = promo["expires_at"]
        if expires_at.tzinfo:
            expires_at = expires_at.astimezone(ZoneInfo("Europe/Vilnius"))
        expires_text = expires_at.strftime("%d.%m.%Y %H:%M")
    
    await callback.answer(
        f"✅ Промокод {promo_code} активирован!\n"
        f"💰 {discount_info}\n"
        f"💵 Мин. заказ: {promo.get('min_order_amount', 0)}€",
        show_alert=True
    )
    
    # Обновляем сообщение или отправляем подтверждение
    await callback.message.answer(
        f"🎉 *Промокод успешно активирован!*\n\n"
        f"`{promo_code}` - {discount_info}\n"
        f"💵 Мин. заказ: {promo.get('min_order_amount', 0)}€\n"
        f"⏳ Действует до: {expires_text}",
        parse_mode="Markdown"
    )

@router.message(Command("orders"))
async def orders_command(message: types.Message, db):
    """Показывает список заказов пользователя"""
    user_id = message.from_user.id
    
    # Проверяем регистрацию
    user = await db.fetchrow("SELECT telegram_id FROM users WHERE telegram_id = $1", user_id)
    if not user:
        return await message.answer("❌ Вы не зарегистрированы в системе.")
    
    # Получаем заказы пользователя
    orders = await db.fetch("""
        SELECT order_id, status, final_amount, created_at
        FROM orders
        WHERE telegram_id = $1
        ORDER BY created_at DESC
        LIMIT 10
    """, user_id)
    
    if not orders:
        return await message.answer("📭 У вас пока нет заказов.")
    
    text = "📋 *Ваши заказы:*\n\n"
    for order in orders:
        status_emoji = {
            'pending': '⏳',
            'accepted': '✅',
            'delivery': '🚚',
            'completed': '💰',
            'declined': '❌'
        }.get(order['status'], '❓')
        
        text += f"{status_emoji} Заказ #{order['order_id']} - {order['final_amount']}€ - {order['status']}\n"
    
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("refstats"))
async def referral_statistics(message: types.Message, db):
    """Статистика по реферальной программе для админов"""
    if not await is_admin(db, message.from_user.id):
        return await message.answer("❌ У вас нет прав для просмотра.")
    
    # Общая сумма "напечатанных денег" (начисленных бонусов)
    total_bonuses_issued = await db.fetchval("""
        SELECT COALESCE(SUM(
            CASE 
                WHEN order_id IS NOT NULL THEN discount_amount 
                ELSE 0 
            END
        ), 0)
        FROM referral_discounts
    """) or 0.0
    
    # Сумма использованных бонусов (списанных)
    total_bonuses_used = await db.fetchval("""
        SELECT COALESCE(SUM(discount_amount), 0)
        FROM orders
        WHERE promo_code_used = 'referral' AND status IN ('completed', 'delivery', 'accepted')
    """) or 0.0
    
    # Активные бонусы (доступные для использования)
    total_bonuses_active = await db.fetchval("""
        SELECT COALESCE(SUM(discount_amount), 0)
        FROM referral_discounts
        WHERE discount_amount > 0
    """) or 0.0
    
    # Топ рефереров
    top_referrers = await db.fetch("""
        SELECT 
            u.username,
            u.telegram_id,
            COUNT(DISTINCT ref.telegram_id) as referrals_count,
            COALESCE(SUM(rd.discount_amount), 0) as total_earned
        FROM users u
        LEFT JOIN users ref ON ref.referred_by = u.telegram_id
        LEFT JOIN referral_discounts rd ON rd.referrer_telegram_id = u.telegram_id
        WHERE ref.telegram_id IS NOT NULL
        GROUP BY u.user_id
        ORDER BY total_earned DESC
        LIMIT 10
    """)
    
    # Статистика по уровням
    level1_bonuses = await db.fetchval("""
        SELECT COALESCE(SUM(discount_amount), 0)
        FROM referral_discounts
        WHERE discount_amount = 2.00
    """) or 0.0
    
    level2_bonuses = await db.fetchval("""
        SELECT COALESCE(SUM(discount_amount), 0)
        FROM referral_discounts
        WHERE discount_amount = 0.50
    """) or 0.0
    
    # Формируем ответ
    text = "💰 СТАТИСТИКА РЕФЕРАЛЬНОЙ ПРОГРАММЫ\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n\n"
    
    text += "📊 Общая информация:\n"
    text += f"   💵 Всего начислено: {total_bonuses_issued:.2f}€\n"
    text += f"   ✅ Использовано: {total_bonuses_used:.2f}€\n"
    text += f"   💰 Активных бонусов: {total_bonuses_active:.2f}€\n"
    text += f"   🔥 Долг (к выплате): {total_bonuses_active:.2f}€\n\n"
    
    text += "📈 По уровням:\n"
    text += f"   1 уровень (2€): {level1_bonuses:.2f}€\n"
    text += f"   2 уровень (0.5€): {level2_bonuses:.2f}€\n\n"
    
    if top_referrers:
        text += "🏆 Топ рефереров:\n"
        for i, ref in enumerate(top_referrers[:10], 1):
            username = ref['username'] or f"ID{ref['telegram_id']}"
            text += f"   {i}. @{username}\n"
            text += f"      👥 Рефералов: {ref['referrals_count']}\n"
            text += f"      💰 Заработано: {ref['total_earned']:.2f}€\n"
    
    text += "\n━━━━━━━━━━━━━━━━━━━━\n"
    text += "ℹ️ Используйте /stats для общей статистики"
    
    await message.answer(text)