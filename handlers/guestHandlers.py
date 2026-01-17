import aiogram
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.types import InputMediaPhoto, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.enums import ParseMode
import keyboards.guest as guest
import database.database as db
from aiogram.fsm.context import FSMContext
from bot_instance import bot_instance, notification_service
from config import USERNAME
from texts import texts

router = Router()

# Ссылка на канал для приглашений
CHANNEL_ID = "@PewPuff_official"

@router.message(Command("start"))
async def start_message(message: types.Message, state: FSMContext):
    # Обработка реферальной ссылки СРАЗУ
    referred_by_telegram_id = None
    payload = message.text.split(" ", 1)
    
    if len(payload) > 1 and payload[1].startswith("ref_"):
        try:
            referred_by_telegram_id = int(payload[1][4:])
            # Проверяем, что реферер существует
            ref_user = await db.fetchrow(
                "SELECT * FROM users WHERE telegram_id = $1", 
                referred_by_telegram_id
            )
            if not ref_user:
                referred_by_telegram_id = None
            elif referred_by_telegram_id == message.from_user.id:
                # Нельзя пригласить самого себя
                referred_by_telegram_id = None
        except ValueError:
            referred_by_telegram_id = None
    
    # Сохраняем реферальный ID в FSM для использования после подписки
    if referred_by_telegram_id:
        await state.update_data(referred_by=referred_by_telegram_id)
    
    # Проверяем подписку
    try:
        member = await bot_instance.get_chat_member(CHANNEL_ID, message.from_user.id)
        if member.status not in [aiogram.enums.ChatMemberStatus.MEMBER,
                               aiogram.enums.ChatMemberStatus.ADMINISTRATOR,
                               aiogram.enums.ChatMemberStatus.CREATOR]:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📢 Подписаться на канал", url=f"https://t.me/{CHANNEL_ID.replace('@', '')}")],
                [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_subscription")]
            ])
            
            await message.answer(
                text=f"Пожалуйста, подпишитесь на наш канал {CHANNEL_ID} чтобы использовать бота.",
                reply_markup=keyboard
            )
            return
    except aiogram.exceptions.TelegramAPIError:
        await message.answer(
            text=f"Не удалось проверить подписку на канал {CHANNEL_ID}.",
        )
        return

    # Регистрируем пользователя
    await register_user(message.from_user, referred_by_telegram_id)
    
    await message.answer(
        text=texts.welcome_text,
        reply_markup=guest.main_menu_keyboard(), parse_mode=ParseMode.MARKDOWN
    )
    await state.clear()


@router.callback_query(F.data == "check_subscription")
async def check_subscription_handler(callback: types.CallbackQuery, state: FSMContext):
    """Проверка подписки после нажатия кнопки"""
    try:
        member = await bot_instance.get_chat_member(CHANNEL_ID, callback.from_user.id)
        if member.status not in [aiogram.enums.ChatMemberStatus.MEMBER,
                               aiogram.enums.ChatMemberStatus.ADMINISTRATOR,
                               aiogram.enums.ChatMemberStatus.CREATOR]:
            await callback.answer("❌ Вы еще не подписались на канал!", show_alert=True)
            return
        
        # Если подписан - продолжаем регистрацию
        await callback.answer("✅ Спасибо за подписку!")
        
        # Получаем реферальный ID из FSM state
        state_data = await state.get_data()
        referred_by_telegram_id = state_data.get('referred_by')
        
        # Регистрируем пользователя
        await register_user(callback.from_user, referred_by_telegram_id)
        
        await callback.message.answer(
            text=texts.welcome_text,
            reply_markup=guest.main_menu_keyboard(), parse_mode=ParseMode.MARKDOWN
        )
        
        # Очищаем состояние
        await state.clear()
        
        # Удаляем сообщение с кнопкой подписки
        try:
            await callback.message.delete()
        except Exception:
            pass
        
    except Exception as e:
        await callback.answer("❌ Ошибка проверки подписки", show_alert=True)
        print(f"Error checking subscription: {e}")



