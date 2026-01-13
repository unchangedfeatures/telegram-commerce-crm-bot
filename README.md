# 🔥 PewPuff Bot

Telegram-бот для продажи товаров без интеграций с оплатой, с веб-панелью администратора.

## 📋 Возможности

### Для пользователей:
- 🛒 Каталог товаров с фото и описанием
- 🛍️ Корзина с управлением количеством
- 🎁 Система промокодов и скидок
- 👥 Реферальная программа (2€ за друга, 0.5€ за внука-реферала)
- 🚚 Бесплатная доставка от 4 товаров
- 📍 Доставка по геолокации или адресу
- 📦 Отслеживание заказов
- 💰 Реферальные бонусы

### Для администраторов:
- 📊 Веб-панель управления (Flask, рекомендуется только для визуального просмотра, остальное советую выполнять командами в самом боте!)
- 👥 Управление пользователями
- 📦 Управление заказами (статусы, уведомления)
- 🎫 Создание и управление промокодами
- 📦 Управление товарами и остатками
- 📢 Рассылки и уведомления
- 📈 Статистика и аналитика

## 🛠️ Технологии

- **Aiogram 3.x** - Telegram Bot API
- **Flask** - Веб-панель администратора
- **PostgreSQL** - База данных
- **asyncpg** - Асинхронный драйвер PostgreSQL
- **Bootstrap 5** - UI веб-панели

## 📦 Установка

### 1. Клонирование репозитория

```bash
git clone https://github.com/unchangedfeatures/pewpuff-bot.git
cd pewpuff-bot
```

### 2. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 3. Настройка PostgreSQL

#### Установка PostgreSQL:

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
```

**macOS:**
```bash
brew install postgresql
brew services start postgresql
```

**Windows:**
Скачайте установщик с [postgresql.org](https://www.postgresql.org/download/windows/)

#### Создание базы данных:

```bash
# Подключение к PostgreSQL
sudo -u postgres psql

# В консоли PostgreSQL выполните:
CREATE DATABASE pewpuff;
CREATE USER pewpuff_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE pewpuff TO pewpuff_user;

# Выход
\q
```

#### Создание таблиц:

```sql
-- Подключитесь к БД
psql -U pewpuff_user -d pewpuff

-- Скопируйте и выполните SQL из файла schema.sql

-- Или импортируйте файл напрямую:
psql -U pewpuff_user -d pewpuff < schema.sql
```

### 4. Настройка переменных окружения

Создайте файл `.env` в корне проекта:

```env
# Telegram Bot
TOKEN=your_telegram_bot_token
ADMIN_ID=your_telegram_admin_id
CHAT_ID=@your_channel_username
USERNAME=your_bot_username
SUPPORT=support_username

# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=pewpuff
DB_USER=pewpuff_user
DB_PASSWORD=your_secure_password
```

**Получение токена бота:**
1. Напишите [@BotFather](https://t.me/BotFather) в Telegram
2. Отправьте `/newbot`
3. Следуйте инструкциям
4. Скопируйте полученный токен

### 5. Обновление config.py

Отредактируйте `database/database.py`, заменив хардкод на переменные окружения:

```python
import os
from dotenv import load_dotenv

load_dotenv()

pool = await asyncpg.create_pool(
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME"),
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT")),
    # ... остальные параметры
)
```

## 🚀 Запуск

### Режим разработки:

```bash
# Только бот
python bot.py

# Только веб-панель
python admin_app.py

# Бот + веб-панель одновременно
python start.py
```

### Production (systemd):

Создайте файл `/etc/systemd/system/pewpuff.service`:

```ini
[Unit]
Description=PewPuff Bot
After=network.target postgresql.service

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/pewpuff-bot
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/python start.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Запуск:
```bash
sudo systemctl daemon-reload
sudo systemctl enable pewpuff
sudo systemctl start pewpuff
sudo systemctl status pewpuff
```

## 🔧 Конфигурация

### Веб-панель

По умолчанию доступна на `http://localhost:5000`

**Учетные данные по умолчанию:**
- Логин: `admin`
- Пароль: `pewpuff_admin`

⚠️ **ВАЖНО:** Измените пароль в `admin_app.py`:

```python
ADMIN_PASSWORD_HASH = generate_password_hash("your_new_password")
```

### Telegram канал

Создайте канал и добавьте бота как администратора:
1. Создайте канал в Telegram
2. Добавьте бота в администраторы
3. Укажите `@channel_username` в `.env` (переменная `CHAT_ID`)

## 🎯 Основные команды

### Для пользователей:
- `/start` - Запуск бота
- `/orders` - Мои заказы
- `/promo <код>` - Активировать промокод

