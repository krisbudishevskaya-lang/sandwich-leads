"""
Сервис расчёта Lead ID, подготовки данных заявки и Price Engine.

Назначение (согласно Master ТЗ, разделы 6, 24-33, 39-42, 45):
    - расчёт предварительной стоимости объекта (Price Engine MVP);
    - генерация уникального Lead ID (формат "SL-XXXXXXX", Master ТЗ §51);
    - валидация контактных данных и сборка структуры лида из данных
      калькулятора и контактной формы перед сохранением (PROMPT 6).

Price Engine (PROMPT 4):
    Принимает структурированные параметры калькулятора, валидирует их
    и возвращает структурированный результат расчёта. Все цены и
    коэффициенты берутся исключительно из config/pricing.py, которые,
    в свою очередь, взяты дословно из Master ТЗ (разделы 24-33).
    Формула не дублируется в JavaScript — единственный источник
    истины для расчёта находится здесь, на backend.

Контактная форма и лид (PROMPT 6):
    build_lead_record() валидирует контактные данные и данные
    калькулятора на backend (frontend-валидация недостаточна),
    заново вызывает calculate_price_estimate() как единственный
    источник истины для стоимости (цена не пересчитывается на
    frontend и не принимается «на слово» от клиента), и собирает
    итоговую структуру лида, готовую для записи в Google Sheets.

UTM и источник лида (PROMPT 7):
    build_lead_record() опционально принимает utm_payload —
    UTM-метки, прочитанные frontend'ом из URL при первой загрузке
    страницы и переданные вместе с лидом при отправке. Значения
    валидируются и очищаются (_sanitize_utm) отдельно от остальной
    формы: некорректное значение конкретного UTM-поля не блокирует
    отправку лида — UTM это аналитика, а не обязательные данные.
"""

import re
import time
from datetime import datetime, timezone

from config import pricing


class PriceEngineError(ValueError):
    """Невалидные входные данные для расчёта стоимости."""


def _parse_positive_number(raw, field_name):
    """Привести значение к положительному float или выбросить ошибку."""
    if raw is None:
        raise PriceEngineError("Не указано значение: {}.".format(field_name))
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise PriceEngineError("Некорректное значение: {}.".format(field_name))
    if not (value == value) or value in (float("inf"), float("-inf")):
        # value == value ложно только для NaN
        raise PriceEngineError("Некорректное значение: {}.".format(field_name))
    if value <= 0:
        raise PriceEngineError("Значение должно быть положительным: {}.".format(field_name))
    return value


def determine_region(city_raw):
    """
    Определить регион (и его коэффициент) по свободному текстовому
    полю "Город / населенный пункт" из калькулятора.

    MVP работает только с Москвой и Московской областью (Master ТЗ,
    раздел 9 и 31). Так как калькулятор на этапе PROMPT 3 намеренно
    собирает город обычным текстовым полем без геокодинга ("не нужно
    сейчас подключать карты, геокодинг... регион можно определить
    позже, на этом этапе не усложнять"), регион определяется простой
    эвристикой по тексту, без придумывания новых коэффициентов —
    используются только два коэффициента региона, прямо заданные в ТЗ
    (раздел 31): Москва (1.00) и Московская область (1.05).

    Правило: если в названии явно упоминается "москва" и при этом
    нет слова "область"/"обл" — это Москва; в остальных случаях
    (в том числе любой другой населённый пункт Подмосковья) —
    Московская область, так как MVP не работает за пределами региона.
    """
    normalized = (city_raw or "").strip().lower()
    if not normalized:
        raise PriceEngineError("Не указан город.")

    is_moscow_city = "москва" in normalized and "област" not in normalized and "обл" not in normalized

    if is_moscow_city:
        region_key = "moscow"
        region_label = "Москва"
    else:
        region_key = "moscow_region"
        region_label = "Московская область"

    coefficient = pricing.get_region_coefficient(region_key)
    return region_label, coefficient


def _round_to(value, step):
    return round(value / step) * step