async def register_user(user: types.User, referred_by_telegram_id: int = None):
    """Общая функция для регистрации/обновления пользователя"""
    # Проверяем существующего пользователя
    existing_user = await db.fetchrow(
        "SELECT * FROM users WHERE telegram_id = $1", 
        user.id
    )

    # Создаем или обновляем пользователя
    if not existing_user:
        await db.execute("""
            INSERT INTO users (
                telegram_id, username, first_name, referred_by,
                role, is_subscribed, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, 'user', TRUE, NOW(), NOW())
        """, 
        user.id,
        user.username or "User",
        user.first_name or "User",
        referred_by_telegram_id)
        
        # ✅ НОВОЕ: Начисляем скидку 2€ новому пользователю при регистрации по реферальной ссылке
        if referred_by_telegram_id:
            # Проверяем, существует ли реферер
            referrer = await db.fetchrow(
                "SELECT telegram_id FROM users WHERE telegram_id = $1",
                referred_by_telegram_id
            )
            
            if referrer:
                # Создаем запись о бонусе для НОВОГО пользователя (того, кто перешел)
                await db.execute("""
                    INSERT INTO referral_discounts (
                        order_id, referrer_telegram_id, referred_telegram_id, 
                        discount_amount, created_at
                    ) VALUES (NULL, $1, $2, 2.00, NOW())
                """, user.id, user.id)  # referrer_telegram_id = новый юзер, чтобы он мог использовать
                
                print(f"✅ Начислено 2€ новому пользователю {user.id} за регистрацию по реферальной ссылке")
                
                # Отправляем уведомление новому пользователю
                try:
                    await notification_service.add(
                        user_id=user.id,
                        text=(
                            f"🎉 Добро пожаловать в PewPuff!\n\n"
                            f"🎁 Вам начислено 2€ за регистрацию по реферальной ссылке!\n"
                            f"Используйте эту скидку при оформлении первого заказа."
                        )
                    )
                except Exception as e:
                    print(f"Ошибка отправки уведомления новому пользователю: {e}")
                
                # Уведомляем реферера о новой регистрации (но не о бонусе - его получит после заказа)
                try:
                    await notification_service.add(
                        user_id=referred_by_telegram_id,
                        text=(
                            f"👥 Пользователь @{user.username or 'новый пользователь'} "
                            f"зарегистрировался по вашей реферальной ссылке!\n\n"
                            f"Вы получите 2€ после того, как он сделает первый заказ. 🎉"
                        )
                    )
                except Exception as e:
                    print(f"Failed to send referral notification: {e}")
    else:
        # Обновляем подписку существующего пользователя
        await db.execute("""
            UPDATE users 
            SET is_subscribed = TRUE, updated_at = NOW()
            WHERE telegram_id = $1
        """, user.id)

