import json
import os
import traceback
from decimal import Decimal, InvalidOperation
from datetime import datetime
from http.server import BaseHTTPRequestHandler

from keyboards.inline import (
    category_keyboard,
    confirm_keyboard,
    currency_keyboard,
    crypto_keyboard,
    delete_confirm_keyboard,
    main_menu_keyboard,
    operation_type_keyboard,
    payment_keyboard,
    report_keyboard,
    saved_keyboard,
    status_records_keyboard,
    status_keyboard,
)
from services import reports, sheets
from services.telegram import TelegramClient, TelegramError
from states.constants import (
    CURRENCY_RUB,
    FIAT_CURRENCIES,
    OPERATION_EXPENSE,
    OPERATION_INCOME,
    PAYMENT_CARD,
    PAYMENT_CASH,
    PAYMENT_CRYPTO,
    STATE_CURRENCY,
    STATE_AMOUNT,
    STATE_CATEGORY,
    STATE_CONFIRM,
    STATE_CRYPTO_CURRENCY,
    STATE_CRYPTO_WALLET,
    STATE_DELETE_CONFIRM,
    STATE_DESCRIPTION,
    STATE_PAYMENT_TYPE,
    STATE_STATUS,
    STATE_STATUS_UPDATE,
    STATE_UNDO_SAVED,
    STATE_OPERATION_TYPE,
)


def env_timezone():
    return os.environ.get("TIMEZONE", "Europe/Moscow")


def admin_chat_ids():
    raw_values = []
    for key in sorted(os.environ):
        if key == "ADMIN_CHAT_ID" or key.startswith("ADMIN_CHAT_ID"):
            raw_values.append(str(os.environ.get(key) or ""))

    result = []
    for raw in raw_values:
        for value in raw.replace(";", ",").split(","):
            value = value.strip()
            if value and value not in result:
                result.append(value)
    return result


def is_admin_chat(chat_id):
    return str(chat_id) in admin_chat_ids()


