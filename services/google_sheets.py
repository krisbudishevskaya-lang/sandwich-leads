"""
Сервис интеграции с Google Sheets.

Назначение (согласно Master ТЗ, раздел 45-49):
    - запись новых заявок в лист "Лиды" (append_lead);
    - структура строки соответствует колонкам, известным на момент
      отправки формы (раздел 45), включая UTM Source/Medium/Campaign/
      Content/Term (PROMPT 7 — utm_content и utm_term добавлены сверх
      трёх UTM-колонок, явно перечисленных в §45, по прямому заданию
      PROMPT 7). Колонки, которые заполняются позже вручную менеджером
      после звонка (Температура, Готовность, Поставщик 1-5, Цена
      продажи, Комментарий — разделы 42-50), сюда не пишутся: они не
      существуют на этапе подачи заявки.

PROMPT 6 — реализация:
    - используется библиотека gspread + google-auth (указаны в
      requirements.txt для продакшена), импортируются ЛЕНИВО (внутри
      функции), чтобы отсутствие этих пакетов в песочнице не ломало
      остальное приложение;
    - credentials берутся только из переменных окружения
      (GOOGLE_SHEETS_CREDENTIALS_JSON, GOOGLE_SHEETS_SPREADSHEET_ID),
      никогда не хранятся в коде;
    - если credentials не заданы или запись в Google Sheets по любой
      причине не удалась — лид не теряется: используется локальный
      резервный журнал data/leads_local_fallback.jsonl. Это ограничение
      явно описано в README и в отчётах по каждому этапу;
    - никакая ошибка Google Sheets (включая credentials) никогда не
      передаётся пользователю и не приводит к падению запроса.

ВАЖНО: реальное подключение к Google Sheets требует пользовательских
credentials и не было выполнено в этой песочнице — библиотеки gspread/
google-auth здесь не установлены, а .env не содержит реальных ключей.
"""

import json
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_FALLBACK_PATH = os.path.join(_PROJECT_ROOT, "data", "leads_local_fallback.jsonl")

SHEET_NAME = "Лиды"

# Порядок колонок соответствует Master ТЗ §45, ограничен полями,
# известными на момент подачи заявки (см. docstring выше).
SHEET_COLUMNS = [
    "Lead ID", "Дата", "Источник",
    "UTM Source", "UTM Medium", "UTM Campaign", "UTM Content", "UTM Term",
    "Регион", "Населенный пункт", "Сегмент",
    "Объект", "Площадь", "Длина", "Ширина", "Высота", "Утеплитель",
    "Толщина", "Монтаж", "Срок", "Проект", "Бюджет",
    "Имя", "Телефон", "Тип клиента", "Компания",
    "Предварительная стоимость (мин)", "Предварительная стоимость (макс)",
    "Статус", "Согласие на обработку ПД", "Согласие на передачу поставщикам",
]


def _record_to_row(record):
    """Преобразовать словарь лида в плоский список значений для строки таблицы."""
    return [
        record.get("lead_id", ""),
        record.get("created_at", ""),
        record.get("source", ""),
        record.get("utm_source") or "",
        record.get("utm_medium") or "",
        record.get("utm_campaign") or "",
        record.get("utm_content") or "",
        record.get("utm_term") or "",
        record.get("region", ""),
        record.get("city", ""),
        record.get("segment", ""),
        record.get("object", ""),
        record.get("area", ""),
        record.get("length", ""),
        record.get("width", ""),
        record.get("height", ""),
        record.get("insulation", ""),
        record.get("thickness", ""),
        record.get("installation", ""),
        record.get("deadline", ""),
        record.get("project", ""),
        record.get("budget", ""),
        record.get("name", ""),
        record.get("phone", ""),
        record.get("client_type", ""),
        record.get("company_name", ""),
        record.get("price_min", ""),
        record.get("price_max", ""),
        record.get("status", ""),
        "Да" if record.get("consent_personal_data") else "Нет",
        "Да" if record.get("consent_share_with_suppliers") else "Нет",
    ]


def _append_local_fallback(record):
    """
    Резервная локальная запись лида (JSON Lines), используется когда
    реальное подключение к Google Sheets недоступно или завершилось
    ошибкой, чтобы не терять лид в MVP-тесте.
    """
    try:
        os.makedirs(os.path.dirname(LOCAL_FALLBACK_PATH), exist_ok=True)
        with open(LOCAL_FALLBACK_PATH, "a", encoding="utf-8") as fallback_file:
            fallback_file.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False


def append_lead(record):
    """
    Записать лид в Google Sheets (лист "Лиды").

    Возвращает словарь {"sheets_ok": bool, "fallback_used": bool,
    "reason": str|None}. Никогда не выбрасывает исключение и никогда
    не логирует credentials или их содержимое — вызывающий код может
    безопасно игнорировать результат (лид в любом случае не теряется
    благодаря локальному резервному журналу).
    """
    credentials_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON")
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")

    if not credentials_json or not spreadsheet_id:
        _append_local_fallback(record)
        return {"sheets_ok": False, "fallback_used": True, "reason": "not_configured"}

    try:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        info = json.loads(credentials_json)
        credentials = Credentials.from_service_account_info(info, scopes=scopes)
        client = gspread.authorize(credentials)
        worksheet = client.open_by_key(spreadsheet_id).worksheet(SHEET_NAME)
        worksheet.append_row(_record_to_row(record), value_input_option="USER_ENTERED")
        return {"sheets_ok": True, "fallback_used": False, "reason": None}
    except Exception:
        # Никогда не поднимаем исключение выше и не логируем
        # содержимое credentials — только факт неудачи.
        _append_local_fallback(record)
        return {"sheets_ok": False, "fallback_used": True, "reason": "write_failed"}
