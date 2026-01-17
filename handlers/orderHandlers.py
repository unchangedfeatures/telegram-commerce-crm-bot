# orderHandlers.py
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from states import OrderStates
from helpers import format_price
import json
from datetime import datetime
import database.database as db
from bot import bot_instance
import config
import aiohttp
import asyncio
from typing import Optional
from decimal import Decimal

router = Router()

async def reverse_geocode(latitude: float, longitude: float) -> Optional[str]:
    """
    Преобразует координаты в адрес через Nominatim (OpenStreetMap)
    Бесплатный сервис, но требует User-Agent
    """
    try:
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            "lat": latitude,
            "lon": longitude,
            "format": "json",
            "addressdetails": 1,
            "accept-language": "ru"  # Получаем адрес на русском
        }
        headers = {
            "User-Agent": "PewPuffBot/1.0 (Telegram Bot)"  # ОБЯЗАТЕЛЬНО для Nominatim
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers, timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Формируем читаемый адрес
                    address_parts = []
                    addr = data.get('address', {})
                    
                    # Улица и дом
                    if addr.get('road'):
                        road = addr['road']
                        house = addr.get('house_number', '')
                        address_parts.append(f"{road} {house}".strip())
                    
                    # Город/населенный пункт
                    city = (addr.get('city') or 
                           addr.get('town') or 
                           addr.get('village') or 
                           addr.get('suburb'))
                    if city:
                        address_parts.append(city)
                    
                    # Страна (опционально)
                    if addr.get('country'):
                        address_parts.append(addr['country'])
                    
                    if address_parts:
                        return ", ".join(address_parts)
                    
                    # Если не удалось распарсить - возвращаем display_name
                    return data.get('display_name', None)
                else:
                    print(f"⚠️ Nominatim API error: {response.status}")
                    return None
                    
    except asyncio.TimeoutError:
        print("⚠️ Nominatim API timeout")
        return None
    except Exception as e:
        print(f"⚠️ Reverse geocoding error: {e}")
        return None

# Вспомогательные функции
async def format_order_text(items: dict, discount_amount: float = 0, 
                          final_amount: float = 0, promo_code: str = None, 
                          delivery_cost: float = 0) -> str:
    """Форматирует текст заказа"""
    text = "🛒 *Ваш заказ:*\n\n"
    total_amount = 0
    
    for product_id, item in items.items():
        item_total = item['price'] * item['quantity']
        total_amount += item_total
        text += f"• {item['name']}: {item['quantity']} × {item['price']}€ = {item_total:.2f}€\n"
    
    text += f"\n💰 *Сумма товаров: {total_amount:.2f}€*\n"
    
    # Добавляем доставку, если она не нулевая
    if delivery_cost > 0:
        text += f"🚚 *Доставка: {delivery_cost:.2f}€*\n"
    else:
        text += f"🚚 *Доставка: БЕСПЛАТНО* (от 4 товаров)\n"
    
    # Показываем промокод и скидку только если они действительно есть
    if promo_code and promo_code not in ["none", None] and discount_amount > 0:
        # Определяем тип промокода
        if promo_code == "referral":
            text += f"🎁 *Реферальный бонус*\n"
        else:
            text += f"🎁 *Промокод: {promo_code}*\n"
        
        text += f"💸 *Скидка: -{discount_amount:.2f}€*\n"
    
    # Итого к оплате (финальная сумма уже включает доставку и скидку)
    text += f"💵 *Итого к оплате: {final_amount:.2f}€*\n"
    
    return text

async def calculate_discount(promo_code: str, total_amount: float, user_id: int = None):
    """Рассчитывает скидку по промокоду или реферальному бонусу"""
    if not promo_code or promo_code == "none":
        return 0, total_amount, None
    
    if promo_code == "referral":
        # ✅ ИСПРАВЛЕНО: Получаем бонусы где пользователь - referrer (свои бонусы)
        referral_bonus = await db.fetchval("""
            SELECT COALESCE(SUM(discount_amount), 0)
            FROM referral_discounts
            WHERE referrer_telegram_id = $1 AND discount_amount > 0
        """, user_id)
        referral_bonus = float(referral_bonus) if referral_bonus else 0.0
        discount_amount = min(referral_bonus, total_amount)
        final_amount = total_amount - discount_amount
        return discount_amount, final_amount, {"type": "referral", "amount": referral_bonus}
    
    promo = await db.fetchrow("""
        SELECT * FROM promo_codes 
        WHERE code = $1 AND is_active = TRUE
    """, promo_code)
    
    if not promo:
        return 0, total_amount, None
    
    # Проверяем минимальную сумму
    min_order = promo.get('min_order_amount', 0)
    if total_amount < min_order:
        return 0, total_amount, None
    
    discount_amount = 0
    if promo.get('discount_percent'):
        discount_amount = total_amount * (promo['discount_percent'] / 100)
    elif promo.get('discount_amount'):
        discount_amount = promo['discount_amount']
    
    # Ограничиваем скидку суммой заказа
    discount_amount = min(discount_amount, total_amount)
    final_amount = total_amount - discount_amount
    
    return discount_amount, final_amount, promo
# Начало оформления заказа
# В начале функции start_checkout добавим проверки

@router.callback_query(F.data == "checkout")
async def start_checkout(callback: types.CallbackQuery, state: FSMContext):
    """Начало оформления заказа"""
    user_id = callback.from_user.id
    
    # Проверяем корзину
    cart = await db.fetchrow(
        "SELECT items_json FROM cart WHERE telegram_id = $1",
        user_id
    )
    
    if not cart or not cart['items_json']:
        await callback.answer("❌ Корзина пуста", show_alert=True)
        return
    
    # Парсим товары
    items = json.loads(cart['items_json'])
    
    # НОВАЯ ПРОВЕРКА #1: Количество единиц товара в заказе
    total_items = sum(item['quantity'] for item in items.values())
    if total_items > 10:
        await callback.answer(
            f"❌ Максимум 10 единиц товара в одном заказе.\n"
            f"У вас в корзине: {total_items} шт.\n"
            f"Для оптового заказа обратитесь к @{config.SUPPORT}",
            show_alert=True
        )
        return
    
    # НОВАЯ ПРОВЕРКА #2: Количество активных заказов пользователя
    rows = await db.fetch("""
        SELECT order_id
        FROM orders
        WHERE telegram_id = $1
            AND status IN ('pending', 'accepted', 'delivery')
            FOR UPDATE
        """, user_id)
    active_orders_count = len(rows)
    
    if active_orders_count >= 2:
        await callback.answer(
            f"❌ У вас уже есть {active_orders_count} активных заказа.\n"
            f"Дождитесь завершения текущих заказов или обратитесь к @{config.SUPPORT}",
            show_alert=True
        )
        return
    
    # Проверяем количество позиций для новых пользователей (старая проверка)
    user = await db.fetchrow(
        "SELECT total_orders FROM users WHERE telegram_id = $1",
        user_id
    )
    
    if user and user['total_orders'] == 0 and len(items) > 6:
        await callback.answer(
            "❌ Для новых пользователей ограничение: не более 6 позиций.\n"
            f"Для оптового заказа обратитесь к @{config.SUPPORT}",
            show_alert=True
        )
        return
    
    # Сохраняем данные в FSM
    await state.update_data(
        user_id=user_id,
        items=items,
        total_amount=sum(item['price'] * item['quantity'] for item in items.values())
    )
    
    # Переходим к выбору промокода
    await show_promo_selection(callback, state)

async def show_promo_selection(callback: types.CallbackQuery, state: FSMContext):
    """Показывает доступные промокоды"""
    data = await state.get_data()
    user_id = data['user_id']
    total_amount = data['total_amount']
    
    # Получаем доступные промокоды пользователя
    promocodes = await db.fetch("""
        SELECT pc.*, up.is_used
        FROM user_promocodes up
        JOIN promo_codes pc ON up.promo_id = pc.promo_id
        WHERE up.telegram_id = $1 
          AND up.is_used = FALSE
          AND pc.is_active = TRUE
          AND (pc.expires_at IS NULL OR pc.expires_at > NOW())
          AND (pc.max_uses = 0 OR pc.current_uses < pc.max_uses)
    """, user_id)
    
    # Получаем сумму реферальных бонусов
    referral_bonus = await db.fetchval("""
        SELECT COALESCE(SUM(discount_amount), 0)
        FROM referral_discounts
        WHERE referrer_telegram_id = $1
    """, user_id)
    referral_bonus = float(referral_bonus) if referral_bonus else 0.0
    
    # Создаем кнопки с промокодами
    buttons = []
    
    for promo in promocodes:
        # Проверяем минимальную сумму
        min_order = promo.get('min_order_amount', 0)
        if total_amount >= min_order:
            discount_text = ""
            if promo.get('discount_percent'):
                discount_text = f"{promo['discount_percent']}%"
            elif promo.get('discount_amount'):
                discount_text = f"{promo['discount_amount']}€"
            
            buttons.append([InlineKeyboardButton(
                text=f"🎁 {promo['code']} ({discount_text})",
                callback_data=f"select_promo:{promo['code']}"
            )])
    
    # Добавляем кнопку реферальных бонусов, если есть
    if referral_bonus > 0:
        buttons.append([InlineKeyboardButton(
            text=f"🤝 Реферальный бонус ({referral_bonus:.2f}€)",
            callback_data="select_promo:referral"
        )])
    
    # Добавляем кнопку "Без промокода"
    buttons.append([InlineKeyboardButton(
        text="🚫 Без скидки",
        callback_data="select_promo:none"
    )])
    
    # Добавляем кнопку "Назад"
    buttons.append([InlineKeyboardButton(
        text="🔙 Назад в корзину",
        callback_data="cart"
    )])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    # Рассчитываем стоимость доставки
    total_items = sum(item['quantity'] for item in data['items'].values())
    delivery_cost = 0 if total_items >= 4 else 1.0
    
    # ИСПРАВЛЕНИЕ: Правильный вызов format_order_text
    order_text = await format_order_text(
        items=data['items'], 
        discount_amount=0,  # Пока нет скидки
        final_amount=total_amount + delivery_cost,  # Сумма + доставка
        promo_code=None,  # Промокод еще не выбран
        delivery_cost=delivery_cost
    )
    order_text += "\n\n*Выберите промокод для применения:*"
    
    await callback.message.edit_text(
        order_text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    
    # Устанавливаем состояние
    await state.set_state(OrderStates.select_promo)
    await callback.answer()

@router.callback_query(F.data.startswith("select_promo:"), OrderStates.select_promo)
async def process_promo_selection(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора промокода"""
    promo_code = callback.data.split(":")[1]
    data = await state.get_data()
    
    # Рассчитываем скидку
    discount_amount, final_amount, promo = await calculate_discount(
        promo_code, data['total_amount'], data['user_id']
    )
    
    # Сохраняем данные промокода
    await state.update_data(
        promo_code=promo_code,
        discount_amount=discount_amount,
        final_amount=final_amount,
        promo_data=promo
    )
    
    await callback.answer()
    
    # Переходим к запросу телефона
    await request_phone(callback, state)

async def request_phone(callback: types.CallbackQuery, state: FSMContext):
    """Запрашивает номер телефона"""
    data = await state.get_data()
    user_id = data['user_id']
    
    # Получаем информацию о пользователе
    user = await db.fetchrow(
        "SELECT username, phone FROM users WHERE telegram_id = $1",
        user_id
    )
    
    # Рассчитываем стоимость доставки
    total_items = sum(item['quantity'] for item in data['items'].values())
    delivery_cost = 0 if total_items >= 4 else 1.0
    
    # ИСПРАВЛЕНИЕ: Правильный вызов format_order_text
    order_text = await format_order_text(
        items=data['items'], 
        discount_amount=data.get('discount_amount', 0), 
        final_amount=data.get('final_amount', data['total_amount']) + delivery_cost,
        promo_code=data.get('promo_code'),
        delivery_cost=delivery_cost
    )
    
    buttons = []
    
    if user and user.get('phone'):
        # У пользователя уже есть номер
        phone = user['phone']
        
        buttons.append([InlineKeyboardButton(
            text=f"✅ Использовать сохраненный: {phone}",
            callback_data="use_existing_phone"
        )])
    
    # Кнопка для ввода нового номера
    buttons.append([InlineKeyboardButton(
        text="📱 Ввести новый номер",
        callback_data="enter_new_phone"
    )])
    
    # Кнопка для отмены
    buttons.append([InlineKeyboardButton(
        text="🔙 Назад к промокодам",
        callback_data="back_to_promos"
    )])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    order_text += "\n\n*Выберите вариант для связи:*"
    
    await callback.message.edit_text(
        order_text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    
    await state.set_state(OrderStates.enter_phone)
@router.callback_query(F.data == "use_existing_phone", OrderStates.enter_phone)
async def use_existing_phone(callback: types.CallbackQuery, state: FSMContext):
    """Использование сохраненного номера телефона"""
    user_id = callback.from_user.id
    
    # Получаем номер из базы
    user = await db.fetchrow(
        "SELECT phone, username FROM users WHERE telegram_id = $1",
        user_id
    )
    
    phone = user.get('phone', '')
    username = user.get('username', '')
    
    # Сохраняем контактные данные
    await state.update_data(
        phone=phone,
        username=username
    )
    
    # Переходим к запросу адреса
    await process_request_address(callback, state)

@router.callback_query(F.data == "enter_new_phone", OrderStates.enter_phone)
async def enter_new_phone(callback: types.CallbackQuery, state: FSMContext):
    """Запрос на ввод нового номера телефона"""
    data = await state.get_data()
    
    # Рассчитываем стоимость доставки
    total_items = sum(item['quantity'] for item in data['items'].values())
    delivery_cost = 0 if total_items >= 4 else 1.0
    
    # Формируем текст заказа
    order_text = await format_order_text(
        data['items'], 
        data.get('discount_amount', 0), 
        data.get('final_amount', data['total_amount']), 
        data.get('promo_code'),
        delivery_cost
    )
    
    order_text += "\n\n📱 *Пожалуйста, отправьте ваш номер телефона:*\n"
    order_text += "Используйте кнопку ниже или напишите в формате +370XXXXXXXX"
    
    # Создаем клавиатуру для отправки контакта
    contact_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Поделиться номером", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    
    await callback.message.answer(
        order_text,
        reply_markup=contact_keyboard,
        parse_mode="Markdown"
    )
    
    # Ждем ввода номера
    await state.set_state(OrderStates.enter_phone)

@router.message(F.contact, OrderStates.enter_phone)
async def handle_contact_input(message: types.Message, state: FSMContext):
    """Обработка полученного контакта"""
    phone = message.contact.phone_number
    
    # Сохраняем номер в базе
    await db.execute(
        "UPDATE users SET phone = $1, updated_at = NOW() WHERE telegram_id = $2",
        phone, message.from_user.id
    )
    
    # Сохраняем в состоянии
    await state.update_data(
        phone=phone,
        username=message.from_user.username
    )
    
    # Убираем клавиатуру
    await message.answer(
        "✅ Номер телефона сохранен!",
        reply_markup=types.ReplyKeyboardRemove()
    )
    
    # Переходим к запросу адреса
    data = await state.get_data()
    
    # Создаем сообщение для продолжения
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📍 Указать адрес", callback_data="request_address")]
    ])
    
    await message.answer(
        "Отлично! Теперь укажите адрес доставки:",
        reply_markup=keyboard
    )
    
    await state.set_state(OrderStates.enter_address)

@router.message(F.text, OrderStates.enter_phone)
async def handle_text_phone_input(message: types.Message, state: FSMContext):
    """Обработка номера телефона в текстовом формате"""
    phone = message.text.strip()
    
    # Игнорируем команды
    if phone.startswith('/'):
        return
    
    # Проверяем формат номера
    if not (phone.startswith('+') or phone.replace('+', '').isdigit()):
        await message.answer(
            "❌ Пожалуйста, введите номер в формате +370XXXXXXXX "
            "или используйте кнопку 'Поделиться номером'"
        )
        return
    
    # Сохраняем номер в базе
    await db.execute(
        "UPDATE users SET phone = $1, updated_at = NOW() WHERE telegram_id = $2",
        phone, message.from_user.id
    )
    
    # Сохраняем в состоянии
    await state.update_data(
        phone=phone,
        username=message.from_user.username
    )
    
    # Переходим к запросу адреса
    data = await state.get_data()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📍 Указать адрес", callback_data="request_address")]
    ])
    
    await message.answer(
        "✅ Номер телефона сохранен! Теперь укажите адрес доставки:",
        reply_markup=keyboard
    )
    
    await state.set_state(OrderStates.enter_address)

@router.callback_query(F.data == "request_address", OrderStates.enter_phone)
@router.callback_query(F.data == "back_to_promos", OrderStates.select_promo)
@router.callback_query(F.data == "back_to_promos", OrderStates.enter_phone)
async def back_to_promos(callback: types.CallbackQuery, state: FSMContext):
    """Возврат к выбору промокодов"""
    await show_promo_selection(callback, state)

@router.callback_query(F.data == "request_address")
async def process_request_address(callback: types.CallbackQuery, state: FSMContext):
    """Запрос адреса доставки"""
    data = await state.get_data()

    # Рассчитываем стоимость доставки
    total_items = sum(item['quantity'] for item in data['items'].values())
    delivery_cost = 0 if total_items >= 4 else 1.0

    # Формируем текст заказа
    order_text = await format_order_text(
        data['items'],
        discount_amount=data.get('discount_amount', 0),
        promo_code=data.get('promo_code'),
        delivery_cost=delivery_cost
    )
    
    # Контактная информация (ИСПРАВЛЕНИЕ: экранируем специальные символы)
    contact_text = "\n📞 *Контактная информация:*\n"
    if data.get('username'):
        # Экранируем @ для Markdown
        username = data['username'].replace('_', '\\_')
        contact_text += f"Telegram: @{username}\n"
    if data.get('phone'):
        phone = data['phone'].replace('_', '\\_').replace('*', '\\*')
        contact_text += f"Телефон: {phone}\n"
    
    order_text += contact_text
    order_text += "\n📍 *Пожалуйста, укажите адрес доставки:*\n"
    order_text += "Отправьте геолокацию или напишите адрес текстом"
    
    buttons = []
    
    # Проверяем сохраненный адрес
    user = await db.fetchrow("SELECT address FROM users WHERE telegram_id = $1", data['user_id'])
    if user and user.get('address'):
        address_preview = user['address'][:30]
        if len(user['address']) > 30:
            address_preview += "..."
        buttons.append([InlineKeyboardButton(
            text=f"✅ Использовать сохраненный: {address_preview}",
            callback_data="use_saved_address"
        )])
    
    # Кнопка для отправки геолокации
    buttons.append([InlineKeyboardButton(
        text="📍 Отправить геолокацию",
        callback_data="send_location"
    )])
    
    # Кнопка для ввода адреса текстом
    buttons.append([InlineKeyboardButton(
        text="🏠 Ввести адрес текстом",
        callback_data="enter_address_text"
    )])
    
    # Проверяем возможность бесплатной доставки
    total_items = sum(item['quantity'] for item in data['items'].values())
    if total_items < 4:
        needed = 4 - total_items
        buttons.append([InlineKeyboardButton(
            text=f"🚚 Бесплатная доставка от 4 товаров (добавить {needed})",
            callback_data="add_for_free_delivery"
        )])
    
    buttons.append([InlineKeyboardButton(
        text="🔙 Назад к телефону",
        callback_data="back_to_phone"
    )])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    # ИСПРАВЛЕНИЕ: Безопасная отправка сообщения
    try:
        await callback.message.edit_text(
            order_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    except Exception as e:
        # Если редактирование не удалось, удаляем и отправляем новое
        try:
            await callback.message.delete()
        except:
            pass
        
        await callback.message.answer(
            order_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    await state.set_state(OrderStates.enter_address)

@router.callback_query(F.data == "back_to_phone", OrderStates.enter_address)
async def back_to_phone(callback: types.CallbackQuery, state: FSMContext):
    """Возврат к вводу телефона"""
    data = await state.get_data()
    
    # Формируем текст заказа
    order_text = await format_order_text(
        data['items'], 
        data.get('discount_amount', 0), 
        data.get('final_amount', data['total_amount']), 
        data.get('promo_code')
    )
    
    buttons = []
    
    # Проверяем есть ли сохраненный номер
    user = await db.fetchrow(
        "SELECT phone FROM users WHERE telegram_id = $1",
        data['user_id']
    )
    
    if user and user.get('phone'):
        buttons.append([InlineKeyboardButton(
            text=f"✅ Использовать сохраненный: {data['phone']}",
            callback_data="use_existing_phone"
        )])
    
    buttons.append([InlineKeyboardButton(
        text="📱 Ввести новый номер",
        callback_data="enter_new_phone"
    )])
    
    buttons.append([InlineKeyboardButton(
        text="🔙 Назад к промокодам",
        callback_data="back_to_promos"
    )])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    order_text += "\n\n*Выберите вариант для связи:*"
    
    await callback.message.edit_text(
        order_text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    
    await state.set_state(OrderStates.enter_phone)

@router.callback_query(F.data == "send_location", OrderStates.enter_address)
async def send_location_handler(callback: types.CallbackQuery, state: FSMContext):
    """Запрос геолокации"""
    location_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Поделиться геолокацией", request_location=True)],
            [KeyboardButton(text="❌ Отмена")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    
    await callback.message.answer(
        "Пожалуйста, поделитесь вашей геолокацией для доставки:",
        reply_markup=location_keyboard
    )
    
    await state.set_state(OrderStates.enter_address)

@router.message(F.location, OrderStates.enter_address)
async def handle_location_input(message: types.Message, state: FSMContext):
    """Обработка полученной геолокации с преобразованием в адрес"""
    latitude = message.location.latitude
    longitude = message.location.longitude
    
    # Показываем индикатор загрузки
    processing_msg = await message.answer("📍 Определяю адрес по координатам...")
    
    # Преобразуем координаты в адрес
    address_text = await reverse_geocode(latitude, longitude)
    
    if not address_text:
        # Если не удалось получить адрес - используем координаты
        address_text = f"📍 Координаты: {latitude:.6f}, {longitude:.6f}"
        await processing_msg.edit_text(
            "⚠️ Не удалось определить адрес автоматически.\n"
            "Координаты сохранены, но рекомендуем указать адрес текстом."
        )
    else:
        await processing_msg.edit_text(f"✅ Адрес определен: {address_text}")
    
    # Сохраняем адрес
    await state.update_data(
        address_type="location",
        address_data=f"{latitude},{longitude}",  # Координаты для админа
        address_text=address_text,  # Читаемый адрес для пользователя
    )
    
    # Убираем клавиатуру
    await message.answer(
        "✅ Геолокация получена!",
        reply_markup=types.ReplyKeyboardRemove()
    )
    
    # ИСПРАВЛЕНИЕ: Переходим к подтверждению
    await confirm_order(message, state)

@router.message(F.text == "❌ Отмена", OrderStates.enter_address)
async def cancel_location_input(message: types.Message, state: FSMContext):
    """Отмена ввода геолокации"""
    await message.answer(
        "❌ Ввод геолокации отменен",
        reply_markup=types.ReplyKeyboardRemove()
    )
    
    # Возвращаемся к запросу адреса
    data = await state.get_data()
    
    # Формируем текст заказа
    order_text = await format_order_text(
        data['items'], 
        data.get('discount_amount', 0), 
        data.get('final_amount', data['total_amount']), 
        data.get('promo_code')
    )
    
    # Контактная информация
    contact_text = "\n📞 *Контактная информация:*\n"
    if data.get('username'):
        contact_text += f"Telegram: @{data['username']}\n"
    if data.get('phone'):
        contact_text += f"Телефон: {data['phone']}\n"
    
    order_text += contact_text
    order_text += "\n📍 *Пожалуйста, укажите адрес доставки:*\n"
    order_text += "Отправьте геолокацию или напишите адрес текстом"
    
    buttons = []
    
    # Кнопка для отправки геолокации
    buttons.append([InlineKeyboardButton(
        text="📍 Отправить геолокацию",
        callback_data="send_location"
    )])
    
    # Кнопка для ввода адреса текстом
    buttons.append([InlineKeyboardButton(
        text="🏠 Ввести адрес текстом",
        callback_data="enter_address_text"
    )])
    
    # Проверяем возможность бесплатной доставки
    total_items = sum(item['quantity'] for item in data['items'].values())
    if total_items < 4:
        needed = 4 - total_items
        buttons.append([InlineKeyboardButton(
            text=f"🚚 Бесплатная доставка от 4 товаров (добавить {needed})",
            callback_data="add_for_free_delivery"
        )])
    
    buttons.append([InlineKeyboardButton(
        text="🔙 Назад к телефону",
        callback_data="back_to_phone"
    )])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await message.answer(
        order_text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    
    await state.set_state(OrderStates.enter_address)

@router.callback_query(F.data == "enter_address_text", OrderStates.enter_address)
async def enter_address_text_handler(callback: types.CallbackQuery, state: FSMContext):
    """Запрос адреса в текстовом формате"""
    await callback.message.answer(
        "🏠 *Пожалуйста, напишите адрес доставки:*\n"
        "Укажите улицу, дом, квартиру и другие детали",
        parse_mode="Markdown"
    )
    
    await state.set_state(OrderStates.enter_address)

@router.callback_query(F.data == "use_saved_address", OrderStates.enter_address)
async def use_saved_address_handler(callback: types.CallbackQuery, state: FSMContext):
    """Использование сохраненного адреса"""
    data = await state.get_data()
    
    # Получаем сохраненный адрес
    user = await db.fetchrow("SELECT address FROM users WHERE telegram_id = $1", data['user_id'])
    if not user or not user.get('address'):
        await callback.answer("❌ Сохраненный адрес не найден", show_alert=True)
        return
    
    address_text = user['address']
    
    # Сохраняем адрес
    await state.update_data(
        address_type="text",
        address_data=address_text,
        address_text=address_text
    )
    
    # ИСПРАВЛЕНИЕ: Переходим к подтверждению
    await confirm_order(callback, state)

@router.message(F.text, OrderStates.enter_address)
async def handle_text_address_input(message: types.Message, state: FSMContext):
    """Обработка адреса в текстовом формате"""
    address_text = message.text.strip()
    
    # Игнорируем команды
    if address_text.startswith('/'):
        return
    
    if len(address_text) < 10:
        await message.answer("❌ Адрес слишком короткий. Пожалуйста, укажите подробный адрес.")
        return
    
    # Сохраняем адрес в базу
    await db.execute(
        "UPDATE users SET address = $1, updated_at = NOW() WHERE telegram_id = $2",
        address_text, message.from_user.id
    )
    
    # Сохраняем адрес
    await state.update_data(
        address_type="text",
        address_data=address_text,
        address_text=address_text
    )
    
    # ИСПРАВЛЕНИЕ: передаем message напрямую
    await confirm_order(message, state)

@router.callback_query(F.data == "add_for_free_delivery", OrderStates.enter_address)
async def add_for_free_delivery_handler(callback: types.CallbackQuery, state: FSMContext):
    """Предложение добавить товар для бесплатной доставки"""
    # Получаем популярные товары для предложения
    popular_products = await db.fetch("""
        SELECT product_id, product_name, price 
        FROM products 
        WHERE stock_quantity > 0 AND is_active = TRUE
        ORDER BY times_chosen DESC 
        LIMIT 5
    """)
    
    buttons = []
    for product in popular_products:
        buttons.append([InlineKeyboardButton(
            text=f"➕ {product['product_name']} ({product['price']}€)",
            callback_data=f"add_free_delivery:{product['product_id']}"
        )])
    
    buttons.append([InlineKeyboardButton(
        text="🔙 Назад к адресу",
        callback_data="request_address"
    )])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(
        "🎁 *Добавьте товар для бесплатной доставки!*\n\n"
        "При заказе от 4 товаров доставка бесплатная!\n"
        "Выберите товар для добавления:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    
    await state.set_state(OrderStates.add_for_delivery)

@router.callback_query(F.data.startswith("add_free_delivery:"), OrderStates.add_for_delivery)
async def handle_add_free_delivery(callback: types.CallbackQuery, state: FSMContext):
    """Добавляет товар для бесплатной доставки"""
    product_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    user_id = data['user_id']
    
    # Получаем информацию о товаре
    product = await db.fetchrow(
        "SELECT product_name, price FROM products WHERE product_id = $1",
        product_id
    )
    
    if not product:
        await callback.answer("❌ Товар не найден", show_alert=True)
        return
    
    # Добавляем товар в корзину и обновляем состояние
    items = data['items']
    
    if str(product_id) in items:
        items[str(product_id)]['quantity'] += 1
    else:
        items[str(product_id)] = {
            'name': product['product_name'],
            'price': float(product['price'] or 0),
            'quantity': 1
        }
    
    # Обновляем корзину в базе
    await db.execute(
        "UPDATE cart SET items_json = $1, last_updated = NOW() WHERE telegram_id = $2",
        json.dumps(items), user_id
    )
    
    # Пересчитываем суммы
    total_amount = sum(item['price'] * item['quantity'] for item in items.values())
    discount_amount, final_amount, promo = await calculate_discount(
        data.get('promo_code', 'none'), total_amount
    )
    
    # Обновляем состояние
    await state.update_data(
        items=items,
        total_amount=total_amount,
        discount_amount=discount_amount,
        final_amount=final_amount
    )
    
    await callback.answer(f"✅ {product['product_name']} добавлен!")
    
    # Возвращаемся к оформлению заказа
    await process_request_address(callback, state)

async def confirm_order(event, state: FSMContext):
    """Подтверждение заказа"""
    data = await state.get_data()
    
    # Рассчитываем стоимость доставки
    total_items = sum(item['quantity'] for item in data['items'].values())
    delivery_cost = 0 if total_items >= 4 else 1.0
    
    # ИСПРАВЛЕНИЕ: Сначала рассчитываем final_amount
    base_final_amount = data.get('final_amount', data['total_amount'])
    final_amount = base_final_amount + delivery_cost
    
    # Формируем текст заказа
    order_text = "✅ *Подтверждение заказа*\n\n"
    order_text += await format_order_text(
        items=data['items'], 
        discount_amount=data.get('discount_amount', 0), 
        final_amount=final_amount, 
        promo_code=data.get('promo_code'),
        delivery_cost=delivery_cost
    )
    
    # Информация о доставке
    order_text += f"\n📍 *Адрес доставки:*\n{data.get('address_text', 'Не указан')}\n"
    
    # Контактная информация (экранируем специальные символы для Markdown)
    order_text += "\n📞 *Контактная информация:*\n"
    if data.get('username'):
        # Экранируем _ для Markdown
        username = data['username'].replace('_', '\\_')
        order_text += f"Telegram: @{username}\n"
    if data.get('phone'):
        phone = data['phone'].replace('_', '\\_').replace('*', '\\*')
        order_text += f"Телефон: {phone}\n"
    
    order_text += "\n*Всё верно? Подтвердите заказ:*"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_order_final"),
            InlineKeyboardButton(text="✏️ Изменить", callback_data="edit_order")
        ],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_order")]
    ])
    
    # ИСПРАВЛЕНИЕ: правильная обработка типа события
    if isinstance(event, types.CallbackQuery):
        # Если это callback query, используем message из него
        try:
            await event.message.edit_text(
                order_text,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        except Exception:
            try:
                await event.message.delete()
            except:
                pass
            await event.message.answer(
                order_text,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
    else:
        # Если это обычное сообщение
        try:
            await event.edit_text(
                order_text,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        except Exception:
            try:
                await event.delete()
            except:
                pass
            await event.answer(
                order_text,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
    
    # Сохраняем delivery_cost и final_amount в состоянии
    await state.update_data(final_amount=final_amount, delivery_cost=delivery_cost)
    
    await state.set_state(OrderStates.confirm_order)

@router.callback_query(F.data == "edit_order", OrderStates.confirm_order)
async def edit_order_handler(callback: types.CallbackQuery, state: FSMContext):
    """Редактирование заказа"""
    buttons = [
        [InlineKeyboardButton(text="🎁 Изменить промокод", callback_data="back_to_promos")],
        [InlineKeyboardButton(text="📱 Изменить телефон", callback_data="back_to_phone")],
        [InlineKeyboardButton(text="📍 Изменить адрес", callback_data="request_address")],
        [InlineKeyboardButton(text="🛒 Вернуться в корзину", callback_data="cart")]
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(
        "✏️ *Что вы хотите изменить?*",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "cancel_order", OrderStates.confirm_order)
async def cancel_order_handler(callback: types.CallbackQuery, state: FSMContext):
    """Отмена заказа"""
    await state.clear()
    
    await callback.message.edit_text(
        "❌ *Оформление заказа отменено*\n\n"
        "Вы можете вернуться в корзину и начать заново.",
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "confirm_order_final", OrderStates.confirm_order)
async def finalize_order(callback: types.CallbackQuery, state: FSMContext):
    """Финальное подтверждение и создание заказа С ТРАНЗАКЦИЕЙ"""
    data = await state.get_data()
    user_id = data['user_id']
    
    try:
        # Начинаем транзакцию
        async with db.pool.acquire() as conn:
            async with conn.transaction():
                # ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА #1: Количество единиц товара
                total_items = sum(item['quantity'] for item in data['items'].values())
                if total_items > 10:
                    await callback.answer(
                        f"❌ Максимум 10 единиц товара в одном заказе.\n"
                        f"Для оптового заказа обратитесь к @{config.SUPPORT}",
                        show_alert=True
                    )
                    return
                
                # ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА #2: Количество активных заказов
                rows = await db.fetch("""
                    SELECT order_id
                    FROM orders
                    WHERE telegram_id = $1
                        AND status IN ('pending', 'accepted', 'delivery')
                    FOR UPDATE
                """, user_id)
                active_orders_count = len(rows)
                
                if active_orders_count >= 2:
                    await callback.answer(
                        f"❌ У вас уже есть {active_orders_count} активных заказа.\n"
                        f"Дождитесь завершения текущих заказов.",
                        show_alert=True
                    )
                    return
                
                # 1. Проверяем и блокируем товары (FOR UPDATE блокирует строки)
                for product_id_str, item in data['items'].items():
                    product_id = int(product_id_str)
                    
                    product = await conn.fetchrow("""
                        SELECT stock_quantity, product_name 
                        FROM products 
                        WHERE product_id = $1
                        FOR UPDATE
                    """, product_id)
                    
                    if not product or product['stock_quantity'] < item['quantity']:
                        await callback.answer(
                            f"❌ Товар '{product['product_name'] if product else 'Unknown'}' закончился или недостаточно на складе",
                            show_alert=True
                        )
                        return
                
                # 2. Создаем заказ
                total_items = sum(item['quantity'] for item in data['items'].values())
                delivery_cost = 0 if total_items >= 4 else 1.0
                final_amount = data.get('final_amount', data['total_amount']) + delivery_cost
                
                order_id = await conn.fetchval("""
                    INSERT INTO orders (
                        telegram_id, total_amount, discount_amount, final_amount,
                        status, payment_status, delivery_address, promo_code_used, created_at
                    ) VALUES ($1, $2, $3, $4, 'pending', 'pending', $5, $6, NOW())
                    RETURNING order_id
                """, 
                user_id, 
                data['total_amount'], 
                data.get('discount_amount', 0), 
                final_amount,
                data.get('address_text', 'Не указан'),
                data.get('promo_code'))
                
                # 3. Добавляем товары и списываем со склада
                for product_id_str, item in data['items'].items():
                    product_id = int(product_id_str)
                    item_total = item['price'] * item['quantity']
                    
                    # Добавляем в order_items
                    await conn.execute("""
                        INSERT INTO order_items (order_id, product_id, quantity, unit_price, total_price)
                        VALUES ($1, $2, $3, $4, $5)
                    """, order_id, product_id, item['quantity'], item['price'], item_total)
                    
                    # Списываем со склада и увеличиваем счетчик
                    await conn.execute("""
                        UPDATE products 
                        SET stock_quantity = stock_quantity - $1,
                            times_chosen = times_chosen + 1
                        WHERE product_id = $2
                    """, item['quantity'], product_id)
                
                # 4. Обрабатываем промокод
                if data.get('promo_code') and data['promo_code'] != 'none' and data['promo_code'] != 'referral':
                    promo = data.get('promo_data')
                    if promo and promo.get('promo_id'):
                        await conn.execute("""
                            UPDATE user_promocodes 
                            SET is_used = TRUE, used_at = NOW()
                            WHERE telegram_id = $1 AND promo_id = $2
                        """, user_id, promo['promo_id'])
                
                # 5. ИСПРАВЛЕНИЕ #2: Правильное списание реферальных бонусов
                if data.get('promo_code') == 'referral' and data.get('discount_amount', 0) > 0:
                    used_amount = data['discount_amount']
                    remaining = used_amount
                    
                    # Получаем бонусы с блокировкой FOR UPDATE
                    bonuses = await conn.fetch("""
                        SELECT referral_discount_id, discount_amount 
                        FROM referral_discounts 
                        WHERE referrer_telegram_id = $1 AND discount_amount > 0
                        ORDER BY created_at ASC
                        FOR UPDATE
                    """, user_id)
                    
                    # Списываем поэтапно
                    for bonus in bonuses:
                        if remaining <= 0:
                            break
                        
                        deduct = min(remaining, bonus['discount_amount'])
                        new_amount = bonus['discount_amount'] - Decimal(deduct)
                        
                        await conn.execute("""
                            UPDATE referral_discounts 
                            SET discount_amount = $1
                            WHERE referral_discount_id = $2
                        """, new_amount, bonus['referral_discount_id'])
                        
                        remaining -= deduct
                    
                    print(f"✅ Списано {used_amount - remaining}€ реферальных бонусов")
                
                # 6. Очищаем корзину
                await conn.execute("DELETE FROM cart WHERE telegram_id = $1", user_id)
                
                # 7. Обновляем статистику пользователя
                await conn.execute("""
                    UPDATE users 
                    SET total_orders = total_orders + 1,
                        total_spent = total_spent + $1,
                        updated_at = NOW()
                    WHERE telegram_id = $2
                """, final_amount, user_id)
                
                print(f"✅ Заказ #{order_id} успешно создан в транзакции")
        
        # Транзакция завершена успешно - отправляем уведомления
        
        # Очищаем состояние
        await state.clear()
        
        # Уведомляем пользователя
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")],
            [InlineKeyboardButton(text="📋 Мои заказы", callback_data="active_orders")]
        ])
        
        await callback.message.edit_text(
            f"🎉 Заказ #{order_id} оформлен!\n\n"
            f"💵 Сумма: {final_amount:.2f}€\n"
            f"📍 Адрес: {data.get('address_text', 'Не указан')}\n\n"
            "📞 С вами свяжется наш менеджер для подтверждения заказа.\n"
            "Ожидайте сообщения в Telegram.",
            reply_markup=keyboard
        )
        
        await callback.answer()
        await notify_admins_about_order(order_id, data)
        
    except Exception as e:
        print(f"🔥 Ошибка при создании заказа: {e}")
        import traceback
        traceback.print_exc()
        
        await callback.answer(
            "❌ Ошибка при оформлении заказа. Попробуйте позже или обратитесь в поддержку.",
            show_alert=True
        )

async def notify_admins_about_order(order_id: int, order_data: dict):
    """Отправка уведомлений админам через очередь (БЫСТРО)"""
    from bot_instance import notification_service
    
    try:
        # Получаем всех админов
        admins = await db.fetch("SELECT telegram_id FROM users WHERE role = 'admin'")
        
        if not admins:
            print("⚠️ Нет администраторов")
            return
        
        # Формируем текст ОДИН раз
        username = order_data.get('username', 'без username')
        phone = order_data.get('phone', 'не указан')
        address = order_data.get('address_text', 'не указан')
        
        notification_text = (
            f"🆕 НОВЫЙ ЗАКАЗ #{order_id}\n\n"
            f"👤 @{username}\n"
            f"📞 {phone}\n"
            f"📍 {address}\n\n"
            f"🛒 Состав:\n"
        )
        
        for item in order_data['items'].values():
            item_total = item['price'] * item['quantity']
            notification_text += f"• {item['name']}: {item['quantity']}шт × {item['price']:.2f}€ = {item_total:.2f}€\n"
        
        notification_text += (
            f"\n💰 Сумма: {order_data['total_amount']:.2f}€\n"
            f"🎁 Скидка: {order_data.get('discount_amount', 0):.2f}€\n"
            f"💳 Итого: {order_data.get('final_amount', order_data['total_amount']):.2f}€\n\n"
            f"Команды:\n"
            f"/accept {order_id}\n"
            f"/decline {order_id}\n"
            f"/deliver {order_id} <мин>\n"
            f"/confirm {order_id}"
        )
        
        # Добавляем ВСЕ уведомления в очередь СРАЗУ (не блокирует!)
        notifications = [
            (admin['telegram_id'], notification_text, {})
            for admin in admins
        ]
        await notification_service.add_bulk_to_queue(notifications)
        
        print(f"✅ {len(admins)} уведомлений добавлено в очередь")
        
    except Exception as e:
        print(f"🔥 Ошибка notify_admins_about_order: {e}")