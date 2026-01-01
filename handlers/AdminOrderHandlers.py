# adminOrderHandlers.py
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import database.database as db
from bot_instance import bot_instance
import os
import config
from helpers import admin_required, format_order_status, format_price, format_date, is_admin_cached
from cache_manager import cache

router = Router()

@router.message(Command("accept"))
async def accept_order(message: types.Message):
    """Администратор принимает заказ по команде /accept <order_id>"""
    user = await db.fetchrow("SELECT role FROM users WHERE telegram_id = $1", message.from_user.id)
    if not user or user['role'] != 'admin':
        await message.answer("❌ У вас нет прав для выполнения этой команды")
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("ℹ️ Использование: /accept <order_id>")
        return
    
    try:
        order_id = int(parts[1])
    except ValueError:
        await message.answer("❌ Неверный ID заказа")
        return
    
    # ИСПРАВЛЕНИЕ #8: Проверяем текущий статус
    order = await db.fetchrow("SELECT status, telegram_id FROM orders WHERE order_id = $1", order_id)
    if not order:
        await message.answer("❌ Заказ не найден")
        return
    
    # Защита от дублей
    if order['status'] == 'accepted':
        await message.answer(f"ℹ️ Заказ #{order_id} уже принят")
        return
    
    if order['status'] in ['completed', 'declined']:
        await message.answer(f"❌ Нельзя изменить статус заказа #{order_id}, он уже {order['status']}")
        return
    
    # Обновляем статус
    await db.execute("""
        UPDATE orders 
        SET status = 'accepted', updated_at = NOW()
        WHERE order_id = $1 AND status = 'pending'
    """, order_id)
    
    # Уведомляем пользователя
    try:
        await bot_instance.send_message(
            chat_id=order['telegram_id'],
            text=f"✅ Ваш заказ #{order_id} принят!\n\n"
                 "Заказ подтвержден. Ожидайте доставки."
        )
    except Exception as e:
        print(f"Ошибка уведомления пользователя: {e}")
    
    await message.answer(f"✅ Заказ #{order_id} принят")

@router.message(Command("decline"))
async def decline_order(message: types.Message):
    """Администратор отклоняет заказ по команде /decline <order_id>"""
    # Проверяем роль администратора
    user = await db.fetchrow("SELECT role FROM users WHERE telegram_id = $1", message.from_user.id)
    if not user or user['role'] != 'admin':
        await message.answer("❌ У вас нет прав для выполнения этой команды")
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("❗ Использование: /decline <order_id>")
        return
    
    try:
        order_id = int(parts[1])
    except ValueError:
        await message.answer("❌ Неверный ID заказа")
        return
    
    # Проверяем статус заказа
    order = await db.fetchrow("SELECT status, telegram_id FROM orders WHERE order_id = $1", order_id)
    if not order:
        await message.answer("❌ Заказ не найден")
        return
    
    if order['status'] in ['completed', 'declined']:
        await message.answer(f"❌ Нельзя изменить статус заказа #{order_id}, он уже {order['status']}")
        return
    
    # Получаем товары из заказа
    order_items = await db.fetch("""
        SELECT oi.product_id, oi.quantity
        FROM order_items oi
        WHERE oi.order_id = $1
    """, order_id)
    
    # Возвращаем товары на склад
    for item in order_items:
        await db.execute("""
            UPDATE products 
            SET stock_quantity = stock_quantity + $1
            WHERE product_id = $2
        """, item['quantity'], item['product_id'])
    
    # Обновляем статус заказа
    await db.execute("""
        UPDATE orders 
        SET status = 'declined', updated_at = NOW()
        WHERE order_id = $1
    """, order_id)
    
    # Уведомляем пользователя
    try:
        await bot_instance.send_message(
            chat_id=order['telegram_id'],
            text=f"❌ *Ваш заказ #{order_id} отклонен.*\n\n"
                 f"По всем вопросам обращайтесь к @{config.SUPPORT}.",
            
        )
    except Exception:
        pass
    
    await message.answer(f"❌ Заказ #{order_id} отклонен")

