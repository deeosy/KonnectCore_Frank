/* Real-time identification number formatter.
 *
 * The pure formatter API is exported for Node tests. The DOM controller below
 * only runs on pages that contain the member identification fields.
 */
(function (root, factory) {
  "use strict";
  var api = factory();
  if (typeof module === "object" && module.exports) { module.exports = api; }
  root.KonnectIDFormatters = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function clamp(value, minimum, maximum) {
    return Math.min(Math.max(value, minimum), maximum);
  }

  function integer(value, fallback) {
    var number = parseInt(value, 10);
    return isNaN(number) ? fallback : number;
  }

  function createFormatter(profile) {
    profile = profile || {};
    var maxLength = integer(profile.max_length, 100);
    var minLength = integer(profile.min_length, 0);
    var isGhanaCard = profile.display === "ghana_card";
    var prefix = isGhanaCard ? (profile.prefix || "GHA") + "-" : "";
    var sanitizeMode = profile.sanitize || "plain";
    var pattern = profile.pattern || "";
    var error = profile.error || "Enter a valid identification number.";

    function toData(value) {
      var text = String(value == null ? "" : value);
      if (sanitizeMode === "digits") {
        return text.replace(/[^0-9]/g, "").slice(0, maxLength);
      }
      if (sanitizeMode === "upper_alnum") {
        return text.replace(/[^A-Za-z0-9]/g, "").toUpperCase().slice(0, maxLength);
      }
      return text.trim().slice(0, maxLength);
    }

    function toDisplay(data) {
      var text = String(data == null ? "" : data);
      if (!isGhanaCard) { return text; }
      return prefix + text.slice(0, 9) + (text.length > 9 ? "-" + text.slice(9, 10) : "");
    }

    function dataIndexFromCaret(value, caret) {
      var text = String(value == null ? "" : value);
      var position = clamp(caret == null ? text.length : caret, 0, text.length);
      return toData(text.slice(0, position)).length;
    }

    function caretFromDataIndex(data, index) {
      var text = String(data == null ? "" : data);
      var position = clamp(index, 0, text.length);
      if (!isGhanaCard) { return position; }
      if (position <= 0) { return prefix.length; }
      if (position <= 9) { return prefix.length + position; }
      return prefix.length + 10 + (position - 9);
    }

    function validate(data) {
      var text = String(data == null ? "" : data);
      if (!text) { return ""; }
      if (text.length < minLength || text.length > maxLength) { return error; }
      if (pattern) {
        try {
          if (!new RegExp(pattern).test(text)) { return error; }
        } catch (ignored) {
          return "";
        }
      }
      return "";
    }

    function canAutoFormat(value, data) {
      if (!value) { return true; }
      // Plain "Other" values can be historical; leave them untouched until
      // the operator deliberately edits them.
      if (!pattern) { return false; }
      var text = String(data == null ? "" : data);
      return text.length >= minLength && text.length <= maxLength;
    }

    return {
      idType: profile.id_type || "",
      label: profile.label || "Identification",
      placeholder: profile.placeholder || "Enter your identification number.",
      help: profile.help || "Enter the number printed on your document.",
      inputMode: profile.input_mode || "text",
      autocomplete: profile.autocomplete || "off",
      issuingAuthority: profile.issuing_authority || "",
      requiresFrontImage: !!profile.requires_front_image,
      prefix: prefix,
      minLength: minLength,
      maxLength: maxLength,
      maxInputLength: toDisplay("0".repeat(maxLength)).length,
      toData: toData,
      toDisplay: toDisplay,
      dataIndexFromCaret: dataIndexFromCaret,
      caretFromDataIndex: caretFromDataIndex,
      validate: validate,
      canAutoFormat: canAutoFormat,
    };
  }

  function formattersFromConfig(config) {
    var formatters = {};
    (config || []).forEach(function (profile) {
      if (profile && profile.id_type) {
        formatters[profile.id_type] = createFormatter(profile);
      }
    });
    return formatters;
  }

  /* Rewrite the real input value from a sanitized canonical value and map the
   * caret from the old formatted position to the new formatted position. */
  function applyValue(formatter, value, caret) {
    var text = String(value == null ? "" : value);
    var dataIndex = formatter.dataIndexFromCaret(text, caret);
    var data = formatter.toData(text);
    var display = formatter.toDisplay(data);
    return {
      data: data,
      display: display,
      caret: clamp(formatter.caretFromDataIndex(data, dataIndex), 0, display.length),
    };
  }

  return {
    createFormatter: createFormatter,
    formattersFromConfig: formattersFromConfig,
    applyValue: applyValue,
  };
});

