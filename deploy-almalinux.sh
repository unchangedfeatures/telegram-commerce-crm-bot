#!/bin/bash
# ============================================================
# ParXpress - AlmaLinux 10 (микро-VPS) Автоматическое развертывание
# Оптимизировано для: 0.5 vCores, 1GB RAM, 5GB SSD
# ============================================================

set -e  # Выход при ошибке

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Конфигурация
APP_USER="parxpress"
APP_DIR="/home/parxpress/app"
VENV_DIR="$APP_DIR/venv"
DB_NAME="parxpress_db"
DB_USER="parxpress"
DB_PASS=$(openssl rand -base64 32)
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

# Функции
print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_error() { echo -e "${RED}✗ $1${NC}"; }
print_info() { echo -e "${YELLOW}ℹ $1${NC}"; }

# ============================================================
# ЭТАП 1: Проверка системы
# ============================================================
print_info "ЭТАП 1: Проверка системы"

if [ "$EUID" -ne 0 ]; then
   print_error "Скрипт должен быть запущен от root (используйте: sudo bash deploy.sh)"
   exit 1
fi

if ! command -v dnf &> /dev/null; then
    print_error "dnf не найден. Это не AlmaLinux/CentOS/RHEL!"
    exit 1
fi

print_success "Система совместима"

# ============================================================
# ЭТАП 2: Обновление системы
# ============================================================
print_info "ЭТАП 2: Обновление системы (это может занять время...)"

dnf update -y > /dev/null 2>&1 || print_error "Ошибка при обновлении"

# Установка базовых инструментов
dnf install -y \
    wget curl git htop nano gcc \
    python3 python3-pip python3-devel \
    postgresql-server postgresql-contrib \
    nginx \
    certbot python3-certbot-nginx \
    fail2ban \
    > /dev/null 2>&1

print_success "Система обновлена и инструменты установлены"

# ============================================================
# ЭТАП 3: Создание пользователя приложения
# ============================================================
print_info "ЭТАП 3: Создание пользователя приложения"

if id "$APP_USER" &>/dev/null; then
    print_info "Пользователь $APP_USER уже существует"
else
    useradd -m -s /bin/bash $APP_USER
    echo "$APP_USER:ParXpress123!" | chpasswd
    usermod -aG wheel $APP_USER
    print_success "Пользователь $APP_USER создан"
fi

# ============================================================
# ЭТАП 4: Подготовка директории приложения
# ============================================================
print_info "ЭТАП 4: Подготовка директории приложения"

mkdir -p $APP_DIR
chown -R $APP_USER:$APP_USER /home/parxpress
chmod 755 /home/parxpress

# Виртуальное окружение
sudo -u $APP_USER python3 -m venv $VENV_DIR > /dev/null 2>&1
print_success "Виртуальное окружение создано"

# Обновление pip
sudo -u $APP_USER $VENV_DIR/bin/pip install --upgrade pip setuptools wheel > /dev/null 2>&1
print_success "Pip обновлен"

# ============================================================
# ЭТАП 5: Установка Python зависимостей
# ============================================================
print_info "ЭТАП 5: Установка Python зависимостей"

# Установка Gunicorn и psycopg2
sudo -u $APP_USER $VENV_DIR/bin/pip install \
    gunicorn==21.2.0 \
    psycopg2-binary \
    python-dotenv \
    > /dev/null 2>&1

print_success "Gunicorn и зависимости БД установлены"

# ============================================================
# ЭТАП 6: Инициализация PostgreSQL
# ============================================================
print_info "ЭТАП 6: Инициализация PostgreSQL (микро-VPS оптимизация)"

if [ ! -d "/var/lib/pgsql/data" ] || [ -z "$(ls -A /var/lib/pgsql/data 2>/dev/null)" ]; then
    /usr/bin/postgresql-setup initdb > /dev/null 2>&1
    print_success "PostgreSQL инициализирована"
fi

systemctl start postgresql
systemctl enable postgresql
print_success "PostgreSQL запущена"

# Оптимизация для микро-VPS
cat > /tmp/pg_optimize.conf << 'EOF'
# Оптимизация для 1GB RAM микро-VPS
shared_buffers = 64MB
effective_cache_size = 256MB
maintenance_work_mem = 16MB
work_mem = 1MB
max_connections = 20
EOF

# Применение оптимизации
sed -i '/^shared_buffers/d' /var/lib/pgsql/data/postgresql.conf
sed -i '/^effective_cache_size/d' /var/lib/pgsql/data/postgresql.conf
sed -i '/^maintenance_work_mem/d' /var/lib/pgsql/data/postgresql.conf
sed -i '/^work_mem/d' /var/lib/pgsql/data/postgresql.conf
sed -i '/^max_connections/d' /var/lib/pgsql/data/postgresql.conf

