-- ParXpress Database Schema
-- Initialize all tables

-- Users
CREATE TABLE IF NOT EXISTS users (
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
CREATE TABLE IF NOT EXISTS products (
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
CREATE TABLE IF NOT EXISTS orders (
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
CREATE TABLE IF NOT EXISTS order_items (
    order_item_id SERIAL PRIMARY KEY,
    order_id INT REFERENCES orders(order_id) ON DELETE CASCADE,
    product_id INT REFERENCES products(product_id),
    quantity INT NOT NULL,
    unit_price DECIMAL(10, 2),
    total_price DECIMAL(10, 2),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Promo Codes
CREATE TABLE IF NOT EXISTS promo_codes (
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
CREATE TABLE IF NOT EXISTS referral_discounts (
    referral_discount_id SERIAL PRIMARY KEY,
    order_id INT REFERENCES orders(order_id),
    referrer_telegram_id BIGINT,
    referred_telegram_id BIGINT,
    discount_amount DECIMAL(10, 2) DEFAULT 2.00,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Cart
CREATE TABLE IF NOT EXISTS cart (
    cart_id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE,
    items_json TEXT,
    applied_discounts TEXT,
    delivery_discount_applied BOOLEAN DEFAULT FALSE,
    last_updated TIMESTAMP DEFAULT NOW()
);

-- Broadcast Jobs (for notifications)
CREATE TABLE IF NOT EXISTS broadcast_jobs (
    job_id SERIAL PRIMARY KEY,
    job_name VARCHAR(255),
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Grant permissions to parxpress_user
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO parxpress_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO parxpress_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO parxpress_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO parxpress_user;