if (typeof document !== "undefined") {
  (function () {
    "use strict";

    var type = document.getElementById("id_id_type");
    var input = document.querySelector("[data-id-number]");
    var configNode = document.getElementById("id-profile-config");
    if (!type || !input || !configNode) { return; }

    var api = (typeof globalThis !== "undefined" ? globalThis : window).KonnectIDFormatters;
    if (!api) { return; }

    var help = document.querySelector("[data-id-help]");
    var status = document.querySelector("[data-id-validation]");
    var otherFields = document.querySelector("[data-other-fields]");
    var form = input.form;
    var numberField = input.closest ? input.closest(".id-number-field") : null;
    var authority = form ? form.querySelector('[name="id_issuing_authority"]') : null;
    function fieldFor(name) {
      var element = form ? form.querySelector('[name="' + name + '"]') : null;
      return element && element.closest ? element.closest("p") : null;
    }
    var frontField = fieldFor("id_front");
    var backField = fieldFor("id_back");
    var formatters = {};
    try {
      formatters = api.formattersFromConfig(JSON.parse(configNode.getAttribute("data-profiles") || "[]"));
    } catch (error) {
      return;
    }

    var plainFormatter = api.createFormatter({ sanitize: "plain", max_length: 100 });
    var previousType = type.value || "";

    function formatterFor(idType) {
      return formatters[idType] || plainFormatter;
    }

    function currentFormatter() {
      return formatterFor(type.value);
    }

    function setDisplay(result, moveCaret) {
      if (input.value !== result.display) { input.value = result.display; }
      if (moveCaret) {
        try { input.setSelectionRange(result.caret, result.caret); } catch (ignored) { /* no-op */ }
      }
    }

    function updateStatus(result) {
      if (!status) { return; }
      var formatter = currentFormatter();
      var legacy = input.getAttribute("data-legacy-display");
      if (legacy && input.value === legacy) {
        status.textContent = "Existing number kept. Edit the number to revalidate it.";
        status.className = "id-validation";
        input.setCustomValidity("");
        input.removeAttribute("aria-invalid");
        return;
      }
      var message = formatter.validate(result.data);
      if (message) {
        status.textContent = message;
        status.className = "id-validation is-invalid";
        input.setAttribute("aria-invalid", "true");
        input.setCustomValidity(message);
      } else if (result.data) {
        status.textContent = "Valid format. Stored as " + formatter.toDisplay(result.data) + ".";
        status.className = "id-validation is-valid";
        input.removeAttribute("aria-invalid");
        input.setCustomValidity("");
      } else {
        status.textContent = "";
        status.className = "id-validation";
        input.removeAttribute("aria-invalid");
        input.setCustomValidity("");
      }
    }

    function run(value, caret, moveCaret) {
      var result = api.applyValue(currentFormatter(), value == null ? input.value : value, caret);
      setDisplay(result, moveCaret !== false);
      updateStatus(result);
      return result;
    }

    function applyProfile() {
      var formatter = currentFormatter();
      input.setAttribute("placeholder", formatter.placeholder);
      input.setAttribute("autocomplete", formatter.autocomplete);
      input.setAttribute("inputmode", formatter.inputMode);
      input.maxLength = formatter.maxInputLength;
      // Validation is reported through setCustomValidity so a formatted Ghana
      // Card value is not blocked by a digits-only native pattern.
      input.removeAttribute("pattern");
      if (help) { help.textContent = formatter.help; }

      var none = !type.value;
      // "No identification" removes every ID-specific input from the form.
      if (numberField) { numberField.classList.toggle("is-hidden", none); }
      if (frontField) { frontField.classList.toggle("is-hidden", none); }
      if (backField) { backField.classList.toggle("is-hidden", none); }
      if (status) { status.classList.toggle("is-hidden", none); }
      if (otherFields) {
        otherFields.classList.toggle("is-hidden", none || type.value !== "other");
      }

      if (authority && !none && type.value !== "other" && formatter.issuingAuthority) {
        // Populate the known issuer on selection; operators can still edit it.
        if (!authority.value || authority.dataset.autoIssuer !== type.value) {
          authority.value = formatter.issuingAuthority;
          authority.dataset.autoIssuer = type.value;
        }
      }
    }

    function clampToPrefix() {
      var formatter = currentFormatter();
      if (!formatter.prefix) { return; }
      var start = input.selectionStart;
      var end = input.selectionEnd;
      if (start == null || end == null || (start >= formatter.prefix.length && end >= formatter.prefix.length)) {
        return;
      }
      var data = formatter.toData(input.value);
      var startIndex = formatter.dataIndexFromCaret(input.value, start);
      var startPosition = formatter.caretFromDataIndex(data, startIndex);
      var endPosition = startPosition;
      if (end > start && end > formatter.prefix.length) {
        endPosition = formatter.caretFromDataIndex(data, formatter.dataIndexFromCaret(input.value, end));
      }
      try { input.setSelectionRange(startPosition, Math.max(endPosition, startPosition)); } catch (ignored) { /* no-op */ }
    }

    function protectPrefix(event) {
      var formatter = currentFormatter();
      if (!formatter.prefix) { return; }
      var start = input.selectionStart;
      var end = input.selectionEnd;
      if (start == null || end == null) { return; }
      if (start >= formatter.prefix.length && end >= formatter.prefix.length) { return; }
      var collapsed = start === end;
      var isDelete = event.type === "keydown"
        ? event.key === "Backspace" || event.key === "Delete"
        : event.inputType === "deleteContentBackward" || event.inputType === "deleteContentForward";
      if (collapsed && isDelete) {
        event.preventDefault();
        try { input.setSelectionRange(formatter.prefix.length, formatter.prefix.length); } catch (ignored) { /* no-op */ }
        return;
      }
      clampToPrefix();
    }

    input.addEventListener("keydown", protectPrefix);
    input.addEventListener("beforeinput", protectPrefix);
    input.addEventListener("paste", clampToPrefix);

    input.addEventListener("input", function () {
      input.removeAttribute("data-legacy-display");
      run(undefined, input.selectionStart, true);
    });

    type.addEventListener("change", function () {
      var canonical = formatterFor(previousType).toData(input.value);
      previousType = type.value;
      var formatter = currentFormatter();
      var result = api.applyValue(formatter, formatter.toDisplay(formatter.toData(canonical)));
      result.caret = formatter.caretFromDataIndex(result.data, result.data.length);
      input.removeAttribute("data-legacy-display");
      applyProfile();
      setDisplay(result, document.activeElement === input);
      updateStatus(result);
    });

    if (form) {
      form.addEventListener("submit", function (event) {
        var result = run(undefined, input.selectionStart, false);
        if (!input.checkValidity()) {
          event.preventDefault();
          input.focus();
        }
        return result;
      });
    }

    applyProfile();
    var initial = api.applyValue(currentFormatter(), input.value, input.value.length);
    if (currentFormatter().canAutoFormat(input.value, initial.data)) {
      input.removeAttribute("data-legacy-display");
      setDisplay(initial, false);
      updateStatus(initial);
    } else {
      updateStatus(initial);
    }
  })();
}
