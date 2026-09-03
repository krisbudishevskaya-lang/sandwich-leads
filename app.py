"""
Sandwich Leads MVP.

Агрегатор заявок на строительство из сэндвич-панелей.
Регион MVP-теста: Москва и Московская область.

Текущий этап: Этап 2 — два коммерческих сценария (строительство /
сэндвич-панели как материал).
Реализовано:
    GET  /                      — лендинг с многошаговым калькулятором
    GET  /privacy
    GET  /consent
    GET  /terms
    GET  /garazh                 — рекламный вход, предвыбирает объект "Гараж"
    GET  /sto                    — рекламный вход, предвыбирает объект "СТО"
    GET  /sklad                  — рекламный вход, предвыбирает объект "Склад"
    POST /api/price-estimate     — расчёт стоимости строительства (Price Engine)
    POST /api/panel-price-estimate — расчёт стоимости сэндвич-панелей (Этап 2)
    POST /api/leads               — приём формы, сохранение лида (construction
                                     или panels — см. lead_type) и уведомления

Matching поставщиков, CRM, личный кабинет и прочая функциональность
будут добавлены на следующих этапах.
"""

import logging
import os

from flask import Flask, jsonify, render_template, request
from dotenv import load_dotenv

from services import google_sheets, telegram
from services.lead_calculator import (
    LeadValidationError,
    PriceEngineError,
    build_lead_record,
    calculate_panel_price_estimate,
    calculate_price_estimate,
)

load_dotenv()

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["FLASK_ENV"] = os.getenv("FLASK_ENV", "development")


@app.route("/")
def index():
    """Главная страница с лендингом и калькулятором."""
    return render_template("index.html", preset_object="", preset_flow="")


@app.route("/garazh")
def garazh():
    """Рекламный вход: калькулятор автоматически выбирает "Гараж" (строительство)."""
    return render_template("index.html", preset_object="garage", preset_flow="construction")


@app.route("/sto")
def sto():
    """Рекламный вход: калькулятор автоматически выбирает "СТО" (строительство)."""
    return render_template("index.html", preset_object="sto", preset_flow="construction")


@app.route("/sklad")
def sklad():
    """Рекламный вход: калькулятор автоматически выбирает "Склад" (строительство)."""
    return render_template("index.html", preset_object="warehouse", preset_flow="construction")


@app.route("/angar")
def angar():
    """Рекламный вход (Этап 2): калькулятор автоматически выбирает "Ангар" (строительство)."""
    return render_template("index.html", preset_object="hangar", preset_flow="construction")


@app.route("/bystrovozvodimye-zdaniya")
def bystrovozvodimye_zdaniya():
    """Рекламный вход (Этап 2): сразу открывает сценарий "Строительство" без preset объекта."""
    return render_template("index.html", preset_object="", preset_flow="construction")


@app.route("/sandwich-paneli")
def sandwich_paneli():
    """Рекламный вход (Этап 2): сразу открывает сценарий "Сэндвич-панели"."""
    return render_template("index.html", preset_object="", preset_flow="panels")


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


@app.route("/api/panel-price-estimate", methods=["POST"])
def panel_price_estimate():
    """
    Price Engine сэндвич-панелей как материала (Этап 2).

    Работает по тому же архитектурному принципу, что и
    /api/price-estimate: принимает JSON с параметрами панели, возвращает
    структурированный расчёт, невалидные данные -> 400, неожиданные
    ошибки -> безопасный 500 без traceback. Строительный Price Engine
    (/api/price-estimate, calculate_price_estimate) этим не затрагивается.
    """
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"ok": False, "error": "Некорректный формат запроса."}), 400

    try:
        result = calculate_panel_price_estimate(payload)
    except PriceEngineError as error:
        return jsonify({"ok": False, "error": str(error)}), 400
    except Exception:
        return jsonify({"ok": False, "error": "Внутренняя ошибка сервера. Попробуйте ещё раз."}), 500

    return jsonify(result), 200