cat /tmp/pg_optimize.conf >> /var/lib/pgsql/data/postgresql.conf
systemctl restart postgresql

print_success "PostgreSQL оптимизирована для микро-VPS"

# ============================================================
# ЭТАП 7: Создание базы данных
# ============================================================
print_info "ЭТАП 7: Создание базы данных"

sudo -u postgres psql << EOF > /dev/null 2>&1 || print_error "Ошибка при создании БД"
CREATE DATABASE $DB_NAME;
CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';
ALTER ROLE $DB_USER SET client_encoding TO 'utf8';
ALTER ROLE $DB_USER SET default_transaction_isolation TO 'read committed';
ALTER ROLE $DB_USER SET default_transaction_deferrable TO on;
ALTER ROLE $DB_USER SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;
EOF

print_success "База данных $DB_NAME создана"
print_info "Пароль БД: $DB_PASS"

# ============================================================
# ЭТАП 8: Создание файла .env
# ============================================================
print_info "ЭТАП 8: Создание файла конфигурации .env"

cat > $APP_DIR/.env << EOF
# Database
DATABASE_URL=postgresql://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME

# Flask
FLASK_ENV=production
FLASK_DEBUG=False
SECRET_KEY=$SECRET_KEY

# Admin credentials
ADMIN_USERNAME=admin
ADMIN_PASSWORD=$(openssl rand -base64 12)

# Telegram (заполните вручную!)
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
ADMIN_ID=your_admin_id

# Logging
LOG_LEVEL=INFO
EOF

chmod 600 $APP_DIR/.env
chown $APP_USER:$APP_USER $APP_DIR/.env

print_success ".env файл создан"
print_info "Отредактируйте $APP_DIR/.env для добавления Telegram параметров"

# ============================================================
# ЭТАП 9: Создание systemd сервисов
# ============================================================
print_info "ЭТАП 9: Создание systemd сервисов"

mkdir -p /var/log/parxpress
chown $APP_USER:$APP_USER /var/log/parxpress

# Веб-сервис
cat > /etc/systemd/system/parxpress-web.service << EOF
[Unit]
Description=ParXpress Flask Web Application
After=network.target postgresql.service

[Service]
Type=notify
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
Environment="PATH=$VENV_DIR/bin"
ExecStart=$VENV_DIR/bin/gunicorn \\
    --workers=1 \\
    --worker-class=sync \\
    --bind=127.0.0.1:5000 \\
    --timeout=60 \\
    --access-logfile=/var/log/parxpress/access.log \\
    --error-logfile=/var/log/parxpress/error.log \\
    admin_app:app

MemoryLimit=256M
CPUQuota=50%
Restart=on-failure
RestartSec=5s
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Бот-сервис
cat > /etc/systemd/system/parxpress-bot.service << EOF
[Unit]
Description=ParXpress Telegram Bot
After=network.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
Environment="PATH=$VENV_DIR/bin"
ExecStart=$VENV_DIR/bin/python3 bot.py

MemoryLimit=256M
Restart=on-failure
RestartSec=5s
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable parxpress-web.service
systemctl enable parxpress-bot.service

print_success "Systemd сервисы созданы"

# ============================================================
# ЭТАП 10: Конфигурация Nginx
# ============================================================
print_info "ЭТАП 10: Конфигурация Nginx"

cat > /etc/nginx/conf.d/parxpress.conf << 'EOF'
# Оптимизация для микро-VPS
upstream app {
    server 127.0.0.1:5000 fail_timeout=0;
}

proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=static_cache:10m max_size=100m inactive=60d use_temp_path=off;

server {
    listen 80 default_server;
    server_name _;
    client_max_body_size 10M;
    
    access_log /var/log/nginx/parxpress_access.log;
    error_log /var/log/nginx/parxpress_error.log;
    
    gzip on;
    gzip_types text/plain text/css text/javascript application/json;
    gzip_min_length 1000;
    
    location /static/ {
        alias /home/parxpress/app/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
        proxy_cache static_cache;
        proxy_cache_valid 200 30d;
    }
    
    location / {
        proxy_pass http://app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    location /health {
        proxy_pass http://app;
        access_log off;
    }
}
EOF

nginx -t > /dev/null 2>&1 && print_success "Конфигурация Nginx корректна" || print_error "Ошибка в конфигурации Nginx"

systemctl enable nginx
systemctl start nginx

print_success "Nginx настроена и запущена"

# ============================================================
# ЭТАП 11: Firewall настройка
# ============================================================
print_info "ЭТАП 11: Настройка firewall (firewalld)"

