from states.constants import BANKS, CATEGORIES, OPERATION_EXPENSE, OPERATION_INCOME, OPERATION_TRANSFER, STATUSES, TRANSFER_CARD_TO_CASH, TRANSFER_CASH_TO_CARD


def button(text, callback_data):
    return {"text": text, "callback_data": callback_data}


def inline_keyboard(rows):
    return {"inline_keyboard": rows}


def main_menu_keyboard():
    return inline_keyboard(
        [
            [button("➕ Добавить операцию", "cmd:add"), button("📊 Отчет", "cmd:report")],
            [button("📜 История", "cmd:history"), button("🔁 Статус", "cmd:status")],
            [button("ℹ Помощь", "cmd:help")],
        ]
    )


def operation_type_keyboard(include_admin_operations=False):
    rows = []
    if include_admin_operations:
        rows.append([button(f"📈 {OPERATION_INCOME}", "operation:income")])
    rows.append([button(f"📉 {OPERATION_EXPENSE}", "operation:expense")])
    if include_admin_operations:
        rows.append([button(f"🔁 {OPERATION_TRANSFER}", "operation:transfer")])
    rows.append([button("❌ Отмена", "flow:cancel")])
    return inline_keyboard(rows)


def transfer_direction_keyboard():
    return inline_keyboard(
        [
            [button(f"💵➡️🏦 {TRANSFER_CASH_TO_CARD}", "transfer:cash_to_card")],
            [button(f"🏦➡️💵 {TRANSFER_CARD_TO_CASH}", "transfer:card_to_cash")],
            [button("❌ Отмена", "flow:cancel")],
        ]
    )


def payment_keyboard():
    return inline_keyboard(
        [
            [button("💵 Наличные", "payment:cash")],
            [button("🏦 Карта", "payment:card")],
            [button("❌ Отмена", "flow:cancel")],
        ]
    )


def bank_keyboard():
    emoji = {
        "Сбербанк": "🟢",
        "ВТБ": "🔵",
        "Газпромбанк": "🧭",
        "Альфа-Банк": "🔴",
        "Промсвязьбанк": "🟠",
        "Совкомбанк": "🟣",
        "Т-Банк": "🟡",
    }
    rows = [[button(f"{emoji.get(bank, '🏦')} {bank}", f"bank:{bank}")] for bank in BANKS]
    rows.append([button("❌ Отмена", "flow:cancel")])
    return inline_keyboard(rows)


def category_keyboard():
    emoji = {
        "Подписки": "💳",
        "Зарплата": "💰",
        "Офис": "🏢",
        "М": "Ⓜ️",
        "Агенты": "🤝",
        "HR": "👥",
        "Обучение": "🎓",
        "Маркетинг": "📢",
        "Прочее": "📁",
    }
    rows = [[button(f"{emoji.get(category, '')} {category}".strip(), f"category:{category}")] for category in CATEGORIES]
    rows.append([button("❌ Отмена", "flow:cancel")])
    return inline_keyboard(rows)


def status_keyboard(prefix="status"):
    emoji = {
        "Оплачен": "✅",
        "На рассмотрении": "⏳",
        "Отказ": "❌",
    }
    rows = [[button(f"{emoji.get(status, '')} {status}".strip(), f"{prefix}:{status}")] for status in STATUSES]
    rows.append([button("❌ Отмена", "flow:cancel")])
    return inline_keyboard(rows)


def status_records_keyboard(items):
    rows = []
    for index, item in enumerate(items, start=1):
        record = item["record"]
        date_time = record.get("Дата и время", "")
        amount = record.get("Сумма", "")
        description = record.get("Описание", "")
        status = record.get("Статус", "") or "без статуса"
        owner = record.get("Chat ID", "")
        label = f"{index}. {date_time} | {amount} ₽ | {description} | {status} | {owner}"
        if len(label) > 60:
            label = label[:57] + "..."
        rows.append([button(label, f"status_row:{item['row_number']}")])
    rows.append([button("❌ Отмена", "flow:cancel")])
    return inline_keyboard(rows)


def confirm_keyboard():
    return inline_keyboard(
        [
            [button("✅ Сохранить", "confirm:save")],
            [button("❌ Отмена", "confirm:cancel")],
        ]
    )


def saved_keyboard():
    return inline_keyboard(
        [
            [button("↩️ Отменить запись", "undo:saved")],
            [button("➕ Добавить еще", "cmd:add")],
        ]
    )


def report_keyboard():
    return inline_keyboard(
        [
            [button("Сегодня", "report:today"), button("7 дней", "report:week")],
            [button("Месяц", "report:month")],
        ]
    )


def delete_confirm_keyboard():
    return inline_keyboard(
        [
            [button("✅ Удалить", "delete:confirm")],
            [button("❌ Отмена", "delete:cancel")],
        ]
    )
