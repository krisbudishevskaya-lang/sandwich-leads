// ПрайсМетр — calculator.js
//
// Многошаговый калькулятор с двумя независимыми коммерческими
// сценариями (Этап 2-3 доработки):
//   activeFlow === "construction" — расчёт строительства объекта
//     (PROMPT 3-8, логика и Price Engine НЕ изменены);
//   activeFlow === "panels"       — расчёт сэндвич-панелей как
//     материала (новый сценарий, отдельный Price Engine).
//
// Оба сценария используют один и тот же движок шагов/навигации/
// контактной формы, чтобы не дублировать архитектуру. Выбор сценария
// происходит либо через две карточки в Hero, либо через кнопки-выбор
// прямо в калькуляторе, либо автоматически по preset_flow с рекламных
// входов (/garazh, /sto, /sklad, /angar, /bystrovozvodimye-zdaniya,
// /sandwich-paneli).
//
// Полностью работает на клиенте, без перезагрузки страницы.

(function () {
    "use strict";

    /* ------------------------------------------------------------------
       Справочники вариантов ответа — СТРОИТЕЛЬСТВО (не изменены)
       ------------------------------------------------------------------ */

    var OBJECT_OPTIONS = [
        { value: "garage", label: "Гараж" },
        { value: "workshop", label: "Мастерская" },
        { value: "warehouse", label: "Склад" },
        { value: "hangar", label: "Ангар" },
        { value: "production", label: "Производство" },
        { value: "sto", label: "СТО" },
        { value: "other", label: "Другое" }
    ];

    // Утеплитель — понятные потребителю варианты вместо технических
    // названий без объяснения (убрано «Не знаю» — клиент всегда должен
    // иметь возможность выбрать понятный вариант с описанием).
    // Технически по-прежнему используются существующие коэффициенты
    // Price Engine (mineral_wool/pir/pur) — формула не менялась.
    var INSULATION_OPTIONS = [
        {
            value: "mineral_wool",
            label: "Бюджетный вариант",
            description: "Подходит для гаражей, бытовок, хозблоков и других объектов, где важна оптимальная стоимость. Рекомендуем для большинства частных объектов."
        },
        {
            value: "pur",
            label: "Повышенная пожарная безопасность",
            description: "Подходит для объектов с повышенными требованиями к пожарной безопасности."
        },
        {
            value: "pir",
            label: "Максимальное энергосбережение",
            description: "Подходит для тёплых объектов и задач, где особенно важно снизить теплопотери."
        }
    ];

    // Режим использования помещения — новый понятный вопрос (Этап 5),
    // заменяет собой прежний прямой технический выбор толщины панели.
    // Толщина для Price Engine подбирается автоматически по режиму
    // (см. deriveThicknessFromUsageMode) — формула расчёта не меняется,
    // меняется только то, какое из уже существующих значений толщины
    // подставляется.
    var USAGE_MODE_OPTIONS = [
        {
            value: "seasonal",
            label: "Летнее / техническое использование",
            description: "Помещение не требует постоянного отопления. Подходит для хранения, техники, инвентаря и сезонного использования."
        },
        {
            value: "year_round",
            label: "Круглогодичное / тёплое использование",
            description: "Помещение планируется регулярно использовать в течение всего года с поддержанием комфортной температуры."
        }
    ];

    var INSTALLATION_OPTIONS = [
        { value: "yes", label: "Да" },
        { value: "no", label: "Нет" },
        { value: "unknown", label: "Пока не знаю" }
    ];

    var DEADLINE_OPTIONS = [
        { value: "asap", label: "В ближайшее время" },
        { value: "within_month", label: "В течение месяца" },
        { value: "1_3_months", label: "В течение 1–3 месяцев" },
        { value: "more_3_months", label: "Позже" },
        { value: "researching", label: "Пока сравниваю варианты" }
    ];

    var PROJECT_OPTIONS = [
        { value: "yes", label: "Есть готовый проект" },
        { value: "no", label: "Есть размеры, но проекта нет" },
        { value: "in_progress", label: "Пока только идея / нужен предварительный расчёт" }
    ];

    // Толщина панели — используется ТОЛЬКО панельным калькулятором
    // (Этап 2), его логика не меняется по этому ТЗ. Для строительства
    // толщина теперь подбирается автоматически по режиму использования
    // (см. deriveThicknessFromUsageMode), явный шаг выбора толщины для
    // строительства убран из QUESTION_STEPS.
    var THICKNESS_OPTIONS = [
        { value: "50", label: "50 мм" },
        { value: "80", label: "80 мм" },
        { value: "100", label: "100 мм" },
        { value: "120", label: "120 мм" },
        { value: "150", label: "150 мм" },
        { value: "200", label: "200 мм" },
        { value: "unknown", label: "Не знаю" }
    ];

    /* ------------------------------------------------------------------
       Справочники вариантов ответа — СЭНДВИЧ-ПАНЕЛИ (Этап 2-3)
       ------------------------------------------------------------------ */

    var PANEL_TYPE_OPTIONS = [
        { value: "wall", label: "Стеновые панели" },
        { value: "roof", label: "Кровельные панели" },
        { value: "wall_and_roof", label: "Стеновые + кровельные" }
    ];

    // Назначение объекта для панелей — лид-only поле (не участвует в
    // Price Engine панелей), нужно для дальнейшего сопоставления с
    // поставщиками. Использует общий словарь подписей OBJECT_LABELS на
    // backend (см. services/display_labels.py) — там же добавлены две
    // новые подписи (sto_workshop/utility) аддитивно.
    var PANEL_PURPOSE_OPTIONS = [
        { value: "garage", label: "Гараж" },
        { value: "warehouse", label: "Склад" },
        { value: "sto_workshop", label: "СТО / мастерская" },
        { value: "production", label: "Производственное помещение" },
        { value: "hangar", label: "Ангар" },
        { value: "utility", label: "Хозяйственная постройка" },
        { value: "other", label: "Другое" }
    ];

    // Утеплитель панелей — убрано «Не знаю», добавлено «Помогите
    // подобрать» (внутреннее значение осталось "unknown" — тот же
    // коэффициент Price Engine, что и раньше, меняется только подпись).
    var PANEL_INSULATION_OPTIONS = [
        { value: "mineral_wool", label: "Минеральная вата" },
        { value: "pir", label: "PIR" },
        { value: "unknown", label: "Помогите подобрать" }
    ];

    // Регион — новый явный вопрос для калькулятора панелей (в отличие
    // от строительства, где регион определяется из свободного
    // текстового поля "город" — эта логика не менялась).
    var REGION_OPTIONS = [
        { value: "moscow", label: "Москва" },
        { value: "moscow_region", label: "Московская область" }
    ];

    // Ворота / окна и двери — только калькулятор строительства.
    var GATES_OPTIONS = [
        { value: "yes", label: "Да" },
        { value: "no", label: "Нет" },
        { value: "unknown", label: "Пока не знаю" }
    ];

    var WINDOWS_DOORS_OPTIONS = [
        { value: "yes", label: "Да" },
        { value: "no", label: "Нет" },
        { value: "unknown", label: "Пока не знаю" }
    ];

    /* ------------------------------------------------------------------
       Конфигурация шагов
       ------------------------------------------------------------------ */

    var QUESTION_STEPS = [
        {
            key: "object",
            type: "cards",
            question: "Что хотите построить?",
            options: OBJECT_OPTIONS
        },
        {
            key: "size",
            type: "size",
            question: "Какой размер здания?"
        },
        {
            key: "usageMode",
            type: "described_cards",
            question: "Как вы планируете использовать помещение?",
            options: USAGE_MODE_OPTIONS
        },
        {
            key: "insulation",
            type: "described_cards",
            question: "Какой утеплитель подойдёт?",
            options: INSULATION_OPTIONS
        },
        {
            key: "installation",
            type: "options",
            question: "Нужен монтаж?",
            options: INSTALLATION_OPTIONS
        },
        {
            key: "gates",
            type: "options",
            question: "Нужны ворота?",
            options: GATES_OPTIONS
        },
        {
            key: "windowsDoors",
            type: "options",
            question: "Нужны окна или двери?",
            options: WINDOWS_DOORS_OPTIONS
        },
        {
            key: "city",
            type: "text",
            question: "Где будет объект?",
            label: "Город / населенный пункт",
            hint: "Сейчас мы работаем с Москвой и Московской областью."
        },
        {
            key: "deadline",
            type: "options",
            question: "Когда планируете строительство?",
            options: DEADLINE_OPTIONS
        },
        {
            key: "project",
            type: "options",
            question: "Есть проект?",
            options: PROJECT_OPTIONS
        }
    ];

    var RESULT_STEP = {
        key: "result",
        type: "result",
        flow: "construction",
        question: "Ваши параметры собраны"
    };

    var PANEL_QUESTION_STEPS = [
        {
            key: "panel_type",
            type: "cards",
            question: "Что вам нужно?",
            options: PANEL_TYPE_OPTIONS
        },
        {
            key: "purpose",
            type: "cards",
            question: "Для какого объекта нужны панели?",
            options: PANEL_PURPOSE_OPTIONS
        },
        {
            key: "size",
            type: "size",
            question: "Какой нужен объём?"
        },
        {
            key: "usageMode",
            type: "described_cards",
            question: "Как будет использоваться помещение?",
            options: USAGE_MODE_OPTIONS
        },
        {
            key: "insulation",
            type: "options",
            question: "Какой утеплитель?",
            options: PANEL_INSULATION_OPTIONS
        },
        {
            key: "installation",
            type: "options",
            question: "Нужен монтаж?",
            options: INSTALLATION_OPTIONS
        },
        {
            key: "region",
            type: "options",
            question: "Где нужен заказ?",
            options: REGION_OPTIONS
        },
        {
            key: "deadline",
            type: "options",
            question: "Когда нужны панели?",
            options: DEADLINE_OPTIONS
        },
        {
            key: "project",
            type: "options",
            question: "Есть готовый проект?",
            options: PROJECT_OPTIONS
        }
    ];

    var PANEL_RESULT_STEP = {
        key: "result",
        type: "result",
        flow: "panels",
        question: "Ваши параметры собраны"
    };

    var CONTACT_STEP = {
        key: "contact",
        type: "contact",
        question: "Оставьте контакты, чтобы узнать точную стоимость"
    };

    // Master ТЗ §39: "Кто вы?"
    var CLIENT_TYPE_OPTIONS = [
        { value: "individual", label: "Частное лицо" },
        { value: "entrepreneur", label: "ИП" },
        { value: "company", label: "Компания" },
        { value: "undecided", label: "Не определился" }
    ];

    // Master ТЗ §40: бюджет (не влияет на расчёт, для квалификации)
    var BUDGET_OPTIONS = [
        { value: "under_500k", label: "До 500 тыс. ₽" },
        { value: "500k_1m", label: "500 тыс.-1 млн ₽" },
        { value: "1m_3m", label: "1-3 млн ₽" },
        { value: "3m_5m", label: "3-5 млн ₽" },
        { value: "over_5m", label: "Более 5 млн ₽" },
        { value: "unknown", label: "Не знаю" }
    ];

    /* ------------------------------------------------------------------
       Состояние
       ------------------------------------------------------------------ */

    // activeFlow: null (сценарий ещё не выбран) | "construction" | "panels"
    var activeFlow = null;

    var state = {
        object: null,
        length: null,
        width: null,
        height: null,
        area: null,
        areaMode: "manual", // 'manual' | 'approximate'
        approxArea: null,
        usageMode: null, // 'seasonal' | 'year_round' — новый понятный вопрос
        insulation: null,
        thickness: null, // подбирается автоматически по usageMode для Price Engine
        recommendedWallThickness: null, // для будущей структуры лида, не влияет на расчёт
        recommendedRoofThickness: null, // для будущей структуры лида, не влияет на расчёт
        installation: null,
        gates: null, // 'yes' | 'no' | 'unknown'
        windowsDoors: null, // 'yes' | 'no' | 'unknown'
        city: null,
        deadline: null,
        project: null,
        smallAreaWarningShownFor: null // object, для которого уже показана подсказка о площади
    };

    var panelState = {
        panel_type: null,
        purpose: null,
        length: null,
        width: null,
        height: null,
        area: null,
        areaMode: "manual", // 'manual' | 'approximate'
        approxArea: null,
        usageMode: null, // 'seasonal' | 'year_round'
        insulation: null,
        thickness: null, // подбирается автоматически по usageMode
        recommendedWallThickness: null,
        recommendedRoofThickness: null,
        installation: null,
        region: null, // 'moscow' | 'moscow_region'
        deadline: null,
        project: null,
        smallAreaWarningShownFor: null
    };

    // Состояние контактной формы — общее для обоих сценариев.
    var contactState = {
        name: null,
        phone: null,
        clientType: null,
        companyName: null,
        budget: null,
        consentPersonalData: false,
        consentShareWithSuppliers: false
    };

    // Последний успешный результат Price Engine — переиспользуется при
    // отправке лида и для краткой сводки на экране контактной формы,
    // без повторного запроса к соответствующему price-estimate.
    var lastPriceResult = null;
    var leadSubmitted = false;
    var lastSubmittedLeadId = null;
    var lastSubmittedName = null;

    // UTM-метки (PROMPT 7) — считываются один раз из URL при загрузке
    // страницы и сохраняются в памяти на протяжении всего сценария.
    var utmParams = {
        utm_source: null,
        utm_medium: null,
        utm_campaign: null,
        utm_content: null,
        utm_term: null
    };

    var currentIndex = 0;

    /* ------------------------------------------------------------------
       Помощники активного сценария
       ------------------------------------------------------------------ */

    function getActiveState() {
        return activeFlow === "panels" ? panelState : state;
    }

    function getActiveQuestionSteps() {
        return activeFlow === "panels" ? PANEL_QUESTION_STEPS : QUESTION_STEPS;
    }

    function getActiveResultStep() {
        return activeFlow === "panels" ? PANEL_RESULT_STEP : RESULT_STEP;
    }

    function getActiveAllSteps() {
        return getActiveQuestionSteps().concat([getActiveResultStep(), CONTACT_STEP]);
    }

    /* ------------------------------------------------------------------
       Утилиты
       ------------------------------------------------------------------ */

    function parsePositiveNumber(raw) {
        if (raw === null || raw === undefined) return null;
        var normalized = String(raw).trim().replace(",", ".");
        if (normalized === "") return null;
        var num = Number(normalized);
        if (!isFinite(num)) return null;
        if (num <= 0) return null;
        return num;
    }

    function roundArea(value) {
        return Math.round(value * 10) / 10;
    }

    function formatNumber(value) {
        if (value === null || value === undefined) return "—";
        return String(value);
    }

    function getOptionLabel(options, value) {
        var found = null;
        for (var i = 0; i < options.length; i++) {
            if (options[i].value === value) {
                found = options[i];
                break;
            }
        }
        return found ? found.label : (value || "—");
    }

    function escapeHtml(str) {
        var div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }

    /* ------------------------------------------------------------------
       Построение DOM шагов
       ------------------------------------------------------------------ */

    function buildOptionsHtml(options, cssClass, field) {
        var fieldAttr = field ? ' data-field="' + field + '"' : "";
        return options
            .map(function (o) {
                return (
                    '<button type="button" class="' + cssClass + '"' + fieldAttr + ' data-value="' +
                    o.value + '" aria-pressed="false">' + escapeHtml(o.label) + "</button>"
                );
            })
            .join("");
    }

    function buildStepInnerHtml(step) {
        var html = '<h2 class="calc-step__question">' + escapeHtml(step.question) + "</h2>";

        if (step.type === "cards") {
            html += '<div class="calc-cards" role="group" aria-label="' +
                escapeHtml(step.question) + '">' +
                buildOptionsHtml(step.options, "calc-card") +
                "</div>";
            return html;
        }

        if (step.type === "described_cards") {
            html += '<div class="calc-described-cards" role="group" aria-label="' +
                escapeHtml(step.question) + '">' +
                step.options
                    .map(function (o) {
                        return (
                            '<button type="button" class="calc-described-card" data-value="' + o.value +
                            '" aria-pressed="false">' +
                                '<span class="calc-described-card__title">' + escapeHtml(o.label) + "</span>" +
                                '<span class="calc-described-card__description">' + escapeHtml(o.description) + "</span>" +
                            "</button>"
                        );
                    })
                    .join("") +
                "</div>";
            return html;
        }

        if (step.type === "options") {
            html += '<div class="calc-options" role="group" aria-label="' +
                escapeHtml(step.question) + '">' +
                buildOptionsHtml(step.options, "calc-option") +
                "</div>";
            if (step.hint) {
                html += '<p class="calc-step__hint">' + escapeHtml(step.hint) + "</p>";
            }
            return html;
        }

        if (step.type === "text") {
            html += '<div class="calc-field">' +
                '<label for="calc-input-' + step.key + '">' + escapeHtml(step.label) + "</label>" +
                '<input type="text" id="calc-input-' + step.key + '" autocomplete="address-level2">' +
                '<p class="calc-field-error" id="calc-error-' + step.key + '"></p>' +
                "</div>";
            if (step.hint) {
                html += '<p class="calc-step__hint">' + escapeHtml(step.hint) + "</p>";
            }
            return html;
        }

        if (step.type === "size") {
            html +=
                '<div class="calc-size" id="calc-size-wrapper" data-mode="manual">' +
                    '<div class="calc-size__manual">' +
                        '<div class="calc-field-row">' +
                            '<div class="calc-field">' +
                                '<label for="calc-length">Длина, м</label>' +
                                '<input type="number" id="calc-length" inputmode="decimal" step="0.1" min="0">' +
                                '<p class="calc-field-error" id="calc-error-length"></p>' +
                            "</div>" +
                            '<div class="calc-field">' +
                                '<label for="calc-width">Ширина, м</label>' +
                                '<input type="number" id="calc-width" inputmode="decimal" step="0.1" min="0">' +
                                '<p class="calc-field-error" id="calc-error-width"></p>' +
                            "</div>" +
                        "</div>" +
                        '<p class="calc-area-preview" id="calc-area-display" hidden>' +
                            "Площадь: <strong><span id=\"calc-area-value\"></span> м²</strong>" +
                        "</p>" +
                    "</div>" +

                    '<div class="calc-field">' +
                        '<label for="calc-height">Высота, м</label>' +
                        '<input type="number" id="calc-height" inputmode="decimal" step="0.1" min="0">' +
                        '<p class="calc-field-error" id="calc-error-height"></p>' +
                    "</div>" +

                    '<label class="calc-checkbox">' +
                        '<input type="checkbox" id="calc-area-toggle">' +
                        "<span>Не знаю размеры — указать примерную площадь</span>" +
                    "</label>" +

                    '<div class="calc-field calc-size__approx">' +
                        '<label for="calc-approx-area">Примерная площадь, м²</label>' +
                        '<input type="number" id="calc-approx-area" inputmode="decimal" step="0.1" min="0">' +
                        '<p class="calc-field-error" id="calc-error-approxArea"></p>' +
                    "</div>" +
                "</div>";
            return html;
        }

        if (step.type === "panel_area") {
            html += '<div class="calc-field">' +
                '<label for="calc-panel-area">Примерная площадь, м²</label>' +
                '<input type="number" id="calc-panel-area" inputmode="decimal" step="0.1" min="0">' +
                '<p class="calc-field-error" id="calc-error-panel-area"></p>' +
                "</div>" +
                '<p class="calc-step__hint">Не знаете точную площадь? Укажите примерное значение — расчёт всё равно будет ориентировочным.</p>';
            return html;
        }

        if (step.type === "result") {
            var isPanels = step.flow === "panels";
            var introText = isPanels
                ? "Предварительная оценка стоимости сэндвич-панелей как материала. Это не оферта и не точная коммерческая цена."
                : "Предварительная оценка рыночной стоимости объекта из сэндвич-панелей. Это не строительная смета.";
            var ctaTitle = "Хотите получить предложения от компаний?";
            var ctaText = isPanels
                ? "Передадим заявку компаниям, которые работают с поставкой сэндвич-панелей."
                : "Подберём компании, которые работают с вашим типом объекта и параметрами.";
            var ctaButtonText = "Получить точный расчёт от компаний";

            html +=
                '<p class="calc-result__intro">' + escapeHtml(introText) + "</p>" +
                '<dl class="calc-summary" id="calc-summary"></dl>' +
                '<div class="calc-price" id="calc-price" aria-live="polite">' +
                    '<p class="calc-price__label">Предварительная стоимость</p>' +
                    '<div class="calc-price__body" id="calc-price-body">' +
                        '<p class="calc-price__loading">Считаем предварительную стоимость…</p>' +
                    "</div>" +
                "</div>";

            if (isPanels) {
                html += '<p class="calc-step__hint">' +
                    "Точную стоимость и условия поставки подтвердит компания." +
                "</p>";
            } else {
                html +=
                    '<details class="calc-scope">' +
                        "<summary>Что входит в расчёт и что нет</summary>" +
                        '<div class="calc-scope__columns">' +
                            '<div class="calc-scope__col">' +
                                '<p class="calc-scope__heading">В расчёт ориентировочно входят:</p>' +
                                "<ul>" +
                                    "<li>металлокаркас</li>" +
                                    "<li>стеновые панели</li>" +
                                    "<li>кровельные панели</li>" +
                                    "<li>базовые комплектующие</li>" +
                                    "<li>стандартный монтаж</li>" +
                                "</ul>" +
                            "</div>" +
                            '<div class="calc-scope__col">' +
                                '<p class="calc-scope__heading">Не входят:</p>' +
                                "<ul>" +
                                    "<li>фундамент</li>" +
                                    "<li>инженерные коммуникации</li>" +
                                    "<li>оборудование</li>" +
                                    "<li>внутренняя отделка</li>" +
                                    "<li>нестандартные ворота</li>" +
                                    "<li>кран-балки</li>" +
                                    "<li>холодильное оборудование</li>" +
                                    "<li>благоустройство</li>" +
                                    "<li>нестандартные работы</li>" +
                                "</ul>" +
                            "</div>" +
                        "</div>" +
                    "</details>";
            }

            html +=
                '<div class="calc-next-step">' +
                    '<h3 class="calc-next-step__title">' + escapeHtml(ctaTitle) + "</h3>" +
                    '<p class="calc-next-step__text">' + escapeHtml(ctaText) + "</p>" +
                    '<button type="button" class="button-primary calc-next-step__cta" id="calc-get-offers">' +
                        escapeHtml(ctaButtonText) +
                    "</button>" +
                "</div>";
            return html;
        }

        if (step.type === "contact") {
            html +=
                '<div class="calc-contact-recap" id="calc-contact-recap"></div>' +
                '<p class="calc-contact-subtitle">Мы передадим вашу заявку подходящим компаниям — они свяжутся с вами, чтобы назвать точную стоимость.</p>' +
                '<div id="calc-contact-form-wrapper">' +
                    '<div class="calc-field">' +
                        '<label for="calc-contact-name">Имя</label>' +
                        '<input type="text" id="calc-contact-name" autocomplete="name">' +
                        '<p class="calc-field-error" id="calc-error-contact-name"></p>' +
                    "</div>" +
                    '<div class="calc-field">' +
                        '<label for="calc-contact-phone">Телефон</label>' +
                        '<input type="tel" id="calc-contact-phone" inputmode="tel" autocomplete="tel" placeholder="+7 999 123-45-67">' +
                        '<p class="calc-field-error" id="calc-error-contact-phone"></p>' +
                    "</div>" +
                    '<div class="calc-field">' +
                        '<p class="calc-contact-label">Кто вы?</p>' +
                        '<div class="calc-options calc-options--compact calc-options-group" role="group" aria-label="Кто вы?">' +
                            buildOptionsHtml(CLIENT_TYPE_OPTIONS, "calc-option calc-option--compact", "clientType") +
                        "</div>" +
                    "</div>" +
                    '<div class="calc-field calc-contact__company" id="calc-contact-company-field" hidden>' +
                        '<label for="calc-contact-company">Название компании</label>' +
                        '<input type="text" id="calc-contact-company">' +
                        '<p class="calc-field-error" id="calc-error-contact-company"></p>' +
                    "</div>" +
                    '<div class="calc-field">' +
                        '<p class="calc-contact-label">Бюджет <span class="calc-contact-label__optional">(необязательно)</span></p>' +
                        '<div class="calc-options calc-options--compact calc-options-group" role="group" aria-label="Бюджет">' +
                            buildOptionsHtml(BUDGET_OPTIONS, "calc-option calc-option--compact", "budget") +
                        "</div>" +
                    "</div>" +
                    '<label class="calc-checkbox calc-checkbox--consent">' +
                        '<input type="checkbox" id="calc-consent-personal">' +
                        '<span>Я ознакомлен(а) и согласен(на) на <a href="/consent" target="_blank" rel="noopener">обработку персональных данных</a>.</span>' +
                    "</label>" +
                    '<label class="calc-checkbox calc-checkbox--consent">' +
                        '<input type="checkbox" id="calc-consent-share">' +
                        '<span>Разрешаю передать данные компаниям для подготовки предложений (<a href="/consent-transfer" target="_blank" rel="noopener">подробнее</a>).</span>' +
                    "</label>" +
                    '<p class="calculator__error" id="calc-contact-error" role="alert" aria-live="polite"></p>' +
                    '<button type="button" class="button-primary calc-contact__submit" id="calc-contact-submit">Получить точный расчёт от компаний</button>' +
                "</div>" +
                '<div class="calc-contact-success" id="calc-contact-success" hidden></div>';
            return html;
        }

        return html;
    }

    function buildStepsForFlow() {
        var container = document.getElementById("calc-steps");
        if (!container) return;
        container.innerHTML = "";

        getActiveAllSteps().forEach(function (step, index) {
            var el = document.createElement("div");
            el.className = "calc-step";
            el.id = "calc-step-" + step.key;
            el.setAttribute("data-step", String(index + 1));
            el.setAttribute("data-key", step.key);
            el.hidden = true;
            el.innerHTML = buildStepInnerHtml(step);
            container.appendChild(el);
        });
    }

    /* ------------------------------------------------------------------
       Ошибки
       ------------------------------------------------------------------ */

    function clearStepErrors() {
        var fieldErrors = document.querySelectorAll(".calc-field-error");
        fieldErrors.forEach(function (el) {
            el.textContent = "";
        });
        var generalError = document.getElementById("calc-step-error");
        if (generalError) {
            generalError.textContent = "";
            generalError.classList.remove("calculator__error--advisory");
        }
    }

    function showSizeAdvisory(message) {
        // Мягкая, не блокирующая подсказка (не ошибка) — переиспользует
        // общий элемент ошибки шага с визуальным модификатором. Расчёт
        // при этом не запрещается: повторное нажатие «Далее» продолжает
        // сценарий с уже выбранным объектом.
        var el = document.getElementById("calc-step-error");
        if (el) {
            el.textContent = message;
            el.classList.add("calculator__error--advisory");
        }
    }

    function setFieldError(fieldKey, message) {
        var el = document.getElementById("calc-error-" + fieldKey);
        if (el) el.textContent = message;
    }

    function showGeneralError(message) {
        var el = document.getElementById("calc-step-error");
        if (el) el.textContent = message;
    }

    /* ------------------------------------------------------------------
       Валидация текущего шага
       ------------------------------------------------------------------ */

    function validateSizeStep() {
        var valid = true;
        var activeState = getActiveState();
        var heightInput = document.getElementById("calc-height");
        var heightVal = parsePositiveNumber(heightInput.value);

        if (heightVal === null) {
            setFieldError("height", "Введите высоту — положительное число.");
            valid = false;
        } else {
            activeState.height = heightVal;
        }

        if (activeState.areaMode === "approximate") {
            var approxInput = document.getElementById("calc-approx-area");
            var approxVal = parsePositiveNumber(approxInput.value);
            if (approxVal === null) {
                setFieldError("approxArea", "Введите примерную площадь — положительное число.");
                valid = false;
            } else {
                activeState.approxArea = approxVal;
                activeState.area = approxVal;
                activeState.length = null;
                activeState.width = null;
            }
        } else {
            var lengthInput = document.getElementById("calc-length");
            var widthInput = document.getElementById("calc-width");
            var lengthVal = parsePositiveNumber(lengthInput.value);
            var widthVal = parsePositiveNumber(widthInput.value);

            if (lengthVal === null) {
                setFieldError("length", "Введите длину — положительное число.");
                valid = false;
            } else {
                activeState.length = lengthVal;
            }

            if (widthVal === null) {
                setFieldError("width", "Введите ширину — положительное число.");
                valid = false;
            } else {
                activeState.width = widthVal;
            }

            if (lengthVal !== null && widthVal !== null) {
                activeState.area = roundArea(lengthVal * widthVal);
            }
        }

        // Мягкая подсказка объект/площадь актуальна только для сценария
        // "Строительство" (термины "тип объекта" относятся к нему);
        // для панелей "назначение" — отдельное лид-only поле с другими
        // формулировками и не участвует в этой проверке.
        if (valid && activeFlow === "construction") {
            var smallAreaSensitiveObjects = ["hangar", "warehouse", "production"];
            var needsAdvisory =
                smallAreaSensitiveObjects.indexOf(activeState.object) !== -1 &&
                activeState.area !== null &&
                activeState.area < 50;

            if (needsAdvisory && activeState.smallAreaWarningShownFor !== activeState.object) {
                showSizeAdvisory(
                    "Для объектов типа ангара, склада или цеха обычно рассматривают площадь " +
                    "от 50 м². Возможно, для вашей задачи больше подойдёт гараж, хозблок или " +
                    "бытовка — вы можете вернуться назад и изменить тип объекта. Либо просто " +
                    "нажмите «Далее» ещё раз, чтобы продолжить с выбранным объектом."
                );
                activeState.smallAreaWarningShownFor = activeState.object;
                return false;
            }
        }

        return valid;
    }

    function validatePanelAreaStep() {
        var input = document.getElementById("calc-panel-area");
        var value = input ? parsePositiveNumber(input.value) : null;
        if (value === null) {
            setFieldError("panel-area", "Введите примерную площадь — положительное число.");
            return false;
        }
        panelState.area = value;
        return true;
    }

    function validateCurrentStep() {
        var step = getActiveAllSteps()[currentIndex];
        var activeState = getActiveState();
        clearStepErrors();

        if (step.type === "cards" || step.type === "options" || step.type === "described_cards") {
            if (!activeState[step.key]) {
                showGeneralError("Пожалуйста, выберите один из вариантов.");
                return false;
            }
            return true;
        }

        if (step.type === "text") {
            var input = document.getElementById("calc-input-" + step.key);
            var value = input ? input.value.trim() : "";
            if (!value) {
                setFieldError(step.key, "Пожалуйста, заполните это поле.");
                return false;
            }
            activeState[step.key] = value;
            return true;
        }

        if (step.type === "size") {
            return validateSizeStep();
        }

        if (step.type === "panel_area") {
            return validatePanelAreaStep();
        }

        return true;
    }

    /* ------------------------------------------------------------------
       Прогресс / навигация
       ------------------------------------------------------------------ */

    function updateProgress() {
        var totalQuestions = getActiveQuestionSteps().length;
        var fill = document.getElementById("calc-progress-fill");
        var label = document.getElementById("calc-progress-label");
        if (!fill || !label) return;

        if (currentIndex < totalQuestions) {
            var stepNum = currentIndex + 1;
            fill.style.width = (stepNum / totalQuestions) * 100 + "%";
            label.textContent = "Шаг " + stepNum + " из " + totalQuestions;
        } else if (currentIndex === totalQuestions) {
            fill.style.width = "100%";
            label.textContent = "Готово";
        } else {
            fill.style.width = "100%";
            label.textContent = "Контакты";
        }
    }

    function updateNav() {
        var backBtn = document.getElementById("calc-back");
        var nextBtn = document.getElementById("calc-next");
        if (!backBtn || !nextBtn) return;

        var totalQuestions = getActiveQuestionSteps().length;

        backBtn.hidden = currentIndex === 0;

        if (currentIndex >= totalQuestions) {
            // экран результата и контактная форма используют
            // собственные кнопки, а не общую кнопку "Далее".
            nextBtn.hidden = true;
        } else {
            nextBtn.hidden = false;
            nextBtn.textContent =
                currentIndex === totalQuestions - 1 ? "Показать результат" : "Далее";
        }
    }

    function buildConstructionSummaryRows() {
        var rows = [];
        rows.push(["Объект", getOptionLabel(OBJECT_OPTIONS, state.object)]);

        if (state.areaMode === "approximate") {
            rows.push(["Площадь", formatNumber(state.area) + " м² (указана примерно)"]);
            rows.push(["Высота", formatNumber(state.height) + " м"]);
        } else {
            rows.push(["Площадь", formatNumber(state.area) + " м²"]);
            rows.push([
                "Размер",
                formatNumber(state.length) + " × " + formatNumber(state.width) +
                    " × " + formatNumber(state.height) + " м"
            ]);
        }

        rows.push(["Режим использования", getOptionLabel(USAGE_MODE_OPTIONS, state.usageMode)]);
        rows.push(["Утеплитель", getOptionLabel(INSULATION_OPTIONS, state.insulation)]);
        rows.push(["Монтаж", getOptionLabel(INSTALLATION_OPTIONS, state.installation)]);
        rows.push(["Ворота", getOptionLabel(GATES_OPTIONS, state.gates)]);
        rows.push(["Окна/двери", getOptionLabel(WINDOWS_DOORS_OPTIONS, state.windowsDoors)]);
        rows.push(["Город", state.city || "—"]);
        rows.push(["Срок", getOptionLabel(DEADLINE_OPTIONS, state.deadline)]);
        rows.push(["Проект", getOptionLabel(PROJECT_OPTIONS, state.project)]);
        return rows;
    }

    function buildPanelSummaryRows() {
        var rows = [];
        rows.push(["Тип панели", getOptionLabel(PANEL_TYPE_OPTIONS, panelState.panel_type)]);
        rows.push(["Объект", getOptionLabel(PANEL_PURPOSE_OPTIONS, panelState.purpose)]);
        rows.push(["Площадь", formatNumber(panelState.area) + " м²"]);
        rows.push(["Режим использования", getOptionLabel(USAGE_MODE_OPTIONS, panelState.usageMode)]);
        rows.push(["Утеплитель", getOptionLabel(PANEL_INSULATION_OPTIONS, panelState.insulation)]);
        rows.push(["Монтаж", getOptionLabel(INSTALLATION_OPTIONS, panelState.installation)]);
        rows.push(["Регион", getOptionLabel(REGION_OPTIONS, panelState.region)]);
        rows.push(["Срок", getOptionLabel(DEADLINE_OPTIONS, panelState.deadline)]);
        rows.push(["Проект", getOptionLabel(PROJECT_OPTIONS, panelState.project)]);
        return rows;
    }

    function renderSummary() {
        var summary = document.getElementById("calc-summary");
        if (!summary) return;

        var rows = activeFlow === "panels" ? buildPanelSummaryRows() : buildConstructionSummaryRows();

        summary.innerHTML = rows
            .map(function (row) {
                return (
                    '<div class="calc-summary__row"><dt>' + escapeHtml(row[0]) +
                    "</dt><dd>" + escapeHtml(String(row[1])) + "</dd></div>"
                );
            })
            .join("");
    }

    /* ------------------------------------------------------------------
       Price Engine — запрос расчёта стоимости
       ------------------------------------------------------------------ */

    // Толщина для Price Engine подбирается автоматически по режиму
    // использования (Этап 5) — формула и коэффициенты Price Engine не
    // меняются, подставляется одно из уже существующих значений
    // толщины ("50"/"100"). Отдельно (только для будущей структуры
    // лида, не для расчёта) запоминаются рекомендуемые толщины стен и
    // кровли — Price Engine работает с одним значением толщины на
    // объект и не поддерживает раздельный расчёт "стены/кровля".
    function applyUsageModeToThickness(targetState) {
        if (targetState.usageMode === "year_round") {
            targetState.thickness = "100";
            targetState.recommendedWallThickness = "100";
            targetState.recommendedRoofThickness = "120";
        } else if (targetState.usageMode === "seasonal") {
            targetState.thickness = "50";
            targetState.recommendedWallThickness = "50";
            targetState.recommendedRoofThickness = "80";
        }
    }

    function buildPriceEnginePayload() {
        applyUsageModeToThickness(state);
        return {
            object: state.object,
            area: state.area,
            height: state.height,
            insulation: state.insulation,
            thickness: state.thickness,
            installation: state.installation,
            city: state.city
        };
    }

    // Расширенный payload калькулятора для /api/leads (только
    // строительство) — дополняет обычный payload Price Engine
    // метаданными об источнике параметров (Этап 5, п.10/14) и новыми
    // квалификационными полями (ворота, окна/двери). Backend читает
    // эти поля через .get() и попросту игнорирует их при расчёте — на
    // формулу и на Google Sheets/Telegram они не влияют без отдельного
    // аддитивного изменения структуры лида.
    function buildConstructionLeadCalculatorPayload() {
        var payload = buildPriceEnginePayload();
        payload.usage_mode = state.usageMode;
        payload.insulation_source = "user_selected";
        payload.thickness_source = "auto_selected";
        payload.recommended_wall_thickness = state.recommendedWallThickness;
        payload.recommended_roof_thickness = state.recommendedRoofThickness;
        payload.gates = state.gates;
        payload.windows_doors = state.windowsDoors;
        return payload;
    }

    function buildPanelPriceEnginePayload() {
        applyUsageModeToThickness(panelState);
        return {
            panel_type: panelState.panel_type,
            area: panelState.area,
            insulation: panelState.insulation,
            thickness: panelState.thickness
        };
    }

    // Расширенный payload калькулятора панелей для /api/leads —
    // дополняет обычный payload Price Engine новыми квалификационными
    // полями (назначение объекта, режим использования, монтаж, регион,
    // срок, проект) и метаданными об источнике толщины. Как и для
    // строительства, backend просто игнорирует лишние ключи при
    // расчёте — они попадают только в структуру лида.
    function buildPanelLeadCalculatorPayload() {
        var payload = buildPanelPriceEnginePayload();
        payload.purpose = panelState.purpose;
        payload.length = panelState.length;
        payload.width = panelState.width;
        payload.usage_mode = panelState.usageMode;
        payload.insulation_source = panelState.insulation === "unknown" ? "help_requested" : "user_selected";
        payload.thickness_source = "auto_selected";
        payload.recommended_wall_thickness = panelState.recommendedWallThickness;
        payload.recommended_roof_thickness = panelState.recommendedRoofThickness;
        payload.installation = panelState.installation;
        payload.region = panelState.region;
        payload.deadline = panelState.deadline;
        payload.project = panelState.project;
        return payload;
    }

    function renderPriceLoading() {
        lastPriceResult = null;
        var body = document.getElementById("calc-price-body");
        if (!body) return;
        body.innerHTML = '<p class="calc-price__loading">Считаем предварительную стоимость…</p>';
    }

    function renderPriceError(message) {
        lastPriceResult = null;
        var body = document.getElementById("calc-price-body");
        if (!body) return;
        body.innerHTML =
            '<p class="calc-price__error-text">' +
            escapeHtml(message || "Не удалось рассчитать стоимость. Попробуйте ещё раз.") +
            "</p>" +
            '<button type="button" class="calc-price__retry" id="calc-price-retry">Повторить расчёт</button>';

        var retryBtn = document.getElementById("calc-price-retry");
        if (retryBtn) {
            retryBtn.addEventListener("click", fetchPriceEstimate);
        }
    }

    function renderPriceResult(data) {
        lastPriceResult = data;
        
        if (typeof ym === "function") {
            ym(112274629, "reachGoal", "calculation_complete");
        }

        var body = document.getElementById("calc-price-body");
        if (!body) return;

        // Не показывать искусственный "диапазон" вида "30 000 ₽ – 30 000 ₽" —
        // если после округления для отображения min и max совпадают,
        // показываем одно значение с "≈". Сам расчёт (min/max) при этом
        // не меняется, меняется только то, как он отображается.
        var totalLine = data.price_min_formatted === data.price_max_formatted
            ? "≈ " + escapeHtml(data.price_min_formatted)
            : escapeHtml(data.price_min_formatted) + " – " + escapeHtml(data.price_max_formatted);

        var perM2Line = data.price_per_m2_min_formatted === data.price_per_m2_max_formatted
            ? "≈ " + escapeHtml(data.price_per_m2_min_formatted)
            : "≈ " + escapeHtml(data.price_per_m2_min_formatted) + " – " + escapeHtml(data.price_per_m2_max_formatted);

        body.innerHTML =
            '<p class="calc-price__range">' + totalLine + "</p>" +
            '<p class="calc-price__per-m2">' + perM2Line + "</p>" +
            '<p class="calc-price__note">' +
                "Расчет предварительный. Финальная стоимость зависит от проекта, комплектации, " +
                "фундамента, логистики и дополнительных работ." +
            "</p>";
    }

    function fetchPriceEstimate() {
        renderPriceLoading();

        var isPanels = activeFlow === "panels";
        var endpoint = isPanels ? "/api/panel-price-estimate" : "/api/price-estimate";
        var payload = isPanels ? buildPanelPriceEnginePayload() : buildPriceEnginePayload();

        fetch(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        })
            .then(function (response) {
                return response.json().then(function (data) {
                    return { status: response.status, data: data };
                });
            })
            .then(function (result) {
                if (result.status === 200 && result.data && result.data.ok) {
                    renderPriceResult(result.data);
                } else {
                    var message = result.data && result.data.error
                        ? result.data.error
                        : "Не удалось рассчитать стоимость. Попробуйте ещё раз.";
                    renderPriceError(message);
                }
            })
            .catch(function () {
                renderPriceError("Не удалось связаться с сервером. Проверьте соединение и попробуйте ещё раз.");
            });
    }

    /* ------------------------------------------------------------------
       Контактная форма и отправка лида
       ------------------------------------------------------------------ */

    function updateCompanyFieldVisibility() {
        var field = document.getElementById("calc-contact-company-field");
        if (!field) return;
        field.hidden = contactState.clientType !== "company";
    }

    function getEntrySourceLabel() {
        var section = document.getElementById("calculator");
        var presetObject = section ? section.getAttribute("data-preset-object") : "";
        var presetFlow = section ? section.getAttribute("data-preset-flow") : "";
        var objectLabels = {
            garage: "Гараж (рекламный вход)",
            sto: "СТО (рекламный вход)",
            warehouse: "Склад (рекламный вход)",
            hangar: "Ангар (рекламный вход)"
        };
        if (presetObject && objectLabels[presetObject]) return objectLabels[presetObject];
        if (presetFlow === "panels") return "Сэндвич-панели (рекламный вход)";
        if (presetFlow === "construction") return "Быстровозводимые здания (рекламный вход)";
        return "Прямой заход";
    }

    function renderContactRecap() {
        var recap = document.getElementById("calc-contact-recap");
        if (!recap) return;

        var priceText = lastPriceResult
            ? (lastPriceResult.price_min_formatted === lastPriceResult.price_max_formatted
                ? "≈ " + lastPriceResult.price_min_formatted
                : lastPriceResult.price_min_formatted + " – " + lastPriceResult.price_max_formatted)
            : "предварительная стоимость рассчитывается на предыдущем шаге";

        var summaryLine;
        if (activeFlow === "panels") {
            var panelTypeLabel = getOptionLabel(PANEL_TYPE_OPTIONS, panelState.panel_type);
            var panelAreaText = panelState.area !== null ? formatNumber(panelState.area) + " м²" : "—";
            summaryLine = panelTypeLabel + " · " + panelAreaText + " · " + priceText;
        } else {
            var objectLabel = getOptionLabel(OBJECT_OPTIONS, state.object);
            var areaText = state.area !== null ? formatNumber(state.area) + " м²" : "—";
            summaryLine = objectLabel + " · " + areaText + " · " + priceText;
        }

        recap.innerHTML =
            '<p class="calc-contact-recap__title">Ваш расчёт</p>' +
            '<p class="calc-contact-recap__text">' + escapeHtml(summaryLine) + "</p>";
    }

    function clearContactErrors() {
        clearStepErrors();
        var general = document.getElementById("calc-contact-error");
        if (general) general.textContent = "";
    }

    function validateContactForm() {
        var errors = {};

        var name = (contactState.name || "").trim();
        if (!name) {
            errors["contact-name"] = "Введите имя.";
        } else if (name.length < 2) {
            errors["contact-name"] = "Введите корректное имя.";
        }

        var phoneDigits = (contactState.phone || "").replace(/[^\d+]/g, "");
        if (!phoneDigits) {
            errors["contact-phone"] = "Введите номер телефона.";
        } else if (!/^\+?\d{10,15}$/.test(phoneDigits)) {
            errors["contact-phone"] = "Введите корректный номер телефона, например +7 999 123-45-67.";
        }

        if (contactState.clientType === "company" && !(contactState.companyName || "").trim()) {
            errors["contact-company"] = "Укажите название компании.";
        }

        var generalError = null;
        if (!contactState.consentPersonalData || !contactState.consentShareWithSuppliers) {
            generalError = "Чтобы отправить заявку, нужно поставить оба согласия ниже.";
        }

        return { errors: errors, generalError: generalError };
    }

    function showContactValidation(validation) {
        clearContactErrors();
        Object.keys(validation.errors).forEach(function (fieldKey) {
            setFieldError(fieldKey, validation.errors[fieldKey]);
        });
        if (validation.generalError) {
            var general = document.getElementById("calc-contact-error");
            if (general) general.textContent = validation.generalError;
        }
    }

    function showContactSuccessView(leadId, name) {
        var formWrapper = document.getElementById("calc-contact-form-wrapper");
        var successView = document.getElementById("calc-contact-success");
        if (formWrapper) formWrapper.hidden = true;

        // Финальный экран успешной отправки не должен показывать заголовок
        // шага контактной формы ("Оставьте контакты..."), индикатор
        // прогресса (подпись "КОНТАКТЫ") и кнопку "Назад" — они относятся
        // к состоянию "форма ещё заполняется" и не актуальны, когда
        // заявка уже отправлена. Во время самого заполнения формы (до
        // отправки) эти элементы по-прежнему показываются как раньше —
        // здесь они скрываются только в момент перехода к успеху.
        var stepTitle = document.querySelector("#calc-step-contact .calc-step__question");
        if (stepTitle) stepTitle.hidden = true;

        var progress = document.getElementById("calc-progress");
        if (progress) progress.hidden = true;

        var nav = document.getElementById("calc-nav");
        if (nav) nav.hidden = true;

        if (successView) {
            successView.hidden = false;
            successView.innerHTML =
                '<p class="calc-contact-success__title">Заявка отправлена' +
                    (name ? ", " + escapeHtml(name) : "") + "!</p>" +
                '<p class="calc-contact-success__text">Номер вашей заявки: <strong>' +
                    escapeHtml(leadId) + "</strong>.</p>" +
                '<p class="calc-contact-success__text">' +
                    "Мы передадим вашу заявку компаниям, которые подходят под параметры вашего " +
                    "запроса. Подходящие компании смогут связаться с вами напрямую." +
                "</p>" +
                '<p class="calc-contact-success__text">' +
                    "Обычно первые компании отвечают в течение 1–2 дней." +
                "</p>";
        }
    }

    function submitLead() {
        var validation = validateContactForm();
        if (Object.keys(validation.errors).length > 0 || validation.generalError) {
            showContactValidation(validation);
            return;
        }

        if (!lastPriceResult) {
            clearContactErrors();
            var general = document.getElementById("calc-contact-error");
            if (general) {
                general.textContent =
                    "Не удалось подтвердить расчёт стоимости. Вернитесь на предыдущий шаг и попробуйте снова.";
            }
            return;
        }

        clearContactErrors();

        var submitBtn = document.getElementById("calc-contact-submit");
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = "Отправляем…";
        }

        var isPanels = activeFlow === "panels";

        var payload = {
            contact: {
                name: contactState.name,
                phone: contactState.phone,
                client_type: contactState.clientType,
                company_name: contactState.companyName,
                budget: contactState.budget,
                consent_personal_data: contactState.consentPersonalData === true,
                consent_share_with_suppliers: contactState.consentShareWithSuppliers === true
            },
            calculator: isPanels ? buildPanelLeadCalculatorPayload() : buildConstructionLeadCalculatorPayload(),
            source: getEntrySourceLabel(),
            utm: utmParams,
            lead_type: isPanels ? "panels" : "construction"
        };

        fetch("/api/leads", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        })
            .then(function (response) {
                return response.json().then(function (data) {
                    return { status: response.status, data: data };
                });
            })
            .then(function (result) {
                if (result.status === 201 && result.data && result.data.ok) {
                    leadSubmitted = true;
                    lastSubmittedLeadId = result.data.lead_id;
                    lastSubmittedName = result.data.name;

                    if (typeof ym === "function") {
                        ym(112274629, "reachGoal", isPanels ? "panels_lead" : "construction_lead");
                    }

                    showContactSuccessView(lastSubmittedLeadId, lastSubmittedName);
                } else {
                    var message = result.data && result.data.error
                        ? result.data.error
                        : "Не удалось отправить заявку. Попробуйте ещё раз.";
                    var general = document.getElementById("calc-contact-error");
                    if (general) general.textContent = message;
                    if (submitBtn) {
                        submitBtn.disabled = false;
                        submitBtn.textContent = "Получить точный расчёт от компаний";
                    }
                }
            })
            .catch(function () {
                var general = document.getElementById("calc-contact-error");
                if (general) {
                    general.textContent =
                        "Не удалось связаться с сервером. Проверьте соединение и попробуйте ещё раз.";
                }
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = "Получить точный расчёт от компаний";
                }
            });
    }

    function goToContactStep() {

        if (typeof ym === "function") {
            ym(112274629, "reachGoal", "lead_form_open");
        }

        var allSteps = getActiveAllSteps();
        currentIndex = allSteps.length - 1;
        showStep(currentIndex);
        renderContactRecap();
        if (leadSubmitted) {
            showContactSuccessView(lastSubmittedLeadId, lastSubmittedName);
        }
        scrollCalculatorIntoView();
    }

    function wireContactStep() {
        var ctaBtn = document.getElementById("calc-get-offers");
        if (ctaBtn) {
            ctaBtn.addEventListener("click", goToContactStep);
        }

        var nameInput = document.getElementById("calc-contact-name");
        if (nameInput) {
            nameInput.addEventListener("input", function () {
                contactState.name = nameInput.value;
            });
        }

        var phoneInput = document.getElementById("calc-contact-phone");
        if (phoneInput) {
            phoneInput.addEventListener("input", function () {
                contactState.phone = phoneInput.value;
            });
        }

        var companyInput = document.getElementById("calc-contact-company");
        if (companyInput) {
            companyInput.addEventListener("input", function () {
                contactState.companyName = companyInput.value;
            });
        }

        var consentPersonal = document.getElementById("calc-consent-personal");
        if (consentPersonal) {
            consentPersonal.addEventListener("change", function () {
                contactState.consentPersonalData = consentPersonal.checked;
            });
        }

        var consentShare = document.getElementById("calc-consent-share");
        if (consentShare) {
            consentShare.addEventListener("change", function () {
                contactState.consentShareWithSuppliers = consentShare.checked;
            });
        }

        var submitBtn = document.getElementById("calc-contact-submit");
        if (submitBtn) {
            submitBtn.addEventListener("click", submitLead);
        }
    }

    function showStep(index) {
        var allSteps = getActiveAllSteps();
        allSteps.forEach(function (step, i) {
            var el = document.getElementById("calc-step-" + step.key);
            if (!el) return;
            if (i === index) {
                el.hidden = false;
                el.classList.remove("calc-step--active");
                // форсируем reflow для перезапуска CSS-анимации
                void el.offsetWidth;
                el.classList.add("calc-step--active");
            } else {
                el.hidden = true;
                el.classList.remove("calc-step--active");
            }
        });

        clearStepErrors();
        updateProgress();
        updateNav();

        if (allSteps[index].type === "result") {
            renderSummary();
            fetchPriceEstimate();
        }
    }

    function scrollCalculatorIntoView() {
        if (window.innerWidth > 700) return;
        var card = document.querySelector(".calculator__card");
        if (card) {
            card.scrollIntoView({ behavior: "smooth", block: "start" });
        }
    }

    /* ------------------------------------------------------------------
       Обработчики событий
       ------------------------------------------------------------------ */

    function wireNav() {
        var backBtn = document.getElementById("calc-back");
        var nextBtn = document.getElementById("calc-next");

        if (nextBtn) {
            nextBtn.addEventListener("click", function () {
                if (!validateCurrentStep()) return;
                var allSteps = getActiveAllSteps();
                if (currentIndex < allSteps.length - 1) {
                    currentIndex += 1;
                    showStep(currentIndex);
                    scrollCalculatorIntoView();
                }
            });
        }

        if (backBtn) {
            backBtn.addEventListener("click", function () {
                if (currentIndex > 0) {
                    currentIndex -= 1;
                    showStep(currentIndex);
                    scrollCalculatorIntoView();
                }
            });
        }
    }

    function wireOptionSelection() {
        var container = document.getElementById("calc-steps");
        if (!container) return;

        // Делегирование событий на постоянном контейнере — переживает
        // пересоздание внутреннего содержимого при смене сценария
        // (buildStepsForFlow полностью перестраивает #calc-steps).
        container.addEventListener("click", function (event) {
            var btn = event.target.closest(".calc-option, .calc-card, .calc-described-card");
            if (!btn) return;

            var stepEl = btn.closest(".calc-step");
            if (!stepEl) return;

            var field = btn.getAttribute("data-field");
            var value = btn.getAttribute("data-value");
            var scope = field ? btn.closest(".calc-options-group") : stepEl;

            if (field) {
                contactState[field] = value;
                if (field === "clientType") {
                    updateCompanyFieldVisibility();
                }
            } else {
                var key = stepEl.getAttribute("data-key");
                getActiveState()[key] = value;
            }

            var siblings = scope.querySelectorAll(".calc-option, .calc-card, .calc-described-card");
            siblings.forEach(function (sib) {
                var selected = sib === btn;
                sib.classList.toggle("is-selected", selected);
                sib.setAttribute("aria-pressed", selected ? "true" : "false");
            });

            clearStepErrors();
        });
    }

    function updateAreaPreview() {
        var lengthInput = document.getElementById("calc-length");
        var widthInput = document.getElementById("calc-width");
        var displayEl = document.getElementById("calc-area-display");
        var valueEl = document.getElementById("calc-area-value");
        if (!lengthInput || !widthInput || !displayEl || !valueEl) return;

        var l = parsePositiveNumber(lengthInput.value);
        var w = parsePositiveNumber(widthInput.value);

        if (l !== null && w !== null) {
            var area = roundArea(l * w);
            valueEl.textContent = formatNumber(area);
            displayEl.hidden = false;
        } else {
            displayEl.hidden = true;
        }
    }

    function wireSizeStep() {
        var lengthInput = document.getElementById("calc-length");
        var widthInput = document.getElementById("calc-width");
        var areaToggle = document.getElementById("calc-area-toggle");
        var sizeWrapper = document.getElementById("calc-size-wrapper");

        if (lengthInput) lengthInput.addEventListener("input", updateAreaPreview);
        if (widthInput) widthInput.addEventListener("input", updateAreaPreview);

        if (areaToggle && sizeWrapper) {
            areaToggle.addEventListener("change", function () {
                var activeState = getActiveState();
                activeState.areaMode = areaToggle.checked ? "approximate" : "manual";
                sizeWrapper.setAttribute("data-mode", activeState.areaMode);
                clearStepErrors();
            });
        }
    }

    function wireCityInput() {
        var cityInput = document.getElementById("calc-input-city");
        if (!cityInput) return;
        cityInput.addEventListener("input", function () {
            state.city = cityInput.value;
        });
    }

    function applyPresetObject() {
        var section = document.getElementById("calculator");
        if (!section) return;
        var preset = section.getAttribute("data-preset-object");
        if (!preset) return;

        var matchBtn = document.querySelector(
            '.calc-step[data-key="object"] .calc-card[data-value="' + preset + '"]'
        );
        if (matchBtn) {
            state.object = preset;
            matchBtn.classList.add("is-selected");
            matchBtn.setAttribute("aria-pressed", "true");
        }
    }

    /* ------------------------------------------------------------------
       Выбор сценария (Этап 3)
       ------------------------------------------------------------------ */

    function startFlow(flow) {
        activeFlow = flow;

        if (typeof ym === "function") {
            ym(112274629, "reachGoal", flow === "panels" ? "panels_start" : "construction_start");
        }

        currentIndex = 0;
        leadSubmitted = false;
        lastPriceResult = null;

        var chooser = document.getElementById("calc-flow-chooser");
        if (chooser) chooser.hidden = true;
        var progress = document.getElementById("calc-progress");
        if (progress) progress.hidden = false;
        var nav = document.getElementById("calc-nav");
        if (nav) nav.hidden = false;

        buildStepsForFlow();

        if (flow === "construction") {
            wireSizeStep();
            wireCityInput();
            applyPresetObject();
        } else if (flow === "panels") {
            wireSizeStep();
        }
        wireContactStep();

        showStep(0);
    }

    function wireFlowChoosers() {
        var heroCtaPanels = document.getElementById("hero-cta-panels");
        var heroCtaConstruction = document.getElementById("hero-cta-construction");
        var calcChoosePanels = document.getElementById("calc-choose-panels");
        var calcChooseConstruction = document.getElementById("calc-choose-construction");

        function startAndScroll(flow) {
            startFlow(flow);
            var calcSection = document.getElementById("calculator");
            if (calcSection) {
                calcSection.scrollIntoView({ behavior: "smooth", block: "start" });
            }
        }

        if (heroCtaPanels) {
            heroCtaPanels.addEventListener("click", function () { startAndScroll("panels"); });
        }
        if (heroCtaConstruction) {
            heroCtaConstruction.addEventListener("click", function () { startAndScroll("construction"); });
        }
        if (calcChoosePanels) {
            calcChoosePanels.addEventListener("click", function () { startFlow("panels"); });
        }
        if (calcChooseConstruction) {
            calcChooseConstruction.addEventListener("click", function () { startFlow("construction"); });
        }
    }

    /* ------------------------------------------------------------------
       UTM-метки (PROMPT 7)
       ------------------------------------------------------------------ */

    function parseUtmParams() {
        try {
            var params = new URLSearchParams(window.location.search);
            utmParams.utm_source = params.get("utm_source");
            utmParams.utm_medium = params.get("utm_medium");
            utmParams.utm_campaign = params.get("utm_campaign");
            utmParams.utm_content = params.get("utm_content");
            utmParams.utm_term = params.get("utm_term");
        } catch (e) {
            // URLSearchParams недоступен или URL некорректен — просто
            // работаем без UTM, это не критичная для лида информация.
        }
    }

    /* ------------------------------------------------------------------
       Инициализация
       ------------------------------------------------------------------ */

    function init() {
        var section = document.getElementById("calculator");
        if (!section) return;

        parseUtmParams();
        wireNav();
        wireOptionSelection();
        wireFlowChoosers();

        var presetFlow = section.getAttribute("data-preset-flow");
        if (presetFlow === "construction" || presetFlow === "panels") {
            startFlow(presetFlow);
        }
        // Иначе остаётся видимым #calc-flow-chooser — ждём выбора
        // сценария пользователем (через Hero-карточки или кнопки внутри
        // калькулятора).
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
