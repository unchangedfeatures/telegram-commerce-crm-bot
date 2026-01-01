import json
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InputMediaPhoto, InlineKeyboardButton, InlineKeyboardMarkup
import keyboards.guest as guest
import database.database as db
from bot_instance import bot_instance, notification_service
from helpers import admin_required, format_order_status, format_price, format_date
from datetime import datetime, timedelta

_products_cache = {}
_cache_time = {}
router = Router()

async def get_products_cached(brand_id: int):
    """Получить товары с простым кэшем"""
    cache_key = f"products_{brand_id}"
    
    # Проверяем кэш (TTL 5 минут)
    if cache_key in _products_cache:
        if datetime.now() < _cache_time.get(cache_key, datetime.min):
            return _products_cache[cache_key]
    
    # Загружаем из БД
    products = await db.get_products_by_brand_cached(brand_id)
    
    # Сохраняем в кэш
    _products_cache[cache_key] = products
    _cache_time[cache_key] = datetime.now() + timedelta(minutes=5)
    
    return products


# Обработчик для отображения всех товаров HQD
@router.callback_query(F.data == "hqd")
async def hqd_flavors_v2(callback: types.CallbackQuery):
    """Показать товары HQD (С КЭШЕМ)"""
    
    # Используем кэш!
    products = await get_products_cached(brand_id=1)
    
    buttons = []
    
    for product in products:
        stock = product['stock_quantity'] or 0
        
        # Эмодзи наличия
        if stock > 15:
            emoji = "✅"
        elif stock > 0:
            emoji = "⏳"
        else:
            emoji = "❌"
        
        button_text = f"{emoji} {product['product_name']}"
        if product['price'] > 0:
            button_text += f" ({product['price']:.2f}€)"
        
        buttons.append([InlineKeyboardButton(
            text=button_text,
            callback_data=f"product_detail:{product['product_id']}"
        )])
    
    buttons.append([InlineKeyboardButton(text="🛒 Корзина", callback_data="cart")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    try:
        await callback.message.edit_text(
            "Выберите товар HQD:",
            reply_markup=keyboard
        )
        await callback.answer()
    except:
        try:
            await callback.message.delete()
        except:
            pass

        await callback.message.answer("Выберите товар HQD:",
            reply_markup=keyboard
        )
        await callback.answer()

# Обработчик для детальной информации о товаре
@router.callback_query(F.data.startswith("product_detail:"))
async def product_detail(callback: types.CallbackQuery):
    product_id = int(callback.data.split(":")[1])
    
    product = await db.fetchrow(
        """
        SELECT product_id, product_name, stock_quantity, price, 
               description, image_url, times_chosen
        FROM products 
        WHERE product_id = $1 AND is_active = TRUE
        """,
        product_id
    )
    
    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return
    
    stock = product['stock_quantity'] or 0
    price = product['price'] or 0
    description = product['description'] or "Описание отсутствует"
    
    # Определяем доступность
    if stock > 0:
        availability = f"✅ В наличии: {stock} шт."
        add_to_cart_button = InlineKeyboardButton(
            text="➕ Добавить в корзину",
            callback_data=f"add_to_cart:{product_id}"
        )
    else:
        availability = "❌ Нет в наличии"
        add_to_cart_button = InlineKeyboardButton(
            text="❌ Недоступно",
            callback_data="unavailable"
        )
    
    # Создаем клавиатуру
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [add_to_cart_button],
        [
            InlineKeyboardButton(text="🛒 Корзина", callback_data="cart"),
            InlineKeyboardButton(text="📋 Список товаров", callback_data="hqd")
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="hqd")]
    ])
    
    # Проверяем, пробовал ли пользователь этот вкус
    tried = await db.fetchval("""
        SELECT 1 FROM order_items oi
        JOIN orders o ON oi.order_id = o.order_id
        WHERE o.telegram_id = $1 AND oi.product_id = $2 AND o.status IN ('completed', 'delivery')
        LIMIT 1
    """, callback.from_user.id, product_id)
    
    tried_text = "🍓 Вы уже пробовали этот вкус!" if tried else ""
    
    # Формируем текст сообщения
    caption = f"🛍️ *{product['product_name']}*\n\n"
    caption += f"💰 Цена: {price}€\n"
    caption += f"📦 {availability}\n"
    if description:
        caption += f"📝 {description}\n"
    if tried_text:
        caption += f"\n{tried_text}\n"
    caption += f"\n📊 Выбрано раз: {product['times_chosen'] or 0}"
    
    # Отправляем фото с подписью и клавиатурой
    await callback.message.delete()
    if product['image_url']:
        await callback.message.answer_photo(
            photo=product['image_url'],
            caption=caption,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    else:
        await callback.message.answer(
            caption,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    await callback.answer()

# Обработчик для добавления товара в корзину
@router.callback_query(F.data.startswith("add_to_cart:"))
async def add_to_cart(callback: types.CallbackQuery):
    telegram_id = callback.from_user.id
    product_id = int(callback.data.split(":")[1])
    
    # Получаем информацию о товаре
    product = await db.fetchrow(
        """
        SELECT product_id, product_name, price, stock_quantity
        FROM products 
        WHERE product_id = $1 AND is_active = TRUE
        """,
        product_id
    )
    
    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return
    
    stock = product['stock_quantity'] or 0
    if stock <= 0:
        await callback.answer("Товар закончился", show_alert=True)
        return
    
    # Проверяем, есть ли уже корзина у пользователя
    cart = await db.fetchrow(
        "SELECT * FROM cart WHERE telegram_id = $1",
        telegram_id
    )
    
    if cart:
        # Обновляем существующую корзину
        items = json.loads(cart['items_json']) if cart['items_json'] else {}
        
        # Проверяем, есть ли уже этот товар в корзине
        current_quantity = items.get(str(product_id), {}).get('quantity', 0)
        new_quantity = current_quantity + 1
        
        if new_quantity > stock:
            # Предлагаем уменьшить количество до доступного
            if stock > 0:
                await callback.message.answer(
                    f"⚠️ На складе доступно только {stock} шт. {product['product_name']}.\n"
                    f"Уменьшить количество до {stock} шт.?",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(
                            text=f"✅ Да, добавить {stock} шт.",
                            callback_data=f"add_limited:{product_id}:{stock}"
                        )],
                        [InlineKeyboardButton(
                            text="❌ Отмена",
                            callback_data="cancel_add"
                        )]
                    ])
                )
                return
            else:
                await callback.answer("Товар закончился", show_alert=True)
                return
        
        if str(product_id) in items:
            items[str(product_id)]['quantity'] = new_quantity
        else:
            items[str(product_id)] = {
                'name': product['product_name'],
                'price': float(product['price'] or 0),
                'quantity': new_quantity
            }
        
        # Обновляем корзину в базе
        await db.execute(
            """
            UPDATE cart 
            SET items_json = $1, last_updated = NOW()
            WHERE telegram_id = $2
            """,
            json.dumps(items),
            telegram_id
        )
    else:
        # Создаем новую корзину
        items = {
            str(product_id): {
                'name': product['product_name'],
                'price': float(product['price'] or 0),
                'quantity': 1
            }
        }
        
        await db.execute(
            """
            INSERT INTO cart (telegram_id, items_json, applied_discounts, 
                            delivery_discount_applied, last_updated)
            VALUES ($1, $2, '[]', FALSE, NOW())
            """,
            telegram_id,
            json.dumps(items)
        )
    
    await callback.answer(f"✅ {product['product_name']} добавлен в корзину!")

