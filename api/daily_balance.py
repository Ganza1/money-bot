import json
import os
from http.server import BaseHTTPRequestHandler

from services import reports, sheets
from services.telegram import TelegramClient


def json_response(handler, status, payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def authorized(headers):
    secret = os.environ.get("CRON_SECRET")
    if not secret:
        return True
    return headers.get("Authorization") == f"Bearer {secret}"


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


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not authorized(self.headers):
            json_response(self, 401, {"ok": False, "error": "Unauthorized"})
            return
        tz_name = os.environ.get("TIMEZONE", "Europe/Moscow")
        admins = admin_chat_ids()
        if not admins:
            json_response(self, 500, {"ok": False, "error": "ADMIN_CHAT_ID is not configured"})
            return
        rows = sheets.all_expenses()
        text = reports.balance_text(rows, tz_name)
        telegram = TelegramClient()
        for admin_chat_id in admins:
            telegram.send_message(admin_chat_id, text)
        json_response(self, 200, {"ok": True})
