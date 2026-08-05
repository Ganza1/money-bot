# Telegram Money Bot for Vercel

Production-ready Telegram-бот для учета денег в рублях в Google Sheets.

Стек:

- Python
- Vercel Serverless Functions
- Telegram Bot API через webhook
- FSM с хранением состояния в Google Sheets
- Inline-кнопки Telegram
- Google Sheets как основное хранилище
- `requests`, `gspread`, `google-auth`
- Таймзона `Europe/Moscow`

## Структура

```text
expense-bot/
├── api/
│   ├── bot.py
│   ├── weekly_report.py
│   └── monthly_report.py
├── services/
│   ├── telegram.py
│   ├── sheets.py
│   └── reports.py
├── keyboards/
│   └── inline.py
├── states/
│   └── constants.py
├── requirements.txt
├── vercel.json
├── .env.example
└── README.md
```

## Возможности

- Пошаговое добавление операций через `/add`
- Учет только в рублях
- Inline-кнопки для выбора типа операции, источника, категории и статуса
- Inline-кнопки для статуса операции: `Оплачен`, `На рассмотрении`, `Отказ`
- Хранение операций в листе `Operations`
- Автоматическое обновление сводки в листе `Итоги`
- Хранение текущих состояний пользователей в листе `States`
- Автоматическое создание заголовков при первом запуске
- Отчеты за сегодня, последние 7 дней и текущий месяц
- История последних 20 операций
- Удаление последней операции с подтверждением
- Уведомление всем администраторам из `ADMIN_CHAT_ID` после создания новой оплаты
- Автоматический еженедельный отчет по пятницам в 17:00 МСК
- Автоматический ежемесячный отчет 1 числа в 17:00 МСК за прошлый месяц

## Переменные окружения

Создайте переменные в Vercel Project Settings → Environment Variables:

```env
BOT_TOKEN=123456789:telegram_bot_token
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account","project_id":"..."}
GOOGLE_SHEET_ID=google_sheet_id
ADMIN_CHAT_ID=123456789
ADMIN_CHAT_ID2=987654321
ADMIN_CHAT_ID3=555555555
TIMEZONE=Europe/Moscow
```

Опционально, но рекомендуется:

```env
CRON_SECRET=long_random_secret
```

Если `CRON_SECRET` задан, cron-endpoints требуют заголовок:

```http
Authorization: Bearer long_random_secret
```

Vercel Cron обычно добавляет этот заголовок автоматически, если переменная `CRON_SECRET` настроена в проекте.

## Создание бота через BotFather

1. Откройте Telegram и найдите `@BotFather`.
2. Отправьте команду `/newbot`.
3. Укажите имя бота.
4. Укажите username, который заканчивается на `bot`.
5. Скопируйте токен. Это значение переменной `BOT_TOKEN`.

## Создание Google Sheets

1. Создайте новую таблицу в Google Sheets.
2. Скопируйте ID таблицы из URL.

Пример URL:

```text
https://docs.google.com/spreadsheets/d/1abcDEFghiJKLmnopQRstuVWxyz/edit
```

В этом примере:

```text
GOOGLE_SHEET_ID=1abcDEFghiJKLmnopQRstuVWxyz
```

Бот сам создаст листы:

- `Operations`
- `States`

## Создание Service Account

