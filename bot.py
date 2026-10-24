import html
import logging
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from urllib.parse import quote

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def read_admin_id():
    raw = os.environ.get("ADMIN_CHAT_ID", "").strip()
    if not raw:
        return 0
    try:
        return int(raw)
    except ValueError:
        logger.warning("ADMIN_CHAT_ID must be an integer")
        return 0


TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
ADMIN_ID = read_admin_id()
CONTACT_USERNAME = os.environ.get("CONTACT_USERNAME", "FluentFable").strip().lstrip("@") or "FluentFable"
DB_PATH = os.environ.get("DB_PATH", "bot.db")

PROJECT_TYPE, BUDGET, DESCRIPTION, DEADLINE, CONFIRM, QUESTION = range(6)
PAGE_SIZE = 5
ACTIVE_STATUSES = ("new", "in_progress")
ADMIN_STATUSES = ("new", "in_progress", "done")
MAX_PROJECT_TYPE = 100
MAX_BUDGET = 100
MAX_DESCRIPTION = 800
MAX_DEADLINE = 100
MAX_QUESTION = 2000
ADMIN_CALLBACK_PATTERN = r"^adm:(?:panel|list:\d+|view:\d+:\d+|set:\d+:(?:new|in_progress|done):\d+)$"

TEXTS = {
    "ru": {
        "choose_language": "Выбери язык / Choose your language:",
        "main_menu": "Главное меню. Что тебе нужно?",
        "btn_site": "💻 Создать сайт",
        "btn_bot": "🤖 Создать Telegram-бота",
        "btn_question": "❓ Задать вопрос",
        "btn_orders": "📋 Мои заказы",
        "btn_admin": "⚙️ Админ-панель",
        "btn_cancel": "❌ Отмена",
        "btn_submit": "✅ Отправить заявку",
        "btn_main_menu": "🏠 Главное меню",
        "btn_back": "⬅️ Назад",
        "btn_refresh": "🔄 Обновить",
        "btn_admin_orders": "📋 Заявки",
        "btn_open_order": "⚙️ Открыть заявку",
        "service_site": "Сайт",
        "service_bot": "Telegram-бот",
        "step_project_type": "Шаг 1/4. <b>{service}</b>\n\nКакой тип проекта? Напиши кратко.",
        "step_budget": "Шаг 2/4. Укажи бюджет (число или диапазон).",
        "step_description": "Шаг 3/4. Опиши задачу.",
        "step_deadline": "Шаг 4/4. Какой срок?",
        "summary": "Проверь заявку:\n\n<b>Услуга:</b> {service}\n<b>Тип проекта:</b> {project_type}\n<b>Бюджет:</b> {budget}\n<b>Описание:</b> {description}\n<b>Срок:</b> {deadline}",
        "order_success": "Спасибо! Заявка отправлена. Я свяжусь с тобой.\n\nСвязаться напрямую: {contact}",
        "order_cancelled": "Заявка отменена.",
        "no_orders": "У тебя пока нет заявок.",
        "orders_title": "<b>Твои заявки:</b>",
        "order_line": "<b>#{order_id}</b> · {service}\nСтатус: {status}\nБюджет: {budget}\nСоздана: {created_at}",
        "cancel_order_btn": "❌ Отменить #{order_id}",
        "order_not_found": "Заявка не найдена.",
        "cannot_cancel": "Эту заявку уже нельзя отменить.",
        "question_prompt": "Напиши свой вопрос одним сообщением.",
        "question_sent": "Вопрос отправлен. Я отвечу тебе в чате.",
        "cancelled": "Действие отменено.",
        "too_long": "Слишком длинно. Максимум {limit} символов.",
        "admin_only": "Доступ запрещён.",
        "admin_panel": "⚙️ <b>Админ-панель</b>\n\n🆕 Новые: {new}\n⏳ В обработке: {in_progress}\n✅ Завершено: {done}\n\nВсего заявок: {total}",
        "admin_orders_title": "<b>Заявки</b> · стр. {page}/{pages}",
        "admin_orders_empty": "Заявок пока нет.",
        "admin_order_line": "<b>#{order_id}</b> · {service} · {status}\n{username} · {created_at}",
        "admin_order_btn": "#{order_id} · {service} · {status}",
        "admin_order_card": "<b>Заявка #{order_id}</b>\n\n<b>Клиент:</b> {username}\n<b>ID:</b> <code>{user_id}</code>\n<b>Услуга:</b> {service}\n<b>Тип проекта:</b> {project_type}\n<b>Бюджет:</b> {budget}\n<b>Описание:</b> {description}\n<b>Срок:</b> {deadline}\n<b>Статус:</b> {status}\n<b>Создана:</b> {created_at}",
        "admin_order_missing": "Заявка не найдена.",
        "admin_status_updated": "Статус изменён: {status}.",
        "status_new": "Новая",
        "status_in_progress": "В обработке",
        "status_done": "Завершена",
        "status_cancelled": "Отменена",
        "btn_status_new": "🆕 Новая",
        "btn_status_in_progress": "⏳ В обработке",
        "btn_status_done": "✅ Завершена",
        "admin_new_order": "🔔 <b>Новая заявка #{order_id}</b>\n\n<b>Клиент:</b> {username}\n<b>ID:</b> <code>{user_id}</code>\n<b>Услуга:</b> {service}\n<b>Тип проекта:</b> {project_type}\n<b>Бюджет:</b> {budget}\n<b>Описание:</b> {description}\n<b>Срок:</b> {deadline}",
        "admin_new_question": "❓ <b>Новый вопрос</b>\n\n<b>Клиент:</b> {username}\n<b>ID:</b> <code>{user_id}</code>\n\n{question}",
    },
    "en": {
        "choose_language": "Choose your language / Выбери язык:",
        "main_menu": "Main menu. What do you need?",
        "btn_site": "💻 Build a website",
        "btn_bot": "🤖 Build a Telegram bot",
        "btn_question": "❓ Ask a question",
        "btn_orders": "📋 My orders",
        "btn_admin": "⚙️ Admin panel",
        "btn_cancel": "❌ Cancel",
        "btn_submit": "✅ Submit request",
        "btn_main_menu": "🏠 Main menu",
        "btn_back": "⬅️ Back",
        "btn_refresh": "🔄 Refresh",
        "btn_admin_orders": "📋 Orders",
        "btn_open_order": "⚙️ Open request",
        "service_site": "Website",
        "service_bot": "Telegram bot",
        "step_project_type": "Step 1/4. <b>{service}</b>\n\nWhat type of project is it? Keep it short.",
        "step_budget": "Step 2/4. What is your budget (amount or range)?",
        "step_description": "Step 3/4. Describe the task.",
        "step_deadline": "Step 4/4. What is the deadline?",
        "summary": "Check your request:\n\n<b>Service:</b> {service}\n<b>Project type:</b> {project_type}\n<b>Budget:</b> {budget}\n<b>Description:</b> {description}\n<b>Deadline:</b> {deadline}",
        "order_success": "Thank you! Your request has been sent. I will contact you.\n\nContact me directly: {contact}",
        "order_cancelled": "The request has been cancelled.",
        "no_orders": "You don't have any requests yet.",
        "orders_title": "<b>Your requests:</b>",
        "order_line": "<b>#{order_id}</b> · {service}\nStatus: {status}\nBudget: {budget}\nCreated: {created_at}",
        "cancel_order_btn": "❌ Cancel #{order_id}",
        "order_not_found": "Request not found.",
        "cannot_cancel": "This request can no longer be cancelled.",
        "question_prompt": "Send your question in one message.",
        "question_sent": "Your question has been sent. I will reply in this chat.",
        "cancelled": "Action cancelled.",
        "too_long": "Too long. Maximum {limit} characters.",
        "admin_only": "Access denied.",
        "admin_panel": "⚙️ <b>Admin panel</b>\n\n🆕 New: {new}\n⏳ In progress: {in_progress}\n✅ Completed: {done}\n\nTotal requests: {total}",
        "admin_orders_title": "<b>Requests</b> · page {page}/{pages}",
        "admin_orders_empty": "There are no requests yet.",
        "admin_order_line": "<b>#{order_id}</b> · {service} · {status}\n{username} · {created_at}",
        "admin_order_btn": "#{order_id} · {service} · {status}",
        "admin_order_card": "<b>Request #{order_id}</b>\n\n<b>Client:</b> {username}\n<b>ID:</b> <code>{user_id}</code>\n<b>Service:</b> {service}\n<b>Project type:</b> {project_type}\n<b>Budget:</b> {budget}\n<b>Description:</b> {description}\n<b>Deadline:</b> {deadline}\n<b>Status:</b> {status}\n<b>Created:</b> {created_at}",
        "admin_order_missing": "Request not found.",
        "admin_status_updated": "Status updated: {status}.",
        "status_new": "New",
        "status_in_progress": "In progress",
        "status_done": "Completed",
        "status_cancelled": "Cancelled",
        "btn_status_new": "🆕 New",
        "btn_status_in_progress": "⏳ In progress",
        "btn_status_done": "✅ Completed",
        "admin_new_order": "🔔 <b>New request #{order_id}</b>\n\n<b>Client:</b> {username}\n<b>ID:</b> <code>{user_id}</code>\n<b>Service:</b> {service}\n<b>Project type:</b> {project_type}\n<b>Budget:</b> {budget}\n<b>Description:</b> {description}\n<b>Deadline:</b> {deadline}",
        "admin_new_question": "❓ <b>New question</b>\n\n<b>Client:</b> {username}\n<b>ID:</b> <code>{user_id}</code>\n\n{question}",
    },
}


