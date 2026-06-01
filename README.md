# Telegram Commerce CRM Bot

Production-used Telegram commerce and CRM bot built for a local business.

This project was developed as a real Telegram-based shop and lightweight CRM system for a local business with an active customer base of around 200–300 people. The bot helped automate product sales, order management, promo codes, referrals, customer communication, delivery flow, and admin operations directly inside Telegram.

The system included a customer-facing Telegram bot, admin commands, PostgreSQL storage, and a Flask-based web admin panel for visual order and user management.

## Key Features

### Customer Side

* Product catalog with photos and descriptions
* Shopping cart with quantity management
* Promo codes and discount system
* Referral rewards program
* Free delivery rules based on order size
* Delivery by address or geolocation
* Order status tracking
* Customer notifications
* User bonus balance and referral history

### Admin Side

* Flask-based web admin panel
* User management
* Order management and status updates
* Product and stock management
* Promo code creation and management
* Broadcast messages and notifications
* Basic statistics and analytics
* Telegram admin commands for fast order handling

## CRM and Business Logic

The bot was designed to reduce manual work for the business and give admins a structured way to manage customers and orders.

Core business logic included:

* Customer profiles
* Order history
* Referral tracking
* Promo code usage tracking
* Product stock management
* Broadcast campaigns
* Admin notifications for new orders
* Order lifecycle management from creation to delivery confirmation
* Delivery flow by address or geolocation
* Bonus and referral reward accounting

## Tech Stack

* Python
* Aiogram 3.x
* Flask
* PostgreSQL
* asyncpg
* Bootstrap 5
* Docker / docker-compose
* systemd deployment setup

## Architecture Overview

The project is split into several main parts:

* `bot.py` — Telegram bot entry point
* `start.py` — combined bot and admin panel startup
* `admin_app.py` — Flask-based admin panel
* `handlers/` — user, admin, order, promo, catalog, and delivery flows
* `keyboards/` — Telegram inline and reply keyboards
* `database/` — PostgreSQL access layer
* `schema.sql` — database schema
* `templates/` — admin panel UI templates
* `notifications.py` — notification and broadcast logic
* `docker-compose.yml` — local deployment configuration

## Why I Built It

I built this project for a real local-business workflow where order handling, customer communication, discounts, referrals, and delivery coordination were being managed manually.
The goal was to create a lightweight commerce system inside Telegram, where customers could place orders easily and admins could manage the business without switching between multiple tools.
This project gave me practical experience with production-style product development: building for real users, handling business requirements, designing admin workflows, working with databases, and improving the system based on actual usage.

## What I Learned

* Building Telegram bots with Aiogram 3.x
* Designing multi-step user flows for real customers
* Managing shopping cart and order state
* Building admin workflows for order processing
* Working with PostgreSQL and asyncpg
* Creating a lightweight Flask admin panel
* Designing promo code and referral systems
* Structuring notifications and broadcasts
* Preparing a bot for VPS/systemd deployment
* Balancing quick business needs with maintainable backend structure

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/unchangedfeatures/telegram-commerce-crm-bot.git
cd telegram-commerce-crm-bot
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure PostgreSQL

```sql
CREATE DATABASE telegram_crm;
CREATE USER telegram_crm_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE telegram_crm TO telegram_crm_user;
```

Import the schema:

```bash
psql -U telegram_crm_user -d telegram_crm < schema.sql
```

### 4. Configure environment variables

Create a `.env` file in the project root:

```env
TOKEN=your_telegram_bot_token
ADMIN_ID=your_telegram_admin_id
CHAT_ID=@your_channel_username
USERNAME=your_bot_username
SUPPORT=support_username

DB_HOST=localhost
DB_PORT=5432
DB_NAME=telegram_crm
DB_USER=telegram_crm_user
DB_PASSWORD=your_secure_password
```

### 5. Run the bot

```bash
python bot.py
```

### 6. Run the admin panel

```bash
python admin_app.py
```

### 7. Run bot and admin panel together

```bash
python start.py
```

## Main User Commands

```text
/start
/orders
/promo <code>
```

## Main Admin Commands

```text
/pending_orders
/look_order <id>
/accept <id>
/decline <id>
/deliver <id> <minutes>
/confirm <id>
/stats
/stock
/notify <id> <message>
/broadcast <message>
/createpromo
```

## Production Notes

The project was designed for a real Telegram-based local business and was used with an active customer base.

## Security Notes

* Do not commit `.env` files or bot tokens
* Change default admin credentials before deployment
* Use strong database passwords
* Use HTTPS in production
* Restrict database access with firewall rules
* Rotate bot tokens if they were exposed
* Remove or anonymize real customer data before publishing
* Keep backups of the PostgreSQL database

## Future Improvements

* Add payment provider integration
* Add courier role and delivery assignment flow
* Improve the web admin panel UI
* Add automated tests for order and promo logic
* Add database migrations
* Add analytics dashboard
* Add Docker-first local setup
* Add CI checks
* Improve role-based access control
* Add screenshots and demo GIFs

## Credits

* Aiogram — Telegram bot framework
* Flask — web admin panel
* PostgreSQL — database layer