@router.message(Command("deliver"))
async def deliver_order(message: types.Message):
    """Администратор отмечает заказ как отправленный по команде /deliver <order_id> <время_в_минутах>"""
    # Проверяем роль администратора
    user = await db.fetchrow("SELECT role FROM users WHERE telegram_id = $1", message.from_user.id)
    if not user or user['role'] != 'admin':
        await message.answer("❌ У вас нет прав для выполнения этой команды")
        return
    
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("ℹ️ Использование: /deliver <order_id> <время_в_минутах>")
        return
    
    try:
        order_id = int(parts[1])
        delivery_time = int(parts[2])
    except ValueError:
        await message.answer("❌ Неверный ID заказа или время доставки")
        return
    
    # Проверяем статус заказа
    order = await db.fetchrow("SELECT status, telegram_id FROM orders WHERE order_id = $1", order_id)
    if not order:
        await message.answer("❌ Заказ не найден")
        return
    
    if order['status'] in ['completed', 'declined']:
        await message.answer(f"❌ Нельзя изменить статус заказа #{order_id}, он уже {order['status']}")
        return
    
    # Обновляем статус заказа
    await db.execute("""
        UPDATE orders 
        SET status = 'delivery', updated_at = NOW()
        WHERE order_id = $1
    """, order_id)
    
    # Уведомляем пользователя
    try:
        await bot_instance.send_message(
            chat_id=order['telegram_id'],
            text=f"🚚 Ваш заказ #{order_id} отправлен!\n\n"
                 f"⏰ Ожидаемое время доставки: {delivery_time} минут.\n"
                 "Заказ в пути. Ожидайте доставки."
        )
    except Exception as e:
        print(f"Ошибка отправки уведомления пользователю: {e}")
    
    await message.answer(f"🚚 Заказ #{order_id} отправлен (время доставки: {delivery_time} мин)")

@router.message(Command("confirm"))
async def confirm_order(message: types.Message):
    """Администратор подтверждает оплату и завершает заказ"""
    user = await db.fetchrow("SELECT role FROM users WHERE telegram_id = $1", message.from_user.id)
    if not user or user['role'] != 'admin':
        await message.answer("❌ У вас нет прав для выполнения этой команды")
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("ℹ️ Использование: /confirm <order_id>")
        return
    
    try:
        order_id = int(parts[1])
    except ValueError:
        await message.answer("❌ Неверный ID заказа")
        return
    
    # Проверяем текущий статус
    order = await db.fetchrow("SELECT status, telegram_id FROM orders WHERE order_id = $1", order_id)
    if not order:
        await message.answer("❌ Заказ не найден")
        return
    
    if order['status'] == 'completed':
        await message.answer(f"ℹ️ Заказ #{order_id} уже завершен")
        return
    
    if order['status'] == 'declined':
        await message.answer(f"❌ Нельзя завершить отклоненный заказ")
        return
    
    # Обновляем username перед завершением заказа
    user_info = await db.fetchrow("""
        SELECT username, first_name 
        FROM users 
        WHERE telegram_id = $1
    """, order['telegram_id'])
    
    if user_info:
        try:
            from bot_instance import bot_instance
            chat_member = await bot_instance.get_chat(order['telegram_id'])
            
            actual_username = chat_member.username or user_info['username'] or 'User'
            actual_first_name = chat_member.first_name or user_info['first_name'] or 'User'
            
            await db.execute("""
                UPDATE users 
                SET username = $1,
                    first_name = $2,
                    updated_at = NOW()
                WHERE telegram_id = $3
            """, actual_username, actual_first_name, order['telegram_id'])
            
            print(f"✅ Обновлен username: @{actual_username} при завершении заказа #{order_id}")
        except Exception as e:
            print(f"⚠️ Не удалось обновить username через API: {e}")
    
    # Проверяем, не начислялись ли уже бонусы
    existing_bonuses = await db.fetchval("""
        SELECT COUNT(*) FROM referral_discounts 
        WHERE order_id = $1
    """, order_id)
    
    if existing_bonuses > 0:
        await message.answer(f"⚠️ Бонусы за заказ #{order_id} уже были начислены. Завершаем без повторного начисления.")
        
        await db.execute("""
            UPDATE orders 
            SET status = 'completed', payment_status = 'paid', updated_at = NOW()
            WHERE order_id = $1
        """, order_id)
        
        await message.answer(f"✅ Заказ #{order_id} завершен (без повторного начисления бонусов)")
        return
    
    # Обновляем статус заказа
    await db.execute("""
        UPDATE orders 
        SET status = 'completed', 
            payment_status = 'paid',
            updated_at = NOW()
        WHERE order_id = $1
    """, order_id)
    
    # ✅ НОВАЯ ЛОГИКА: Начисляем бонусы
    order_full = await db.fetchrow("""
        SELECT o.telegram_id, o.final_amount, u.referred_by, u.total_orders
        FROM orders o
        LEFT JOIN users u ON o.telegram_id = u.telegram_id
        WHERE o.order_id = $1
    """, order_id)
    
    # Начисляем бонусы только если у пользователя есть реферер
    if order_full and order_full.get('referred_by'):
        referrer_telegram_id = order_full['referred_by']
        
        # Проверяем, существует ли реферер
        referrer = await db.fetchrow(
            "SELECT telegram_id, referred_by FROM users WHERE telegram_id = $1",
            referrer_telegram_id
        )
        
        if referrer:
            # ✅ Проверяем, первый ли это заказ пользователя
            user_orders_count = await db.fetchval("""
                SELECT COUNT(*) FROM orders 
                WHERE telegram_id = $1 AND status = 'completed'
            """, order_full['telegram_id'])
            
            # Если это ПЕРВЫЙ завершенный заказ - начисляем бонус РЕФЕРЕРУ
            if user_orders_count == 1:  # Только что завершили первый заказ
                await db.execute("""
                    INSERT INTO referral_discounts (
                        order_id, referrer_telegram_id, referred_telegram_id, discount_amount
                    ) VALUES ($1, $2, $3, $4)
                """, order_id, referrer_telegram_id, order_full['telegram_id'], 2.00)
                
                try:
                    await bot_instance.send_message(
                        chat_id=referrer_telegram_id,
                        text=f"🎉 Вы получили 2€ за реферала!\n\n"
                             f"Пользователь совершил заказ #{order_id}.\n"
                             f"Ваш бонус: 2€"
                    )
                except Exception as e:
                    print(f"Ошибка уведомления рефа: {e}")
                
                print(f"✅ Начислено 2€ рефереру {referrer_telegram_id} за первый заказ реферала #{order_id}")
            
            # Бонус дедушке (0.5€) - если это первый заказ И есть дедушка
            if user_orders_count == 1 and referrer.get('referred_by'):
                grandparent_telegram_id = referrer['referred_by']
                
                grandparent = await db.fetchrow(
                    "SELECT telegram_id FROM users WHERE telegram_id = $1",
                    grandparent_telegram_id
                )
                
                if grandparent:
                    await db.execute("""
                        INSERT INTO referral_discounts (
                            order_id, referrer_telegram_id, referred_telegram_id, discount_amount, created_at
                        ) VALUES ($1, $2, $3, $4, NOW())
                    """, order_id, grandparent_telegram_id, order_full['telegram_id'], 0.50)
                    
                    try:
                        await bot_instance.send_message(
                            chat_id=grandparent_telegram_id,
                            text=f"🎉 Вы получили 0.5€ за дедушка-реферала!\n\n"
                                 f"Ваш реферал привел нового пользователя, который совершил заказ #{order_id}.\n"
                                 f"Ваш бонус: 0.5€"
                        )
                    except Exception as e:
                        print(f"Ошибка уведомления дедушки: {e}")
                    
                    print(f"✅ Начислено 0.5€ дедушке {grandparent_telegram_id}")
    
    # Уведомляем пользователя
    try:
        await bot_instance.send_message(
            chat_id=order_full['telegram_id'],
            text="🙏 Спасибо, что заказали у нас! Следите за обновлениями в нашем канале."
        )
    except Exception as e:
        print(f"Ошибка уведомления пользователя: {e}")
    
