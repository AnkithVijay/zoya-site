/* Zoya Deals: renders deals.json as a simple list. No analytics, no third-party requests. */
(function () {
  "use strict";
  var $ = function (s) { return document.querySelector(s); };
  var cfg = { amazon_tag: "", flipkart_affid: "" };
  var deals = [];
  var STORE = { amazon: "Amazon", flipkart: "Flipkart" };

  function getJSON(u) {
    return fetch(u, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error(u + " " + r.status);
      return r.json();
    });
  }

  // Affiliate links: URL may carry {AMAZON_TAG} / {FLIPKART_AFFID}.
  // Empty config value -> that query param is removed (plain link).
  // Set value -> placeholder filled; URLs without a placeholder get the param appended.
  function setParam(url, key, val) {
    try {
      var u = new URL(url);
      if (val) u.searchParams.set(key, val); else u.searchParams.delete(key);
      return u.toString();
    } catch (e) { return url; }
  }
  function buyUrl(d) {
    var url = String(d.url || "");
    var store = (d.store || "amazon").toLowerCase();
    var key = store === "flipkart" ? "affid" : "tag";
    var val = store === "flipkart" ? cfg.flipkart_affid : cfg.amazon_tag;
    url = url.replace(/\{AMAZON_TAG\}|\{FLIPKART_AFFID\}/g, "__PH__");
    if (url.indexOf("__PH__") !== -1) {
      try {
        var u = new URL(url);
        u.searchParams.forEach(function (v, k) { if (v === "__PH__") key = k; });
        u.searchParams.delete(key);
        url = u.toString();
      } catch (e) { url = url.replace(/[?&][^=&]+=__PH__/g, ""); }
    }
    return setParam(url, key, (val || "").trim());
  }

  var inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
  function money(v) { return typeof v === "number" ? inr.format(v) : String(v || ""); }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  var SVGNS = "http://www.w3.org/2000/svg";
  function chevron() {
    var s = document.createElementNS(SVGNS, "svg");
    s.setAttribute("class", "chev"); s.setAttribute("viewBox", "0 0 8 14"); s.setAttribute("aria-hidden", "true");
    var p = document.createElementNS(SVGNS, "path"); p.setAttribute("d", "M1 1l6 6-6 6");
    s.appendChild(p); return s;
  }

  function row(d, isNew, i) {
    var store = (d.store || "amazon").toLowerCase();
    var storeName = STORE[store] || store;
    var li = el("li"), a = el("a", "row");
    a.href = buyUrl(d); a.target = "_blank"; a.rel = "nofollow sponsored noopener";
    a.setAttribute("aria-label", (d.title || "") + ", " + money(d.price) + " on " + storeName);
    var t = el("span", "thumb"), img = el("img");
    img.src = d.image; img.alt = ""; img.width = 46; img.height = 46; img.loading = i < 8 ? "eager" : "lazy"; 
    t.appendChild(img); a.appendChild(t);
    var info = el("span", "info");
    info.appendChild(el("p", "name", d.title));
    var meta = el("p", "meta", money(d.price) + " · " + storeName);
    if (isNew) meta.appendChild(el("span", "new", "New"));
    info.appendChild(meta);
    a.appendChild(info); a.appendChild(chevron());
    li.appendChild(a);
    return li;
  }

  function norm(s) { return String(s || "").toLowerCase(); }
  function matches(d, q) {
    if (!q) return true;
    var hay = norm([d.title, d.store, d.slug].join(" "));
    return q.split(/\s+/).every(function (w) { return hay.indexOf(w) !== -1; });
  }

  function render() {
    var q = norm($("#q").value).trim();
    var list = $("#list"); list.textContent = "";
    var shown = deals.filter(function (d) { return matches(d, q); });
    shown.forEach(function (d, i) { list.appendChild(row(d, d === deals[0], i)); });
    var empty = $("#empty");
    if (!deals.length) { empty.textContent = "New deals land with every reel."; empty.hidden = false; }
    else if (!shown.length) { empty.textContent = "No matches."; empty.hidden = false; }
    else empty.hidden = true;
  }

  Promise.all([
    getJSON("config.json").catch(function () { return {}; }),
    getJSON("deals.json")
  ]).then(function (res) {
    cfg.amazon_tag = (res[0] && res[0].amazon_tag) || "";
    cfg.flipkart_affid = (res[0] && res[0].flipkart_affid) || "";
    var list = Array.isArray(res[1]) ? res[1] : (res[1].deals || []);
    deals = list.filter(function (d) { return d && d.title && d.url; })
      .sort(function (a, b) { return String(b.date || "").localeCompare(String(a.date || "")); });
    if (deals.length > 6) {
      var q0 = new URLSearchParams(location.search).get("q");
      if (q0) $("#q").value = q0;
      $("#q").hidden = false;
      var t;
      $("#q").addEventListener("input", function () { clearTimeout(t); t = setTimeout(render, 80); });
    }
    render();
  }).catch(function (e) {
    $("#empty").textContent = "Deals couldn't load. Watch the latest on YouTube.";
    $("#empty").hidden = false;
    console.error(e);
  });

  window.__zoya = { buyUrl: buyUrl, cfg: cfg };
})();
