"""
Сервис интеграции с Telegram Bot API.

Назначение (согласно Master ТЗ, раздел 51):
    - отправка уведомления менеджеру о новой заявке (сегмент, объект,
      параметры, контакты, температура и т.д.) сразу после успешного
      создания лида.

PROMPT 8 — реализация:
    - используется только стандартная библиотека Python (urllib) —
      простой HTTP-запрос к Telegram Bot API без дополнительных
      зависимостей;
    - токен бота и chat_id берутся только из переменных окружения
      (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID), никогда не хранятся
      в коде;
    - если Telegram не настроен или запрос завершился ошибкой —
      исключение никогда не поднимается наружу и не ломает создание
      лида (лид уже сохранён к моменту отправки уведомления);
    - текст токена никогда не логируется и не попадает в исключения,
      которые могли бы всплыть наружу.

Этап 2 (два коммерческих сценария — construction / panels):
    build_lead_notification_text() теперь выбирает шаблон по
    record["lead_type"]: для "construction" — прежний шаблон §51 с
    добавленной строкой "Тип заявки" (см. уточнение к ТЗ, §16), для
    "panels" — отдельный шаблон под сэндвич-панели как материал.
    Общие человекочитаемые подписи вынесены в services/display_labels
    (используются и здесь, и в services/google_sheets), чтобы не
    дублировать один и тот же словарь в двух местах.

ВАЖНО: реальная отправка в Telegram требует пользовательских
TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID. Логика отправки протестирована
через мок HTTP-слоя (см. отчёты по этапам).
"""

import json
import logging
import os
import urllib.error
import urllib.request

from services.display_labels import (
    DEADLINE_LABELS,
    INSTALLATION_LABELS,
    INSULATION_LABELS,
    LEAD_TYPE_LABELS_TELEGRAM,
    OBJECT_LABELS,
    PANEL_TYPE_LABELS,
    PROJECT_LABELS,
    THICKNESS_LABELS,
)
from services.lead_calculator import BUDGET_LABELS, CLIENT_TYPE_LABELS

logger = logging.getLogger(__name__)

TELEGRAM_API_URL_TEMPLATE = "https://api.telegram.org/bot{token}/sendMessage"
TELEGRAM_TIMEOUT_SECONDS = 5

def determine_temperature(deadline):
    """
    Определить температуру лида по сроку (Master ТЗ §43):
        HOT  - как можно скорее / в течение месяца
        WARM - 1-3 месяца
        COLD - более 3 месяцев / пока изучаю цены

    Используется только для текста Telegram-уведомления. Менеджер
    может изменить температуру после звонка — здесь фиксируется
    только исходное системное значение.
    """
    if deadline in ("asap", "within_month"):
        return "HOT"
    if deadline == "1_3_months":
        return "WARM"
    return "COLD"


def _fmt_num(value):
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _format_size_line(record):
    length = _fmt_num(record.get("length"))
    width = _fmt_num(record.get("width"))
    height = _fmt_num(record.get("height"))
    if length is not None and width is not None and height is not None:
        return "{} × {} × {} м".format(length, width, height)
    if height is not None:
        return "площадь указана вручную, высота {} м".format(height)
    return "—"


def _build_construction_notification_text(record):
    """
    Шаблон уведомления для строительства (Master ТЗ §51, дополнен
    строкой "Тип заявки" и "Тип клиента" по уточнению — Этап 2, §16/§23).
    """
    segment = (record.get("segment") or "—").upper()
    object_label = OBJECT_LABELS.get(record.get("object"), record.get("object") or "—")
    insulation_label = INSULATION_LABELS.get(record.get("insulation"), record.get("insulation") or "—")
    thickness_label = THICKNESS_LABELS.get(record.get("thickness"), record.get("thickness") or "—")
    installation_label = INSTALLATION_LABELS.get(record.get("installation"), record.get("installation") or "—")
    deadline_label = DEADLINE_LABELS.get(record.get("deadline"), record.get("deadline") or "—")
    project_label = PROJECT_LABELS.get(record.get("project"), record.get("project") or "—")
    client_type_label = CLIENT_TYPE_LABELS.get(record.get("client_type"), record.get("client_type") or "—")

    budget_value = record.get("budget")
    budget_label = BUDGET_LABELS.get(budget_value, "Не указан") if budget_value else "Не указан"

    area = _fmt_num(record.get("area")) or "—"
    size_line = _format_size_line(record)
    price_line = "{} – {}".format(
        record.get("price_min_formatted") or "—",
        record.get("price_max_formatted") or "—",
    )
    temperature = determine_temperature(record.get("deadline"))

    lines = [
        "🔥  НОВЫЙ ЛИД #{}".format(record.get("lead_id") or "—"),
        "",
        "Тип заявки: {}".format(LEAD_TYPE_LABELS_TELEGRAM.get("construction")),
        "",
        "Сегмент: {}".format(segment),
        "Объект: {}".format(object_label),
        "Площадь: {} м²".format(area),
        "",
        "Размер: {}".format(size_line),
        "Утеплитель: {}".format(insulation_label),
        "Толщина: {}".format(thickness_label),
        "Монтаж: {}".format(installation_label),
        "",
        "Город: {}".format(record.get("city") or "—"),
        "Срок: {}".format(deadline_label),
        "Проект: {}".format(project_label),
        "Бюджет: {}".format(budget_label),
        "",
        "Предварительный расчет:",
        price_line,
        "",
        "Клиент: {}".format(record.get("name") or "—"),
        "Телефон: {}".format(record.get("phone") or "—"),
        "Тип клиента: {}".format(client_type_label),
        "",
        "Температура: {}".format(temperature),
    ]
    return "\n".join(lines)