@router.callback_query(F.data.startswith("admin_accept:"))
async def admin_accept_order(callback: types.CallbackQuery):
    """Администратор принимает заказ"""
    order_id = int(callback.data.split(":")[1])
    
    # Обновляем статус заказа
    await db.execute("""
        UPDATE orders 
        SET status = 'accepted', updated_at = NOW()
        WHERE order_id = $1
    """, order_id)
    
    # Получаем информацию о заказе
    order = await db.fetchrow("SELECT telegram_id FROM orders WHERE order_id = $1", order_id)
    
    if order:
        # Уведомляем пользователя
        try:
            await bot_instance.send_message(
                chat_id=order['telegram_id'],
                text=f"✅ *Ваш заказ #{order_id} принят!*\n\n"
                     "Заказ подтвержден. Ожидайте доставки.",
                
            )
        except Exception:
            pass
    
    await callback.answer("✅ Заказ принят")
    await callback.message.edit_reply_markup(
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Принято", callback_data="no_action")]
        ])
    )

@router.callback_query(F.data.startswith("admin_decline:"))
async def admin_decline_order(callback: types.CallbackQuery):
    """Администратор отклоняет заказ"""
    order_id = int(callback.data.split(":")[1])
    
    # Получаем товары из заказа
    order_items = await db.fetch("""
        SELECT oi.product_id, oi.quantity
        FROM order_items oi
        WHERE oi.order_id = $1
    """, order_id)
    
    # Возвращаем товары на склад
    for item in order_items:
        await db.execute("""
            UPDATE products 
            SET stock_quantity = stock_quantity + $1
            WHERE product_id = $2
        """, item['quantity'], item['product_id'])
    
    # Обновляем статус заказа
    await db.execute("""
        UPDATE orders 
        SET status = 'declined', updated_at = NOW()
        WHERE order_id = $1
    """, order_id)
    
    # Получаем информацию о заказе
    order = await db.fetchrow("SELECT telegram_id FROM orders WHERE order_id = $1", order_id)
    
    if order:
        # Уведомляем пользователя
        try:
            await bot_instance.send_message(
                chat_id=order['telegram_id'],
                text=f"❌ *Ваш заказ #{order_id} отклонен.*\n\n"
                     f"По всем вопросам обращайтесь к @{config.SUPPORT}.",
                
            )
        except Exception:
            pass
    
    await callback.answer("❌ Заказ отклонен")
    await callback.message.edit_reply_markup(
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отклонено", callback_data="no_action")]
        ])
    )

