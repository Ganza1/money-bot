from collections import OrderedDict
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from states.constants import OPERATION_EXPENSE, OPERATION_INCOME, OPERATION_TRANSFER, PAYMENT_CARD, PAYMENT_CASH, PAYMENT_GROUPS, STATUSES


PAID_STATUS = "Оплачен"
PAID_STATUS_ALIASES = {"оплачен", "оплачено", "paid", "остаток"}
CARD_ALIASES = {PAYMENT_CARD, "Безналичные", "Карта"}
CASH_ALIASES = {PAYMENT_CASH, "Наличные"}
CASH_TO_CARD_ALIASES = {"Наличные → Карта", "Наличные -> Карта", "cash_to_card"}
CARD_TO_CASH_ALIASES = {"Карта → Наличные", "Карта -> Наличные", "card_to_cash"}

STATUS_EMOJI = {
    "Оплачен": "✅",
    "На рассмотрении": "⏳",
    "Отказ": "❌",
    "Без статуса": "▫️",
}

GROUP_EMOJI = {
    "Карта": "🏦",
    "Безналичные": "🏦",
    "Наличные": "💵",
}


def status_label(status):
    return f"{STATUS_EMOJI.get(status, '▫️')} {status}"


def group_label(group):
    base = str(group).split()[0]
    return f"{GROUP_EMOJI.get(base, '💳')} {group}"


def clean_text(value):
    return str(value or "").strip()


def clean_lookup(value):
    text = clean_text(value).casefold().replace("ё", "е")
    for marker in ("✅", "☑️", "⏳", "❌", "▫️"):
        text = text.replace(marker, "")
    return " ".join(text.split())


def timezone(name):
    return ZoneInfo(name or "Europe/Moscow")


def now_in_timezone(tz_name):
    return datetime.now(timezone(tz_name))


def parse_amount(value):
    if value is None:
        return Decimal("0")
    normalized = str(value).replace(" ", "").replace("\u00a0", "").replace(",", ".")
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return Decimal("0")


def format_amount(value):
    value = Decimal(value).quantize(Decimal("0.01"))
    if value == value.to_integral():
        return str(value.to_integral())
    return str(value).rstrip("0").rstrip(".")


def parse_expense_datetime(row, tz_name):
    value = str(row.get("Дата и время", "")).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone(tz_name))
        except ValueError:
            pass
    date_value = str(row.get("Дата", "")).strip()
    try:
        return datetime.strptime(date_value, "%Y-%m-%d").replace(tzinfo=timezone(tz_name))
    except ValueError:
        return None


def payment_group(row):
    payment_type = clean_text(row.get("Тип оплаты")) or clean_text(row.get("Источник"))
    payment_lookup = clean_lookup(payment_type)
    if payment_type in CARD_ALIASES or "карт" in payment_lookup or "безнал" in payment_lookup:
        return PAYMENT_CARD
    if payment_type in CASH_ALIASES or "налич" in payment_lookup:
        return PAYMENT_CASH
    return payment_type or PAYMENT_CARD


def amount_with_currency(row):
    return f"{row.get('Сумма')} ₽".strip()


def operation_type(row):
    for key in ("Тип операции", "Категория"):
        value = clean_text(row.get(key))
        lookup = clean_lookup(value)
        if value in (OPERATION_INCOME, OPERATION_EXPENSE, OPERATION_TRANSFER):
            return value
        if lookup == "доход":
            return OPERATION_INCOME
        if lookup == "расход":
            return OPERATION_EXPENSE
        if lookup == "перевод":
            return OPERATION_TRANSFER
    return OPERATION_EXPENSE


def is_paid(row):
    return clean_lookup(row.get("Статус")) in PAID_STATUS_ALIASES


def operation_sign(row):
    if operation_type(row) == OPERATION_INCOME:
        return Decimal("1")
    if operation_type(row) == OPERATION_EXPENSE:
        return Decimal("-1")
    return Decimal("0")


def transfer_direction(row):
    return clean_text(row.get("Направление перевода")) or clean_text(row.get("Направление")) or clean_text(row.get("Перевод"))


def apply_to_balances(card_balance, cash_balance, row):
    amount = parse_amount(row.get("Сумма"))
    op_type = operation_type(row)
    group = payment_group(row)
    direction = transfer_direction(row)

    if op_type == OPERATION_INCOME:
        if group == PAYMENT_CASH:
            cash_balance += amount
        else:
            card_balance += amount
    elif op_type == OPERATION_EXPENSE:
        if group == PAYMENT_CASH:
            cash_balance -= amount
        else:
            card_balance -= amount
    elif op_type == OPERATION_TRANSFER:
        if direction in CASH_TO_CARD_ALIASES:
            cash_balance -= amount
            card_balance += amount
        elif direction in CARD_TO_CASH_ALIASES:
            card_balance -= amount
            cash_balance += amount
    return card_balance, cash_balance