1. Откройте [Google Cloud Console](https://console.cloud.google.com/).
2. Создайте проект или выберите существующий.
3. Включите API:
   - Google Sheets API
   - Google Drive API
4. Откройте IAM & Admin → Service Accounts.
5. Создайте Service Account.
6. Перейдите во вкладку Keys.
7. Создайте JSON key.
8. Скачайте JSON-файл.

## Доступ Service Account к таблице

1. Откройте скачанный JSON.
2. Найдите поле `client_email`.
3. Откройте вашу Google Sheets-таблицу.
4. Нажмите Share.
5. Добавьте `client_email` с правом Editor.

## Подготовка `GOOGLE_SERVICE_ACCOUNT_JSON`

Вставьте весь JSON service account в переменную `GOOGLE_SERVICE_ACCOUNT_JSON` одной строкой.

Пример:

```env
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account","project_id":"my-project","private_key_id":"...","private_key":"-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n","client_email":"bot@my-project.iam.gserviceaccount.com","client_id":"...","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token","auth_provider_x509_cert_url":"https://www.googleapis.com/oauth2/v1/certs","client_x509_cert_url":"...","universe_domain":"googleapis.com"}
```

Важно: не удаляйте `\n` внутри `private_key`.

## Деплой через GitHub и Vercel

1. Создайте GitHub-репозиторий.
2. Загрузите содержимое папки `expense-bot` в репозиторий.
3. Откройте [Vercel Dashboard](https://vercel.com/dashboard).
4. Нажмите Add New → Project.
5. Импортируйте GitHub-репозиторий.
6. Framework Preset оставьте `Other`.
7. Добавьте переменные окружения.
8. Нажмите Deploy.

После деплоя Vercel выдаст production URL:

```text
https://your-project.vercel.app
```

## Установка webhook

Замените:

- `<BOT_TOKEN>` на токен из BotFather
- `<VERCEL_URL>` на production URL проекта

Откройте в браузере:

```text
https://api.telegram.org/bot<BOT_TOKEN>/setWebhook?url=<VERCEL_URL>/api/bot
```

Пример:

```text
https://api.telegram.org/bot123456789:ABC/setWebhook?url=https://expense-bot.vercel.app/api/bot
```

Проверить webhook:

```text
https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo
```

## Vercel Cron

В `vercel.json` настроены два cron-задания:

```json
{
  "crons": [
    {
      "path": "/api/weekly_report",
      "schedule": "0 14 * * 5"
    },
    {
      "path": "/api/monthly_report",
      "schedule": "0 14 1 * *"
    }
  ]
}
```

Vercel Cron работает в UTC.

- `0 14 * * 5` = каждую пятницу в 14:00 UTC = 17:00 МСК
- `0 14 1 * *` = 1 числа каждого месяца в 14:00 UTC = 17:00 МСК

Еженедельный отчет отправляет данные за последние 7 дней.
Ежемесячный отчет отправляет данные за прошлый месяц.

Автоматические отчеты и уведомления о новых оплатах отправляются всем администраторам. Можно указать несколько переменных: `ADMIN_CHAT_ID`, `ADMIN_CHAT_ID2`, `ADMIN_CHAT_ID3`. Внутри каждой переменной также можно перечислять ID через запятую или точку с запятой.

## Команды

```text
/start - приветствие и главное меню
/help - инструкция
/add - добавить операцию
/today - отчет за сегодня
/week - отчет за последние 7 дней
/month - отчет за текущий месяц
/history - последние 20 операций
/status - изменить статус одной из последних 10 операций
/delete_last - удалить последнюю запись
/time - текущее время Europe/Moscow
/id - показать chat_id
/debug - диагностика Google Sheets для администратора
```

Если `/history` вызывает пользователь из списка `ADMIN_CHAT_ID`, бот показывает последние 20 операций по всей таблице.
Если `/status` вызывает пользователь из списка `ADMIN_CHAT_ID`, бот позволяет менять статус последних 10 операций по всей таблице.

## Сценарий `/add`

1. Выбор типа операции:
   - Доход
   - Расход
2. Выбор источника:
   - Наличные
   - Карта
3. Ввод суммы в рублях
4. Ввод описания
5. Выбор категории
6. Выбор статуса
7. Сохранение в Google Sheets

Доход может вносить только администратор. Расход доступен обычным пользователям.

## Смена статуса после сохранения

Команда `/status` показывает последние 10 операций текущего пользователя.

1. Выберите нужную операцию.
2. Выберите новый статус:
   - Оплачен
   - На рассмотрении
   - Отказ
3. Бот обновит колонку `Статус` в листе `Operations`.

## Формат Google Sheets

Лист `Operations`:

```text
Дата
Время
Дата и время
Категория
Описание
Сумма
Тип оплаты
Статус
Chat ID
Timezone
Тип операции
```

Лист `Итоги` обновляется ботом автоматически после сохранения, удаления и смены статуса. Финансовые итоги считаются только по операциям со статусом `Оплачен`. Операции `На рассмотрении` и `Отказ` показываются отдельно и не меняют баланс.

Лист `States`:

```text
Chat ID
State
Data JSON
Updated At
```

## Проверка работы

1. Откройте бота в Telegram.
2. Отправьте `/start`.
3. Отправьте `/id` и проверьте chat_id.
4. Если нужно, вставьте этот chat_id в `ADMIN_CHAT_ID`. Для дополнительных админов используйте `ADMIN_CHAT_ID2`, `ADMIN_CHAT_ID3` и так далее.
5. Отправьте `/add`.
6. Добавьте тестовую операцию.
7. Проверьте, что строка появилась в листе `Operations`.
8. Отправьте `/today`.
9. Проверьте отчет.

## Локальная проверка синтаксиса

```bash
python -m compileall api services keyboards states
```

## Безопасность

- Токен Telegram не хранится в коде.
- JSON service account не хранится в коде.
- Google Sheet ID и Admin Chat ID берутся из environment variables.
- Cron endpoint можно защитить через `CRON_SECRET`.
- Некорректный ввод суммы не роняет бота.
- Ошибки API возвращаются как JSON и не ломают webhook Telegram.

## Примечания

- SQLite и локальный Excel не используются.
- FSM хранится в Google Sheets, поэтому состояние не теряется между serverless-вызовами.
- Для production используйте только production URL Vercel при установке webhook.