def _format_total(value):
    """
    Единый формат отображения итоговой стоимости (Master ТЗ, раздел
    34): без избыточной точности, в млн ₽ при крупных суммах.
    """
    if value >= 1_000_000:
        rounded = _round_to(value, 100_000)
        millions = rounded / 1_000_000
        return "{:.1f}".format(millions).replace(".", ",") + " млн ₽"
    rounded = int(_round_to(value, 10_000))
    return "{:,}".format(rounded).replace(",", " ") + " ₽"


def _format_per_m2(value):
    rounded = int(_round_to(value, 100))
    return "{:,}".format(rounded).replace(",", " ") + " ₽/м²"


def calculate_price_estimate(payload):
    """
    Рассчитать предварительную стоимость объекта.

    payload — словарь с ключами:
        object        — тип объекта (значение из OBJECT_OPTIONS)
        area           — площадь, м² (число)
        height          — высота, м (число)
        insulation     — тип утеплителя (значение из INSULATION_OPTIONS)
        thickness      — толщина панели (значение из THICKNESS_OPTIONS)
        installation   — нужен ли монтаж (значение из INSTALLATION_OPTIONS)
        city           — город / населённый пункт (строка)

    Возвращает словарь с результатом расчёта (см. ниже) или выбрасывает
    PriceEngineError с понятным сообщением при невалидных данных.
    """
    if not isinstance(payload, dict):
        raise PriceEngineError("Некорректный формат данных.")

    object_type = payload.get("object")
    base_range = pricing.get_base_price_range(object_type)
    if base_range is None:
        raise PriceEngineError("Неизвестный тип объекта.")
    base_min, base_max = base_range

    area = _parse_positive_number(payload.get("area"), "площадь")
    height = _parse_positive_number(payload.get("height"), "высота")

    area_coefficient = pricing.get_area_coefficient(area)
    if area_coefficient is None:
        raise PriceEngineError("Не удалось определить коэффициент площади.")

    height_coefficient = pricing.get_height_coefficient(height)
    if height_coefficient is None:
        raise PriceEngineError("Не удалось определить коэффициент высоты.")

    insulation = payload.get("insulation")
    insulation_coefficient = pricing.get_insulation_coefficient(insulation)
    if insulation_coefficient is None:
        raise PriceEngineError("Неизвестный тип утеплителя.")

    thickness = payload.get("thickness")
    thickness_coefficient = pricing.get_thickness_coefficient(thickness)
    if thickness_coefficient is None:
        raise PriceEngineError("Неизвестная толщина панели.")

    installation = payload.get("installation")
    installation_coefficient = pricing.get_installation_coefficient(installation)
    if installation_coefficient is None:
        raise PriceEngineError("Неизвестный вариант монтажа.")

    region_label, region_coefficient = determine_region(payload.get("city"))

    coefficient_product = (
        area_coefficient
        * height_coefficient
        * insulation_coefficient
        * thickness_coefficient
        * installation_coefficient
        * region_coefficient
    )

    # §32: Базовая цена × коэффициенты — применяем к обоим концам
    # базового диапазона цены (§25 задаёт цену как диапазон ₽/м²).
    per_m2_min = base_min * coefficient_product
    per_m2_max = base_max * coefficient_product

    total_min = per_m2_min * area
    total_max = per_m2_max * area

    # §33: дополнительный диапазон ±10% вокруг итоговой суммы.
    total_min = total_min * pricing.RANGE_LOWER_MULTIPLIER
    total_max = total_max * pricing.RANGE_UPPER_MULTIPLIER

    if total_min < 0 or total_max < 0:
        # Не должно происходить при валидных положительных входных
        # данных и положительных коэффициентах, но проверяем явно.
        raise PriceEngineError("Не удалось рассчитать стоимость.")

    return {
        "ok": True,
        "area": area,
        "price_min": round(total_min),
        "price_max": round(total_max),
        "price_per_m2_min": round(per_m2_min),
        "price_per_m2_max": round(per_m2_max),
        "price_min_formatted": _format_total(total_min),
        "price_max_formatted": _format_total(total_max),
        "price_per_m2_min_formatted": _format_per_m2(per_m2_min),
        "price_per_m2_max_formatted": _format_per_m2(per_m2_max),
        "region": region_label,
    }


# ==========================================================================
# PROMPT 6 — контактная форма и сбор квалифицированного лида
# ==========================================================================


