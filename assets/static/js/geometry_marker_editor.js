(function () {
  "use strict";

  function parseGeometry(value) {
    try {
      var geometry = JSON.parse(value || "[]");
      return Array.isArray(geometry) ? geometry : [];
    } catch (error) {
      return [];
    }
  }

  function createCoordinateInput(dimension, value, update) {
    var field = document.createElement("label");
    field.className = "geometry-coordinate-field";

    var label = document.createElement("span");
    label.textContent = dimension.toUpperCase();

    var input = document.createElement("input");
    input.type = "number";
    input.step = "any";
    input.inputMode = "decimal";
    input.setAttribute("aria-label", dimension.toUpperCase() + " coordinate");
    input.value = value === undefined || value === null ? "" : String(value);
    input.addEventListener("input", update);

    field.append(label, input);
    return field;
  }

  function initialize(root) {
    if (!root || root.dataset.geometryReady === "true") return;
    var hidden = root.querySelector("[data-geometry-value]");
    var list = root.querySelector("[data-geometry-vertices]");
    var addButton = root.querySelector("[data-add-geometry-vertex]");
    if (!hidden || !list || !addButton) return;

    var dimensions = (root.dataset.dimensions || "x,z").split(",");
    var minimum = Number(root.dataset.minVertices || 2);
    var geometry = parseGeometry(hidden.value);
    while (geometry.length < minimum) geometry.push({});

    function synchronize() {
      geometry = Array.from(list.querySelectorAll("[data-geometry-vertex]")).map(function (row) {
        var point = {};
        dimensions.forEach(function (dimension) {
          point[dimension] = row.querySelector('[data-dimension="' + dimension + '"]').value;
        });
        return point;
      });
      hidden.value = JSON.stringify(geometry);
    }

    function render() {
      list.replaceChildren();
      geometry.forEach(function (point, index) {
        var row = document.createElement("div");
        row.className = "geometry-vertex-row";
        row.dataset.geometryVertex = "";

        var number = document.createElement("span");
        number.className = "geometry-vertex-number";
        number.textContent = String(index + 1);
        number.setAttribute("aria-hidden", "true");
        row.appendChild(number);

        dimensions.forEach(function (dimension) {
          var field = createCoordinateInput(dimension, point[dimension], synchronize);
          field.querySelector("input").dataset.dimension = dimension;
          row.appendChild(field);
        });

        var remove = document.createElement("button");
        remove.type = "button";
        remove.className = "geometry-vertex-remove";
        remove.textContent = "\u00d7";
        remove.setAttribute("aria-label", "Remove vertex " + (index + 1));
        remove.disabled = geometry.length <= minimum;
        remove.addEventListener("click", function () {
          geometry.splice(index, 1);
          render();
        });
        row.appendChild(remove);
        list.appendChild(row);
      });
      synchronize();
    }

    addButton.addEventListener("click", function () {
      synchronize();
      geometry.push({});
      render();
      var lastInput = list.querySelector("[data-geometry-vertex]:last-child input");
      if (lastInput) lastInput.focus();
    });

    root.dataset.geometryReady = "true";
    render();
  }

  function refresh(scope) {
    (scope || document).querySelectorAll("[data-geometry-editor]").forEach(initialize);
  }

  window.AtlasCrafterGeometryEditor = { refresh: refresh };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { refresh(document); });
  } else {
    refresh(document);
  }
})();