@router.callback_query(F.data.startswith("admin_delivery:"))
async def admin_delivery_order(callback: types.CallbackQuery):
    """Администратор отмечает заказ как отправленный"""
    order_id = int(callback.data.split(":")[1])
    
    # Обновляем статус заказа
    await db.execute("""
        UPDATE orders 
        SET status = 'delivery', updated_at = NOW()
        WHERE order_id = $1
    """, order_id)
    
    # Получаем информацию о заказе
    order = await db.fetchrow("SELECT telegram_id FROM orders WHERE order_id = $1", order_id)
    
    if order:
        # Уведомляем пользователя
        try:
            await bot_instance.send_message(
                chat_id=order['telegram_id'],
                text=f"🚚 *Ваш заказ #{order_id} отправлен!*\n\n"
                     "Заказ в пути. Ожидайте доставки.",
                
            )
        except Exception:
            pass
    
    await callback.answer("🚚 Заказ отправлен")
    await callback.message.edit_reply_markup(
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚚 В доставке", callback_data="no_action")]
        ])
    )

@router.callback_query(F.data.startswith("admin_confirm:"))
async def admin_confirm_order(callback: types.CallbackQuery):
    """Администратор подтверждает оплату и завершает заказ"""
    order_id = int(callback.data.split(":")[1])
    
    # Обновляем статус заказа
    await db.execute("""
        UPDATE orders 
        SET status = 'completed', 
            payment_status = 'paid',
            updated_at = NOW()
        WHERE order_id = $1
    """, order_id)
    
    # Получаем информацию о заказе и пользователе
    order = await db.fetchrow("""
        SELECT o.telegram_id, o.final_amount, u.referred_by
        FROM orders o
        LEFT JOIN users u ON o.telegram_id = u.telegram_id
        WHERE o.order_id = $1
    """, order_id)
    
    if order and order.get('referred_by'):
        # Начисляем бонус рефереру (2€)
        referrer_telegram_id = order['referred_by']
        
        # Проверяем существование рефе��ера
        referrer = await db.fetchrow(
            "SELECT telegram_id, referred_by FROM users WHERE telegram_id = $1",
            referrer_telegram_id
        )
        
        if referrer:
            # Добавляем запись о реферальном бонусе
            await db.execute("""
                INSERT INTO referral_discounts (
                    order_id, referrer_telegram_id, referred_telegram_id, discount_amount, created_at
                ) VALUES ($1, $2, $3, $4, NOW())
            """, order_id, referrer_telegram_id, order['telegram_id'], 2.00)
            
            # Уведомляем рефе��ера
            try:
                await bot_instance.send_message(
                    chat_id=referrer_telegram_id,
                    text=f"🎉 *Вы получили 2€ за реферала!*\n\n"
                         f"Пользователь совершил заказ #{order_id}.\n"
                         f"Ваш бонус: 2€",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
            
            # ИСПРАВЛЕНИЕ #4: Начисляем бонус дедушке (0.5€)
            if referrer.get('referred_by'):
                grandparent_telegram_id = referrer['referred_by']
                
                grandparent = await db.fetchrow(
                    "SELECT telegram_id FROM users WHERE telegram_id = $1",
                    grandparent_telegram_id
                )
                
                if grandparent:
                    await db.execute("""
                        INSERT INTO referral_discounts (
                            order_id, referrer_telegram_id, referred_telegram_id, discount_amount, created_at
                        ) VALUES ($1, $2, $3, $4, NOW())
                    """, order_id, grandparent_telegram_id, order['telegram_id'], 0.50)
                    
                    try:
                        await bot_instance.send_message(
                            chat_id=grandparent_telegram_id,
                            text=f"🎉 *Вы получили 0.5€ за внука-реферала!*\n\n"
                                 f"Ваш реферал привел пользователя, который совершил заказ #{order_id}.\n"
                                 f"Ваш бонус: 0.5€",
                            parse_mode="Markdown"
                        )
                    except Exception:
                        pass
    
    await callback.answer(f"💰 Заказ #{order_id} завершен")
    await callback.message.edit_reply_markup(
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 Завершено", callback_data="no_action")]
        ])
    )

