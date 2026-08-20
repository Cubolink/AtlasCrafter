(function () {
  "use strict";

  var symbols = {
    none: "",
    pin: "📍",
    star: "★",
    home: "⌂",
    shop: "◆",
    portal: "◉",
    warning: "⚠"
  };

  function update(form) {
    if (!form) return;
    var preview = form.querySelector("[data-html-marker-preview]");
    if (!preview) return;
    var label = form.querySelector("[data-html-marker-label]");
    var variant = form.querySelector("[data-html-marker-variant]");
    var size = form.querySelector("[data-html-marker-size]");
    var symbol = form.querySelector("[data-html-marker-symbol]");
    var textColor = form.querySelector("[data-html-marker-text-color]");
    var backgroundColor = form.querySelector("[data-html-marker-background-color]");
    var previewLabel = preview.querySelector("[data-html-marker-preview-label]");
    var previewSymbol = preview.querySelector("[data-html-marker-preview-symbol]");

    preview.dataset.variant = variant ? variant.value : "badge";
    preview.dataset.size = size ? size.value : "medium";
    preview.style.setProperty("--marker-preview-text", textColor ? textColor.value : "#ffffff");
    preview.style.setProperty(
      "--marker-preview-background",
      backgroundColor ? backgroundColor.value : "#2563eb"
    );
    if (previewLabel) {
      previewLabel.textContent = label && label.value.trim() ? label.value : "Styled label";
    }
    if (previewSymbol) previewSymbol.textContent = symbols[symbol ? symbol.value : "pin"] || "";
  }

  function refresh(root) {
    (root || document).querySelectorAll("form").forEach(update);
  }

  document.addEventListener("input", function (event) {
    update(event.target.closest("form"));
  });
  document.addEventListener("change", function (event) {
    update(event.target.closest("form"));
  });
  document.addEventListener("DOMContentLoaded", function () { refresh(document); });

  window.AtlasCrafterHTMLMarkerPreview = { refresh: refresh };
})();