@router.callback_query(F.data.startswith("add_limited:"))
async def add_limited_to_cart(callback: types.CallbackQuery):
    telegram_id = callback.from_user.id
    parts = callback.data.split(":")
    product_id = int(parts[1])
    quantity = int(parts[2])
    
    # Получаем информацию о товаре
    product = await db.fetchrow(
        """
        SELECT product_id, product_name, price, stock_quantity
        FROM products 
        WHERE product_id = $1 AND is_active = TRUE
        """,
        product_id
    )
    
    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return
    
    stock = product['stock_quantity'] or 0
    if quantity > stock:
        await callback.answer("Количество превышает доступное", show_alert=True)
        return
    
    # Проверяем, есть ли уже корзина у пользователя
    cart = await db.fetchrow(
        "SELECT * FROM cart WHERE telegram_id = $1",
        telegram_id
    )
    
    if cart:
        # Обновляем существующую корзину
        items = json.loads(cart['items_json']) if cart['items_json'] else {}
        
        items[str(product_id)] = {
            'name': product['product_name'],
            'price': float(product['price'] or 0),
            'quantity': quantity
        }
        
        # Обновляем корзину в базе
        await db.execute(
            """
            UPDATE cart 
            SET items_json = $1, last_updated = NOW()
            WHERE telegram_id = $2
            """,
            json.dumps(items),
            telegram_id
        )
    else:
        # Создаем новую корзину
        items = {
            str(product_id): {
                'name': product['product_name'],
                'price': float(product['price'] or 0),
                'quantity': quantity
            }
        }
        
        await db.execute(
            """
            INSERT INTO cart (telegram_id, items_json, applied_discounts, 
                            delivery_discount_applied, last_updated)
            VALUES ($1, $2, '[]', FALSE, NOW())
            """,
            telegram_id,
            json.dumps(items)
        )
    
    await callback.message.edit_text(
        f"✅ {product['product_name']} ({quantity} шт.) добавлен в корзину!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Перейти в корзину", callback_data="cart")],
            [InlineKeyboardButton(text="🔙 Продолжить покупки", callback_data="back")]
        ])
    )

