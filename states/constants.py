STATE_PAYMENT_TYPE = "payment_type"
STATE_CRYPTO_CURRENCY = "crypto_currency"
STATE_CRYPTO_WALLET = "crypto_wallet"
STATE_CURRENCY = "currency"
STATE_AMOUNT = "amount"
STATE_DESCRIPTION = "description"
STATE_CATEGORY = "category"
STATE_STATUS = "status"
STATE_CONFIRM = "confirm"
STATE_DELETE_CONFIRM = "delete_confirm"
STATE_STATUS_UPDATE = "status_update"
STATE_UNDO_SAVED = "undo_saved"

PAYMENT_CASH = "Наличные"
PAYMENT_CARD = "Безналичные"
PAYMENT_CRYPTO = "Крипта"

CURRENCY_RUB = "RUB"
FIAT_CURRENCIES = (CURRENCY_RUB,)

CRYPTO_CURRENCIES = ("BTC", "ETH", "USDT")

CATEGORIES = (
    "Подписки",
    "Зарплата",
    "Офис",
    "Обучение",
    "Маркетинг",
    "Прочее",
)

STATUSES = (
    "Оплачен",
    "На рассмотрении",
    "Отказ",
)

PAYMENT_GROUPS = (
    "Наличные RUB",
    "Безналичные RUB",
    "BTC",
    "ETH",
    "USDT",
)
