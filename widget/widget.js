(function () {
  "use strict";

  var scriptEl = document.currentScript;
  var API_BASE =
    (scriptEl && scriptEl.getAttribute("data-api-base")) ||
    location.origin;

  // Inject styles
  var style = document.createElement("style");
  style.textContent =
    '.qfix-widget{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}' +
    ".qfix-widget .qfix-btn{display:inline-flex;align-items:center;gap:8px;padding:12px 20px;border:none;border-radius:32px;font-size:14px;font-weight:500;cursor:pointer;transition:background .15s;text-decoration:none;color:#fff;background:#6b7280}" +
    ".qfix-widget .qfix-btn:hover{background:#4b5563}" +
    '.qfix-widget[data-theme="dark"] .qfix-btn{background:#fff;color:#1a1a1a}' +
    '.qfix-widget[data-theme="dark"] .qfix-btn:hover{background:#e5e5e5}' +
    '.qfix-widget[data-theme="light"] .qfix-btn{background:#1a1a1a;color:#fff}' +
    '.qfix-widget[data-theme="light"] .qfix-btn:hover{background:#333}' +
    ".qfix-widget .qfix-loading{display:inline-flex;align-items:center;gap:8px;padding:10px 0;color:#888;font-size:13px}" +
    ".qfix-widget .qfix-loading-dot{width:6px;height:6px;border-radius:50%;background:#888;animation:qfix-pulse 1.2s ease-in-out infinite}" +
    ".qfix-widget .qfix-loading-dot:nth-child(2){animation-delay:.2s}" +
    ".qfix-widget .qfix-loading-dot:nth-child(3){animation-delay:.4s}" +
    "@keyframes qfix-pulse{0%,80%,100%{opacity:.3}40%{opacity:1}}";
  document.head.appendChild(style);

  var SERVICES = [
    {
      key: "repair",
      label: "Reparera",
      icon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
        '<path d="M3 21L14 10"/><path d="M14 10l-3-3 5-5 3 3-5 5z"/><path d="M14 10a6 6 0 0 1-6 6"/></svg>'
    },
    {
      key: "adjustment",
      label: "Måttanpassa",
      icon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
        '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="4"/>' +
        '<path d="M22 12h-3"/><path d="M21.2 8.5l-2.8.8"/><path d="M21.2 15.5l-2.8-.8"/>' +
        '<path d="M19.5 5.5l-2.3 1.6"/><path d="M19.5 18.5l-2.3-1.6"/></svg>'
    },
    {
      key: "care",
      label: "Skötsel",
      icon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
        '<path d="M7 16.3c2.2 0 4-1.83 4-4.05 0-1.16-.57-2.26-1.71-3.19S7.29 6.75 7 5.3c-.29 1.45-1.14 2.84-2.29 3.76S3 11.1 3 12.25c0 2.22 1.8 4.05 4 4.05z"/>' +
        '<path d="M12.56 14.1c1.34 0 2.44-1.12 2.44-2.47 0-.7-.35-1.38-1.05-1.95S12.78 8.57 12.56 7.7c-.17.88-.7 1.73-1.4 2.3s-1.04 1.23-1.04 1.95c0 1.35 1.1 2.47 2.44 2.47z"/></svg>'
    }
  ];

  function initWidgets() {
    var elements = document.querySelectorAll("[data-qfix]");

    elements.forEach(function (el) {
      var productId = el.getAttribute("data-product-id");
      var brand = el.getAttribute("data-brand");
      if (!productId || !brand) return;

      var theme = el.getAttribute("data-theme") || "default";
      el.classList.add("qfix-widget");
      el.setAttribute("data-theme", theme);

      // Show loading dots
      el.innerHTML =
        '<div class="qfix-loading">' +
        '<span class="qfix-loading-dot"></span>' +
        '<span class="qfix-loading-dot"></span>' +
        '<span class="qfix-loading-dot"></span>' +
        "</div>";

      // Fetch service URLs
      fetch(API_BASE + "/widget/" + brand + "/product/" + productId)
        .then(function (res) {
          if (!res.ok) throw new Error("Not found");
          return res.json();
        })
        .then(function (data) {
          el.innerHTML = "";
          var services = data.services || {};

          SERVICES.forEach(function (svc) {
            var url = services[svc.key];
            if (!url) return;
            var a = document.createElement("a");
            a.className = "qfix-btn";
            a.href = url;
            a.target = "_blank";
            a.rel = "noopener";
            a.innerHTML = svc.icon + " " + svc.label;
            el.appendChild(a);
          });

          if (!el.children.length) el.innerHTML = "";
        })
        .catch(function () {
          el.innerHTML = "";
        });
    });
  }

  window.QFixWidget = { init: initWidgets };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initWidgets);
  } else {
    initWidgets();
  }
})();
