# states.py
from aiogram.fsm.state import State, StatesGroup

class OrderStates(StatesGroup):
    """Состояния для оформления заказа"""
    select_promo = State()        # Выбор промокода
    enter_phone = State()         # Ввод телефона
    enter_address = State()       # Ввод адреса
    confirm_order = State()       # Подтверждение заказа
    add_for_delivery = State()    # Добавление товара для бесплатной доставки