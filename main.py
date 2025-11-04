import os
import asyncio
import nest_asyncio  # ← ДОБАВЛЕНО
from datetime import datetime, time as dt_time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
import pytz

# Применяем патч для вложенных event loop'ов (актуально для Windows и некоторых сред)
nest_asyncio.apply()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Токен бота не задан! Укажите переменную окружения BOT_TOKEN.")


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

scheduler = AsyncIOScheduler(timezone=TZ)
active_chats = set()
async def send_shift_message(bot, chat_id: int, message: str):
    try:
        await bot.send_message(chat_id=chat_id, text=message)
        print(f"[{datetime.now(TZ).strftime('%Y-%m-%d %H:%M')}] Отправлено в {chat_id}: {message}")
    except Exception as e:
        print(f"Ошибка отправки в {chat_id}: {e}")

async def schedule_shifts_for_user(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    if chat_id in active_chats:
        await context.bot.send_message(chat_id=chat_id, text="⚠️ График уже запущен на сегодня!")
        return

    bot = context.bot
    today = datetime.now(TZ).date()
    has_scheduled = False

    for time_str, msg in SHIFT_PLAN:
        hour, minute = map(int, time_str.split(":"))
        run_time = TZ.localize(datetime.combine(today, dt_time(hour, minute)))

        if run_time <= datetime.now(TZ):
            continue

        job_id = f"shift_{chat_id}_{time_str.replace(':', '')}"
        scheduler.add_job(
            send_shift_message,
            trigger=DateTrigger(run_date=run_time, timezone=TZ),
            args=[bot, chat_id, msg],
            id=job_id,
            replace_existing=True
        )
        has_scheduled = True

    if has_scheduled:
        active_chats.add(chat_id)
        await context.bot.send_message(chat_id=chat_id, text="✅ График рабочего дня запущен! Уведомления придут по расписанию.")
    else:
        await context.bot.send_message(chat_id=chat_id, text="ℹ️ Все события на сегодня уже прошли.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("▶️ Начать рабочий день", callback_data="start_shift")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Привет! Я помогу тебе следить за режимом труда и отдыха по нормам РБ.\n"
        "Нажми кнопку, чтобы запустить уведомления на сегодня:",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "start_shift":
        await schedule_shifts_for_user(query.message.chat_id, context)
    else:
        await query.edit_message_text("Неизвестная команда.")

async def main():
    # Запускаем планировщик ДО создания Application
    scheduler.start()
    print("✅ Планировщик запущен.")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Бот запущен. Напишите /start в Telegram.")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
