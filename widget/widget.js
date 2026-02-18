(function () {
  "use strict";

  // Use data-api-base attribute to override, or auto-detect:
  // - Same origin when served from a proxy/CDN
  // - Direct API URL as fallback
  var scriptEl = document.currentScript;
  var API_BASE =
    (scriptEl && scriptEl.getAttribute("data-api-base")) ||
    (location.protocol === "file:" ? "https://kappahl-qfix.fly.dev" :
      location.origin);

  // Inject styles
  var style = document.createElement("style");
  style.textContent =
    '.qfix-widget{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;margin:12px 0}' +
    ".qfix-widget .qfix-btn{display:inline-flex;align-items:center;gap:8px;padding:10px 20px;border:none;border-radius:6px;font-size:14px;font-weight:600;cursor:pointer;transition:background .2s,transform .1s;text-decoration:none}" +
    ".qfix-widget .qfix-btn:hover{transform:translateY(-1px)}" +
    ".qfix-widget .qfix-btn:active{transform:translateY(0)}" +
    '.qfix-widget[data-theme="dark"] .qfix-btn{background:#fff;color:#1a1a1a}' +
    '.qfix-widget[data-theme="dark"] .qfix-btn:hover{background:#e5e5e5}' +
    ".qfix-widget .qfix-btn--light{background:#1a1a1a;color:#fff}" +
    ".qfix-widget .qfix-btn--light:hover{background:#333}" +
    ".qfix-widget .qfix-loading{display:inline-flex;align-items:center;gap:8px;padding:10px 0;color:#888;font-size:13px}" +
    ".qfix-widget .qfix-loading-dot{width:6px;height:6px;border-radius:50%;background:#888;animation:qfix-pulse 1.2s ease-in-out infinite}" +
    ".qfix-widget .qfix-loading-dot:nth-child(2){animation-delay:.2s}" +
    ".qfix-widget .qfix-loading-dot:nth-child(3){animation-delay:.4s}" +
    "@keyframes qfix-pulse{0%,80%,100%{opacity:.3}40%{opacity:1}}";
  document.head.appendChild(style);

  var WRENCH_SVG =
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>' +
    "</svg>";

  function initWidgets() {
    var elements = document.querySelectorAll("[data-qfix], #qfix-repair");

    elements.forEach(function (el) {
      var productId = el.getAttribute("data-product-id");
      var brand = el.getAttribute("data-brand") || "kappahl";
      var theme = el.getAttribute("data-theme") || "light";
      var apiKey = el.getAttribute("data-api-key");

      if (!productId) return;

      el.classList.add("qfix-widget");
      el.setAttribute("data-theme", theme);

      // Show loading state
      el.innerHTML =
        '<div class="qfix-loading">' +
        '<span class="qfix-loading-dot"></span>' +
        '<span class="qfix-loading-dot"></span>' +
        '<span class="qfix-loading-dot"></span>' +
        "</div>";

      var fetchOpts = {};
      if (apiKey) {
        fetchOpts.headers = { "X-API-Key": apiKey };
      }

      fetch(API_BASE + "/" + brand + "/product/" + productId, fetchOpts)
        .then(function (res) {
          if (!res.ok) throw new Error("Not found");
          return res.json();
        })
        .then(function (data) {
          var qfixUrl = data.qfix && data.qfix.qfix_url;
          if (!qfixUrl) {
            el.innerHTML = "";
            return;
          }

          var btnClass = theme === "dark" ? "qfix-btn" : "qfix-btn qfix-btn--light";
          el.innerHTML =
            '<a class="' + btnClass + '" href="' + qfixUrl + '" target="_blank" rel="noopener">' +
            WRENCH_SVG +
            "Repair this item" +
            "</a>";
        })
        .catch(function () {
          el.innerHTML = "";
        });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initWidgets);
  } else {
    initWidgets();
  }
})();
