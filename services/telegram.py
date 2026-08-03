import os

import requests


class TelegramError(RuntimeError):
    pass


class TelegramClient:
    def __init__(self, token=None):
        self.token = token or os.environ.get("BOT_TOKEN")
        if not self.token:
            raise TelegramError("BOT_TOKEN is not configured")
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    def request(self, method, payload):
        response = requests.post(f"{self.base_url}/{method}", json=payload, timeout=20)
        if not response.ok:
            raise TelegramError(f"Telegram API error {response.status_code}: {response.text[:500]}")
        data = response.json()
        if not data.get("ok"):
            raise TelegramError(f"Telegram API returned not ok: {data}")
        return data.get("result")

    def send_message(self, chat_id, text, reply_markup=None, parse_mode=None):
        payload = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        if parse_mode:
            payload["parse_mode"] = parse_mode
        return self.request("sendMessage", payload)

    def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            return self.request("editMessageText", payload)
        except TelegramError:
            return self.send_message(chat_id, text, reply_markup=reply_markup)

    def answer_callback_query(self, callback_query_id, text=None, show_alert=False):
        payload = {"callback_query_id": callback_query_id, "show_alert": show_alert}
        if text:
            payload["text"] = text
        return self.request("answerCallbackQuery", payload)
