import threading
import os
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from apscheduler.schedulers.background import BackgroundScheduler
import pytz
from datetime import datetime, time as dt_time

# --- Настройки ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required")

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

scheduler = BackgroundScheduler(timezone=str(TZ))
scheduler.start()

active_chats = set()

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

    def log_message(self, format, *args):
        return

def run_http_server(port):
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"HTTP server listening on port {port}")
    server.serve_forever()

# Запускаем HTTP-сервер в фоне
http_thread = threading.Thread(target=run_http_server, args=(PORT,), daemon=True)
http_thread.start()

# --- Telegram-бот (ЗАПУСКАЕМ КОРРЕКТНО) ---
def send_message_safe(bot, chat_id: int, text: str):
    try:
        bot.send_message(chat_id=chat_id, text=text)
    except Exception as e:
        print(f"Ошибка отправки в {chat_id}: {e}")

def start(update, context):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    update.message.reply_text(
        "Нажмите кнопку, чтобы начать рабочий день:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("▶️ Начать", callback_data="start_shift")]
        ])
    )

def button_handler(update, context):
    query = update.callback_query
    query.answer()
    chat_id = query.message.chat_id

    if chat_id in active_chats:
        context.bot.send_message(chat_id=chat_id, text="⚠️ График уже запущен на сегодня!")
        return

    today = datetime.now(TZ).date()
    for time_str, msg in SHIFT_PLAN:
        hour, minute = map(int, time_str.split(":"))
        run_time = TZ.localize(datetime.combine(today, dt_time(hour, minute)))
        if run_time <= datetime.now(TZ):
            continue
        scheduler.add_job(
            send_message_safe,
            'date',
            run_date=run_time,
            args=[context.bot, chat_id, msg],
            id=f"shift_{chat_id}_{time_str.replace(':', '')}",
            replace_existing=True
        )
    active_chats.add(chat_id)
    context.bot.send_message(chat_id=chat_id, text="✅ График рабочего дня запущен!")

# Создаём и запускаем бота — НЕ в async-функции!
app = Application.builder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(button_handler))

print("Starting Telegram bot in main thread (blocking)...")
app.run_polling()  # ← БЛОКИРУЮЩИЙ ВЫЗОВ, НЕ КОРУТИНА!