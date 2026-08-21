STATE_OPERATION_TYPE = "operation_type"
STATE_PAYMENT_TYPE = "payment_type"
STATE_TRANSFER_DIRECTION = "transfer_direction"
STATE_BANK = "bank"
STATE_BANK_CUSTOM = "bank_custom"
STATE_CARD_PHONE = "card_phone"
STATE_AMOUNT = "amount"
STATE_DESCRIPTION = "description"
STATE_CATEGORY = "category"
STATE_STATUS = "status"
STATE_CONFIRM = "confirm"
STATE_DELETE_CONFIRM = "delete_confirm"
STATE_STATUS_UPDATE = "status_update"
STATE_UNDO_SAVED = "undo_saved"

OPERATION_INCOME = "Доход"
OPERATION_EXPENSE = "Расход"
OPERATION_TRANSFER = "Перевод"

PAYMENT_CASH = "Наличные"
PAYMENT_CARD = "Карта"

TRANSFER_CASH_TO_CARD = "Наличные → Карта"
TRANSFER_CARD_TO_CASH = "Карта → Наличные"

CURRENCY_RUB = "RUB"

BANKS = (
    "Сбербанк",
    "ВТБ",
    "Газпромбанк",
    "Альфа-Банк",
    "Промсвязьбанк",
    "Совкомбанк",
    "Т-Банк",
    "Другой банк",
)

CATEGORIES = (
    "Подписки",
    "Зарплата",
    "Офис",
    "М",
    "Агенты",
    "HR",
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
    "Карта",
    "Наличные",
)