@router.message(Command("orders"))
async def list_pending_orders(message: types.Message):
    """Показывает все неподтвержденные заказы для админов"""
    # Проверяем роль администратора
    user = await db.fetchrow("SELECT role FROM users WHERE telegram_id = $1", message.from_user.id)
    if not user or user['role'] != 'admin':
        await message.answer("❌ У вас нет прав для выполнения этой команды")
        return
    
    # Получаем все неподтвержденные заказы
    orders = await db.fetch("""
        SELECT o.order_id, o.created_at, o.final_amount, o.status,
               u.username, u.first_name, u.last_name
        FROM orders o
        JOIN users u ON o.telegram_id = u.telegram_id
        WHERE o.status = 'pending'
        ORDER BY o.created_at DESC
    """)
    
    if not orders:
        await message.answer("📋 Нет неподтвержденных заказов")
        return
    
    text = "📋 *Неподтвержденные заказы:*\n\n"
    
    for order in orders:
        order_id = order['order_id']
        created_at = order['created_at'].strftime("%d.%m.%Y %H:%M")
        amount = order['final_amount']
        username = order.get('username', 'N/A')
        first_name = order.get('first_name', '')
        last_name = order.get('last_name', '')
        name = f"{first_name} {last_name}".strip() or username or "N/A"
        
        text += f"🆔 {order_id} | 👤 {name} (@{username}) | 💰 {amount}€ | 📅 {created_at}\n"
    
    await message.answer(text, )

@router.message(Command("pending_orders"))
async def list_pending_delivery_orders(message: types.Message):
    """Показывает активные заказы (ОПТИМИЗИРОВАНО)"""
    
    # Проверяем права
    is_admin = await db.check_admin_role(message.from_user.id)
    if not is_admin:
        return await message.answer("❌ У вас нет прав")
    
    # ОДИН запрос вместо N+1
    orders = await db.get_active_orders_with_items()
    
    if not orders:
        return await message.answer("📋 Нет активных заказов")
    
    text = "📋 Активные заказы:\n\n"
    
    for order in orders:
        status_emoji = {'pending': '⏳', 'delivery': '🚚'}.get(order['status'], '❓')
        status_text = {'pending': 'Ожидает', 'delivery': 'Доставляется'}.get(order['status'], order['status'])
        
        # Контакт
        username = order.get('username')
        phone = order.get('phone')
        contact = f"@{username}" if username else (phone if phone else "нет контакта")
        
        # Товары (уже получены!)
        items = order.get('items') or []
        items_text = ", ".join([f"{item['quantity']}x{item['product_id']}" for item in items if item])
        
        text += f"{status_emoji} Заказ #{order['order_id']}\n"
        text += f"👤 {contact}\n"
        text += f"📍 {order.get('delivery_address', 'не указан')}\n"
        text += f"🛒 {items_text}\n"
        text += f"💰 {order['final_amount']:.2f}€ | 📅 {order['created_at'].strftime('%d.%m.%Y %H:%M')}\n"
        text += f"📊 {status_text}\n"
        text += "─────────────────\n\n"
    
    await message.answer(text)

@router.callback_query(F.data.startswith("admin_confirm:"))
async def admin_confirm_order(callback: types.CallbackQuery):
    order_id = int(callback.data.split(":")[1])
    
    # Проверяем роль администратора
    user = await db.fetchrow("SELECT role, username FROM users WHERE telegram_id = $1", callback.from_user.id)
    if not user or user['role'] != 'admin':
        await callback.answer("❌ У вас нет прав", show_alert=True)
        return
    
    # Проверяем статус заказа
    order = await db.fetchrow("SELECT status, telegram_id FROM orders WHERE order_id = $1", order_id)
    if not order or order['status'] != 'pending':
        await callback.answer("❌ Заказ не найден или уже обработан", show_alert=True)
        return
    
    # Обновляем статус
    await db.execute("""
        UPDATE orders 
        SET status = 'accepted', updated_at = NOW()
        WHERE order_id = $1
    """, order_id)
    
    # Уведомляем пользователя
    try:
        await bot_instance.send_message(
            chat_id=order['telegram_id'],
            text=f"✅ *Ваш заказ #{order_id} подтвержден!*\n\n"
                 "Мы начали подготовку вашего заказа.",
            
        )
    except Exception:
        pass
    
    await callback.answer(f"✅ Заказ #{order_id} подтвержден")
    await callback.message.edit_reply_markup(reply_markup=None)

@router.callback_query(F.data.startswith("admin_decline:"))
async def admin_decline_order(callback: types.CallbackQuery):
    order_id = int(callback.data.split(":")[1])
    
    # Проверяем роль администратора
    user = await db.fetchrow("SELECT role, username FROM users WHERE telegram_id = $1", callback.from_user.id)
    if not user or user['role'] != 'admin':
        await callback.answer("❌ У вас нет прав", show_alert=True)
        return
    
    # Проверяем статус заказа
    order = await db.fetchrow("SELECT status, telegram_id FROM orders WHERE order_id = $1", order_id)
    if not order or order['status'] != 'pending':
        await callback.answer("❌ Заказ не найден или уже обработан", show_alert=True)
        return
    
    # Обновляем статус
    await db.execute("""
        UPDATE orders 
        SET status = 'declined', updated_at = NOW()
        WHERE order_id = $1
    """, order_id)
    
    # Уведомляем пользователя
    try:
        await bot_instance.send_message(
            chat_id=order['telegram_id'],
            text=f"❌ *Ваш заказ #{order_id} отклонен.*\n\n"
                 f"По всем вопросам обращайтесь к @{config.SUPPORT}.",
            
        )
    except Exception:
        pass
    
    await callback.answer(f"❌ Заказ #{order_id} отклонен")
    await callback.message.edit_reply_markup(reply_markup=None)

