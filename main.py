import asyncio
import threading
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz
from datetime import datetime, time as dt_time

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is required")

TZ = pytz.timezone("Europe/Minsk")

SHIFT_PLAN = [
    ("09:00", "🟢 Начало рабочего дня. Работа за ПЭВМ (1-й блок)."),
    ("10:00", "⏸️ Перерыв 15 мин (отдых глаз, разминка)."),
    # ... остальные события
    ("18:00", "🔚 Рабочий день окончен! Хорошего отдыха!"),
]

scheduler = AsyncIOScheduler(timezone=TZ)
active_chats = set()

# --- Функции бота (как раньше, без nest_asyncio) ---

async def send_shift_message(bot, chat_id: int, message: str):
    try:
        await bot.send_message(chat_id=chat_id, text=message)
    except Exception as e:
        print(f"Ошибка отправки: {e}")

async def schedule_shifts_for_user(chat_id: int, context):
    bot = context.bot
    today = datetime.now(TZ).date()
    for time_str, msg in SHIFT_PLAN:
        hour, minute = map(int, time_str.split(":"))
        run_time = TZ.localize(datetime.combine(today, dt_time(hour, minute)))
        if run_time <= datetime.now(TZ):
            continue
        scheduler.add_job(
            send_shift_message,
            trigger='date',
            run_date=run_time,
            args=[bot, chat_id, msg],
            id=f"shift_{chat_id}_{time_str.replace(':', '')}",
            replace_existing=True
        )
    active_chats.add(chat_id)
    await context.bot.send_message(chat_id=chat_id, text="✅ График запущен!")

async def start(update, context):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    await update.message.reply_text(
        "Нажмите кнопку, чтобы начать рабочий день:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ Начать", callback_data="start_shift")]])
    )

async def button_handler(update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "start_shift":
        await schedule_shifts_for_user(query.message.chat_id, context)

# --- HTTP-сервер для Render (Web Service) ---

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

def run_http_server(port):
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

# --- Основной запуск ---

async def main():
    scheduler.start()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    # Запускаем polling в фоне
    polling_task = asyncio.create_task(app.run_polling())

    # HTTP-сервер будет запущен в отдельном потоке
    port = int(os.getenv("PORT", 10000))
    http_thread = threading.Thread(target=run_http_server, args=(port,), daemon=True)
    http_thread.start()

    print(f"✅ Бот запущен. HTTP-сервер слушает порт {port}")
    await polling_task  # ждём завершения polling (теоретически — никогда)

if __name__ == "__main__":
    asyncio.run(main())