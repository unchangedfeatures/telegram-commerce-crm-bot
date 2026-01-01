from aiogram.types import ReplyKeyboardRemove, \
    ReplyKeyboardMarkup, KeyboardButton, \
    InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import  InlineKeyboardBuilder
from aiogram import types

#Кнопка назад
back_button = InlineKeyboardButton(text="НАЗАД 🔙", callback_data="back")

#Кнопки меню
catalogue_button = InlineKeyboardButton(text="ЗАКАЗАТЬ ✨", callback_data="catalogue")
promo_button = InlineKeyboardButton(text="АКЦИИ 🔥", callback_data="promo")
cart_button = InlineKeyboardButton(text="КОРЗИНА 🛒", callback_data="cart")
help_button = InlineKeyboardButton(text="ИНФО ℹ️", callback_data="help")
profile_button = InlineKeyboardButton(text="ПРОФИЛЬ 👤", callback_data="profile")
invite_button = InlineKeyboardButton(text="ПРИГЛАСИТЬ ДРУЗЕЙ 🤝", callback_data="invite")

#Основное меню
def main_menu_keyboard():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [catalogue_button],
            [promo_button, cart_button],
            [help_button, profile_button],
            [invite_button],
        ]
    )
    return keyboard

#Кнопки помощи
pay_questions_button = InlineKeyboardButton(text="ОПЛАТА 💳", callback_data="pay_questions")
delivery_questions_button = InlineKeyboardButton(text="ДОСТАВКА 🚚", callback_data="delivery")
contact_support_button = InlineKeyboardButton(text="Связь 📞", callback_data="contact_support")


#Меню помощи
def help_menu_keyboard():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [pay_questions_button, delivery_questions_button],
            [contact_support_button, back_button],
        ]
    )
    return keyboard

# Кнопки каталога

brands_button = InlineKeyboardButton(text="HQD !", callback_data="hqd")
promo_choice_button = InlineKeyboardButton(text="ПО СКИДКЕ 🔥", callback_data="promo_choice")
promo_brand_items = InlineKeyboardButton(text="НАШ КАНАЛ С ВЕЩАМИ 🏷️", callback_data="vinted")

# Меню каталога
def catalogue_menu_keyboard():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [brands_button],
            [promo_brand_items],
            [back_button],
        ]
    )
    return keyboard

# Кнопки профиля
active_orders_button = InlineKeyboardButton(text="АКТУАЛЬНЫЕ ЗАКАЗЫ 📦", callback_data="active_orders")
referalls_button = InlineKeyboardButton(text="РЕФЕРАЛЬНАЯ СИСТЕМА 🤝", callback_data="invite")

# Меню профиля
def profile_menu_keyboard():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [active_orders_button, referalls_button],
            [back_button],
        ]
    )
    return keyboard

# Кнопки корзины
confirm_order_button = InlineKeyboardButton(text="ПОДТВЕРДИТЬ ЗАКАЗ ✅", callback_data="confirm_order")
promo_order_button = InlineKeyboardButton(text="ПРОМОКОД 🎟️", callback_data="promo_code")
clear_cart_button = InlineKeyboardButton(text="ОЧИСТИТЬ КОРЗИНУ 🗑️", callback_data="clear_cart")

# Меню корзины
def cart_menu_keyboard():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [confirm_order_button],
            [ clear_cart_button, promo_order_button],
            [back_button],
        ]
    )
    return keyboard

# ТУТ короче дописать текстом всё
# Меню приглашения
def invite_menu_keyboard():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [back_button],
        ]
    )
    return keyboard


# Кнопки акций
promo_item_1_button = InlineKeyboardButton(text="ПЕРЕЙТИ К ЗАКАЗУ ✨", callback_data="promo_choice")
# Меню акций
def promo_menu_keyboard():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [promo_item_1_button],
            [back_button],
        ]
    )
    return keyboard



# Кнопки вкусов