systemctl enable firewalld
systemctl start firewalld

firewall-cmd --permanent --add-service=http > /dev/null 2>&1
firewall-cmd --permanent --add-service=https > /dev/null 2>&1
firewall-cmd --permanent --add-port=22/tcp > /dev/null 2>&1
firewall-cmd --reload > /dev/null 2>&1

print_success "Firewall настроена"

# ============================================================
# ЭТАП 12: Fail2ban для защиты
# ============================================================
print_info "ЭТАП 12: Установка Fail2ban (защита от атак)"

systemctl enable fail2ban
systemctl start fail2ban

print_success "Fail2ban активирован"

# ============================================================
# ЭТАП 13: Создание скрипта мониторинга
# ============================================================
print_info "ЭТАП 13: Создание скрипта здоровья приложения"

cat > /usr/local/bin/parxpress-health-check.sh << 'EOF'
#!/bin/bash
LOG_FILE="/var/log/parxpress/health-check.log"

HEALTH=$(curl -s http://localhost:5000/health 2>/dev/null)
if [[ $HEALTH == *"healthy"* ]]; then
    echo "[$(date)] Web: OK" >> $LOG_FILE
else
    echo "[$(date)] Web: FAILED - Restart" >> $LOG_FILE
    systemctl restart parxpress-web.service
fi

MEMORY_USAGE=$(free | grep Mem | awk '{print int($3/$2 * 100)}')
echo "[$(date)] Memory: ${MEMORY_USAGE}%" >> $LOG_FILE

if [ $MEMORY_USAGE -gt 90 ]; then
    echo "[$(date)] CRITICAL: Memory at ${MEMORY_USAGE}%" >> $LOG_FILE
fi

DISK_USAGE=$(df / | tail -1 | awk '{print int($3/$2 * 100)}')
echo "[$(date)] Disk: ${DISK_USAGE}%" >> $LOG_FILE

if [ $DISK_USAGE -gt 85 ]; then
    echo "[$(date)] CRITICAL: Disk at ${DISK_USAGE}%" >> $LOG_FILE
fi
EOF

chmod +x /usr/local/bin/parxpress-health-check.sh

# Добавляем в cron
(crontab -l 2>/dev/null || echo "") | grep -v "parxpress-health-check" > /tmp/cron_new
echo "*/5 * * * * /usr/local/bin/parxpress-health-check.sh" >> /tmp/cron_new
crontab /tmp/cron_new

print_success "Скрипт мониторинга установлен"

# ============================================================
# ЭТАП 14: Финальные проверки
# ============================================================
print_info "ЭТАП 14: Финальные проверки"

sleep 2

# Проверяем сервисы
if systemctl is-active --quiet postgresql; then
    print_success "PostgreSQL работает"
else
    print_error "PostgreSQL не запущена!"
fi

if systemctl is-active --quiet nginx; then
    print_success "Nginx работает"
else
    print_error "Nginx не запущена!"
fi

# Проверяем Flask (может быть не активен сразу)
print_info "Стартуем веб-приложение..."
systemctl start parxpress-web.service
sleep 3

# ============================================================
# ФИНАЛЬНЫЙ ОТЧЕТ
# ============================================================
echo ""
echo "================================================================"
echo -e "${GREEN}✓ РАЗВЕРТЫВАНИЕ ЗАВЕРШЕНО!${NC}"
echo "================================================================"
echo ""
echo "📊 Информация о конфигурации:"
echo "  • Приложение: $APP_DIR"
echo "  • Пользователь: $APP_USER"
echo "  • БД: $DB_NAME @ localhost"
echo "  • Пароль БД: $DB_PASS"
echo ""
echo "🔐 Адреса доступа:"
echo "  • Веб-интерфейс: http://<your_vps_ip>/"
echo "  • Health check: http://<your_vps_ip>/health"
echo ""
echo "📝 Требуемые действия:"
echo "  1. Отредактируйте $APP_DIR/.env и добавьте Telegram параметры"
echo "  2. Перезагрузите бот: sudo systemctl restart parxpress-bot.service"
echo "  3. Проверьте логи: sudo journalctl -u parxpress-web -f"
echo ""
echo "📚 Полезные команды:"
echo "  • Статус: sudo systemctl status parxpress-web parxpress-bot"
echo "  • Логи веб: sudo tail -100 /var/log/parxpress/error.log"
echo "  • Логи бота: sudo journalctl -u parxpress-bot -f"
echo "  • Памяти: free -h"
echo "  • Диск: df -h"
echo ""
echo "📖 Для полной документации смотрите: ALMALINUX_DEPLOY_GUIDE.md"
echo "================================================================"
echo ""