def filter_rows(rows, start_dt, end_dt, tz_name, chat_id=None):
    result = []
    for row in rows:
        if chat_id is not None and str(row.get("Chat ID", "")) != str(chat_id):
            continue
        row_dt = parse_expense_datetime(row, tz_name)
        if row_dt and start_dt <= row_dt < end_dt:
            result.append(row)
    return result


def summarize(rows):
    groups = OrderedDict((group, Decimal("0")) for group in PAYMENT_GROUPS)
    income_total = Decimal("0")
    expense_total = Decimal("0")
    transfer_total = Decimal("0")
    transfer_count = 0
    card_balance = Decimal("0")
    cash_balance = Decimal("0")
    paid_count = 0

    for row in rows:
        amount = parse_amount(row.get("Сумма"))
        op_type = operation_type(row)
        group = payment_group(row)
        if group not in groups:
            groups[group] = Decimal("0")

        if not is_paid(row):
            continue

        paid_count += 1
        if op_type == OPERATION_INCOME:
            income_total += amount
            groups[group] += amount
        elif op_type == OPERATION_EXPENSE:
            expense_total += amount
            groups[group] -= amount
        elif op_type == OPERATION_TRANSFER:
            transfer_total += amount
            transfer_count += 1

        card_balance, cash_balance = apply_to_balances(card_balance, cash_balance, row)

    return {
        "groups": groups,
        "income_total": income_total,
        "expense_total": expense_total,
        "net_total": income_total - expense_total,
        "transfer_total": transfer_total,
        "transfer_count": transfer_count,
        "card_balance": card_balance,
        "cash_balance": cash_balance,
        "total_balance": card_balance + cash_balance,
        "rows_count": len(rows),
        "paid_count": paid_count,
    }


def summarize_statuses(rows):
    groups = OrderedDict((status, Decimal("0")) for status in STATUSES)
    groups["Без статуса"] = Decimal("0")
    counts = OrderedDict((status, 0) for status in groups)
    for row in rows:
        status = str(row.get("Статус", "")).strip() or "Без статуса"
        if status not in groups:
            groups[status] = Decimal("0")
            counts[status] = 0
        groups[status] += parse_amount(row.get("Сумма")) * operation_sign(row)
        counts[status] += 1
    return groups, counts


def format_expense_line(row):
    group = payment_group(row)
    op_emoji = "📈" if operation_type(row) == OPERATION_INCOME else "📉"
    if operation_type(row) == OPERATION_TRANSFER:
        op_emoji = "🔁"
    return (
        f"🕒 {row.get('Дата и время')} | {op_emoji} {operation_type(row)} | {group_label(group)} | 🏷️ {row.get('Категория')} | "
        f"💰 {amount_with_currency(row)} | 📝 {row.get('Описание')}"
    )


def format_expense_history_line(row):
    status = str(row.get("Статус", "")).strip() or "Без статуса"
    return f"{format_expense_line(row)} | {status_label(status)}"


def pending_and_rejected_text(rows):
    important = [row for row in rows if str(row.get("Статус", "")).strip() in ("На рассмотрении", "Отказ")]
    if not important:
        return []

    lines = ["", "⚠️ Не учитываются в финансовых итогах:"]
    for status in ("На рассмотрении", "Отказ"):
        status_rows = [row for row in important if str(row.get("Статус", "")).strip() == status]
        if not status_rows:
            continue
        lines.append(f"{status_label(status)}:")
        for row in status_rows[:10]:
            lines.append(format_expense_history_line(row))
        if len(status_rows) > 10:
            lines.append(f"...и еще {len(status_rows) - 10}")
    return lines


def report_text(title, rows):
    summary = summarize(rows)
    status_groups, status_counts = summarize_statuses(rows)
    lines = [f"📊 {title}", "", "💵 Финансовые итоги считаются только по статусу Оплачен.", ""]
    lines.extend(
        [
            f"📈 Доходы всего: {format_amount(summary['income_total'])} ₽",
            f"📉 Расходы всего: {format_amount(summary['expense_total'])} ₽",
            f"🧮 Общий итог: {format_amount(summary['net_total'])} ₽",
            "",
            f"🏦 Баланс карты: {format_amount(summary['card_balance'])} ₽",
            f"💵 Баланс наличных: {format_amount(summary['cash_balance'])} ₽",
            f"💰 Общий баланс: {format_amount(summary['total_balance'])} ₽",
            "",
            f"🔁 Переводы: {format_amount(summary['transfer_total'])} ₽ ({summary['transfer_count']})",
            f"📌 Операций: {len(rows)}",
            "",
            "🔄 По статусам:",
        ]
    )
    for status, amount in status_groups.items():
        count = status_counts.get(status, 0)
        if count:
            lines.append(f"{status_label(status)}: {format_amount(amount)} ₽ ({count})")
    lines.extend(pending_and_rejected_text(rows))
    return "\n".join(lines)