@router.callback_query(F.data == "back")
async def back_button(callback: types.CallbackQuery):
    """Возврат в главное меню"""
    try:
        # ИСПРАВЛЕНИЕ: Пытаемся отредактировать текст
        await callback.message.edit_text(
            text=texts.welcome_text,
            reply_markup=guest.main_menu_keyboard(), parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()
    except Exception:
        # Если не получилось (например, было фото) - удаляем и отправляем новое
        try:
            await callback.message.delete()
        except:
            pass
        
        await callback.message.answer(
            text=texts.welcome_text,
            reply_markup=guest.main_menu_keyboard(), parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()

@router.callback_query(F.data == "help")
async def help_menu(callback: types.CallbackQuery):
    """Меню помощи"""
    try:
        await callback.message.edit_text(
            text=texts.help_menu_text,
            reply_markup=guest.help_menu_keyboard(), parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()
    except Exception:
        try:
            await callback.message.delete()
        except:
            pass
        
        await callback.message.answer(
            text=texts.help_menu_text,
            reply_markup=guest.help_menu_keyboard(), parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()

@router.callback_query(F.data == "main_menu")
async def main_menu_handler(callback: types.CallbackQuery):
    """Возврат в главное меню через кнопку"""
    try:
        await callback.message.edit_text(
            text="🏠 Главное меню",
            reply_markup=guest.main_menu_keyboard(), parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()
    except Exception:
        # Если не получилось (например, было фото) - удаляем и отправляем новое
        try:
            await callback.message.delete()
        except:
            pass
        
        await callback.message.answer(
            text="🏠 Главное меню",
            reply_markup=guest.main_menu_keyboard(), parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()

@router.callback_query(F.data == "catalogue")
async def catalogue_menu(callback: types.CallbackQuery):
    """Меню каталога"""
    try:
        await callback.message.edit_text(
            text="Here is the catalogue menu. Choose an option below.",
            reply_markup=guest.catalogue_menu_keyboard()
        )
        await callback.answer()
    except Exception:
        try:
            await callback.message.delete()
        except:
            pass
        
        await callback.message.answer(
            text="Here is the catalogue menu. Choose an option below.",
            reply_markup=guest.catalogue_menu_keyboard()
        )
        await callback.answer()

@router.callback_query(F.data == "promo")
async def promo_menu(callback: types.CallbackQuery):
    promo = await db.fetchrow("""
        SELECT * FROM promotions 
        WHERE is_active = TRUE 
          AND start_date <= NOW() 
          AND (end_date IS NULL OR end_date >= NOW())
        ORDER BY created_at DESC 
        LIMIT 1
    """)
    
    if promo:
        banner_url = promo["banner_url"]
        description = promo["description"]
    else:
        banner_url = "https://osgf.gov.ng/storage/temp/oc64663771bc022/assets/images/no-banner.jpg"
        description = "No current promotions available."
    
    # ИСПРАВЛЕНИЕ #2: Правильная обработка медиа
    try:
        # Пытаемся отредактировать как медиа
        await callback.message.edit_media(
            media=InputMediaPhoto(media=banner_url, caption=description),
            reply_markup=guest.promo_menu_keyboard()
        )
        await callback.answer()
    except Exception as e:
        # Если не получилось - удаляем и отправляем новое
        try:
            await callback.message.delete()
        except:
            pass
        
        await callback.message.answer_photo(
            photo=banner_url,
            caption=description,
            reply_markup=guest.promo_menu_keyboard()
        )
        await callback.answer()

@router.callback_query(F.data == "profile")
async def profile_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    # Получаем статистику пользователя
    # Любимый вкус
    favorite_product = await db.fetchval("""
        SELECT p.product_name 
        FROM products p 
        WHERE p.product_id = (
            SELECT oi.product_id 
            FROM order_items oi 
            JOIN orders o ON oi.order_id = o.order_id 
            WHERE o.telegram_id = $1 AND o.status IN ('completed', 'delivery')
            GROUP BY oi.product_id 
            ORDER BY COUNT(*) DESC 
            LIMIT 1
        )
    """, user_id)
    
    # Попробовано вкусов
    tried_count = await db.fetchval("""
        SELECT COUNT(DISTINCT oi.product_id) 
        FROM order_items oi 
        JOIN orders o ON oi.order_id = o.order_id 
        WHERE o.telegram_id = $1 AND o.status IN ('completed', 'delivery')
    """, user_id) or 0
    
    # Дни с регистрации
    days_since_reg = await db.fetchval("""
        SELECT EXTRACT(EPOCH FROM (NOW() - created_at)) / 86400 
        FROM users 
        WHERE telegram_id = $1
    """, user_id) or 0
    days_since_reg = int(days_since_reg)
    
    # Приглашено друзей
    friends_invited = await db.fetchval("""
        SELECT COUNT(*) 
        FROM users 
        WHERE referred_by = $1
    """, user_id) or 0
    
    # Получено евро с друзей
    earned_from_friends = await db.fetchval("""
        SELECT COALESCE(SUM(discount_amount), 0) 
        FROM referral_discounts 
        WHERE referrer_telegram_id = $1
    """, user_id) or 0
    earned_from_friends = float(earned_from_friends)
    
    # Формируем текст профиля
    try:
        await callback.message.edit_text(
            text=texts.get_profile_text(
        favorite_product,
        tried_count,
        days_since_reg,
        friends_invited,
        earned_from_friends),
            reply_markup=guest.profile_menu_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()
    except Exception:
        try:
            await callback.message.delete()
        except:
            pass
        
        await callback.message.answer(
            text=texts.get_profile_text(
        favorite_product,
        tried_count,
        days_since_reg,
        friends_invited,
        earned_from_friends),
            reply_markup=guest.profile_menu_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()

@router.callback_query(F.data == "active_orders")
async def active_orders_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    # Получаем актуальные заказы пользователя (pending, accepted, delivered)
    orders = await db.fetch("""
        SELECT order_id, status, final_amount, created_at
        FROM orders
        WHERE telegram_id = $1 AND status IN ('pending', 'accepted', 'delivered')
        ORDER BY created_at DESC
        LIMIT 10
    """, user_id)
    
    if not orders:
        text = "📦 У вас нет актуальных заказов."
    else:
        text = "📦 *Ваши актуальные заказы:*\n\n"
        for order in orders:
            status_text = {
                'pending': '⏳ Ожидает подтверждения',
                'accepted': '✅ Подтвержден',
                'delivered': '🚚 Доставлен'
            }.get(order['status'], order['status'])
            created_at = order['created_at'].strftime("%d.%m.%Y %H:%M")
            text += f"🆔 {order['order_id']} | {status_text} | 💰 {order['final_amount']}€ | 📅 {created_at}\n"
    
    await callback.message.edit_text(
        text=text,
        reply_markup=guest.profile_menu_keyboard(), parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()

@router.callback_query(F.data == "invite")
async def invite_menu(callback: types.CallbackQuery):
    # Генерируем реферальную ссылку
    ref_link = f"https://t.me/{USERNAME}?start=ref_{callback.from_user.id}"
    
    # Получаем сумму реферальных бонусов
    referral_bonus = await db.fetchval("""
        SELECT COALESCE(SUM(discount_amount), 0)
        FROM referral_discounts
        WHERE referrer_telegram_id = $1
    """, callback.from_user.id)
    referral_bonus = float(referral_bonus) if referral_bonus else 0.0
    
    
    await callback.message.edit_text(
        text=texts.get_referral_text(ref_link, referral_bonus),
        reply_markup=guest.invite_menu_keyboard(), parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()

@router.callback_query(F.data == "pay_questions")
async def pay_questions_menu(callback: types.CallbackQuery):
    await callback.message.edit_text(
        text=texts.payment_text,
        reply_markup=guest.help_menu_keyboard(), parse_mode=ParseMode.MARKDOWN
        
    )
    await callback.answer()

@router.callback_query(F.data == "delivery")
async def delivery_questions_menu(callback: types.CallbackQuery):
    await callback.message.edit_text(
        text=texts.delivery_text,
        reply_markup=guest.help_menu_keyboard(), parse_mode=ParseMode.MARKDOWN
        
    )
    await callback.answer()

@router.callback_query(F.data == "contact_support")
async def contact_support_menu(callback: types.CallbackQuery):
    await callback.message.edit_text(
        text=texts.contact_text,
        reply_markup=guest.help_menu_keyboard(), parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()

# Depricated!
#Не используется

@router.callback_query(F.data == "brands")
async def brands_menu(callback: types.CallbackQuery):
    await callback.message.edit_text(
        text="Explore products from HQD and other brands.",
        reply_markup=guest.catalogue_menu_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "promo_choice")
async def promo_choice_menu(callback: types.CallbackQuery):
    await callback.message.edit_text(
        text="Here are the products currently on promotion!",
        reply_markup=guest.catalogue_menu_keyboard()
    )
    await callback.answer()