class LeadValidationError(ValueError):
    """Невалидные данные контактной формы или отсутствующие данные калькулятора."""


# Master ТЗ, §39: "Кто вы?"
CLIENT_TYPE_LABELS = {
    "individual": "Частное лицо",
    "entrepreneur": "ИП",
    "company": "Компания",
    "undecided": "Не определился",
}

# Master ТЗ, §40: бюджет (не влияет на расчёт, используется для квалификации)
BUDGET_LABELS = {
    "under_500k": "До 500 тыс. ₽",
    "500k_1m": "500 тыс.-1 млн ₽",
    "1m_3m": "1-3 млн ₽",
    "3m_5m": "3-5 млн ₽",
    "over_5m": "Более 5 млн ₽",
    "unknown": "Не знаю",
}

_PHONE_RE = re.compile(r"^\+?\d{10,15}$")


def _validate_name(raw):
    name = (raw or "").strip()
    if not name:
        raise LeadValidationError("Введите имя.")
    if len(name) < 2:
        raise LeadValidationError("Введите корректное имя.")
    if len(name) > 100:
        raise LeadValidationError("Слишком длинное имя.")
    return name


def _validate_phone(raw):
    """
    Нормализовать и проверить телефон.

    Не определяем оператора/регион номера (это прямо запрещено
    инструкцией PROMPT 6) — только базовая проверка формата: после
    удаления пробелов/скобок/дефисов должно остаться от 10 до 15
    цифр, опционально с ведущим "+".
    """
    raw_value = (raw or "").strip()
    if not raw_value:
        raise LeadValidationError("Введите номер телефона.")
    normalized = re.sub(r"[^\d+]", "", raw_value)
    if not _PHONE_RE.match(normalized):
        raise LeadValidationError("Введите корректный номер телефона.")
    return normalized


def _validate_client_type(raw):
    if not raw:
        return "undecided"
    if raw not in CLIENT_TYPE_LABELS:
        raise LeadValidationError("Некорректный тип клиента.")
    return raw


def _validate_budget(raw):
    if not raw:
        return None
    if raw not in BUDGET_LABELS:
        raise LeadValidationError("Некорректное значение бюджета.")
    return raw


def _validate_company_name(raw, client_type):
    name = (raw or "").strip()
    if client_type == "company" and not name:
        raise LeadValidationError("Укажите название компании.")
    if len(name) > 200:
        raise LeadValidationError("Слишком длинное название компании.")
    return name or None


def determine_segment(area):
    """
    Определить сегмент клиента по площади объекта (Master ТЗ, §3):
    до 100 м² — B2C, 100-500 м² — Small Business, 500+ м² — B2B.
    """
    if area < 100:
        return "B2C"
    if area < 500:
        return "Small Business"
    return "B2B"


def generate_lead_id():
    """
    Сгенерировать Lead ID в формате "SL-XXXXXXX" (Master ТЗ §51,
    пример "SL-0001042").

    Ограничение MVP: в проекте намеренно нет базы данных со сквозным
    счётчиком (Master ТЗ прямо исключает PostgreSQL на этом этапе), а
    единственное постоянное хранилище (Google Sheets) не гарантирует
    атомарного «следующего номера» без гонок между запросами. Поэтому
    ID строится из последних 7 цифр текущего времени в миллисекундах —
    практически уникален для ожидаемого объёма MVP-теста (единицы или
    десятки заявок), но не даёт математической гарантии уникальности
    при экстремально высокой одновременной нагрузке. Телефон и любые
    другие персональные данные в ID не включаются.
    """
    millis = int(time.time() * 1000)
    digits = millis % 10_000_000
    return "SL-{:07d}".format(digits)


_UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")
_UTM_VALUE_RE = re.compile(r"^[\w\-.:/%,+ ]{1,100}$", re.UNICODE)


