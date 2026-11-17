import logging
import os
import sqlite3
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# ================== НАСТРОЙКИ ==================
# Токен и ваш chat_id НЕ нужно вписывать в код.
# Положите рядом с bot.py два текстовых файла:
#   token.txt     - внутри только токен бота (целиком, с цифрами и двоеточием)
#   admin_id.txt  - внутри только ваш chat_id (узнать через команду /id)
# Либо задайте переменные окружения BOT_TOKEN и ADMIN_ID.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def read_setting(name: str, filename: str, default: str = "") -> str:
    """Берёт значение из переменной окружения, а если её нет, из файла рядом с bot.py."""
    value = os.getenv(name, "").strip()
    if not value:
        path = os.path.join(BASE_DIR, filename)
        if os.path.exists(path):
            with open(path, encoding="utf-8-sig") as f:
                value = f.read().strip()
    value = value.strip().strip('"').strip("'").strip()
    return value or default


BOT_TOKEN = read_setting("BOT_TOKEN", "token.txt")
ADMIN_ID = int(read_setting("ADMIN_ID", "admin_id.txt", "0"))
CONTACT_URL = "https://t.me/@IT_Programm1st"  # замените на ссылку на ваш аккаунт
DB_PATH = os.path.join(BASE_DIR, "orders.db")

# Тексты вкладок: меняйте под себя
TABS = {
    "tab_home": (
        "👋 Привет! Я Python-разработчик.\n\n"
        "Делаю Telegram-ботов, парсеры и автоматизацию под ключ.\n"
        "Выберите раздел ниже или оставьте заявку."
    ),
    "tab_services": (
        "🛠 Услуги\n\n"
        "• Telegram-бот под ключ: от 5 000 ₽\n"
        "• Парсер сайтов: от 3 000 ₽\n"
        "• Автоматизация (Google Таблицы, CRM, отчёты): от 3 000 ₽\n\n"
        "Точная цена и сроки зависят от задачи."
    ),
    "tab_portfolio": (
        "📁 Портфолио\n\n"
        "• Проект 1: описание, ссылка на GitHub\n"
        "• Проект 2: описание, ссылка на GitHub\n"
        "• Этот бот тоже мой :)"
    ),
    "tab_contacts": (
        "📬 Контакты\n\n"
        "Telegram: @IT_Programm1st\n"
        "Канал: «Дневник программиста»\n\n"
        "Отвечаю обычно в течение нескольких часов."
    ),
}

# Состояния диалога заявки
TASK, BUDGET, CONTACT = range(3)

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s: %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


# ================== БАЗА ДАННЫХ ==================
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT,
                user_id INTEGER,
                username TEXT,
                task TEXT,
                budget TEXT,
                contact TEXT,
                status TEXT DEFAULT 'new'
            )
            """
        )


def save_application(user_id, username, task, budget, contact) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO applications (created_at, user_id, username, task, budget, contact) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M"), user_id, username, task, budget, contact),
        )
        return cur.lastrowid


# ================== КЛАВИАТУРА И ВКЛАДКИ ==================
def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Главная", callback_data="tab_home"),
                InlineKeyboardButton("Услуги", callback_data="tab_services"),
            ],
            [
                InlineKeyboardButton("Портфолио", callback_data="tab_portfolio"),
                InlineKeyboardButton("Контакты", callback_data="tab_contacts"),
            ],
            [InlineKeyboardButton("📝 Оставить заявку", callback_data="apply")],
            [InlineKeyboardButton("💬 Написать лично", url=CONTACT_URL)],
        ]
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(TABS["tab_home"], reply_markup=main_keyboard())


async def on_tab(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        await query.edit_message_text(TABS[query.data], reply_markup=main_keyboard())
    except BadRequest:
        pass  # нажали на ту же вкладку, текст не изменился


# ================== ЗАЯВКА (диалог по шагам) ==================
async def apply_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "Опишите вашу задачу своими словами.\n(Отмена: /cancel)"
    )
    return TASK


async def get_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["task"] = update.message.text
    await update.message.reply_text("Какой у вас примерный бюджет?")
    return BUDGET


async def get_budget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["budget"] = update.message.text
    await update.message.reply_text(
        "Как с вами связаться? Напишите @username, телефон или почту."
    )
    return CONTACT


async def get_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    task = context.user_data.get("task", "")
    budget = context.user_data.get("budget", "")
    contact = update.message.text
    username = f"@{user.username}" if user.username else "(нет username)"

    app_id = save_application(user.id, username, task, budget, contact)

    if ADMIN_ID:
        text = (
            f"🔔 Новая заявка #{app_id}\n\n"
            f"От: {user.full_name} {username} (id {user.id})\n"
            f"Задача: {task}\n"
            f"Бюджет: {budget}\n"
            f"Контакт: {contact}"
        )
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=text)
        except Exception:
            logger.exception("Не удалось отправить уведомление администратору")

    await update.message.reply_text(
        "Спасибо! Заявка принята, скоро свяжусь с вами.", reply_markup=main_keyboard()
    )
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Заявка отменена.", reply_markup=main_keyboard())
    return ConversationHandler.END


# ================== СЛУЖЕБНЫЕ КОМАНДЫ ==================
async def show_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Ваш chat_id: {update.effective_user.id}")


async def orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT id, created_at, username, task, budget, contact, status "
            "FROM applications ORDER BY id DESC LIMIT 10"
        ).fetchall()
    if not rows:
        await update.message.reply_text("Заявок пока нет.")
        return
    lines = [
        f"#{r[0]} | {r[1]} | {r[2]}\nЗадача: {r[3]}\nБюджет: {r[4]} | Контакт: {r[5]} | {r[6]}"
        for r in rows
    ]
    await update.message.reply_text("\n\n".join(lines))


# ================== ЗАПУСК ==================
def main():
    if ":" not in BOT_TOKEN:
        print(
            "9140068199:AAFyQl8QStaqI6iXxrKNKA8fPUiGKrkTxC4.\n"
            "9140068199:AAGhXYN_ZSHhbZV6m2VvSxz22dzECawnYEQ "
            "(он выглядит как 123456789:AAF...)."
        )
        return

    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    apply_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(apply_start, pattern="^apply$")],
        states={
            TASK: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_task)],
            BUDGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_budget)],
            CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_contact)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)],
    )

    app.add_handler(apply_conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", show_id))
    app.add_handler(CommandHandler("orders", orders))
    app.add_handler(CallbackQueryHandler(on_tab, pattern="^tab_"))

    app.run_polling()


if __name__ == "__main__":
    main()
