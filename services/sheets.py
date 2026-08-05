import json
import os
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials


EXPENSES_SHEET = "Operations"
STATES_SHEET = "States"
SUMMARY_SHEET = "Итоги"

EXPENSE_HEADERS = [
    "Дата",
    "Время",
    "Дата и время",
    "Категория",
    "Описание",
    "Сумма",
    "Тип оплаты",
    "Статус",
    "Chat ID",
    "Timezone",
    "Тип операции",
]

LEGACY_EXPENSE_HEADERS = [
    "Дата",
    "Время",
    "Дата и время",
    "Категория",
    "Описание",
    "Сумма",
    "Тип оплаты",
    "_legacy_removed_1",
    "Статус",
    "Chat ID",
    "Timezone",
    "_legacy_removed_2",
    "_legacy_removed_3",
    "Тип операции",
]

STATE_HEADERS = ["Chat ID", "State", "Data JSON", "Updated At"]
CHAT_ID_INDEX = EXPENSE_HEADERS.index("Chat ID")
STATUS_INDEX = EXPENSE_HEADERS.index("Статус")
LEGACY_STATUS_INDEX = LEGACY_EXPENSE_HEADERS.index("Статус")


class SheetsError(RuntimeError):
    pass


def _load_service_account_info():
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise SheetsError("GOOGLE_SERVICE_ACCOUNT_JSON is not configured")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SheetsError("GOOGLE_SERVICE_ACCOUNT_JSON must be valid JSON") from exc


def _client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = Credentials.from_service_account_info(_load_service_account_info(), scopes=scopes)
    return gspread.authorize(credentials)


def _spreadsheet():
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not sheet_id:
        raise SheetsError("GOOGLE_SHEET_ID is not configured")
    return _client().open_by_key(sheet_id)


def _worksheet(spreadsheet, title, headers):
    try:
        worksheet = spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=title, rows=1000, cols=max(len(headers), 10))

    first_row = worksheet.row_values(1)
    if first_row != headers:
        worksheet.resize(rows=max(worksheet.row_count, 1000), cols=max(len(headers), worksheet.col_count))
        worksheet.update("A1", [headers])
    return worksheet


def _summary_worksheet(spreadsheet):
    try:
        return spreadsheet.worksheet(SUMMARY_SHEET)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=SUMMARY_SHEET, rows=100, cols=6)


def _operations_worksheet(spreadsheet):
    try:
        worksheet = spreadsheet.worksheet(EXPENSES_SHEET)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=EXPENSES_SHEET, rows=1000, cols=len(EXPENSE_HEADERS))

    rows = worksheet.get_all_values()
    needs_migration = (not rows) or rows[0] != EXPENSE_HEADERS or any(len(row) > len(EXPENSE_HEADERS) for row in rows[1:])
    if needs_migration:
        records = _records_from_values(rows) if rows else []
        values = [EXPENSE_HEADERS]
        values.extend([record.get(header, "") for header in EXPENSE_HEADERS] for record in records)
        worksheet.clear()
        worksheet.resize(rows=max(len(values), 1000), cols=len(EXPENSE_HEADERS))
        worksheet.update("A1", values, value_input_option="USER_ENTERED")
    return worksheet


def get_expenses_sheet():
    return _operations_worksheet(_spreadsheet())


def get_states_sheet():
    return _worksheet(_spreadsheet(), STATES_SHEET, STATE_HEADERS)


def ensure_sheets():
    spreadsheet = _spreadsheet()
    operations = _operations_worksheet(spreadsheet)
    _worksheet(spreadsheet, STATES_SHEET, STATE_HEADERS)
    _summary_worksheet(spreadsheet)
    _update_summary_from_rows(spreadsheet, operations.get_all_values())


def debug_info():
    spreadsheet = _spreadsheet()
    operations = _operations_worksheet(spreadsheet)
    states = _worksheet(spreadsheet, STATES_SHEET, STATE_HEADERS)
    summary = _summary_worksheet(spreadsheet)
    operation_rows = operations.get_all_values()
    state_rows = states.get_all_values()
    summary_rows = summary.get_all_values()
    headers = operation_rows[0] if operation_rows else []
    return {
        "sheet_id": os.environ.get("GOOGLE_SHEET_ID", ""),
        "operations_sheet": EXPENSES_SHEET,
        "summary_sheet": SUMMARY_SHEET,
        "operations_rows": max(len(operation_rows) - 1, 0),
        "states_rows": max(len(state_rows) - 1, 0),
        "summary_rows": len(summary_rows),
        "headers": headers,
    }