def _sanitize_utm(raw):
    """
    Провалидировать и очистить UTM-параметры (PROMPT 7).

    UTM — это аналитические данные, а не критичные для приёма лида
    (в отличие от имени/телефона/согласий). Поэтому некорректное,
    слишком длинное или потенциально опасное значение конкретного
    UTM-поля не блокирует отправку лида целиком — такое значение
    просто отбрасывается (сохраняется как отсутствующее), а остальные
    корректные UTM-поля и сам лид сохраняются как обычно.

    Разрешённый формат значения: буквы (включая кириллицу), цифры,
    пробел и стандартные для UTM-меток символы "-_.:/%,+", не длиннее
    100 символов. Отсутствие UTM (частичное или полное) — норма и не
    считается ошибкой.
    """
    cleaned = {key: None for key in _UTM_KEYS}
    if not isinstance(raw, dict):
        return cleaned
    for key in _UTM_KEYS:
        value = raw.get(key)
        if not isinstance(value, str):
            continue
        value = value.strip()
        if not value or not _UTM_VALUE_RE.match(value):
            continue
        cleaned[key] = value
    return cleaned


def build_lead_record(contact_payload, calculator_payload, entry_source=None, utm_payload=None):
    """
    Провалидировать контактные данные и данные калькулятора на backend
    и собрать итоговую структуру лида.

    Стоимость НЕ принимается от frontend "на слово" — Price Engine
    (calculate_price_estimate) вызывается здесь заново, на тех же
    параметрах калькулятора, которые пользователь уже видел на экране
    результата. Это гарантирует, что записанная стоимость всегда
    соответствует единственному источнику истины и не может быть
    подделана на клиенте.

    Выбрасывает LeadValidationError или PriceEngineError с понятным
    сообщением, если данные некорректны или отсутствуют.
    """
    if not isinstance(contact_payload, dict):
        raise LeadValidationError("Некорректные данные контактной формы.")
    if not isinstance(calculator_payload, dict):
        raise LeadValidationError("Отсутствуют данные калькулятора.")

    name = _validate_name(contact_payload.get("name"))
    phone = _validate_phone(contact_payload.get("phone"))
    client_type = _validate_client_type(contact_payload.get("client_type"))
    company_name = _validate_company_name(contact_payload.get("company_name"), client_type)
    budget = _validate_budget(contact_payload.get("budget"))

    consent_personal_data = contact_payload.get("consent_personal_data") is True
    consent_share_with_suppliers = contact_payload.get("consent_share_with_suppliers") is True

    if not consent_personal_data:
        raise LeadValidationError("Необходимо согласие на обработку персональных данных.")
    if not consent_share_with_suppliers:
        raise LeadValidationError("Необходимо согласие на передачу данных производителям.")

    # Единственный источник истины для стоимости — Price Engine.
    # Одновременно валидирует все параметры калькулятора (объект,
    # площадь, высоту, утеплитель, толщину, монтаж, город).
    price = calculate_price_estimate(calculator_payload)

    segment = determine_segment(price["area"])
    lead_id = generate_lead_id()
    created_at = datetime.now(timezone.utc).isoformat()
    utm = _sanitize_utm(utm_payload)

    return {
        "lead_id": lead_id,
        "created_at": created_at,
        "source": entry_source or "Прямой заход",
        "utm_source": utm["utm_source"],
        "utm_medium": utm["utm_medium"],
        "utm_campaign": utm["utm_campaign"],
        "utm_content": utm["utm_content"],
        "utm_term": utm["utm_term"],
        "region": price["region"],
        "city": calculator_payload.get("city"),
        "segment": segment,
        "object": calculator_payload.get("object"),
        "area": price["area"],
        "length": calculator_payload.get("length"),
        "width": calculator_payload.get("width"),
        "height": calculator_payload.get("height"),
        "insulation": calculator_payload.get("insulation"),
        "thickness": calculator_payload.get("thickness"),
        "installation": calculator_payload.get("installation"),
        "deadline": calculator_payload.get("deadline"),
        "project": calculator_payload.get("project"),
        "budget": budget,
        "name": name,
        "phone": phone,
        "client_type": client_type,
        "company_name": company_name,
        "price_min": price["price_min"],
        "price_max": price["price_max"],
        "price_min_formatted": price["price_min_formatted"],
        "price_max_formatted": price["price_max_formatted"],
        "status": "Новый",
        "consent_personal_data": True,
        "consent_share_with_suppliers": True,
        "consent_recorded_at": created_at,
    }