@router.callback_query(F.data.startswith("admin_complete:"))
async def admin_complete_order(callback: types.CallbackQuery):
    order_id = int(callback.data.split(":")[1])
    
    # Проверяем роль администратора
    user = await db.fetchrow("SELECT role, username FROM users WHERE telegram_id = $1", callback.from_user.id)
    if not user or user['role'] != 'admin':
        await callback.answer("❌ У вас нет прав", show_alert=True)
        return
    
    # Проверяем статус заказа
    order = await db.fetchrow("SELECT status, telegram_id, final_amount FROM orders WHERE order_id = $1", order_id)
    if not order or order['status'] != 'delivery':
        await callback.answer("❌ Заказ не найден или не в доставке", show_alert=True)
        return
    
    # Обновляем статус
    await db.execute("""
        UPDATE orders 
        SET status = 'completed', updated_at = NOW()
        WHERE order_id = $1
    """, order_id)
    
    # Обновляем статистику пользователя
    await db.execute("""
        UPDATE users 
        SET total_orders = total_orders + 1, total_spent = total_spent + $2
        WHERE telegram_id = $3
    """, order['final_amount'], order['telegram_id'])
    
    # Уведомляем пользователя
    try:
        await bot_instance.send_message(
            chat_id=order['telegram_id'],
            text=f"💰 *Заказ #{order_id} завершен администратором {user['username']}!*\n\n"
                 "Спасибо за заказ! Оставьте отзыв в нашем канале.",
            
        )
    except Exception:
        pass
    
    await callback.answer(f"💰 Заказ #{order_id} завершен")
    await callback.message.edit_reply_markup(reply_markup=None)

@router.message(Command("look_order"))
async def look_order(message: types.Message):
    """Просмотр заказа (ОПТИМИЗИРОВАНО)"""
    
    # Проверяем права
    is_admin = await db.check_admin_role(message.from_user.id)
    
    if not is_admin:
        user = await db.fetchrow(
            "SELECT telegram_id FROM users WHERE telegram_id = $1",
            message.from_user.id
        )
        if not user:
            return await message.answer("❌ Вы не зарегистрированы")
    
    parts = message.text.split()
    if len(parts) != 2:
        return await message.answer("ℹ️ Использование: /look_order <order_id>")
    
    try:
        order_id = int(parts[1])
    except ValueError:
        return await message.answer("❌ Неверный ID заказа")
    
    # ОДИН запрос вместо 3-5
    order = await db.get_order_with_items(order_id)
    
    if not order:
        return await message.answer("❌ Заказ не найден")
    
    # Проверка доступа
    if not is_admin and order['telegram_id'] != message.from_user.id:
        return await message.answer("❌ У вас нет доступа")
    
    # Формируем ответ
    status_map = {
        'pending': ('⏳', 'Ожидает подтверждения'),
        'accepted': ('✅', 'Принят'),
        'delivery': ('🚚', 'В доставке'),
        'completed': ('💰', 'Завершен'),
        'declined': ('❌', 'Отклонен')
    }
    emoji, status_text = status_map.get(order['status'], ('❓', order['status']))
    
    text = f"{emoji} ЗАКАЗ #{order_id}\n"
    text += f"━━━━━━━━━━━━━━━━━━━━\n\n"
    
    # Клиент
    text += f"👤 Клиент:\n"
    if order.get('username'):
        text += f"   @{order['username']}\n"
    if order.get('phone'):
        text += f"   📞 {order['phone']}\n"
    text += f"\n"
    
    # Статус
    text += f"📊 Статус: {status_text}\n"
    text += f"📅 Создан: {order['created_at'].strftime('%d.%m.%Y %H:%M')}\n"
    if order.get('updated_at'):
        text += f"🔄 Обновлен: {order['updated_at'].strftime('%d.%m.%Y %H:%M')}\n"
    text += f"\n"
    
    # Адрес
    text += f"📍 Адрес: {order.get('delivery_address', 'не указан')}\n\n"
    
    # Товары (уже получены!)
    text += f"🛒 Состав:\n"
    items = order.get('items') or []
    for item in items:
        if item:
            text += f"   • {item.get('product_name', 'Товар')}\n"
            text += f"     {item['quantity']} × {item['unit_price']:.2f}€ = {item['total_price']:.2f}€\n"
    
    text += f"\n"
    
    # Финансы
    text += f"💰 Финансы:\n"
    text += f"   Сумма: {order['total_amount']:.2f}€\n"
    if order.get('discount_amount', 0) > 0:
        text += f"   Скидка: -{order['discount_amount']:.2f}€\n"
    text += f"   ИТОГО: {order['final_amount']:.2f}€\n"
    
    if order.get('promo_code_used'):
        text += f"   🎁 Промокод: {order['promo_code_used']}\n"
    
    # Команды для админа
    if is_admin:
        text += f"\n━━━━━━━━━━━━━━━━━━━━\n"
        text += f"🔧 Команды:\n"
        if order['status'] == 'pending':
            text += f"/accept {order_id} | /decline {order_id}\n"
        if order['status'] in ['pending', 'accepted']:
            text += f"/deliver {order_id} <мин>\n"
        if order['status'] in ['delivery', 'accepted']:
            text += f"/confirm {order_id}\n"
    
    await message.answer(text)

