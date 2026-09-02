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

Шаблон уведомления (Master ТЗ §51) воспроизведён максимально точно:
поля и их порядок соответствуют примеру из ТЗ. Метки для отображения
внутренних значений калькулятора (например insulation="pir" -> "PIR")
определены здесь же — они не меняют и не дублируют сам калькулятор
или Price Engine, а только форматируют уже готовую запись лида для
человекочитаемого сообщения.

ВАЖНО: реальная отправка в Telegram требует пользовательских
TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID и не была выполнена в этой
песочнице — сеть отключена, а .env не содержит реальных значений.
Логика отправки протестирована через мок HTTP-слоя (см. отчёт).
"""

import json
import os
import urllib.error
import urllib.request

TELEGRAM_API_URL_TEMPLATE = "https://api.telegram.org/bot{token}/sendMessage"
TELEGRAM_TIMEOUT_SECONDS = 5

# Отображаемые подписи для значений калькулятора (только для текста
# уведомления). Сами значения ("garage", "pir", "within_month" и т.д.)
# заданы в static/js/calculator.js и не меняются — здесь только их
# человекочитаемое представление для менеджера.

OBJECT_LABELS = {
    "garage": "Гараж",
    "workshop": "Мастерская",
    "sto": "СТО",
    "warehouse": "Склад",
    "hangar": "Ангар",
    "production": "Производство",
    "other": "Другое",
}

INSULATION_LABELS = {
    "mineral_wool": "Минвата",
    "pir": "PIR",
    "pur": "PUR",
    "unknown": "Не знаю",
}

THICKNESS_LABELS = {
    "50": "50 мм",
    "80": "80 мм",
    "100": "100 мм",
    "120": "120 мм",
    "150": "150 мм",
    "200": "200 мм",
    "unknown": "Не знаю",
}

INSTALLATION_LABELS = {
    "yes": "Да",
    "no": "Нет",
    "unknown": "Пока не знаю",
}

DEADLINE_LABELS = {
    "asap": "Как можно скорее",
    "within_month": "В течение месяца",
    "1_3_months": "1-3 месяца",
    "more_3_months": "Более 3 месяцев",
    "researching": "Пока изучаю цены",
}

PROJECT_LABELS = {
    "yes": "Да",
    "no": "Нет",
    "in_progress": "В разработке",
}

BUDGET_LABELS = {
    "under_500k": "До 500 тыс. ₽",
    "500k_1m": "500 тыс.-1 млн ₽",
    "1m_3m": "1-3 млн ₽",
    "3m_5m": "3-5 млн ₽",
    "over_5m": "Более 5 млн ₽",
    "unknown": "Не знаю",
}


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


def build_lead_notification_text(record):
    """
    Собрать текст уведомления по шаблону Master ТЗ §51 из готовой
    записи лида (см. services/lead_calculator.build_lead_record).
    """
    segment = (record.get("segment") or "—").upper()
    object_label = OBJECT_LABELS.get(record.get("object"), record.get("object") or "—")
    insulation_label = INSULATION_LABELS.get(record.get("insulation"), record.get("insulation") or "—")
    thickness_label = THICKNESS_LABELS.get(record.get("thickness"), record.get("thickness") or "—")
    installation_label = INSTALLATION_LABELS.get(record.get("installation"), record.get("installation") or "—")
    deadline_label = DEADLINE_LABELS.get(record.get("deadline"), record.get("deadline") or "—")
    project_label = PROJECT_LABELS.get(record.get("project"), record.get("project") or "—")

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
        "",
        "Температура: {}".format(temperature),
    ]
    return "\n".join(lines)


def send_lead_notification(record):
    """
    Отправить уведомление о новом лиде менеджеру в Telegram.

    Возвращает {"sent": bool, "reason": str|None}. Никогда не
    выбрасывает исключение наружу — ошибка или недоступность Telegram
    не должна ронять создание лида и не должна возвращать пользователю
    ошибку API. Токен никогда не логируется и не попадает в текст
    исключения, которое могло бы куда-то всплыть.
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
            return {"sent": False, "reason": "http_error_{}".format(status)}
    except Exception:
        # Никогда не поднимаем исключение выше и не логируем токен
        # или тело ошибки — только факт неудачи.
        return {"sent": False, "reason": "request_failed"}