### Для администраторов:
- `/accept <id>` - Принять заказ
- `/decline <id>` - Отклонить заказ
- `/deliver <id> <минуты>` - Отправить в доставку
- `/confirm <id>` - Подтвердить получение
- `/look_order <id>` - Информация о заказе
- `/pending_orders` - Активные заказы
- `/stats` - Статистика
- `/stock` - Управление остатками
- `/notify <id> <текст>` - Уведомление пользователю
- `/broadcast <текст>` - Рассылка всем
- `/createpromo` - Создать промокод

## 🔐 Безопасность

- ✅ Не храните `.env` и `config.py` в Git
- ✅ Используйте сильные пароли для БД
- ✅ Измените пароль админ-панели
- ✅ Используйте HTTPS в production
- ✅ Настройте firewall для БД
- ✅ Регулярно делайте бэкапы

## 📊 SQL Schema

<details>
<summary>Развернуть SQL схему</summary>

```sql
-- Users
CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    phone VARCHAR(20),
    address TEXT,
    referred_by BIGINT,
    role VARCHAR(20) DEFAULT 'user',
    is_subscribed BOOLEAN DEFAULT FALSE,
    total_orders INT DEFAULT 0,
    total_spent DECIMAL(10, 2) DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Products
CREATE TABLE products (
    product_id SERIAL PRIMARY KEY,
    brand_id INT,
    product_name VARCHAR(255) NOT NULL,
    price DECIMAL(10, 2) DEFAULT 0,
    stock_quantity INT DEFAULT 0,
    description TEXT,
    image_url TEXT,
    times_chosen INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Orders
CREATE TABLE orders (
    order_id SERIAL PRIMARY KEY,
    telegram_id BIGINT REFERENCES users(telegram_id),
    total_amount DECIMAL(10, 2),
    discount_amount DECIMAL(10, 2) DEFAULT 0,
    final_amount DECIMAL(10, 2),
    status VARCHAR(50) DEFAULT 'pending',
    payment_status VARCHAR(50) DEFAULT 'pending',
    delivery_address TEXT,
    promo_code_used VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Order Items
CREATE TABLE order_items (
    order_item_id SERIAL PRIMARY KEY,
    order_id INT REFERENCES orders(order_id) ON DELETE CASCADE,
    product_id INT REFERENCES products(product_id),
    quantity INT NOT NULL,
    unit_price DECIMAL(10, 2),
    total_price DECIMAL(10, 2),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Promo Codes
CREATE TABLE promo_codes (
    promo_id SERIAL PRIMARY KEY,
    code VARCHAR(100) UNIQUE NOT NULL,
    discount_percent DECIMAL(5, 2),
    discount_amount DECIMAL(10, 2),
    min_order_amount DECIMAL(10, 2) DEFAULT 0,
    max_uses INT DEFAULT 0,
    current_uses INT DEFAULT 0,
    expires_at TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Referral Discounts
CREATE TABLE referral_discounts (
    referral_discount_id SERIAL PRIMARY KEY,
    order_id INT REFERENCES orders(order_id),
    referrer_telegram_id BIGINT,
    referred_telegram_id BIGINT,
    discount_amount DECIMAL(10, 2) DEFAULT 2.00,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Cart
CREATE TABLE cart (
    cart_id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE,
    items_json TEXT,
    applied_discounts TEXT,
    delivery_discount_applied BOOLEAN DEFAULT FALSE,
    last_updated TIMESTAMP DEFAULT NOW()
);
```
</details>

## 🐛 Troubleshooting

### Бот не отвечает
- Проверьте токен в `.env`
- Убедитесь, что бот запущен: `systemctl status pewpuff`
- Проверьте логи: `journalctl -u pewpuff -f`

### Ошибки БД
- Проверьте подключение: `psql -U pewpuff_user -d pewpuff`
- Убедитесь, что PostgreSQL запущен: `systemctl status postgresql`
- Проверьте пароль в `.env`

### Веб-панель не открывается
- Проверьте, что Flask запущен на порту 5000
- Откройте порт в firewall: `sudo ufw allow 5000`

## 📝 Лицензия

MIT License - используйте как хотите!

## 🤝 Контакты

- Telegram: [@forge_spirit](https://t.me/forge_spirit) / Пожалуйста, только без жалоб на неработающий код <3

## 🙏 Благодарности

- [Aiogram](https://github.com/aiogram/aiogram) - отличная библиотека для Telegram ботов
- [Flask](https://flask.palletsprojects.com/) - микрофреймворк для веб-панели
- [Claude](https://claude.ai) - за сервер

---