@router.message(Command("cancel_order"))
async def cancel_order_user(message: types.Message):
    """Отмена заказа пользователем (только pending)"""
    user = await db.fetchrow("SELECT telegram_id FROM users WHERE telegram_id = $1", message.from_user.id)
    if not user:
        await message.answer("❌ Вы не зарегистрированы")
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("ℹ️ Использование: /cancel_order <order_id>")
        return
    
    try:
        order_id = int(parts[1])
    except ValueError:
        await message.answer("❌ Неверный ID заказа")
        return
    
    # Проверяем заказ
    order = await db.fetchrow("""
        SELECT status, telegram_id FROM orders 
        WHERE order_id = $1 AND telegram_id = $2
    """, order_id, message.from_user.id)
    
    if not order:
        await message.answer("❌ Заказ не найден или не принадлежит вам")
        return
    
    if order['status'] != 'pending':
        await message.answer("❌ Можно отменить только заказы в статусе 'ожидает подтверждения'")
        return
    
    # Возвращаем товары на склад
    items = await db.fetch("""
        SELECT product_id, quantity FROM order_items WHERE order_id = $1
    """, order_id)
    
    for item in items:
        await db.execute("""
            UPDATE products 
            SET stock_quantity = stock_quantity + $1
            WHERE product_id = $2
        """, item['quantity'], item['product_id'])
    
    # Отменяем заказ
    await db.execute("""
        UPDATE orders 
        SET status = 'declined', updated_at = NOW()
        WHERE order_id = $1
    """, order_id)
    
    await message.answer(f"✅ Заказ #{order_id} отменен. Товары возвращены на склад.")

@router.message(Command("stats"))
async def admin_stats(message: types.Message):
    """Простая статистика для админов"""
    user = await db.fetchrow("SELECT role FROM users WHERE telegram_id = $1", message.from_user.id)
    if not user or user['role'] != 'admin':
        await message.answer("❌ У вас нет прав для выполнения этой команды")
        return
    
    # Общая статистика
    stats = await db.fetchrow("""
        SELECT 
            COUNT(*) as total_orders,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending_orders,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_orders,
            SUM(CASE WHEN status = 'declined' THEN 1 ELSE 0 END) as declined_orders,
            COALESCE(SUM(CASE WHEN status = 'completed' THEN final_amount ELSE 0 END), 0) as total_revenue
        FROM orders
    """)
    
    # Статистика за сегодня
    today_stats = await db.fetchrow("""
        SELECT 
            COUNT(*) as today_orders,
            COALESCE(SUM(final_amount), 0) as today_revenue
        FROM orders
        WHERE DATE(created_at) = CURRENT_DATE
    """)
    
    # Топ товаров
    top_products = await db.fetch("""
        SELECT p.product_name, COUNT(*) as orders_count
        FROM order_items oi
        JOIN products p ON oi.product_id = p.product_id
        JOIN orders o ON oi.order_id = o.order_id
        WHERE o.status = 'completed'
        GROUP BY p.product_name
        ORDER BY orders_count DESC
        LIMIT 5
    """)
    
    # Количество пользователей
    users_count = await db.fetchval("SELECT COUNT(*) FROM users")
    
    text = "📊 СТАТИСТИКА БОТА\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n\n"
    
    text += f"👥 Пользователей: {users_count}\n\n"
    
    text += "📦 Заказы:\n"
    text += f"   Всего: {stats['total_orders']}\n"
    text += f"   ⏳ Ожидают: {stats['pending_orders']}\n"
    text += f"   ✅ Завершено: {stats['completed_orders']}\n"
    text += f"   ❌ Отклонено: {stats['declined_orders']}\n\n"
    
    text += f"💰 Выручка: {stats['total_revenue']:.2f}€\n\n"
    
    text += "📅 Сегодня:\n"
    text += f"   Заказов: {today_stats['today_orders']}\n"
    text += f"   Выручка: {today_stats['today_revenue']:.2f}€\n\n"
    
    if top_products:
        text += "🏆 Топ товаров:\n"
        for i, prod in enumerate(top_products, 1):
            text += f"   {i}. {prod['product_name']} ({prod['orders_count']})\n"
    
    await message.answer(text)

# ============================================
# ОБРАБОТЧИК: Кнопка "Мои заказы" в меню
# ============================================

