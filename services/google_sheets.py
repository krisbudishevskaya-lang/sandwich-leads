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

Этап 2 (два коммерческих сценария — construction / panels):
    - добавлены колонки "Тип заявки" и "Тип панели" — намеренно
      ДОБАВЛЕНЫ В КОНЕЦ списка колонок, а не в середину (как в
      иллюстративном примере уточнения к ТЗ), чтобы не сдвинуть уже
      существующие реальные строки, записанные в таблицу до этого
      этапа. Порядок ранее существовавших 31 колонки не меняется;
    - все отображаемые в Google Sheets значения переведены на русский
      язык (объект, утеплитель, толщина, монтаж, срок, проект, тип
      клиента, бюджет, тип заявки, тип панели) через общий модуль
      services/display_labels — внутренние enum-значения бекенда при
      этом не меняются, перевод применяется только здесь, при
      формировании строки таблицы.

ВАЖНО: реальное подключение к Google Sheets требует пользовательских
credentials и не было выполнено в этой песочнице — библиотеки gspread/
google-auth здесь не установлены, а .env не содержит реальных ключей.
"""

import json
import os

from services.display_labels import (
    DEADLINE_LABELS,
    GATES_LABELS,
    INSTALLATION_LABELS,
    INSULATION_LABELS,
    LEAD_TYPE_LABELS_SHEETS,
    OBJECT_LABELS,
    PANEL_TYPE_LABELS,
    PARAMETER_SOURCE_LABELS,
    PROJECT_LABELS,
    THICKNESS_LABELS,
    USAGE_MODE_LABELS,
    WINDOWS_DOORS_LABELS,
    get_label,
)
from services.lead_calculator import BUDGET_LABELS, CLIENT_TYPE_LABELS

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_FALLBACK_PATH = os.path.join(_PROJECT_ROOT, "data", "leads_local_fallback.jsonl")

SHEET_NAME = "Лиды"

# Порядок первых 31 колонки соответствует Master ТЗ §45 и НЕ меняется
# (существующие реальные строки в таблице уже используют этот порядок).
# "Тип заявки" и "Тип панели" (Этап 2), а также колонки ниже (доп. ТЗ
# "Доделка калькуляторов") добавлены в КОНЕЦ списка, чтобы не сдвинуть
# ранее записанные строки.
SHEET_COLUMNS = [
    "Lead ID", "Дата", "Источник",
    "UTM Source", "UTM Medium", "UTM Campaign", "UTM Content", "UTM Term",
    "Регион", "Населенный пункт", "Сегмент",
    "Объект", "Площадь", "Длина", "Ширина", "Высота", "Утеплитель",
    "Толщина", "Монтаж", "Срок", "Проект", "Бюджет",
    "Имя", "Телефон", "Тип клиента", "Компания",
    "Предварительная стоимость (мин)", "Предварительная стоимость (макс)",
    "Статус", "Согласие на обработку ПД", "Согласие на передачу поставщикам",
    "Тип заявки", "Тип панели",
    "Режим использования", "Источник утеплителя", "Источник толщины",
    "Ворота", "Окна и двери",
]


def _record_to_row(record):
    """
    Преобразовать словарь лида в плоский список значений для строки
    таблицы. Порядок и количество значений всегда строго соответствуют
    SHEET_COLUMNS — пустые/неприменимые для данного lead_type поля
    записываются как "" и никогда не сдвигают остальные значения.
    Отображаемые значения — на русском (см. docstring выше).
    """
    lead_type = record.get("lead_type", "construction")
    return [
        record.get("lead_id", ""),
        record.get("created_at", ""),
        record.get("source", ""),
        record.get("utm_source") or "",
        record.get("utm_medium") or "",
        record.get("utm_campaign") or "",
        record.get("utm_content") or "",
        record.get("utm_term") or "",
        record.get("region") or "",
        record.get("city") or "",
        record.get("segment", ""),
        get_label(OBJECT_LABELS, record.get("object"), ""),
        record.get("area", ""),
        record.get("length") or "",
        record.get("width") or "",
        record.get("height") or "",
        get_label(INSULATION_LABELS, record.get("insulation"), ""),
        get_label(THICKNESS_LABELS, record.get("thickness"), ""),
        get_label(INSTALLATION_LABELS, record.get("installation"), ""),
        get_label(DEADLINE_LABELS, record.get("deadline"), ""),
        get_label(PROJECT_LABELS, record.get("project"), ""),
        get_label(BUDGET_LABELS, record.get("budget"), ""),
        record.get("name", ""),
        record.get("phone", ""),
        get_label(CLIENT_TYPE_LABELS, record.get("client_type"), ""),
        record.get("company_name") or "",
        record.get("price_min", ""),
        record.get("price_max", ""),
        record.get("status", ""),
        "Да" if record.get("consent_personal_data") else "Нет",
        "Да" if record.get("consent_share_with_suppliers") else "Нет",
        get_label(LEAD_TYPE_LABELS_SHEETS, lead_type, ""),
        get_label(PANEL_TYPE_LABELS, record.get("panel_type"), ""),
        get_label(USAGE_MODE_LABELS, record.get("usage_mode"), ""),
        get_label(PARAMETER_SOURCE_LABELS, record.get("insulation_source"), ""),
        get_label(PARAMETER_SOURCE_LABELS, record.get("thickness_source"), ""),
        get_label(GATES_LABELS, record.get("gates"), ""),
        get_label(WINDOWS_DOORS_LABELS, record.get("windows_doors"), ""),
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


def _ensure_headers(worksheet):
    """
    Если лист пуст (в первой строке нет данных), один раз записать
    заголовки из SHEET_COLUMNS перед первой записью лида. Если в первой
    строке уже что-то есть (заголовки или чьи-то данные) — ничего не
    делает и не трогает существующее содержимое листа.
    """
    try:
        first_row = worksheet.row_values(1)
    except Exception:
        # Не удалось прочитать первую строку — не блокируем запись
        # лида, просто пропускаем попытку добавить заголовки.
        return
    if not first_row:
        worksheet.append_row(SHEET_COLUMNS, value_input_option="RAW")


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
        _ensure_headers(worksheet)
        # value_input_option="RAW": Google Sheets не пытается сама
        # распознавать/переформатировать значения (даты, телефоны,
        # числа-как-текст и т.п.) — данные попадают в ячейки как есть,
        # без непредсказуемого авто-форматирования между заявками.
        worksheet.append_row(_record_to_row(record), value_input_option="RAW")
        return {"sheets_ok": True, "fallback_used": False, "reason": None}
    except Exception:
        # Никогда не поднимаем исключение выше и не логируем
        # содержимое credentials — только факт неудачи.
        _append_local_fallback(record)
        return {"sheets_ok": False, "fallback_used": True, "reason": "write_failed"}
