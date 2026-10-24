// Language selection for the AIO website.
// A new language needs an entry here plus data-l="<code>" blocks in the pages.
// Pages without a block for the chosen language fall back to English, then German.
(function () {
  "use strict";

  var LANGS = [
    { code: "de", name: "Deutsch", dir: "ltr" },
    { code: "en", name: "English", dir: "ltr" }
  ];
  var FALLBACK = ["en", "de"];
  var KEY = "aio-lang";

  function stored() {
    try { return localStorage.getItem(KEY); } catch (e) { return null; }
  }
  function store(code) {
    try { localStorage.setItem(KEY, code); } catch (e) { /* private mode: choice lasts for this page only */ }
  }
  function known(code) {
    return LANGS.some(function (l) { return l.code === code; });
  }
  function suggested() {
    var prefs = navigator.languages || [navigator.language || ""];
    for (var i = 0; i < prefs.length; i++) {
      var code = String(prefs[i]).toLowerCase().split("-")[0];
      if (known(code)) return code;
    }
    return "en";
  }

  function apply(code) {
    var root = document.documentElement;
    var blocks = document.querySelectorAll("[data-l]");
    var available = {};
    blocks.forEach(function (el) { available[el.getAttribute("data-l")] = true; });
    var chain = [code].concat(FALLBACK);
    var shown = chain.filter(function (c) { return available[c]; })[0] || code;
    blocks.forEach(function (el) { el.hidden = el.getAttribute("data-l") !== shown; });
    var meta = LANGS.filter(function (l) { return l.code === shown; })[0];
    root.lang = shown;
    root.dir = meta ? meta.dir : "ltr";
    root.classList.add("i18n");
    var titleEl = document.querySelector('[data-title][data-l="' + shown + '"]');
    if (titleEl) document.title = titleEl.getAttribute("data-title");
    document.querySelectorAll(".lang-list button").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.value === code));
    });
  }

  function buildDialog() {
    var dlg = document.createElement("dialog");
    dlg.id = "lang-dialog";
    dlg.setAttribute("aria-labelledby", "lang-dialog-title");
    dlg.innerHTML =
      '<h2 id="lang-dialog-title">Sprache wählen · Choose language</h2>' +
      "<p>Die Auswahl wird nur in deinem Browser gespeichert. · Your choice is only stored in your browser.</p>" +
      '<ul class="lang-list"></ul>';
    var list = dlg.querySelector(".lang-list");
    LANGS.forEach(function (l) {
      var li = document.createElement("li");
      var b = document.createElement("button");
      b.type = "button";
      b.value = l.code;
      b.lang = l.code;
      b.dir = l.dir;
      b.textContent = l.name;
      b.addEventListener("click", function () {
        store(l.code);
        apply(l.code);
        dlg.close();
      });
      li.appendChild(b);
      list.appendChild(li);
    });
    // Closing with Esc keeps the suggested language but does not store it.
    document.body.appendChild(dlg);
    return dlg;
  }

  function open(dlg, current) {
    if (typeof dlg.showModal === "function") {
      dlg.showModal();
      var btn = dlg.querySelector('button[value="' + current + '"]');
      if (btn) btn.focus();
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var saved = stored();
    var current = known(saved) ? saved : suggested();
    var dlg = buildDialog();
    apply(current);
    document.querySelectorAll("[data-open-lang]").forEach(function (el) {
      el.hidden = false;
      el.addEventListener("click", function () { open(dlg, document.documentElement.lang); });
    });
    if (!known(saved)) open(dlg, current);
  });
})();
