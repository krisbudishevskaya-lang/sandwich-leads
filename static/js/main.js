// ПрайсМетр — main.js
//
// Лёгкая UI-логика лендинга, не связанная с бизнес-логикой калькулятора
// (та находится в calculator.js). Сейчас: стрелки навигации горизонтальной
// карусели компаний в trust-блоке (карточки прокручиваются и свайпом,
// стрелки — просто удобный alternative-способ на desktop).

(function () {
    "use strict";

    function wireCompaniesCarousel() {
        var grid = document.getElementById("companies-grid");
        var prevBtn = document.getElementById("companies-prev");
        var nextBtn = document.getElementById("companies-next");
        if (!grid || !prevBtn || !nextBtn) return;

        function scrollByCard(direction) {
            var card = grid.querySelector(".company-card");
            var step = card ? card.getBoundingClientRect().width + 16 : 280;
            grid.scrollBy({ left: direction * step, behavior: "smooth" });
        }

        prevBtn.addEventListener("click", function () {
            scrollByCard(-1);
        });
        nextBtn.addEventListener("click", function () {
            scrollByCard(1);
        });
    }

    function init() {
        wireCompaniesCarousel();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
