"""
Sandwich Leads MVP.

Агрегатор заявок на строительство из сэндвич-панелей.
Регион MVP-теста: Москва и Московская область.

Текущий этап: PROMPT 8 — Telegram-уведомление о новом лиде.
Реализовано:
    GET  /                    — лендинг с многошаговым калькулятором
    GET  /privacy
    GET  /consent
    GET  /terms
    GET  /garazh               — рекламный вход, предвыбирает объект "Гараж"
    GET  /sto                  — рекламный вход, предвыбирает объект "СТО"
    GET  /sklad                — рекламный вход, предвыбирает объект "Склад"
    POST /api/price-estimate   — расчёт предварительной стоимости (Price Engine)
    POST /api/leads            — приём контактной формы, сохранение лида
                                  и отправка Telegram-уведомления менеджеру

Matching поставщиков, CRM, личный кабинет и прочая функциональность
будут добавлены на следующих этапах.
"""

import os

from flask import Flask, jsonify, render_template, request
from dotenv import load_dotenv

from services import google_sheets, telegram
from services.lead_calculator import (
    LeadValidationError,
    PriceEngineError,
    build_lead_record,
    calculate_price_estimate,
)

load_dotenv()

app = Flask(__name__)
app.config["FLASK_ENV"] = os.getenv("FLASK_ENV", "development")


@app.route("/")
def index():
    """Главная страница с лендингом и калькулятором."""
    return render_template("index.html", preset_object="")


@app.route("/garazh")
def garazh():
    """Рекламный вход: калькулятор автоматически выбирает "Гараж"."""
    return render_template("index.html", preset_object="garage")


@app.route("/sto")
def sto():
    """Рекламный вход: калькулятор автоматически выбирает "СТО"."""
    return render_template("index.html", preset_object="sto")


@app.route("/sklad")
def sklad():
    """Рекламный вход: калькулятор автоматически выбирает "Склад"."""
    return render_template("index.html", preset_object="warehouse")


@app.route("/api/price-estimate", methods=["POST"])
def price_estimate():
    """
    Price Engine MVP (Master ТЗ, разделы 24-33).

    Принимает JSON с параметрами объекта, собранными калькулятором,
    и возвращает структурированный расчёт предварительной стоимости.
    Невалидные входные данные не приводят к 500 — возвращается 400
    с понятным сообщением об ошибке. Любая неожиданная ошибка тоже
    не должна показывать пользователю технический traceback —
    возвращается безопасный JSON-ответ с кодом 500.
    """
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"ok": False, "error": "Некорректный формат запроса."}), 400

    try:
        result = calculate_price_estimate(payload)
    except PriceEngineError as error:
        return jsonify({"ok": False, "error": str(error)}), 400
    except Exception:
        # Не даём техническим деталям/traceback попасть к пользователю.
        return jsonify({"ok": False, "error": "Внутренняя ошибка сервера. Попробуйте ещё раз."}), 500

    return jsonify(result), 200


@app.route("/api/leads", methods=["POST"])
def create_lead():
    """
    Приём контактной формы и сохранение лида (Master ТЗ, разделы 6,
    39-42, 45).

    Ожидает JSON вида:
        {
            "contact": {name, phone, client_type, company_name,
                        budget, consent_personal_data,
                        consent_share_with_suppliers},
            "calculator": {object, area, length, width, height,
                            insulation, thickness, installation,
                            city, deadline, project},
            "source": "..." (необязательно, откуда пришёл пользователь),
            "utm": {utm_source, utm_medium, utm_campaign, utm_content,
                    utm_term} (необязательно, PROMPT 7)
        }

    Стоимость не принимается от клиента — пересчитывается на backend
    через тот же Price Engine, что и на экране результата (единственный
    источник истины). Frontend-валидация недостаточна: все поля
    проверяются здесь заново. Ошибки записи в Google Sheets и ошибки
    отправки Telegram-уведомления никогда не приводят к падению запроса
    и не раскрывают пользователю технические детали — лид в любом случае
    считается принятым, если прошла валидация, а сохранение подстраховано
    локальным резервным журналом.
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "Некорректный формат запроса."}), 400

    contact = payload.get("contact")
    calculator_data = payload.get("calculator")
    entry_source = payload.get("source")
    utm_data = payload.get("utm")

    if not isinstance(contact, dict) or not isinstance(calculator_data, dict):
        return jsonify({"ok": False, "error": "Некорректный формат запроса."}), 400

    try:
        record = build_lead_record(contact, calculator_data, entry_source, utm_data)
    except (LeadValidationError, PriceEngineError) as error:
        return jsonify({"ok": False, "error": str(error)}), 400
    except Exception:
        return jsonify({"ok": False, "error": "Внутренняя ошибка сервера. Попробуйте ещё раз."}), 500

    try:
        google_sheets.append_lead(record)
    except Exception:
        # append_lead уже не должен поднимать исключения, но не даём
        # сохранению в Sheets уронить приём лида ни при каких условиях.
        pass

    try:
        telegram.send_lead_notification(record)
    except Exception:
        # send_lead_notification уже не должна поднимать исключения,
        # но недоступность/ошибка Telegram ни при каких условиях не
        # должна ронять уже успешно созданный и сохранённый лид.
        pass

    return jsonify({"ok": True, "lead_id": record["lead_id"], "name": record["name"]}), 201


@app.route("/privacy")
def privacy():
    """Политика обработки персональных данных (placeholder)."""
    return render_template("privacy.html")


@app.route("/consent")
def consent():
    """Согласие на обработку персональных данных (placeholder)."""
    return render_template("consent.html")


@app.route("/terms")
def terms():
    """Пользовательское соглашение (placeholder)."""
    return render_template("terms.html")


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    port = int(os.getenv("PORT", 5000))
    app.run(debug=debug, port=port)