@router.callback_query(F.data == "my_orders")
async def my_orders_handler(callback: types.CallbackQuery):
    """История заказов пользователя"""
    user_id = callback.from_user.id
    
    orders = await db.fetch("""
        SELECT order_id, status, final_amount, created_at
        FROM orders
        WHERE telegram_id = $1
        ORDER BY created_at DESC
        LIMIT 10
    """, user_id)
    
    if not orders:
        await callback.message.edit_text(
            "📭 У вас пока нет заказов",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛒 Перейти к покупкам", callback_data="catalogue")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="profile")]
            ])
        )
        return
    
    text = "📋 Ваши заказы:\n\n"
    
    buttons = []
    
    #for order in orders:
    #    status_emoji = {
    #        'pending': '⏳',
    #        'accepted': '✅', 
    #        'delivery': '🚚',
    #        'completed': '💰',
    #        'declined': '❌'
    #    }.get(order['status'], '❓')
    #    
    #    date_str = order['created_at'].strftime('%d.%m.%Y')
    #    
    #    text += f"{status_emoji} Заказ #{order['order_id']}\n"
    #    text += f"   {order['final_amount']}€ | {date_str}\n\n"
    #    
    #    # Добавляем кнопку для каждого заказа
    #    buttons.append([InlineKeyboardButton(
    #        text=f"📋 Заказ #{order['order_id']}",
    #        callback_data=f"view_order:{order['order_id']}"
    #    )])
    
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="profile")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data.startswith("view_order:"))
async def view_order_details(callback: types.CallbackQuery):
    """Просмотр деталей заказа через кнопку"""
    order_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    
    # Получаем заказ
    order = await db.fetchrow("""
        SELECT * FROM orders 
        WHERE order_id = $1 AND telegram_id = $2
    """, order_id, user_id)
    
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    
    # Получаем товары
    items = await db.fetch("""
        SELECT oi.*, p.product_name
        FROM order_items oi
        LEFT JOIN products p ON oi.product_id = p.product_id
        WHERE oi.order_id = $1
    """, order_id)
    
    status_emoji = {
        'pending': '⏳',
        'accepted': '✅',
        'delivery': '🚚',
        'completed': '💰',
        'declined': '❌'
    }.get(order['status'], '❓')
    
    status_text = {
        'pending': 'Ожидает подтверждения',
        'accepted': 'Принят',
        'delivery': 'В доставке',
        'completed': 'Завершен',
        'declined': 'Отклонен'
    }.get(order['status'], order['status'])
    
    text = f"{status_emoji} Заказ #{order_id}\n"
    text += f"━━━━━━━━━━━━━━━━━━━━\n\n"
    text += f"📊 Статус: {status_text}\n"
    text += f"📅 Дата: {order['created_at'].strftime('%d.%m.%Y %H:%M')}\n\n"
    
    text += "🛒 Состав:\n"
    for item in items:
        text += f"  • {item.get('product_name', 'Товар')} - {item['quantity']}шт\n"
    
    text += f"\n💰 Сумма: {order['total_amount']}€\n"
    if order.get('discount_amount', 0) > 0:
        text += f"🎁 Скидка: -{order['discount_amount']}€\n"
    text += f"💳 Итого: {order['final_amount']}€\n"
    
    buttons = []
    
    # Кнопка отмены для pending заказов
    if order['status'] == 'pending':
        buttons.append([InlineKeyboardButton(
            text="❌ Отменить заказ",
            callback_data=f"cancel_order_btn:{order_id}"
        )])
    
    buttons.append([InlineKeyboardButton(text="🔙 К списку заказов", callback_data="my_orders")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("cancel_order_btn:"))
async def cancel_order_button(callback: types.CallbackQuery):
    """Отмена заказа через кнопку"""
    order_id = int(callback.data.split(":")[1])
    
    order = await db.fetchrow("""
        SELECT status FROM orders 
        WHERE order_id = $1 AND telegram_id = $2
    """, order_id, callback.from_user.id)
    
    if not order or order['status'] != 'pending':
        await callback.answer("❌ Заказ нельзя отменить", show_alert=True)
        return
    
    # Возвращаем товары
    items = await db.fetch("""
        SELECT product_id, quantity FROM order_items WHERE order_id = $1
    """, order_id)
    
    for item in items:
        await db.execute("""
            UPDATE products 
            SET stock_quantity = stock_quantity + $1
            WHERE product_id = $2
        """, item['quantity'], item['product_id'])
    
    # Отменяем
    await db.execute("""
        UPDATE orders 
        SET status = 'declined', updated_at = NOW()
        WHERE order_id = $1
    """, order_id)
    
    await callback.answer("✅ Заказ отменен", show_alert=True)
    await callback.message.edit_text(
        f"❌ Заказ #{order_id} отменен\n\nТовары возвращены на склад.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Мои заказы", callback_data="active_orders")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
    )