@router.callback_query(F.data == "cancel_add")
async def cancel_add(callback: types.CallbackQuery):
    await callback.message.delete()

# Обработчик для просмотра корзины
@router.callback_query(F.data == "cart")
async def view_cart(callback: types.CallbackQuery):
    telegram_id = callback.from_user.id
    
    # Получаем корзину пользователя
    cart = await db.fetchrow(
        "SELECT * FROM cart WHERE telegram_id = $1",
        telegram_id
    )
    
    if not cart or not cart['items_json']:
        # Пустая корзина
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛍️ К товарам", callback_data="hqd")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="hqd")]
        ])
        
        # ИСПРАВЛЕНИЕ: Удаляем сообщение и отправляем новое текстовое
        try:
            await callback.message.delete()
        except:
            pass
        
        await callback.message.answer(
            "🛒 Ваша корзина пуста\n\n"
            "Добавьте товары, чтобы сделать заказ!",
            reply_markup=keyboard
        )
        await callback.answer()
        return
    
    # Парсим товары из JSON
    items = json.loads(cart['items_json'])
    
    # Рассчитываем количество товаров для определения доставки
    total_items = sum(item['quantity'] for item in items.values())
    delivery_cost = 0 if total_items >= 4 else 1.0
    
    # Формируем сообщение с содержимым корзины
    cart_text = "🛒 *Ваша корзина*\n\n"
    total_price = 0
    
    for product_id, item in items.items():
        item_total = item['price'] * item['quantity']
        total_price += item_total
        
        cart_text += (
            f"• {item['name']}\n"
            f"  Количество: {item['quantity']} × {item['price']}€ = {item_total:.2f}€\n"
        )
    
    cart_text += f"\n💰 *Сумма: {total_price:.2f}€*\n"
    cart_text += f"🚚 *Доставка: {delivery_cost:.2f}€*\n"
    cart_text += f"💵 *Итого к оплате: {(total_price + delivery_cost):.2f}€*"
    
    # Создаем кнопки управления корзиной
    keyboard_buttons = []
    
    # Кнопки для каждого товара в корзине
    for product_id in items.keys():
        product_name = items[product_id]['name']
        # Обрезаем длинное название
        if len(product_name) > 20:
            button_text = f"✏️ {product_name[:17]}..."
        else:
            button_text = f"✏️ {product_name}"
        
        keyboard_buttons.append([InlineKeyboardButton(
            text=button_text,
            callback_data=f"edit_cart_item:{product_id}"
        )])
    
    # Основные кнопки управления
    keyboard_buttons.extend([
        [
            InlineKeyboardButton(text="➕ Добавить товары", callback_data="hqd"),
            InlineKeyboardButton(text="🗑️ Очистить корзину", callback_data="clear_cart")
        ],
        [
            InlineKeyboardButton(text="✅ Оформить заказ", callback_data="checkout")
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="hqd")]
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    # ИСПРАВЛЕНИЕ: Проверяем тип последнего сообщения
    try:
        # Пытаемся отредактировать как текст
        await callback.message.edit_text(
            cart_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    except Exception as e:
        # Если не получилось (например, было фото), удаляем и отправляем новое
        try:
            await callback.message.delete()
        except:
            pass
        
        await callback.message.answer(
            cart_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    await callback.answer()

# Обработчик для редактирования товара в корзине
@router.callback_query(F.data.startswith("edit_cart_item:"))
async def edit_cart_item(callback: types.CallbackQuery):
    telegram_id = callback.from_user.id
    product_id = callback.data.split(":")[1]
    
    # Получаем корзину
    cart = await db.fetchrow(
        "SELECT items_json FROM cart WHERE telegram_id = $1",
        telegram_id
    )
    
    if not cart:
        await callback.answer("Корзина не найдена", show_alert=True)
        return
    
    items = json.loads(cart['items_json'])
    
    if product_id not in items:
        await callback.answer("Товар не найден в корзине", show_alert=True)
        return
    
    item = items[product_id]
    
    # Создаем клавиатуру для управления количеством
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➖ Уменьшить", callback_data=f"cart_decrease:{product_id}"),
            InlineKeyboardButton(text="➕ Увеличить", callback_data=f"cart_increase:{product_id}")
        ],
        [
            InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"cart_remove:{product_id}"),
            InlineKeyboardButton(text="🔙 Назад", callback_data="cart")
        ]
    ])
    
    item_total = item['price'] * item['quantity']
    
    text = (
        f"✏️ <b>Редактирование товара</b>\n\n"
        f"<b>{item['name']}</b>\n"
        f"💰 Цена за единицу: {item['price']}€\n"
        f"📦 Количество: <b>{item['quantity']}</b>\n"
        f"💰 Итого за товар: {item_total:.2f}€\n\n"
        f"Используйте кнопки для изменения количества:"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

# Обработчики для изменения количества
@router.callback_query(F.data.startswith("cart_increase:"))
async def increase_quantity(callback: types.CallbackQuery):
    await modify_cart_quantity(callback, increase=True)

@router.callback_query(F.data.startswith("cart_decrease:"))
async def decrease_quantity(callback: types.CallbackQuery):
    await modify_cart_quantity(callback, increase=False)

@router.callback_query(F.data.startswith("cart_remove:"))
async def remove_from_cart(callback: types.CallbackQuery):
    telegram_id = callback.from_user.id
    product_id = callback.data.split(":")[1]
    
    cart = await db.fetchrow(
        "SELECT items_json FROM cart WHERE telegram_id = $1",
        telegram_id
    )
    
    if not cart:
        await callback.answer("Корзина не найдена", show_alert=True)
        return
    
    items = json.loads(cart['items_json'])
    
    if product_id in items:
        removed_item = items.pop(product_id)
        
        # Обновляем или удаляем корзину
        if items:
            await db.execute(
                "UPDATE cart SET items_json = $1, last_updated = NOW() WHERE telegram_id = $2",
                json.dumps(items),
                telegram_id
            )
        else:
            await db.execute("DELETE FROM cart WHERE telegram_id = $1", telegram_id)
        
        await callback.answer(f"🗑️ {removed_item['name']} удален из корзины")
        await view_cart(callback)
    else:
        await callback.answer("Товар не найден в корзине", show_alert=True)

# Функция для изменения количества
async def modify_cart_quantity(callback: types.CallbackQuery, increase: bool):
    telegram_id = callback.from_user.id
    product_id = callback.data.split(":")[1]
    
    cart = await db.fetchrow(
        "SELECT items_json FROM cart WHERE telegram_id = $1",
        telegram_id
    )
    
    if not cart:
        await callback.answer("Корзина не найдена", show_alert=True)
        return
    
    items = json.loads(cart['items_json'])
    
    if product_id not in items:
        await callback.answer("Товар не найден в корзине", show_alert=True)
        return
    
    if increase:
        items[product_id]['quantity'] += 1
        await callback.answer("Количество увеличено")
    else:
        if items[product_id]['quantity'] > 1:
            items[product_id]['quantity'] -= 1
            await callback.answer("Количество уменьшено")
        else:
            await callback.answer("Минимальное количество - 1")
            return
    
    # Обновляем корзину
    await db.execute(
        "UPDATE cart SET items_json = $1, last_updated = NOW() WHERE telegram_id = $2",
        json.dumps(items),
        telegram_id
    )
    
    # Возвращаемся к редактированию товара
    await edit_cart_item(callback)

# Обработчик для очистки корзины
@router.callback_query(F.data == "clear_cart")
async def clear_cart(callback: types.CallbackQuery):
    telegram_id = callback.from_user.id
    
    # Создаем клавиатуру подтверждения
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, очистить", callback_data="confirm_clear_cart"),
            InlineKeyboardButton(text="❌ Нет, отмена", callback_data="cart")
        ]
    ])
    
    await callback.message.edit_text(
        "⚠️ <b>Вы уверены, что хотите очистить корзину?</b>\n\n"
        "Все добавленные товары будут удалены.",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "confirm_clear_cart")
async def confirm_clear_cart(callback: types.CallbackQuery):
    telegram_id = callback.from_user.id
    
    await db.execute("DELETE FROM cart WHERE telegram_id = $1", telegram_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛍️ К товарам", callback_data="hqd")]
    ])
    
    await callback.message.edit_text(
        "🗑️ Корзина успешно очищена!",
        reply_markup=keyboard
    )
    await callback.answer()

# Обработчик для недоступных товаров
@router.callback_query(F.data == "unavailable")
async def unavailable_product(callback: types.CallbackQuery):
    await callback.answer("❌ Этот товар временно недоступен", show_alert=True)


