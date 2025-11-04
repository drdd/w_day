import requests
import threading
import os
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
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
    ("13:11", "🍽️ Обеденный перерыв (30 мин)."),
    ("13:30", "💻 Работа за ПЭВМ (4-й блок)."),
    ("14:30", "⏸️ Перерыв 15 мин."),
    ("14:45", "💻 Работа за ПЭВМ (5-й блок)."),
    ("15:45", "📝 Работа БЕЗ ПЭВМ: ревью, аналитика, общение."),
    ("16:45", "🕗 Завершение основного рабочего времени. Гибкая активность."),
    ("17:30", "🔚 Рабочий день окончен! Хорошего отдыха!"),
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
    server.serve_forever()


# --- Помощники ---
def get_current_shift_status():
    now = datetime.now(TZ).time()
    current = "🕗 Не рабочее время"
    next_event = None
    for time_str, msg in SHIFT_PLAN:
        hour, minute = map(int, time_str.split(":"))
        event_time = dt_time(hour, minute)
        if event_time <= now:
            current = msg
        else:
            next_event = (time_str, msg)
            break
    return current, next_event


def send_scheduled_message(bot, chat_id, text):
    """Отправка через прямой HTTP-запрос к Telegram Bot API (синхронно, из любого потока)"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if not response.ok:
            print(f"Ошибка Telegram API: {response.text}")
    except Exception as e:
        print(f"Ошибка отправки: {e}")


# --- Асинхронные обработчики ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("▶️ Начать", callback_data="start_shift")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Нажмите кнопку, чтобы начать рабочий день:",
        reply_markup=reply_markup
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id

    if chat_id in active_chats:
        current, next_event = get_current_shift_status()
        response = f"✅ График уже запущен.\n\n🕗 Сейчас: **{current}**"
        if next_event:
            time_str, msg = next_event
            response += f"\n\n➡️ Следующее: **{msg}** в {time_str}"
        await context.bot.send_message(chat_id=chat_id, text=response, parse_mode="Markdown")
        return

    today = datetime.now(TZ).date()
    for time_str, msg in SHIFT_PLAN:
        hour, minute = map(int, time_str.split(":"))
        run_time = TZ.localize(datetime.combine(today, dt_time(hour, minute)))
        if run_time <= datetime.now(TZ):
            continue
        scheduler.add_job(
            send_scheduled_message,
            'date',
            run_date=run_time,
            args=[context.bot, chat_id, msg],
            id=f"shift_{chat_id}_{time_str.replace(':', '')}",
            replace_existing=True
        )
    active_chats.add(chat_id)
    await context.bot.send_message(chat_id=chat_id, text="✅ График рабочего дня запущен!")


# --- ЗАПУСК: именно так, без asyncio.run и без await ---
if __name__ == "__main__":
    # 1. Запускаем HTTP-сервер в фоне (обязательно для Render)
    http_thread = threading.Thread(target=run_http_server, args=(PORT,), daemon=True)
    http_thread.start()

    # 2. Создаём и запускаем Telegram-бота КОРРЕКТНО
    print(f"HTTP health server started on port {PORT}")
    print("Starting Telegram bot (blocking)...")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    # ✅ КЛЮЧЕВОЙ МОМЕНТ: вызываем run_polling() напрямую, НЕ через await и НЕ в async def!
    app.run_polling()