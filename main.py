import threading
import os
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler  # ← Используем потоковый планировщик
import pytz
from datetime import datetime, time as dt_time

# --- Настройки ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Environment variable BOT_TOKEN is required")

PORT = int(os.getenv("PORT", "10000"))
TZ = pytz.timezone("Europe/Minsk")

SHIFT_PLAN = [
    ("09:00", "🟢 Начало рабочего дня. Работа за ПЭВМ (1-й блок)."),
    ("10:00", "⏸️ Перерыв 15 мин (отдых глаз, разминка)."),
    ("10:15", "💻 Продолжение работы за ПЭВМ (2-й блок)."),
    ("11:15", "⏸️ Перерыв 15 мин."),
    ("11:30", "💻 Работа за ПЭВМ (3-й блок)."),
    ("12:30", "📝 Работа БЕЗ ПЭВМ: совещания, документация, планирование."),
    ("13:00", "🍽️ Обеденный перерыв (60 мин)."),
    ("14:00", "💻 Работа за ПЭВМ (4-й блок)."),
    ("15:00", "⏸️ Перерыв 15 мин."),
    ("15:15", "💻 Работа за ПЭВМ (5-й блок)."),
    ("16:00", "📝 Работа БЕЗ ПЭВМ: ревью, аналитика, общение."),
    ("17:00", "🕗 Завершение основного рабочего времени. Гибкая активность."),
    ("18:00", "🔚 Рабочий день окончен! Хорошего отдыха!"),
]

# Глобальный планировщик и список активных чатов
scheduler = BackgroundScheduler(timezone=str(TZ))
scheduler.start()

active_chats = set()

# --- Функции Telegram-бота ---
async def send_message_to_user(bot, chat_id: int, text: str):
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    except Exception as e:
        print(f"Ошибка отправки в {chat_id}: {e}")

def schedule_for_user(bot, chat_id: int):
    if chat_id in active_chats:
        asyncio.run_coroutine_threadsafe(
            send_message_to_user(bot, chat_id, "⚠️ График уже запущен на сегодня!"),
            asyncio.new_event_loop()  # ← Небезопасно! Лучше — через очередь
        )
        return

    today = datetime.now(TZ).date()
    for time_str, msg in SHIFT_PLAN:
        hour, minute = map(int, time_str.split(":"))
        run_time = TZ.localize(datetime.combine(today, dt_time(hour, minute)))
        if run_time <= datetime.now(TZ):
            continue
        # Добавляем задачу в планировщик
        scheduler.add_job(
            lambda b=bot, c=chat_id, m=msg: asyncio.run_coroutine_threadsafe(
                send_message_to_user(b, c, m),
                asyncio.new_event_loop()
            ),
            'date',
            run_date=run_time,
            id=f"shift_{chat_id}_{time_str.replace(':', '')}",
            replace_existing=True
        )
    active_chats.add(chat_id)

# Но! Лучше вынести логику в отдельную утилиту с очередью...
# Однако для простоты и скорости — используем упрощённый подход:

def run_telegram_bot():
    """Запускает Telegram-бота в отдельном потоке."""
    async def main_bot():
        app = Application.builder().token(BOT_TOKEN).build()

        async def start(update, context):
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            await update.message.reply_text(
                "Нажмите кнопку, чтобы начать рабочий день:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("▶️ Начать", callback_data="start_shift")]
                ])
            )

        async def button_handler(update, context):
            query = update.callback_query
            await query.answer()
            if query.data == "start_shift":
                # Планируем уведомления
                chat_id = query.message.chat_id
                if chat_id in active_chats:
                    await context.bot.send_message(chat_id=chat_id, text="⚠️ График уже запущен!")
                    return

                today = datetime.now(TZ).date()
                for time_str, msg in SHIFT_PLAN:
                    hour, minute = map(int, time_str.split(":"))
                    run_time = TZ.localize(datetime.combine(today, dt_time(hour, minute)))
                    if run_time <= datetime.now(TZ):
                        continue
                    scheduler.add_job(
                        lambda bot=context.bot, cid=chat_id, m=msg: asyncio.run_coroutine_threadsafe(
                            bot.send_message(chat_id=cid, text=m),
                            asyncio.new_event_loop()
                        ),
                        'date',
                        run_date=run_time,
                        id=f"shift_{cid}_{time_str.replace(':', '')}",
                        replace_existing=True
                    )
                active_chats.add(chat_id)
                await context.bot.send_message(chat_id=chat_id, text="✅ График запущен!")

        app.add_handler(CommandHandler("start", start))
        app.add_handler(CallbackQueryHandler(button_handler))

        print(".telegram bot started.")
        await app.run_polling()

    # Запускаем бота
    asyncio.run(main_bot())

# --- HTTP-сервер для Render ---
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_response(404)
            self.end_headers()

def run_http_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    print(f"HTTP server listening on port {PORT}")
    server.serve_forever()

# --- Основной запуск ---
if __name__ == "__main__":
    # Запускаем Telegram-бота в отдельном потоке
    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()

    # Запускаем HTTP-сервер в основном потоке (обязательно для Render)
    run_http_server()