@app.route("/api/leads", methods=["POST"])
def create_lead():
    """
    Приём контактной формы и сохранение лида (Master ТЗ, разделы 6,
    39-42, 45; Этап 2 — lead_type).

    Ожидает JSON вида:
        {
            "contact": {name, phone, client_type, company_name,
                        budget, consent_personal_data,
                        consent_share_with_suppliers},
            "calculator": {
                # для lead_type="construction" (по умолчанию):
                object, area, length, width, height, insulation,
                thickness, installation, city, deadline, project
                # для lead_type="panels":
                panel_type, area, insulation, thickness, city
            },
            "source": "..." (необязательно, откуда пришёл пользователь),
            "utm": {utm_source, utm_medium, utm_campaign, utm_content,
                    utm_term} (необязательно, PROMPT 7),
            "lead_type": "construction" | "panels" (необязательно,
                          по умолчанию "construction" для обратной
                          совместимости со старыми вызовами)
        }

    Стоимость не принимается от клиента — пересчитывается на backend
    через соответствующий Price Engine (строительный или панельный —
    единственные источники истины, формула не дублируется на frontend).
    Frontend-валидация недостаточна: все поля проверяются здесь заново.
    Ошибки записи в Google Sheets и ошибки отправки Telegram-уведомления
    никогда не приводят к падению запроса и не раскрывают пользователю
    технические детали — лид в любом случае считается принятым, если
    прошла валидация, а сохранение подстраховано локальным резервным
    журналом.
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "Некорректный формат запроса."}), 400

    contact = payload.get("contact")
    calculator_data = payload.get("calculator")
    entry_source = payload.get("source")
    utm_data = payload.get("utm")
    lead_type = payload.get("lead_type") or "construction"

    if not isinstance(contact, dict) or not isinstance(calculator_data, dict):
        return jsonify({"ok": False, "error": "Некорректный формат запроса."}), 400

    try:
        record = build_lead_record(contact, calculator_data, entry_source, utm_data, lead_type)
    except (LeadValidationError, PriceEngineError) as error:
        return jsonify({"ok": False, "error": str(error)}), 400
    except Exception:
        return jsonify({"ok": False, "error": "Внутренняя ошибка сервера. Попробуйте ещё раз."}), 500

    try:
        sheets_result = google_sheets.append_lead(record)
        if not sheets_result.get("sheets_ok"):
            logger.warning(
                "Google Sheets: лид %s не записан (reason=%s), использован локальный fallback.",
                record.get("lead_id"), sheets_result.get("reason"),
            )
    except Exception:
        # append_lead уже не должен поднимать исключения, но не даём
        # сохранению в Sheets уронить приём лида ни при каких условиях.
        logger.warning("Google Sheets: неожиданное исключение при сохранении лида %s.", record.get("lead_id"))

    try:
        telegram_result = telegram.send_lead_notification(record)
        if not telegram_result.get("sent"):
            logger.warning(
                "Telegram: уведомление о лиде %s не отправлено (reason=%s).",
                record.get("lead_id"), telegram_result.get("reason"),
            )
    except Exception:
        # send_lead_notification уже не должна поднимать исключения,
        # но недоступность/ошибка Telegram ни при каких условиях не
        # должна ронять уже успешно созданный и сохранённый лид.
        logger.warning("Telegram: неожиданное исключение при отправке уведомления о лиде %s.", record.get("lead_id"))

    return jsonify({"ok": True, "lead_id": record["lead_id"], "name": record["name"]}), 201


@app.route("/privacy")
def privacy():
    """Политика в отношении обработки персональных данных."""
    return render_template("privacy.html")


@app.route("/consent")
def consent():
    """Согласие на обработку персональных данных."""
    return render_template("consent.html")


@app.route("/consent-transfer")
def consent_transfer():
    """Согласие на предоставление персональных данных потенциальным производителям, поставщикам и подрядчикам."""
    return render_template("consent-transfer.html")


@app.route("/terms")
def terms():
    """Пользовательское соглашение."""
    return render_template("terms.html")


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    port = int(os.getenv("PORT", 5000))
    app.run(debug=debug, port=port)