def append_expense(expense):
    worksheet = get_expenses_sheet()
    row = [expense.get(header, "") for header in EXPENSE_HEADERS]
    result = worksheet.append_row(row, value_input_option="USER_ENTERED")
    _try_update_summary()
    return result


def all_expenses():
    return _records_from_values(get_expenses_sheet().get_all_values())


def _records_from_values(rows):
    records = []
    for row in rows[1:]:
        if any(str(cell).strip() for cell in row):
            records.append(_record_from_row(row))
    return records


def _record_from_row(row):
    headers = LEGACY_EXPENSE_HEADERS if len(row) > len(EXPENSE_HEADERS) else EXPENSE_HEADERS
    padded = row + [""] * (len(headers) - len(row))
    record = dict(zip(headers, padded))
    return {header: record.get(header, "") for header in EXPENSE_HEADERS}


def _status_column_for_row(row):
    if len(row) > len(EXPENSE_HEADERS):
        return LEGACY_STATUS_INDEX + 1
    return STATUS_INDEX + 1


def _try_update_summary():
    try:
        update_summary()
    except Exception as exc:
        print(f"Summary update failed: {type(exc).__name__}: {exc}", flush=True)


def _update_summary_from_rows(spreadsheet, rows):
    from services import reports

    worksheet = _summary_worksheet(spreadsheet)
    values = reports.summary_sheet_values(_records_from_values(rows))
    worksheet.clear()
    worksheet.update("A1", values, value_input_option="USER_ENTERED")


def update_summary():
    spreadsheet = _spreadsheet()
    operations = _operations_worksheet(spreadsheet)
    _update_summary_from_rows(spreadsheet, operations.get_all_values())


def get_state(chat_id):
    worksheet = get_states_sheet()
    chat_id = str(chat_id)
    rows = worksheet.get_all_values()
    for index, row in enumerate(rows[1:], start=2):
        if row and row[0] == chat_id:
            data = {}
            if len(row) > 2 and row[2]:
                try:
                    data = json.loads(row[2])
                except json.JSONDecodeError:
                    data = {}
            return {"row": index, "state": row[1] if len(row) > 1 else "", "data": data}
    return {"row": None, "state": "", "data": {}}


def set_state(chat_id, state, data):
    worksheet = get_states_sheet()
    current = get_state(chat_id)
    values = [str(chat_id), state, json.dumps(data, ensure_ascii=False), datetime.utcnow().isoformat(timespec="seconds")]
    if current["row"]:
        worksheet.update(f"A{current['row']}:D{current['row']}", [values])
    else:
        worksheet.append_row(values, value_input_option="USER_ENTERED")


def clear_state(chat_id):
    worksheet = get_states_sheet()
    current = get_state(chat_id)
    if current["row"]:
        worksheet.delete_rows(current["row"])


def find_last_expense_row(chat_id):
    worksheet = get_expenses_sheet()
    rows = worksheet.get_all_values()
    chat_id = str(chat_id)
    for index in range(len(rows), 1, -1):
        row = rows[index - 1]
        record = _record_from_row(row)
        if str(record.get("Chat ID", "")) == chat_id:
            return index, record
    return None, None


def recent_expense_rows(chat_id, limit=10, include_all=False):
    worksheet = get_expenses_sheet()
    rows = worksheet.get_all_values()
    chat_id = str(chat_id)
    result = []
    for index in range(len(rows), 1, -1):
        row = rows[index - 1]
        record = _record_from_row(row)
        if include_all or str(record.get("Chat ID", "")) == chat_id:
            result.append({"row_number": index, "record": record})
            if len(result) >= limit:
                break
    return result


def delete_expense_row(row_number):
    get_expenses_sheet().delete_rows(row_number)
    _try_update_summary()


def get_expense_row(row_number):
    worksheet = get_expenses_sheet()
    row = worksheet.row_values(int(row_number))
    if not row:
        return None
    return _record_from_row(row)


def update_expense_status(row_number, chat_id, status, allow_any=False):
    worksheet = get_expenses_sheet()
    row = worksheet.row_values(int(row_number))
    if not row:
        return False
    current = _record_from_row(row)
    if not allow_any and str(current.get("Chat ID", "")) != str(chat_id):
        return False
    worksheet.update_cell(int(row_number), _status_column_for_row(row), status)
    _try_update_summary()
    return True


def expense_matches(record, expected):
    if not record:
        return False
    for header in EXPENSE_HEADERS:
        if str(record.get(header, "")) != str(expected.get(header, "")):
            return False
    return True


def delete_expense_row_if_matches(row_number, expected):
    current = get_expense_row(row_number)
    if not expense_matches(current, expected):
        return False
    delete_expense_row(row_number)
    return True
