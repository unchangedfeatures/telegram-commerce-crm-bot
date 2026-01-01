import asyncio
import threading
import logging
from bot import main as bot_main
from admin_app import app, init_async

logging.basicConfig(level=logging.INFO)

def run_flask():
    """Запуск Flask в отдельном потоке"""
    init_async()  # Инициализация async компонентов для Flask
    app.run(debug=False, host='0.0.0.0', port=5000, threaded=True, use_reloader=False)

def run_bot():
    """Запуск бота"""
    asyncio.run(bot_main())

if __name__ == "__main__":
    print("🚀 Запуск системы...")
    
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    print("✅ Flask сервер запущен на http://localhost:5000")
    print("🤖 Запуск бота...")
    
    # Запускаем бота в основном потоке
    try:
        run_bot()
    except KeyboardInterrupt:\
        print("\n👋 Остановка системы...")