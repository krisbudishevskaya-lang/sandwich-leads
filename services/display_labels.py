"""
Общие человекочитаемые (русские) подписи для внутренних значений
калькулятора — используются ТОЛЬКО для отображения (Telegram, Google
Sheets). Внутренние enum-значения ("garage", "pir", "within_month" и
т.д.), которыми оперирует калькулятор и Price Engine, не меняются —
здесь только их перевод для человека.

Единый источник этих подписей, чтобы services/telegram.py и
services/google_sheets.py не хранили две независимые копии одного и
того же словаря.
"""

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
    "mineral_wool": "Минеральная вата",
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

# Тип заявки (Этап 2, lead_type) — два разных стиля подписи:
# Telegram использует заглавные буквы (§16), Google Sheets — обычный
# регистр (§17). Оба варианта заданы дословно в ТЗ.
LEAD_TYPE_LABELS_TELEGRAM = {
    "construction": "СТРОИТЕЛЬСТВО",
    "panels": "СЭНДВИЧ-ПАНЕЛИ",
}

LEAD_TYPE_LABELS_SHEETS = {
    "construction": "Строительство",
    "panels": "Сэндвич-панели",
}

# Тип панели (Этап 2, panel calculator).
PANEL_TYPE_LABELS = {
    "wall": "Стеновые",
    "roof": "Кровельные",
    "wall_and_roof": "Стеновые и кровельные",
}


def get_label(mapping, value, fallback="—"):
    """Безопасно получить подпись из словаря или вернуть fallback."""
    if not value:
        return fallback
    return mapping.get(value, value)
