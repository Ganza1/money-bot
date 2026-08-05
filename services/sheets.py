import json
import os
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials


EXPENSES_SHEET = "Expenses"
STATES_SHEET = "States"

EXPENSE_HEADERS = [
    "Дата",
    "Время",
    "Дата и время",
    "Категория",
    "Описание",
    "Сумма",
    "Тип оплаты",
    "Криптовалюта",
    "Статус",
    "Chat ID",
    "Timezone",
    "Кошелек",
    "Валюта",
    "Тип операции",
]

STATE_HEADERS = ["Chat ID", "State", "Data JSON", "Updated At"]
CHAT_ID_INDEX = EXPENSE_HEADERS.index("Chat ID")
STATUS_INDEX = EXPENSE_HEADERS.index("Статус")


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


def get_expenses_sheet():
    return _worksheet(_spreadsheet(), EXPENSES_SHEET, EXPENSE_HEADERS)


def get_states_sheet():
    return _worksheet(_spreadsheet(), STATES_SHEET, STATE_HEADERS)


def ensure_sheets():
    spreadsheet = _spreadsheet()
    _worksheet(spreadsheet, EXPENSES_SHEET, EXPENSE_HEADERS)
    _worksheet(spreadsheet, STATES_SHEET, STATE_HEADERS)


def append_expense(expense):
    row = [expense.get(header, "") for header in EXPENSE_HEADERS]
    return get_expenses_sheet().append_row(row, value_input_option="USER_ENTERED")


def all_expenses():
    return get_expenses_sheet().get_all_records(expected_headers=EXPENSE_HEADERS)


def _record_from_row(row):
    padded = row + [""] * (len(EXPENSE_HEADERS) - len(row))
    return dict(zip(EXPENSE_HEADERS, padded))


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
        if len(row) > CHAT_ID_INDEX and row[CHAT_ID_INDEX] == chat_id:
            record = _record_from_row(row)
            return index, record
    return None, None


def recent_expense_rows(chat_id, limit=10, include_all=False):
    worksheet = get_expenses_sheet()
    rows = worksheet.get_all_values()
    chat_id = str(chat_id)
    result = []
    for index in range(len(rows), 1, -1):
        row = rows[index - 1]
        if include_all or (len(row) > CHAT_ID_INDEX and row[CHAT_ID_INDEX] == chat_id):
            result.append({"row_number": index, "record": _record_from_row(row)})
            if len(result) >= limit:
                break
    return result


def delete_expense_row(row_number):
    get_expenses_sheet().delete_rows(row_number)


def get_expense_row(row_number):
    worksheet = get_expenses_sheet()
    row = worksheet.row_values(int(row_number))
    if not row:
        return None
    return _record_from_row(row)


def update_expense_status(row_number, chat_id, status, allow_any=False):
    current = get_expense_row(row_number)
    if not current:
        return False
    if not allow_any and str(current.get("Chat ID", "")) != str(chat_id):
        return False
    worksheet = get_expenses_sheet()
    worksheet.update_cell(int(row_number), STATUS_INDEX + 1, status)
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