def json_response(handler, status, payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def text_from_message(message):
    return (message or {}).get("text", "").strip()


def parse_amount(text):
    try:
        value = Decimal(text.replace(" ", "").replace(",", "."))
    except (InvalidOperation, AttributeError):
        return None
    if value <= 0:
        return None
    formatted = format(value, "f")
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return formatted


def row_number_from_append_result(result):
    updated_range = (result or {}).get("updates", {}).get("updatedRange", "")
    if "!" in updated_range:
        updated_range = updated_range.split("!", 1)[1]
    row_part = updated_range.split(":", 1)[0]
    digits = "".join(char for char in row_part if char.isdigit())
    return int(digits) if digits else None


def start_add_flow(chat_id, telegram):
    sheets.set_state(chat_id, STATE_OPERATION_TYPE, {})
    telegram.send_message(chat_id, "📌 Выберите тип операции:", reply_markup=operation_type_keyboard())


def start_status_update_flow(chat_id, telegram):
    include_all = is_admin_chat(chat_id)
    items = sheets.recent_expense_rows(chat_id, limit=10, include_all=include_all)
    if not items:
        telegram.send_message(chat_id, "📭 Нет операций для изменения статуса.")
        return
    sheets.clear_state(chat_id)
    title = "🔄 Выберите операцию для смены статуса:" if not include_all else "🔄 Выберите операцию для смены статуса по всей таблице:"
    telegram.send_message(
        chat_id,
        title,
        reply_markup=status_records_keyboard(items),
    )


def send_start(chat_id, telegram):
    telegram.send_message(
        chat_id,
        "👋 Привет! Я помогу учитывать расходы в Google Sheets.",
        reply_markup=main_menu_keyboard(),
    )


def send_help(chat_id, telegram):
    telegram.send_message(
        chat_id,
        "\n".join(
            [
                "📋 Команды:",
                "➕ /add - добавить операцию",
                "📅 /today - отчет за сегодня",
                "🗓️ /week - отчет за последние 7 дней",
                "📆 /month - отчет за текущий месяц",
                "📜 /history - последние 20 операций",
                "🔄 /status - изменить статус одной из последних 10 операций",
                "🗑️ /delete_last - удалить последнюю запись",
                "🕒 /time - текущее время Europe/Moscow",
                "🆔 /id - показать chat_id",
                "🛠️ /debug - диагностика для администратора",
            ]
        ),
    )


def build_expense(data, chat_id):
    tz_name = env_timezone()
    try:
        now = datetime.strptime(data.get("created_at", ""), "%Y-%m-%d %H:%M:%S").replace(tzinfo=reports.timezone(tz_name))
    except ValueError:
        now = reports.now_in_timezone(tz_name)
    return {
        "Дата": now.strftime("%Y-%m-%d"),
        "Время": now.strftime("%H:%M:%S"),
        "Дата и время": now.strftime("%Y-%m-%d %H:%M:%S"),
        "Категория": data.get("category", ""),
        "Описание": data.get("description", ""),
        "Сумма": data.get("amount", ""),
        "Тип оплаты": data.get("payment_type", ""),
        "Криптовалюта": data.get("crypto_currency", ""),
        "Статус": data.get("status", ""),
        "Chat ID": str(chat_id),
        "Timezone": tz_name,
        "Кошелек": data.get("crypto_wallet", ""),
        "Валюта": data.get("currency", CURRENCY_RUB) if data.get("payment_type") != PAYMENT_CRYPTO else "",
        "Тип операции": data.get("operation_type", OPERATION_EXPENSE),
    }


def expense_notification_text(expense, row_number=None):
    lines = ["🆕 Создана новая операция"]
    if row_number:
        lines.append(f"📌 Строка: {row_number}")
    lines.extend(
        [
            f"🕒 Дата и время: {expense.get('Дата и время')}",
            f"📌 Тип операции: {expense.get('Тип операции')}",
            f"💳 Тип оплаты: {expense.get('Тип оплаты')}",
        ]
    )
    if expense.get("Криптовалюта"):
        lines.append(f"💱 Криптовалюта: {expense.get('Криптовалюта')}")
    if expense.get("Кошелек"):
        lines.append(f"👛 Кошелек: {expense.get('Кошелек')}")
    if expense.get("Валюта"):
        lines.append(f"💱 Валюта: {expense.get('Валюта')}")
    lines.extend(
        [
            f"🏷️ Категория: {expense.get('Категория')}",
            f"🔄 Статус: {expense.get('Статус')}",
            f"💰 Сумма: {expense.get('Сумма')}",
            f"📝 Описание: {expense.get('Описание')}",
            f"🆔 Chat ID: {expense.get('Chat ID')}",
        ]
    )
    return "\n".join(lines)


def notify_admin_about_expense(telegram, expense, row_number=None):
    text = expense_notification_text(expense, row_number=row_number)
    for admin_id in admin_chat_ids():
        try:
            telegram.send_message(admin_id, text)
        except TelegramError as exc:
            print(f"Admin notification failed for {admin_id}: {exc}", flush=True)


def save_current_expense(chat_id, message_id, data, telegram):
    expense = build_expense(data, chat_id)
    result = sheets.append_expense(expense)
    row_number = row_number_from_append_result(result)
    if not row_number:
        row_number, _ = sheets.find_last_expense_row(chat_id)
    print(
        f"Expense saved: chat_id={chat_id}, amount={expense.get('Сумма')}, "
        f"category={expense.get('Категория')}, updated_range={result.get('updates', {}).get('updatedRange')}",
        flush=True,
    )
    if row_number:
        sheets.set_state(chat_id, STATE_UNDO_SAVED, {"row_number": row_number, "expense": expense})
    else:
        sheets.clear_state(chat_id)
    notify_admin_about_expense(telegram, expense, row_number=row_number)
    telegram.edit_message_text(chat_id, message_id, "✅ Запись сохранена в лист Operations.", reply_markup=saved_keyboard())


def handle_command(chat_id, command, telegram):
    tz_name = env_timezone()
    if command == "/start":
        send_start(chat_id, telegram)
        try:
            sheets.ensure_sheets()
        except sheets.SheetsError as exc:
            print(f"Sheets setup failed on /start: {exc}", flush=True)
            telegram.send_message(
                chat_id,
                "⚠️ Бот запущен, но Google Sheets пока не настроен. Проверьте переменные GOOGLE_SERVICE_ACCOUNT_JSON, GOOGLE_SHEET_ID и доступ service account к таблице.",
            )
    elif command == "/help":
        send_help(chat_id, telegram)
    elif command == "/add":
        start_add_flow(chat_id, telegram)
    elif command == "/today":
        rows = sheets.all_expenses()
        start, end = reports.today_range(tz_name)
        telegram.send_message(chat_id, reports.build_period_report(rows, "Отчет за сегодня", start, end, tz_name, chat_id))
    elif command == "/week":
        rows = sheets.all_expenses()
        start, end = reports.last_7_days_range(tz_name)
        telegram.send_message(chat_id, reports.build_period_report(rows, "Отчет за последние 7 дней", start, end, tz_name, chat_id))
    elif command == "/month":
        rows = sheets.all_expenses()
        start, end = reports.current_month_range(tz_name)
        telegram.send_message(chat_id, reports.build_period_report(rows, "Отчет за текущий месяц", start, end, tz_name, chat_id))
    elif command == "/history":
        telegram.send_message(chat_id, reports.history_text(sheets.all_expenses(), chat_id, include_all=is_admin_chat(chat_id)))
    elif command == "/status":
        start_status_update_flow(chat_id, telegram)
    elif command == "/delete_last":
        row_number, record = sheets.find_last_expense_row(chat_id)
        if not row_number:
            telegram.send_message(chat_id, "📭 Нет записей для удаления.")
            return
        sheets.set_state(chat_id, STATE_DELETE_CONFIRM, {"row_number": row_number})
        telegram.send_message(
            chat_id,
            "🗑️ Удалить последнюю запись?\n"
            f"{record.get('Дата и время')} | {record.get('Категория')} | {record.get('Сумма')} | {record.get('Описание')}",
            reply_markup=delete_confirm_keyboard(),
        )
    elif command == "/time":
        now = reports.now_in_timezone(tz_name)
        telegram.send_message(chat_id, f"{now.strftime('%Y-%m-%d %H:%M:%S')} {tz_name}")
    elif command == "/id":
        telegram.send_message(chat_id, f"🆔 Ваш chat_id: {chat_id}")
    elif command == "/debug":
        if not is_admin_chat(chat_id):
            telegram.send_message(
                chat_id,
                "🔒 Диагностика доступна только администратору.\n"
                f"🆔 Ваш chat_id: {chat_id}",
            )
            return
        try:
            info = sheets.debug_info()
            headers = ", ".join(str(item) for item in info["headers"]) or "нет"
            telegram.send_message(
                chat_id,
                "🛠️ Диагностика\n"
                f"✅ Google Sheets подключен\n"
                f"📄 Sheet ID: {info['sheet_id']}\n"
                f"📋 Лист операций: {info['operations_sheet']}\n"
                f"📊 Operations rows: {info['operations_rows']}\n"
                f"🧠 States rows: {info['states_rows']}\n"
                f"🔖 Headers: {headers}\n"
                f"🆔 Ваш chat_id: {chat_id}\n"
                f"👑 Admin IDs: {', '.join(admin_chat_ids()) or 'не заданы'}",
            )
        except Exception as exc:
            telegram.send_message(chat_id, f"⚠️ Ошибка диагностики: {type(exc).__name__}: {str(exc)[:600]}")
    else:
        telegram.send_message(chat_id, "❓ Неизвестная команда. Нажмите /help.")


def show_report_menu(chat_id, telegram):
    telegram.send_message(chat_id, "📊 Выберите отчет:", reply_markup=report_keyboard())


def handle_message(message, telegram):
    chat_id = message["chat"]["id"]
    text = text_from_message(message)
    if text.startswith("/"):
        handle_command(chat_id, text.split()[0], telegram)
        return

    current = sheets.get_state(chat_id)
    state = current["state"]
    data = current["data"]

    if state == STATE_AMOUNT:
        amount = parse_amount(text)
        if amount is None:
            telegram.send_message(chat_id, "💰 Введите положительную сумму числом. Например: 2500")
            return
        data["amount"] = amount
        sheets.set_state(chat_id, STATE_DESCRIPTION, data)
        telegram.send_message(chat_id, "📝 Введите описание.\nПример: Яндекс Директ")
    elif state == STATE_DESCRIPTION:
        if not text:
            telegram.send_message(chat_id, "📝 Описание не должно быть пустым.")
            return
        data["description"] = text[:500]
        sheets.set_state(chat_id, STATE_CATEGORY, data)
        telegram.send_message(chat_id, "🏷️ Выберите категорию:", reply_markup=category_keyboard())
    elif state == STATE_CRYPTO_WALLET:
        if not text:
            telegram.send_message(chat_id, "👛 Номер кошелька не должен быть пустым.")
            return
        data["crypto_wallet"] = text[:200]
        sheets.set_state(chat_id, STATE_AMOUNT, data)
        telegram.send_message(chat_id, "💰 Введите сумму.\nПример: 25")
    else:
        telegram.send_message(chat_id, "👇 Выберите действие в меню или отправьте /add.", reply_markup=main_menu_keyboard())


def handle_callback(callback, telegram):
    callback_id = callback["id"]
    message = callback.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    data_value = callback.get("data", "")
    telegram.answer_callback_query(callback_id)

    current = sheets.get_state(chat_id)
    state = current["state"]
    data = current["data"]

    if data_value == "flow:cancel" or data_value == "confirm:cancel":
        sheets.clear_state(chat_id)
        telegram.edit_message_text(chat_id, message_id, "❌ Действие отменено.")
        return

    if data_value.startswith("cmd:"):
        command = data_value.split(":", 1)[1]
        if command == "add":
            start_add_flow(chat_id, telegram)
        elif command == "history":
            telegram.send_message(chat_id, reports.history_text(sheets.all_expenses(), chat_id, include_all=is_admin_chat(chat_id)))
        elif command == "help":
            send_help(chat_id, telegram)
        elif command == "report":
            show_report_menu(chat_id, telegram)
        elif command == "status":
            start_status_update_flow(chat_id, telegram)
        return

    if data_value.startswith("report:"):
        tz_name = env_timezone()
        rows = sheets.all_expenses()
        report_type = data_value.split(":", 1)[1]
        if report_type == "today":
            start, end = reports.today_range(tz_name)
            text = reports.build_period_report(rows, "Отчет за сегодня", start, end, tz_name, chat_id)
        elif report_type == "week":
            start, end = reports.last_7_days_range(tz_name)
            text = reports.build_period_report(rows, "Отчет за последние 7 дней", start, end, tz_name, chat_id)
        else:
            start, end = reports.current_month_range(tz_name)
            text = reports.build_period_report(rows, "Отчет за текущий месяц", start, end, tz_name, chat_id)
        telegram.send_message(chat_id, text)
        return

    if data_value.startswith("operation:") and state == STATE_OPERATION_TYPE:
        selected = data_value.split(":", 1)[1]
        operation_map = {"income": OPERATION_INCOME, "expense": OPERATION_EXPENSE}
        data["operation_type"] = operation_map.get(selected)
        if not data["operation_type"]:
            telegram.send_message(chat_id, "Не удалось распознать тип операции. Попробуйте /add заново.")
            sheets.clear_state(chat_id)
            return
        if data["operation_type"] == OPERATION_INCOME and not is_admin_chat(chat_id):
            telegram.send_message(chat_id, "🔒 Доход может вносить только администратор.")
            start_add_flow(chat_id, telegram)
            return
        sheets.set_state(chat_id, STATE_PAYMENT_TYPE, data)
        telegram.edit_message_text(chat_id, message_id, "💳 Выберите способ оплаты:", reply_markup=payment_keyboard())
        return

    if data_value.startswith("payment:") and state == STATE_PAYMENT_TYPE:
        selected = data_value.split(":", 1)[1]
        payment_map = {"cash": PAYMENT_CASH, "card": PAYMENT_CARD, "crypto": PAYMENT_CRYPTO}
        data["payment_type"] = payment_map.get(selected)
        if not data["payment_type"]:
            telegram.send_message(chat_id, "Не удалось распознать способ оплаты. Попробуйте /add заново.")
            sheets.clear_state(chat_id)
            return
        if data["payment_type"] == PAYMENT_CRYPTO:
            sheets.set_state(chat_id, STATE_CRYPTO_CURRENCY, data)
            telegram.edit_message_text(chat_id, message_id, "💱 Уточните валюту:", reply_markup=crypto_keyboard())
        else:
            data["currency"] = CURRENCY_RUB
            sheets.set_state(chat_id, STATE_AMOUNT, data)
            telegram.edit_message_text(chat_id, message_id, "💰 Введите сумму.\nПример: 2500")
        return

    if data_value.startswith("crypto:") and state == STATE_CRYPTO_CURRENCY:
        currency = data_value.split(":", 1)[1]
        data["crypto_currency"] = currency
        sheets.set_state(chat_id, STATE_CRYPTO_WALLET, data)
        telegram.edit_message_text(chat_id, message_id, "👛 Введите номер кошелька.")
        return

    if data_value.startswith("currency:") and state == STATE_CURRENCY:
        currency = data_value.split(":", 1)[1].upper()
        if currency not in FIAT_CURRENCIES:
            telegram.send_message(chat_id, "Не удалось распознать валюту. Попробуйте /add заново.")
            sheets.clear_state(chat_id)
            return
        data["currency"] = currency
        sheets.set_state(chat_id, STATE_AMOUNT, data)
        telegram.edit_message_text(chat_id, message_id, "💰 Введите сумму.\nПример: 2500")
        return

    if data_value.startswith("category:") and state == STATE_CATEGORY:
        category = data_value.split(":", 1)[1]
        data["category"] = category
        sheets.set_state(chat_id, STATE_STATUS, data)
        telegram.edit_message_text(chat_id, message_id, "🔄 Выберите статус:", reply_markup=status_keyboard())
        return

    if data_value.startswith("status:") and state == STATE_STATUS:
        status = data_value.split(":", 1)[1]
        data["status"] = status
        tz_name = env_timezone()
        created_at = reports.now_in_timezone(tz_name)
        data["created_at"] = created_at.strftime("%Y-%m-%d %H:%M:%S")
        save_current_expense(chat_id, message_id, data, telegram)
        return

    if data_value.startswith("status_row:"):
        row_number = data_value.split(":", 1)[1]
        record = sheets.get_expense_row(row_number)
        if not record or (not is_admin_chat(chat_id) and str(record.get("Chat ID", "")) != str(chat_id)):
            sheets.clear_state(chat_id)
            telegram.edit_message_text(chat_id, message_id, "⚠️ Не удалось найти эту операцию.")
            return
        sheets.set_state(chat_id, STATE_STATUS_UPDATE, {"row_number": int(row_number)})
        telegram.edit_message_text(
            chat_id,
            message_id,
            "🔄 Выберите новый статус:\n"
            f"{record.get('Дата и время')} | {record.get('Категория')} | "
            f"{record.get('Сумма')} | {record.get('Описание')}\n"
            f"🆔 Chat ID: {record.get('Chat ID')}",
            reply_markup=status_keyboard(prefix="status_update"),
        )
        return

    if data_value.startswith("status_update:") and state == STATE_STATUS_UPDATE:
        status = data_value.split(":", 1)[1]
        row_number = data.get("row_number")
        if row_number and sheets.update_expense_status(int(row_number), chat_id, status, allow_any=is_admin_chat(chat_id)):
            sheets.clear_state(chat_id)
            telegram.edit_message_text(chat_id, message_id, f"✅ Статус обновлен: {status}")
        else:
            sheets.clear_state(chat_id)
            telegram.edit_message_text(chat_id, message_id, "⚠️ Не удалось обновить статус: операция не найдена.")
        return

    if data_value == "confirm:save" and state == STATE_CONFIRM:
        save_current_expense(chat_id, message_id, data, telegram)
        return

    if data_value == "undo:saved" and state == STATE_UNDO_SAVED:
        row_number = data.get("row_number")
        expense = data.get("expense", {})
        if row_number and expense and sheets.delete_expense_row_if_matches(int(row_number), expense):
            sheets.clear_state(chat_id)
            telegram.edit_message_text(chat_id, message_id, "↩️ Запись отменена и удалена из Operations.")
        else:
            sheets.clear_state(chat_id)
            telegram.edit_message_text(chat_id, message_id, "⚠️ Не удалось отменить запись: она уже изменена или удалена.")
        return

    if data_value == "delete:confirm" and state == STATE_DELETE_CONFIRM:
        row_number = data.get("row_number")
        if row_number:
            sheets.delete_expense_row(int(row_number))
            sheets.clear_state(chat_id)
            telegram.edit_message_text(chat_id, message_id, "🗑️ Последняя запись удалена.")
        else:
            telegram.edit_message_text(chat_id, message_id, "⚠️ Не удалось найти запись для удаления.")
        return

    if data_value == "delete:cancel":
        sheets.clear_state(chat_id)
        telegram.edit_message_text(chat_id, message_id, "❌ Удаление отменено.")
        return

    telegram.send_message(chat_id, "⏳ Состояние устарело. Начните заново: /add")
    sheets.clear_state(chat_id)


def process_update(update):
    telegram = TelegramClient()
    if "message" in update:
        handle_message(update["message"], telegram)
    elif "callback_query" in update:
        handle_callback(update["callback_query"], telegram)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        json_response(self, 200, {"ok": True, "message": "Telegram expense bot webhook is running"})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length).decode("utf-8")
            update = json.loads(raw_body or "{}")
            process_update(update)
            json_response(self, 200, {"ok": True})
        except (TelegramError, sheets.SheetsError) as exc:
            print(f"Handled webhook error: {type(exc).__name__}: {exc}", flush=True)
            json_response(self, 200, {"ok": False, "error": str(exc)})
        except Exception as exc:
            print(f"Unhandled webhook error: {type(exc).__name__}: {exc}", flush=True)
            traceback.print_exc()
            json_response(self, 200, {"ok": False, "error": f"Unhandled error: {exc}"})
