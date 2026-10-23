/* Zoya Deals: renders deals from Supabase (public deal_cards view) as a simple list.
   Falls back to deals.json if Supabase can't be reached. "View deal" goes through the
   /go edge function, which logs the click and redirects with the affiliate tag. */
(function () {
  "use strict";
  var $ = function (s) { return document.querySelector(s); };
  var cfg = { amazon_tag: "", flipkart_affid: "" };
  var deals = [];
  var STORE = { amazon: "Amazon", flipkart: "Flipkart" };
  // Publishable key: safe in client code. RLS only allows reading deals/price_history/deal_cards.
  var SUPA = "https://rrsxsqtfotxkjgkbqnpx.supabase.co";
  var SUPA_KEY = "sb_publishable_qEE2Mx-rNBreFFh3dJGHrA_886HYX43";
  var source = "json";

  function fromSupabase() {
    var ctl = typeof AbortController === "function" ? new AbortController() : null;
    var timer = ctl && setTimeout(function () { ctl.abort(); }, 5000);
    var cols = "id,title,store,image_url,listing_price,current_price,previous_price,price_checked_at,reel_url,created_at";
    return fetch(SUPA + "/rest/v1/deal_cards?select=" + cols + "&order=created_at.desc", {
      headers: { apikey: SUPA_KEY, Accept: "application/json" },
      cache: "no-store", signal: ctl ? ctl.signal : undefined
    }).then(function (r) {
      if (timer) clearTimeout(timer);
      if (!r.ok) throw new Error("deal_cards " + r.status);
      return r.json();
    }).then(function (rows) {
      if (!Array.isArray(rows)) throw new Error("deal_cards: bad payload");
      return rows.map(function (r) {
        return {
          slug: r.id, title: r.title, store: r.store, image: r.image_url,
          price: numOrNull(r.current_price), mrp: numOrNull(r.listing_price),
          prev: numOrNull(r.previous_price), checked: r.price_checked_at,
          date: r.created_at, reel_url: r.reel_url,
          url: SUPA + "/functions/v1/go?d=" + encodeURIComponent(r.id), tracked: true
        };
      });
    });
  }
  function numOrNull(v) { if (v == null || v === "") return null; var n = Number(v); return isFinite(n) ? n : null; }

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
    if (d.tracked) return d.url;
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
  var dfmt = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "Asia/Kolkata" });
  function asOf(v) {
    var t = v ? new Date(v) : null;
    return t && !isNaN(t) ? "Price as of " + dfmt.format(t) : "";
  }
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
    a.setAttribute("aria-label", "View deal: " + (d.title || "") + (typeof d.price === "number" ? ", " + money(d.price) : "") + " on " + storeName);
    var t = el("span", "thumb"), img = el("img");
    img.src = d.image; img.alt = ""; img.width = 46; img.height = 46; img.loading = i < 8 ? "eager" : "lazy"; 
    t.appendChild(img); a.appendChild(t);
    var info = el("span", "info");
    info.appendChild(el("p", "name", d.title));
    var hasPrice = typeof d.price === "number";
    var meta = el("p", "meta");
    meta.appendChild(el("span", "price", hasPrice ? money(d.price) : "See price"));
    if (hasPrice && typeof d.mrp === "number" && d.mrp > d.price) {
      meta.appendChild(document.createTextNode(" "));
      meta.appendChild(el("s", "mrp", money(d.mrp)));
      meta.appendChild(el("span", "off", " " + Math.round((1 - d.price / d.mrp) * 100) + "% off"));
    }
    if (hasPrice && typeof d.prev === "number" && d.prev !== d.price) {
      var down = d.price < d.prev;
      var chg = el("span", "chg " + (down ? "down" : "up"), (down ? "↓ " : "↑ ") + money(Math.abs(d.prev - d.price)));
      chg.title = "Was " + money(d.prev) + " at the previous check";
      meta.appendChild(chg);
    }
    if (isNew) meta.appendChild(el("span", "new", "New"));
    info.appendChild(meta);
    var when = asOf(d.checked || (source === "json" ? d.date : ""));
    info.appendChild(el("p", "asof", storeName + (when ? " · " + when : "")));
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

  function fromJSON() {
    return Promise.all([
      getJSON("config.json").catch(function () { return {}; }),
      getJSON("deals.json")
    ]).then(function (res) {
      cfg.amazon_tag = (res[0] && res[0].amazon_tag) || "";
      cfg.flipkart_affid = (res[0] && res[0].flipkart_affid) || "";
      var list = Array.isArray(res[1]) ? res[1] : (res[1].deals || []);
      return list.filter(function (d) { return d && d.title && d.url; }).map(function (d) {
        return Object.assign({}, d, { price: numOrNull(d.price), mrp: numOrNull(d.mrp) });
      });
    });
  }

  fromSupabase().then(function (list) { source = "supabase"; return list; }, function (e) {
    console.warn("Supabase unavailable, using deals.json", e);
    source = "json";
    return fromJSON();
  }).then(function (list) {
    deals = list.filter(function (d) { return d && d.title && d.url; })
      .sort(function (a, b) { return String(b.date || "").localeCompare(String(a.date || "")); });
    document.documentElement.setAttribute("data-source", source);
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

  window.__zoya = { buyUrl: buyUrl, cfg: cfg, source: function () { return source; } };
})();
