from collections import OrderedDict
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from states.constants import CURRENCY_RUB, FIAT_CURRENCIES, PAYMENT_GROUPS, STATUSES


STATUS_EMOJI = {
    "Оплачен": "✅",
    "На рассмотрении": "⏳",
    "Отказ": "❌",
    "Без статуса": "▫️",
}

GROUP_EMOJI = {
    "Наличные": "💵",
    "Безналичные": "🏦",
    "BTC": "₿",
    "ETH": "⟠",
    "USDT": "💵",
}


def status_label(status):
    return f"{STATUS_EMOJI.get(status, '▫️')} {status}"


def group_label(group):
    base = str(group).split()[0]
    return f"{GROUP_EMOJI.get(base, '💳')} {group}"


def timezone(name):
    return ZoneInfo(name or "Europe/Moscow")


def now_in_timezone(tz_name):
    return datetime.now(timezone(tz_name))


def parse_amount(value):
    if value is None:
        return Decimal("0")
    normalized = str(value).replace(" ", "").replace(",", ".")
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


def fiat_currency(row):
    currency = str(row.get("Валюта", "")).strip().upper()
    return currency if currency in FIAT_CURRENCIES else CURRENCY_RUB


def payment_group(row):
    payment_type = str(row.get("Тип оплаты", "")).strip()
    crypto = str(row.get("Криптовалюта", "")).strip().upper()
    if payment_type == "Крипта" and crypto:
        return crypto
    if payment_type:
        return f"{payment_type} {fiat_currency(row)}"
    return payment_type


def amount_with_currency(row):
    amount = row.get("Сумма")
    if str(row.get("Тип оплаты", "")).strip() == "Крипта":
        currency = str(row.get("Криптовалюта", "")).strip().upper()
    else:
        currency = fiat_currency(row)
    return f"{amount} {currency}".strip()


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
    total = Decimal("0")
    for row in rows:
        amount = parse_amount(row.get("Сумма"))
        group = payment_group(row)
        if group not in groups:
            groups[group] = Decimal("0")
        groups[group] += amount
        total += amount
    return groups, total


def summarize_statuses(rows):
    groups = OrderedDict((status, Decimal("0")) for status in STATUSES)
    groups["Без статуса"] = Decimal("0")
    counts = OrderedDict((status, 0) for status in groups)
    for row in rows:
        status = str(row.get("Статус", "")).strip() or "Без статуса"
        if status not in groups:
            groups[status] = Decimal("0")
            counts[status] = 0
        groups[status] += parse_amount(row.get("Сумма"))
        counts[status] += 1
    return groups, counts


def format_expense_line(row):
    group = payment_group(row)
    return (
        f"🕒 {row.get('Дата и время')} | {group_label(group)} | 🏷️ {row.get('Категория')} | "
        f"💰 {amount_with_currency(row)} | 📝 {row.get('Описание')}"
    )


def format_expense_history_line(row):
    status = str(row.get("Статус", "")).strip() or "Без статуса"
    return f"{format_expense_line(row)} | {status_label(status)}"


def pending_and_rejected_text(rows):
    important = [row for row in rows if str(row.get("Статус", "")).strip() in ("На рассмотрении", "Отказ")]
    if not important:
        return []

    lines = ["", "⚠️ Платежи на рассмотрении и отказ:"]
    for status in ("На рассмотрении", "Отказ"):
        status_rows = [row for row in important if str(row.get("Статус", "")).strip() == status]
        if not status_rows:
            continue
        lines.append(f"{status_label(status)}:")
        for row in status_rows[:10]:
            lines.append(format_expense_history_line(row))
        if len(status_rows) > 10:
            lines.append(f"…и еще {len(status_rows) - 10}")
    return lines


def report_text(title, rows):
    groups, total = summarize(rows)
    status_groups, status_counts = summarize_statuses(rows)
    lines = [f"📊 {title}", ""]
    for group, amount in groups.items():
        lines.append(f"{group_label(group)}: {format_amount(amount)}")
    rub_total = sum(amount for group, amount in groups.items() if group.endswith("RUB"))
    usd_total = sum(amount for group, amount in groups.items() if group.endswith("USD"))
    crypto_total = total - rub_total - usd_total
    lines.extend(
        [
            "",
            f"🧮 Общий итог RUB: {format_amount(rub_total)}",
            f"🧮 Общий итог USD: {format_amount(usd_total)}",
            f"🧮 Общий итог крипта: {format_amount(crypto_total)}",
            f"📌 Операций: {len(rows)}",
            "",
            "🔄 По статусам:",
        ]
    )
    for status, amount in status_groups.items():
        count = status_counts.get(status, 0)
        if count:
            lines.append(f"{status_label(status)}: {format_amount(amount)} ({count})")
    lines.extend(pending_and_rejected_text(rows))
    return "\n".join(lines)


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
        lines.append(format_expense_history_line(row))
    lines.extend(pending_and_rejected_text(recent))
    return "\n".join(lines)


def format_expense_confirmation(data, tz_name, created_at):
    lines = []
    if data.get("payment_type") == "Крипта":
        lines.append("💳 Тип оплаты: Крипта")
        lines.append(f"💱 Валюта: {data.get('crypto_currency')}")
        lines.append(f"👛 Кошелек: {data.get('crypto_wallet')}")
    else:
        lines.append(f"💳 Способ оплаты: {data.get('payment_type')}")
        lines.append(f"💱 Валюта: {data.get('currency', CURRENCY_RUB)}")
    lines.extend(
        [
            f"🏷️ Категория: {data.get('category')}",
            f"🔄 Статус: {data.get('status')}",
            f"💰 Сумма: {data.get('amount')}",
            f"📝 Описание: {data.get('description')}",
            f"🕒 Дата и время: {created_at.strftime('%Y-%m-%d %H:%M:%S')} {tz_name}",
        ]
    )
    return "\n".join(lines)
