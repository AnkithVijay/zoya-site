/* Zoya Deals: one simple list of products.
   1. Paints instantly from products.json (static snapshot of the product_cards view).
   2. Refreshes from Supabase (public product_cards view) in the background and re-renders
      only if something changed.
   "View deal" goes through the /go edge function (?p=<product_id>), which logs the click and
   redirects with the affiliate tag. If Supabase is unreachable, links go straight to the
   store with the tag from config.json. */
(function () {
  "use strict";
  var $ = function (s) { return document.querySelector(s); };
  var cfg = { amazon_tag: "", flipkart_affid: "" };
  var products = [];
  var STORE = { amazon: "Amazon", flipkart: "Flipkart" };
  // Publishable key: safe in client code. RLS only allows reading products/price_history/product_cards.
  var SUPA = "https://rrsxsqtfotxkjgkbqnpx.supabase.co";
  var SUPA_KEY = "sb_publishable_qEE2Mx-rNBreFFh3dJGHrA_886HYX43";
  var COLS = "product_id,title,brand,category,tagline,highlights,image_url,store,store_product_id," +
    "product_url,reel_url,listing_price,current_price,previous_price,price_checked_at,featured,sort_order,created_at";
  var source = "none";     // snapshot | supabase
  var tracked = true;      // links via /go (false once Supabase is known to be down)
  var lastKey = "";

  function fromSupabase() {
    var ctl = typeof AbortController === "function" ? new AbortController() : null;
    var timer = ctl && setTimeout(function () { ctl.abort(); }, 6000);
    return fetch(SUPA + "/rest/v1/product_cards?select=" + COLS + "&order=featured.desc,sort_order.asc,created_at.desc", {
      headers: { apikey: SUPA_KEY, Accept: "application/json" },
      cache: "no-store", signal: ctl ? ctl.signal : undefined
    }).then(function (r) {
      if (timer) clearTimeout(timer);
      if (!r.ok) throw new Error("product_cards " + r.status);
      return r.json();
    }).then(function (rows) {
      if (!Array.isArray(rows)) throw new Error("product_cards: bad payload");
      return rows;
    });
  }
  function fromSnapshot() {
    return getJSON("products.json").then(function (j) {
      return Array.isArray(j) ? j : (j && j.products) || [];
    });
  }
  function normalize(r) {
    return {
      id: r.product_id, title: r.title, brand: r.brand, store: r.store, image: r.image_url,
      highlights: Array.isArray(r.highlights) ? r.highlights.filter(Boolean).slice(0, 4) : [],
      tagline: r.tagline, product_url: r.product_url, reel_url: r.reel_url,
      price: numOrNull(r.current_price), mrp: numOrNull(r.listing_price), prev: numOrNull(r.previous_price),
      checked: r.price_checked_at, created: r.created_at, featured: !!r.featured, sort: Number(r.sort_order) || 0
    };
  }
  function numOrNull(v) { if (v == null || v === "") return null; var n = Number(v); return isFinite(n) ? n : null; }

  function getJSON(u) {
    return fetch(u, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error(u + " " + r.status);
      return r.json();
    });
  }

  // Tracked: /go?p=<id> (logs the click, adds the tag server-side).
  // Untracked fallback: store URL + tag/affid from config.json (empty value -> plain link).
  function buyUrl(d) {
    if (tracked && d.id) return SUPA + "/functions/v1/go?p=" + encodeURIComponent(d.id);
    var store = (d.store || "amazon").toLowerCase();
    var key = store === "flipkart" ? "affid" : "tag";
    var val = ((store === "flipkart" ? cfg.flipkart_affid : cfg.amazon_tag) || "").trim();
    try {
      var u = new URL(String(d.product_url || ""));
      if (val) u.searchParams.set(key, val); else u.searchParams.delete(key);
      return u.toString();
    } catch (e) { return String(d.product_url || ""); }
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
    var hl = d.highlights.length ? d.highlights.join(" · ") : (d.tagline || "");
    if (hl) info.appendChild(el("p", "hl", hl));
    var when = asOf(d.checked);
    info.appendChild(el("p", "asof", storeName + (when ? " · " + when : "")));
    a.appendChild(info); a.appendChild(chevron());
    li.appendChild(a);
    return li;
  }

  function norm(s) { return String(s || "").toLowerCase(); }
  function matches(d, q) {
    if (!q) return true;
    var hay = norm([d.title, d.brand, d.store, d.id, d.highlights.join(" ")].join(" "));
    return q.split(/\s+/).every(function (w) { return hay.indexOf(w) !== -1; });
  }

  var newest = null;
  function render() {
    var q = norm($("#q").value).trim();
    var list = $("#list"); list.textContent = "";
    var shown = products.filter(function (d) { return matches(d, q); });
    shown.forEach(function (d, i) { list.appendChild(row(d, d === newest, i)); });
    var empty = $("#empty");
    if (!products.length) { empty.textContent = "New deals land with every reel."; empty.hidden = false; }
    else if (!shown.length) { empty.textContent = "No matches."; empty.hidden = false; }
    else empty.hidden = true;
  }

  var searchWired = false;
  function apply(rows, from) {
    var list = rows.map(normalize).filter(function (d) { return d.id && d.title && (d.product_url || tracked); });
    list.sort(function (a, b) {
      return (b.featured - a.featured) || (a.sort - b.sort) || String(b.created || "").localeCompare(String(a.created || ""));
    });
    source = from;
    document.documentElement.setAttribute("data-source", source);
    var key = JSON.stringify(list) + tracked;
    if (key === lastKey) return;            // nothing changed: keep the painted DOM
    lastKey = key;
    products = list;
    newest = products.reduce(function (m, d) { return !m || String(d.created) > String(m.created) ? d : m; }, null);
    if (products.length > 6 && !searchWired) {
      searchWired = true;
      var q0 = new URLSearchParams(location.search).get("q");
      if (q0) $("#q").value = q0;
      $("#q").hidden = false;
      var t;
      $("#q").addEventListener("input", function () { clearTimeout(t); t = setTimeout(render, 80); });
    }
    render();
  }

  // Start both requests at once: the snapshot paints first; Supabase replaces it when it lands.
  var live = fromSupabase();
  var snap = fromSnapshot().then(function (rows) {
    if (source !== "supabase") apply(rows, "snapshot");
    return rows;
  }, function (e) { console.warn("products.json unavailable", e); return null; });

  live.then(function (rows) { apply(rows, "supabase"); }, function (e) {
    console.warn("Supabase unavailable; showing the products.json snapshot with direct store links", e);
    tracked = false;
    return Promise.all([snap, getJSON("config.json").catch(function () { return {}; })]).then(function (res) {
      cfg.amazon_tag = (res[1] && res[1].amazon_tag) || "";
      cfg.flipkart_affid = (res[1] && res[1].flipkart_affid) || "";
      if (res[0]) { lastKey = ""; apply(res[0], "snapshot"); }
      else {
        $("#empty").textContent = "Deals couldn't load. Watch the latest on YouTube.";
        $("#empty").hidden = false;
      }
    });
  });

  window.__zoya = { buyUrl: buyUrl, cfg: cfg, source: function () { return source; }, products: function () { return products; } };
})();