def tr(lang, key, **kwargs):
    language = lang if lang in TEXTS else "ru"
    template = TEXTS[language].get(key) or TEXTS["ru"].get(key, key)
    return template.format(**kwargs) if kwargs else template


def get_lang(context):
    lang = context.user_data.get("lang", "ru")
    return lang if lang in TEXTS else "ru"


def is_admin(user_id):
    return bool(ADMIN_ID) and user_id == ADMIN_ID


def esc(value):
    return html.escape(str(value))


def username_text(username):
    return f"@{esc(username)}" if username else "—"


def service_label(service, lang):
    return tr(lang, "service_site" if service == "site" else "service_bot")


def status_label(status, lang):
    return tr(lang, f"status_{status}" if status in {"new", "in_progress", "done", "cancelled"} else "status_new")


def format_created_at(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError):
        return str(value)


def contact_link():
    return f'<a href="https://t.me/{quote(CONTACT_USERNAME, safe="")}">@{esc(CONTACT_USERNAME)}</a>'


def connect_db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with closing(connect_db()) as connection, connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL DEFAULT '',
                service TEXT NOT NULL,
                project_type TEXT NOT NULL,
                budget TEXT NOT NULL,
                description TEXT NOT NULL,
                deadline TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'new',
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")


def create_order(user_id, username, data):
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with closing(connect_db()) as connection, connection:
        cursor = connection.execute(
            """
            INSERT INTO orders
                (user_id, username, service, project_type, budget, description, deadline, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                username or "",
                data["service"],
                data["project_type"],
                data["budget"],
                data["description"],
                data["deadline"],
                "new",
                created_at,
            ),
        )
        return int(cursor.lastrowid)


def get_order(order_id):
    with closing(connect_db()) as connection:
        return connection.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()


def get_user_orders(user_id, limit=20):
    with closing(connect_db()) as connection:
        return connection.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()


def cancel_user_order(order_id, user_id):
    with closing(connect_db()) as connection, connection:
        cursor = connection.execute(
            "UPDATE orders SET status = 'cancelled' WHERE id = ? AND user_id = ? AND status IN ('new', 'in_progress')",
            (order_id, user_id),
        )
        return cursor.rowcount > 0


def get_stats():
    with closing(connect_db()) as connection:
        rows = connection.execute("SELECT status, COUNT(*) FROM orders GROUP BY status").fetchall()
    counts = {row[0]: row[1] for row in rows}
    return {
        "new": counts.get("new", 0),
        "in_progress": counts.get("in_progress", 0),
        "done": counts.get("done", 0),
        "total": sum(counts.values()),
    }


def count_orders():
    with closing(connect_db()) as connection:
        return int(connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0])


def get_orders_page(limit, offset):
    with closing(connect_db()) as connection:
        return connection.execute(
            "SELECT * FROM orders ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()


def set_order_status(order_id, status):
    if status not in ADMIN_STATUSES:
        return False
    with closing(connect_db()) as connection, connection:
        cursor = connection.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
        return cursor.rowcount > 0


def main_menu_keyboard(lang, user_id):
    rows = [
        [
            InlineKeyboardButton(tr(lang, "btn_site"), callback_data="menu:site"),
            InlineKeyboardButton(tr(lang, "btn_bot"), callback_data="menu:bot"),
        ],
        [InlineKeyboardButton(tr(lang, "btn_question"), callback_data="menu:question")],
        [InlineKeyboardButton(tr(lang, "btn_orders"), callback_data="menu:orders")],
    ]
    if is_admin(user_id):
        rows.append([InlineKeyboardButton(tr(lang, "btn_admin"), callback_data="menu:admin")])
    return InlineKeyboardMarkup(rows)


def cancel_keyboard(lang):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(tr(lang, "btn_cancel"), callback_data="flow:cancel")]]
    )


def menu_button(lang):
    return InlineKeyboardButton(tr(lang, "btn_main_menu"), callback_data="menu:main")


def summary_keyboard(lang):
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(tr(lang, "btn_submit"), callback_data="order:submit")],
            [InlineKeyboardButton(tr(lang, "btn_cancel"), callback_data="flow:cancel")],
        ]
    )


async def safe_edit(query, text, reply_markup=None):
    try:
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
        )
    except BadRequest:
        pass


async def send_admin_notification(context, text, order_id=None):
    if not ADMIN_ID:
        logger.warning("ADMIN_CHAT_ID is not set; notification was not sent")
        return
    reply_markup = None
    if order_id is not None:
        reply_markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        tr("ru", "btn_open_order"),
                        callback_data=f"adm:view:{order_id}:0",
                    )
                ]
            ]
        )
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
        )
    except TelegramError:
        logger.exception("Could not send admin notification")


def build_my_orders(user_id, lang):
    orders = get_user_orders(user_id)
    if not orders:
        return tr(lang, "no_orders"), InlineKeyboardMarkup([[menu_button(lang)]])
    blocks = [tr(lang, "orders_title")]
    buttons = []
    for order in orders:
        blocks.append(
            tr(
                lang,
                "order_line",
                order_id=order["id"],
                service=esc(service_label(order["service"], lang)),
                status=esc(status_label(order["status"], lang)),
                budget=esc(order["budget"]),
                created_at=esc(format_created_at(order["created_at"])),
            )
        )
        if order["status"] in ACTIVE_STATUSES:
            buttons.append(
                [
                    InlineKeyboardButton(
                        tr(lang, "cancel_order_btn", order_id=order["id"]),
                        callback_data=f"my:cancel:{order['id']}",
                    )
                ]
            )
    buttons.append([menu_button(lang)])
    return "\n\n".join(blocks), InlineKeyboardMarkup(buttons)


def build_admin_panel(lang):
    stats = get_stats()
    text = tr(
        lang,
        "admin_panel",
        new=stats["new"],
        in_progress=stats["in_progress"],
        done=stats["done"],
        total=stats["total"],
    )
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(tr(lang, "btn_admin_orders"), callback_data="adm:list:0")],
            [
                InlineKeyboardButton(tr(lang, "btn_refresh"), callback_data="adm:panel"),
                menu_button(lang),
            ],
        ]
    )
    return text, keyboard


def build_admin_list(page, lang):
    total = count_orders()
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    orders = get_orders_page(PAGE_SIZE, page * PAGE_SIZE)
    if orders:
        lines = [
            tr(
                lang,
                "admin_order_line",
                order_id=order["id"],
                service=esc(service_label(order["service"], lang)),
                status=esc(status_label(order["status"], lang)),
                username=username_text(order["username"]),
                created_at=esc(format_created_at(order["created_at"])),
            )
            for order in orders
        ]
        text = tr(lang, "admin_orders_title", page=page + 1, pages=pages)
        text = f"{text}\n\n" + "\n\n".join(lines)
    else:
        text = tr(lang, "admin_orders_empty")
    buttons = []
    for order in orders:
        buttons.append(
            [
                InlineKeyboardButton(
                    tr(
                        lang,
                        "admin_order_btn",
                        order_id=order["id"],
                        service=service_label(order["service"], lang),
                        status=status_label(order["status"], lang),
                    ),
                    callback_data=f"adm:view:{order['id']}:{page}",
                )
            ]
        )
    navigation = []
    if page > 0:
        navigation.append(InlineKeyboardButton("⬅️", callback_data=f"adm:list:{page - 1}"))
    if page < pages - 1:
        navigation.append(InlineKeyboardButton("➡️", callback_data=f"adm:list:{page + 1}"))
    if navigation:
        buttons.append(navigation)
    buttons.append(
        [
            InlineKeyboardButton(tr(lang, "btn_admin"), callback_data="adm:panel"),
            menu_button(lang),
        ]
    )
    return text, InlineKeyboardMarkup(buttons)


def build_admin_order(order, page, lang):
    if order is None:
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton(tr(lang, "btn_back"), callback_data=f"adm:list:{page}")],
                [InlineKeyboardButton(tr(lang, "btn_admin"), callback_data="adm:panel")],
            ]
        )
        return tr(lang, "admin_order_missing"), keyboard
    text = tr(
        lang,
        "admin_order_card",
        order_id=order["id"],
        username=username_text(order["username"]),
        user_id=order["user_id"],
        service=esc(service_label(order["service"], lang)),
        project_type=esc(order["project_type"]),
        budget=esc(order["budget"]),
        description=esc(order["description"]),
        deadline=esc(order["deadline"]),
        status=esc(status_label(order["status"], lang)),
        created_at=esc(format_created_at(order["created_at"])),
    )
    order_id = order["id"]
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    tr(lang, "btn_status_new"),
                    callback_data=f"adm:set:{order_id}:new:{page}",
                ),
                InlineKeyboardButton(
                    tr(lang, "btn_status_in_progress"),
                    callback_data=f"adm:set:{order_id}:in_progress:{page}",
                ),
            ],
            [
                InlineKeyboardButton(
                    tr(lang, "btn_status_done"),
                    callback_data=f"adm:set:{order_id}:done:{page}",
                )
            ],
            [
                InlineKeyboardButton(tr(lang, "btn_back"), callback_data=f"adm:list:{page}"),
                InlineKeyboardButton(tr(lang, "btn_admin"), callback_data="adm:panel"),
            ],
        ]
    )
    return text, keyboard


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("order", None)
    context.user_data.pop("question", None)
    lang = get_lang(context)
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🇷🇺 Русский", callback_data="lang:ru"),
                InlineKeyboardButton("🇬🇧 English", callback_data="lang:en"),
            ]
        ]
    )
    await update.effective_message.reply_text(tr(lang, "choose_language"), reply_markup=keyboard)


async def start_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)
    return ConversationHandler.END


async def choose_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data.split(":", 1)[1]
    context.user_data["lang"] = lang
    context.user_data.pop("order", None)
    context.user_data.pop("question", None)
    await safe_edit(query, tr(lang, "main_menu"), main_menu_keyboard(lang, update.effective_user.id))


async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    lang = get_lang(context)
    if query.data == "menu:main":
        await query.answer()
        await safe_edit(
            query,
            tr(lang, "main_menu"),
            main_menu_keyboard(lang, update.effective_user.id),
        )
    elif query.data == "menu:orders":
        await query.answer()
        text, keyboard = build_my_orders(update.effective_user.id, lang)
        await safe_edit(query, text, keyboard)
    elif query.data == "menu:admin":
        if not is_admin(update.effective_user.id):
            await query.answer(tr(lang, "admin_only"), show_alert=True)
            return
        await query.answer()
        text, keyboard = build_admin_panel(lang)
        await safe_edit(query, text, keyboard)


async def cancel_client_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    lang = get_lang(context)
    order_id = int(query.data.rsplit(":", 1)[1])
    order = get_order(order_id)
    if order is None or order["user_id"] != update.effective_user.id:
        await query.answer(tr(lang, "order_not_found"), show_alert=True)
        return
    if order["status"] not in ACTIVE_STATUSES:
        await query.answer(tr(lang, "cannot_cancel"), show_alert=True)
        text, keyboard = build_my_orders(update.effective_user.id, lang)
        await safe_edit(query, text, keyboard)
        return
    cancel_user_order(order_id, update.effective_user.id)
    await query.answer(tr(lang, "order_cancelled"))
    text, keyboard = build_my_orders(update.effective_user.id, lang)
    await safe_edit(query, text, keyboard)


async def admin_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    lang = get_lang(context)
    if not is_admin(update.effective_user.id):
        await query.answer(tr(lang, "admin_only"), show_alert=True)
        return
    parts = query.data.split(":")
    action = parts[1]
    if action == "panel":
        await query.answer()
        text, keyboard = build_admin_panel(lang)
        await safe_edit(query, text, keyboard)
    elif action == "list":
        page = int(parts[2])
        await query.answer()
        text, keyboard = build_admin_list(page, lang)
        await safe_edit(query, text, keyboard)
    elif action == "view":
        order_id = int(parts[2])
        page = int(parts[3])
        await query.answer()
        text, keyboard = build_admin_order(get_order(order_id), page, lang)
        await safe_edit(query, text, keyboard)
    elif action == "set":
        order_id = int(parts[2])
        status = parts[3]
        page = int(parts[4])
        order = get_order(order_id)
        if order is None:
            await query.answer(tr(lang, "admin_order_missing"), show_alert=True)
            text, keyboard = build_admin_list(page, lang)
            await safe_edit(query, text, keyboard)
            return
        if status not in ADMIN_STATUSES:
            await query.answer(tr(lang, "admin_only"), show_alert=True)
            return
        set_order_status(order_id, status)
        await query.answer(
            tr(lang, "admin_status_updated", status=status_label(status, lang))
        )
        text, keyboard = build_admin_order(get_order(order_id), page, lang)
        await safe_edit(query, text, keyboard)


async def start_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    service = query.data.split(":", 1)[1]
    context.user_data["order"] = {"service": service}
    await safe_edit(
        query,
        tr(
            lang,
            "step_project_type",
            service=service_label(service, lang),
        ),
        cancel_keyboard(lang),
    )
    return PROJECT_TYPE


async def set_project_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(context)
    value = update.message.text.strip()
    if len(value) > MAX_PROJECT_TYPE:
        await update.message.reply_text(
            tr(lang, "too_long", limit=MAX_PROJECT_TYPE),
            reply_markup=cancel_keyboard(lang),
        )
        return PROJECT_TYPE
    context.user_data.setdefault("order", {})["project_type"] = value
    await update.message.reply_text(
        tr(lang, "step_budget"),
        reply_markup=cancel_keyboard(lang),
        parse_mode=ParseMode.HTML,
    )
    return BUDGET


async def set_budget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(context)
    value = update.message.text.strip()
    if len(value) > MAX_BUDGET:
        await update.message.reply_text(
            tr(lang, "too_long", limit=MAX_BUDGET),
            reply_markup=cancel_keyboard(lang),
        )
        return BUDGET
    context.user_data.setdefault("order", {})["budget"] = value
    await update.message.reply_text(
        tr(lang, "step_description"),
        reply_markup=cancel_keyboard(lang),
        parse_mode=ParseMode.HTML,
    )
    return DESCRIPTION


async def set_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(context)
    value = update.message.text.strip()
    if len(value) > MAX_DESCRIPTION:
        await update.message.reply_text(
            tr(lang, "too_long", limit=MAX_DESCRIPTION),
            reply_markup=cancel_keyboard(lang),
        )
        return DESCRIPTION
    context.user_data.setdefault("order", {})["description"] = value
    await update.message.reply_text(
        tr(lang, "step_deadline"),
        reply_markup=cancel_keyboard(lang),
        parse_mode=ParseMode.HTML,
    )
    return DEADLINE


async def set_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(context)
    value = update.message.text.strip()
    if len(value) > MAX_DEADLINE:
        await update.message.reply_text(
            tr(lang, "too_long", limit=MAX_DEADLINE),
            reply_markup=cancel_keyboard(lang),
        )
        return DEADLINE
    order = context.user_data.setdefault("order", {})
    order["deadline"] = value
    text = tr(
        lang,
        "summary",
        service=esc(service_label(order.get("service", "site"), lang)),
        project_type=esc(order.get("project_type", "")),
        budget=esc(order.get("budget", "")),
        description=esc(order.get("description", "")),
        deadline=esc(order.get("deadline", "")),
    )
    await update.message.reply_text(
        text,
        reply_markup=summary_keyboard(lang),
        parse_mode=ParseMode.HTML,
    )
    return CONFIRM


async def submit_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    order = context.user_data.get("order")
    user = update.effective_user
    if not order or not all(order.get(key) for key in ("service", "project_type", "budget", "description", "deadline")):
        await query.message.reply_text(
            tr(lang, "main_menu"),
            reply_markup=main_menu_keyboard(lang, user.id),
        )
        return ConversationHandler.END
    order_id = create_order(user.id, user.username or "", order)
    await safe_edit(
        query,
        tr(lang, "order_success", contact=contact_link()),
        InlineKeyboardMarkup([[menu_button(lang)]]),
    )
    context.user_data.pop("order", None)
    text = tr(
        "ru",
        "admin_new_order",
        order_id=order_id,
        username=username_text(user.username or ""),
        user_id=user.id,
        service=esc(service_label(order["service"], "ru")),
        project_type=esc(order["project_type"]),
        budget=esc(order["budget"]),
        description=esc(order["description"]),
        deadline=esc(order["deadline"]),
    )
    await send_admin_notification(context, text, order_id)
    return ConversationHandler.END


async def start_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    await safe_edit(query, tr(lang, "question_prompt"), cancel_keyboard(lang))
    return QUESTION


async def receive_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(context)
    value = update.message.text.strip()
    if len(value) > MAX_QUESTION:
        await update.message.reply_text(
            tr(lang, "too_long", limit=MAX_QUESTION),
            reply_markup=cancel_keyboard(lang),
        )
        return QUESTION
    user = update.effective_user
    text = tr(
        "ru",
        "admin_new_question",
        username=username_text(user.username or ""),
        user_id=user.id,
        question=esc(value),
    )
    await send_admin_notification(context, text)
    await update.message.reply_text(
        tr(lang, "question_sent"),
        reply_markup=InlineKeyboardMarkup([[menu_button(lang)]]),
    )
    return ConversationHandler.END


async def cancel_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("order", None)
    context.user_data.pop("question", None)
    lang = get_lang(context)
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await safe_edit(
            query,
            f"{tr(lang, 'cancelled')}\n\n{tr(lang, 'main_menu')}",
            main_menu_keyboard(lang, update.effective_user.id),
        )
    else:
        await update.effective_message.reply_text(
            tr(lang, "main_menu"),
            reply_markup=main_menu_keyboard(lang, update.effective_user.id),
        )
    return ConversationHandler.END


def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN is not set")
    init_db()
    application = Application.builder().token(TOKEN).build()
    conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_order, pattern=r"^menu:(?:site|bot)$"),
            CallbackQueryHandler(start_question, pattern=r"^menu:question$"),
        ],
        states={
            PROJECT_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_project_type)],
            BUDGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_budget)],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_description)],
            DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_deadline)],
            CONFIRM: [CallbackQueryHandler(submit_order, pattern=r"^order:submit$")],
            QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_question)],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_flow, pattern=r"^flow:cancel$"),
            CommandHandler("cancel", cancel_flow),
            CommandHandler("start", start_flow),
        ],
        allow_reentry=True,
    )
    application.add_handler(conversation)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cancel", cancel_flow))
    application.add_handler(CallbackQueryHandler(choose_language, pattern=r"^lang:(?:ru|en)$"))
    application.add_handler(CallbackQueryHandler(menu_router, pattern=r"^menu:(?:orders|admin|main)$"))
    application.add_handler(CallbackQueryHandler(cancel_client_order, pattern=r"^my:cancel:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_router, pattern=ADMIN_CALLBACK_PATTERN))
    application.add_handler(CallbackQueryHandler(cancel_flow, pattern=r"^flow:cancel$"))
    application.run_polling()


if __name__ == "__main__":
    main()