def balance_text(rows, tz_name):
    summary = summarize(rows)
    updated_at = now_in_timezone(tz_name).strftime("%Y-%m-%d %H:%M:%S")
    return "\n".join(
        [
            "📌 Остатки на сегодня",
            f"🕒 {updated_at} {tz_name}",
            "",
            f"🏦 Карта: {format_amount(summary['card_balance'])} ₽",
            f"💵 Наличные: {format_amount(summary['cash_balance'])} ₽",
            f"💰 Общий остаток: {format_amount(summary['total_balance'])} ₽",
            "",
            f"📈 Доходы всего: {format_amount(summary['income_total'])} ₽",
            f"📉 Расходы всего: {format_amount(summary['expense_total'])} ₽",
            f"🔁 Переводы: {format_amount(summary['transfer_total'])} ₽ ({summary['transfer_count']})",
            "",
            f"📌 Строк прочитано: {summary['rows_count']}",
            f"✅ Учитывается в остатках: {summary['paid_count']}",
        ]
    )


def summary_sheet_values(rows):
    summary = summarize(rows)
    updated_at = now_in_timezone("Europe/Moscow").strftime("%Y-%m-%d %H:%M:%S")
    return [
        ["Показатель", "Сумма, ₽", "Комментарий"],
        ["Остаток на карте", format_amount(summary["card_balance"]), "Оплаченные операции"],
        ["Остаток наличных", format_amount(summary["cash_balance"]), "Оплаченные операции"],
        ["Общий остаток", format_amount(summary["total_balance"]), "Карта + наличные"],
        [],
        ["Доходы всего", format_amount(summary["income_total"]), "Только статус Оплачен"],
        ["Расходы всего", format_amount(summary["expense_total"]), "Только статус Оплачен"],
        ["Итог доходы-расходы", format_amount(summary["net_total"]), "Переводы не меняют итог"],
        ["Переводы", format_amount(summary["transfer_total"]), f"Операций: {summary['transfer_count']}"],
        ["Операций всего", len(rows), "Все строки Operations"],
        ["Учитывается в остатках", summary["paid_count"], "Строки со статусом Оплачен/остаток"],
        ["Обновлено", updated_at, "Europe/Moscow"],
    ]


def today_range(tz_name):
    now = now_in_timezone(tz_name)
    start = datetime.combine(now.date(), time.min, tzinfo=timezone(tz_name))
    return start, start + timedelta(days=1)


def last_7_days_range(tz_name):
    end = now_in_timezone(tz_name)
    return end - timedelta(days=7), end


def current_month_range(tz_name):
    now = now_in_timezone(tz_name)
    start = datetime(now.year, now.month, 1, tzinfo=timezone(tz_name))
    if now.month == 12:
        end = datetime(now.year + 1, 1, 1, tzinfo=timezone(tz_name))
    else:
        end = datetime(now.year, now.month + 1, 1, tzinfo=timezone(tz_name))
    return start, end


def previous_month_range(tz_name):
    current_start, _ = current_month_range(tz_name)
    last_day_previous = current_start.date() - timedelta(days=1)
    start = datetime(last_day_previous.year, last_day_previous.month, 1, tzinfo=timezone(tz_name))
    return start, current_start


def build_period_report(rows, title, start_dt, end_dt, tz_name, chat_id=None):
    filtered = filter_rows(rows, start_dt, end_dt, tz_name, chat_id=chat_id)
    period = f"{start_dt.strftime('%Y-%m-%d %H:%M')} - {end_dt.strftime('%Y-%m-%d %H:%M')} {tz_name}"
    return report_text(f"{title}\n{period}", filtered)


def history_text(rows, chat_id, limit=20, include_all=False):
    history_rows = rows if include_all else [row for row in rows if str(row.get("Chat ID", "")) == str(chat_id)]
    if not history_rows:
        return "📭 История пуста."
    recent = history_rows[-limit:]
    title = "📜 Последние операции по всей таблице:" if include_all else "📜 Последние операции:"
    lines = [title]
    for row in reversed(recent):
        line = format_expense_history_line(row)
        candidate = "\n".join([*lines, line])
        if len(candidate) > 3500:
            lines.append("...история обрезана, последние записи слишком длинные.")
            break
        lines.append(line)
    lines.extend(pending_and_rejected_text(recent))
    return "\n".join(lines)[:3900]


def format_expense_confirmation(data, tz_name, created_at):
    lines = [
        f"💳 Способ оплаты: {data.get('payment_type')}",
        f"🏷️ Категория: {data.get('category')}",
        f"🔄 Статус: {data.get('status')}",
        f"💰 Сумма: {data.get('amount')} ₽",
        f"📝 Описание: {data.get('description')}",
        f"🕒 Дата и время: {created_at.strftime('%Y-%m-%d %H:%M:%S')} {tz_name}",
    ]
    return "\n".join(lines)