def _build_panel_notification_text(record):
    """
    Шаблон уведомления для сэндвич-панелей как материала (Этап 2, §24).

    Поля "Монтаж", "Срок", "Проект", "Регион" в этом сценарии
    калькулятором не собираются (см. services/lead_calculator) —
    соответствующие строки в шаблон не включаются, чтобы не показывать
    менеджеру пустые/неприменимые поля.
    """
    panel_type_label = PANEL_TYPE_LABELS.get(record.get("panel_type"), record.get("panel_type") or "—")
    insulation_label = INSULATION_LABELS.get(record.get("insulation"), record.get("insulation") or "—")
    thickness_label = THICKNESS_LABELS.get(record.get("thickness"), record.get("thickness") or "—")
    client_type_label = CLIENT_TYPE_LABELS.get(record.get("client_type"), record.get("client_type") or "—")

    area = _fmt_num(record.get("area")) or "—"
    price_line = "{} – {}".format(
        record.get("price_min_formatted") or "—",
        record.get("price_max_formatted") or "—",
    )
    per_m2_line = "{} – {}".format(
        record.get("price_per_m2_min_formatted") or "—",
        record.get("price_per_m2_max_formatted") or "—",
    )

    lines = [
        "🔥  НОВЫЙ ЛИД #{}".format(record.get("lead_id") or "—"),
        "",
        "Тип заявки: {}".format(LEAD_TYPE_LABELS_TELEGRAM.get("panels")),
        "",
        "Тип панели: {}".format(panel_type_label),
        "Площадь: {} м²".format(area),
        "Утеплитель: {}".format(insulation_label),
        "Толщина: {}".format(thickness_label),
    ]
    if record.get("city"):
        lines.append("Город: {}".format(record.get("city")))
    lines += [
        "",
        "Предварительный расчет:",
        price_line,
        "Ориентировочно: {}".format(per_m2_line),
        "",
        "Клиент: {}".format(record.get("name") or "—"),
        "Телефон: {}".format(record.get("phone") or "—"),
        "Тип клиента: {}".format(client_type_label),
    ]
    return "\n".join(lines)


def build_lead_notification_text(record):
    """
    Собрать текст уведомления из готовой записи лида (см.
    services/lead_calculator.build_lead_record). Шаблон выбирается по
    record["lead_type"]: "panels" -> сэндвич-панели, иначе (в т.ч. для
    старых вызовов без lead_type) -> строительство (Master ТЗ §51).
    """
    if record.get("lead_type") == "panels":
        return _build_panel_notification_text(record)
    return _build_construction_notification_text(record)


def _safe_error_description(error):
    """
    Безопасно извлечь описание ошибки из ответа Telegram API для
    логов. Тело ответа Telegram (например: "Bad Request: chat not
    found", "Forbidden: bot was blocked by the user") никогда не
    содержит наш токен — токен есть только в URL запроса, который
    здесь не читается и не логируется. Результат обрезается до
    разумной длины.
    """
    try:
        raw = error.read()
    except Exception:
        return "(тело ответа недоступно)"
    if not raw:
        return "(пустой ответ)"
    try:
        payload = json.loads(raw.decode("utf-8", errors="replace"))
        description = payload.get("description")
        if description:
            return str(description)[:200]
    except Exception:
        pass
    return raw.decode("utf-8", errors="replace")[:200]


def send_lead_notification(record):
    """
    Отправить уведомление о новом лиде менеджеру в Telegram.

    Возвращает {"sent": bool, "reason": str|None}. Никогда не
    выбрасывает исключение наружу — ошибка или недоступность Telegram
    не должна ронять создание лида и не должна возвращать пользователю
    ошибку API. Токен никогда не логируется и не попадает в текст
    исключения, которое могло бы куда-то всплыть — в логи попадает
    только HTTP-статус и безопасное описание ошибки от Telegram.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        return {"sent": False, "reason": "not_configured"}

    try:
        text = build_lead_notification_text(record)
        url = TELEGRAM_API_URL_TEMPLATE.format(token=token)
        body = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
        http_request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(http_request, timeout=TELEGRAM_TIMEOUT_SECONDS) as response:
            status = getattr(response, "status", None) or response.getcode()
            if 200 <= status < 300:
                return {"sent": True, "reason": None}
            logger.warning("Telegram sendMessage: неожиданный статус %s без исключения.", status)
            return {"sent": False, "reason": "http_error_{}".format(status)}
    except urllib.error.HTTPError as error:
        description = _safe_error_description(error)
        logger.warning(
            "Telegram sendMessage не доставлено (lead_id=%s): HTTP %s — %s",
            record.get("lead_id"), error.code, description,
        )
        return {"sent": False, "reason": "http_error_{}".format(error.code)}
    except urllib.error.URLError as error:
        logger.warning(
            "Telegram sendMessage: сетевая ошибка (lead_id=%s) — %s",
            record.get("lead_id"), getattr(error, "reason", error),
        )
        return {"sent": False, "reason": "network_error"}
    except Exception:
        # Никогда не поднимаем исключение выше и не логируем токен
        # или тело ошибки — только факт неудачи.
        logger.warning(
            "Telegram sendMessage: непредвиденная ошибка при отправке (lead_id=%s).",
            record.get("lead_id"),
        )
        return {"sent": False, "reason": "request_failed"}
