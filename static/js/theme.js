/* Dark/light theme toggle. Dark is the default; the choice is stored in localStorage ("kc-theme").
   The <head> bootstrap in base.html applies the saved theme before first paint. */
(function () {
  var KEY = "kc-theme";
  var COLORS = { dark: "#131e25", light: "#f7fafa" };
  var root = document.documentElement;

  function current() {
    return root.getAttribute("data-theme") === "light" ? "light" : "dark";
  }

  function apply(theme) {
    root.setAttribute("data-theme", theme);
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) { meta.setAttribute("content", COLORS[theme]); }
    document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
      var next = theme === "dark" ? "light" : "dark";
      btn.setAttribute("aria-pressed", theme === "light" ? "true" : "false");
      btn.setAttribute("title", "Switch to " + next + " mode");
    });
  }

  function init() {
    apply(current());
    document.addEventListener("click", function (event) {
      var btn = event.target && event.target.closest ? event.target.closest("[data-theme-toggle]") : null;
      if (!btn) { return; }
      var next = current() === "dark" ? "light" : "dark";
      apply(next);
      try { localStorage.setItem(KEY, next); } catch (e) { /* storage blocked: theme lasts for this page only */ }
    });
  }

  if (document.readyState === "loading") { document.addEventListener("DOMContentLoaded", init); } else { init(); }
})();
