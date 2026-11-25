(() => {
  "use strict";

  const API = (window.AGRIASSIST_API_BASE || "http://localhost:8000").replace(/\/$/, "");
  const I18N = window.AGRI_I18N || { en: {} };
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  // Browser storage is used only for per-viewer conveniences (session token, language, last location).
  const store = {
    get(key) { try { return localStorage.getItem(key); } catch (_) { return null; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch (_) { /* storage blocked */ } },
    del(key) { try { localStorage.removeItem(key); } catch (_) { /* storage blocked */ } },
  };

  const state = {
    token: store.get("aa_token"),
    user: null,
    lang: store.get("aa_lang") || "en",
    view: "dashboard",
    loadedViews: new Set(),
  };

  const t = (key) => (I18N[state.lang] && I18N[state.lang][key]) || (I18N.en && I18N.en[key]) || key;

  // ---------- small helpers ----------
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function money(value) {
    if (value === null || value === undefined) return "-";
    return "₹" + Math.round(value).toLocaleString("en-IN");
  }

  function num(value, digits = 2) {
    if (value === null || value === undefined || Number.isNaN(value)) return "-";
    return Number(value).toLocaleString("en-IN", { maximumFractionDigits: digits });
  }

  function pct(value, digits = 1) {
    return value === null || value === undefined ? "-" : (value * 100).toFixed(digits) + "%";
  }

  function toast(message, isError = false) {
    const box = $("#toast");
    box.textContent = message;
    box.classList.toggle("error", isError);
    box.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { box.hidden = true; }, 4200);
  }

  function friendlyError(detail) {
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length) return "Please check the values you entered.";
    return "Something went wrong. Please try again.";
  }

  // Horizontal bar rows (HTML + CSS, so they scale on phones).
  function barRows(container, items, { unit = "", format = (v) => num(v), warnBelow = null } = {}) {
    // Appends to the container (it does not clear it), so headings and badges above the chart survive.
    if (!items.length) {
      container.appendChild(el("p", "hint", "No data yet."));
      return;
    }
    const max = Math.max(...items.map((i) => i.value), 1e-9);
    const wrap = el("div", "bars");
    items.forEach((item) => {
      const row = el("div", "bar-row");
      row.appendChild(el("span", "bar-name", item.label));
      const track = el("div", "bar-track");
      const fill = el("div", "bar-fill");
      if (warnBelow !== null && item.value < warnBelow) fill.classList.add("warn");
      fill.style.width = Math.max(0, (item.value / max) * 100).toFixed(1) + "%";
      track.appendChild(fill);
      row.appendChild(track);
      row.appendChild(el("span", "bar-value", format(item.value) + unit));
      wrap.appendChild(row);
    });
    container.appendChild(wrap);
  }

  // ---------- API client ----------
  async function api(path, { method = "GET", body, form, auth = true } = {}) {
    const headers = {};
    if (auth && state.token) headers.Authorization = "Bearer " + state.token;
    let payload;
    if (form) {
      payload = form;
    } else if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(body);
    }
    let res;
    try {
      res = await fetch(API + path, { method, headers, body: payload });
    } catch (_) {
      throw new Error("Cannot reach the AgriAssist server. Check that the backend is running and your internet is on.");
    }
    const data = await res.json().catch(() => ({}));
    if (res.status === 401 && auth && state.token) {
      logout(true);
      throw new Error("Your session has expired. Please log in again.");
    }
    if (!res.ok) throw new Error(friendlyError(data.detail));
    return data;
  }

  // ---------- auth ----------
  function setAuthMode(mode) {
    $$(".seg").forEach((b) => b.classList.toggle("active", b.dataset.auth === mode));
    $("#login-form").hidden = mode !== "login";
    $("#register-form").hidden = mode !== "register";
    $("#auth-error").hidden = true;
  }

  function showAuthError(message) {
    const box = $("#auth-error");
    box.textContent = message;
    box.hidden = false;
  }

  function startSession(token, user) {
    state.token = token;
    state.user = user;
    store.set("aa_token", token);
    setLanguage(user.language || state.lang, false);
    $("#welcome-name").textContent = user.name;
    $("#auth-view").hidden = true;
    $("#app-view").hidden = false;
    $("#logout-btn").hidden = false;
    state.loadedViews.clear();
    showView("dashboard");
    refreshBell();
  }

  function logout(silent = false) {
    state.token = null;
    state.user = null;
    store.del("aa_token");
    $("#app-view").hidden = true;
    $("#auth-view").hidden = false;
    $("#logout-btn").hidden = true;
    setAuthMode("login");
    if (!silent) toast("You have logged out.");
  }

  async function submitLogin(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    try {
      const data = await api("/api/auth/login", {
        method: "POST", auth: false,
        body: { email: form.email.value.trim(), password: form.password.value },
      });
      startSession(data.token, data.user);
    } catch (err) {
      showAuthError(err.message);
    } finally {
      button.disabled = false;
    }
  }

  async function submitRegister(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    try {
      const data = await api("/api/auth/register", {
        method: "POST", auth: false,
        body: {
          name: form.name.value.trim(),
          email: form.email.value.trim(),
          password: form.password.value,
          language: form.language.value,
        },
      });
      toast("Account created. Welcome to AgriAssist!");
      startSession(data.token, data.user);
    } catch (err) {
      showAuthError(err.message);
    } finally {
      button.disabled = false;
    }
  }

  // ---------- language ----------
  function setLanguage(lang, saveToServer) {
    if (!I18N[lang]) lang = "en";
    state.lang = lang;
    store.set("aa_lang", lang);
    document.documentElement.lang = lang;
    $("#lang-select").value = lang;
    $$("[data-i18n]").forEach((node) => { node.textContent = t(node.dataset.i18n); });
    if (saveToServer && state.token) {
      api("/api/me", { method: "PATCH", body: { language: lang } }).catch(() => {});
    }
  }

  // ---------- navigation ----------
  const LOADERS = {
    dashboard: loadDashboard,
    ask: loadAsk,
    alerts: loadAlerts,
  };

  function showView(name) {
    state.view = name;
    $$(".tab").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
    $$("[data-view-panel]").forEach((p) => { p.hidden = p.dataset.viewPanel !== name; });
    if (LOADERS[name]) LOADERS[name]();
  }

  // ---------- notifications ----------
  async function refreshBell() {
    try {
      const data = await api("/api/notifications");
      const count = $("#bell-count");
      count.hidden = data.unread === 0;
      count.textContent = data.unread > 9 ? "9+" : String(data.unread);
      $("#stat-unread") && ($("#stat-unread").textContent = String(data.unread));
      return data;
    } catch (_) {
      return null;
    }
  }

  async function loadAlerts() {
    const list = $("#alert-list");
    list.textContent = "";
    const data = await refreshBell();
    if (!data) return;
    if (!data.items.length) {
      list.appendChild(el("li", "muted", "No alerts yet. Weather and price alerts will appear here."));
      return;
    }
    data.items.forEach((n) => {
      const li = el("li", n.read ? "" : "unread");
      li.appendChild(el("strong", "", n.title));
      li.appendChild(el("p", "", n.body));
      const footer = el("div", "toolbar");
      footer.style.marginBottom = "0";
      footer.appendChild(el("span", "muted", new Date(n.created_at).toLocaleString("en-IN")));
      if (!n.read) {
        const btn = el("button", "ghost", "Mark as read");
        btn.type = "button";
        btn.addEventListener("click", async () => {
          await api(`/api/notifications/${n.id}/read`, { method: "POST" });
          loadAlerts();
        });
        footer.appendChild(btn);
      }
      li.appendChild(footer);
      list.appendChild(li);
    });
  }

  // ---------- dashboard ----------
  async function loadDashboard() {
    $("#welcome-name").textContent = state.user ? state.user.name : "";
    try {
      const models = await api("/api/models", { auth: false });
      const disease = models.disease_metrics;
      const crop = models.crop_metrics;
      $("#stat-disease").textContent = disease ? pct(disease.test_accuracy) : "-";
      $("#stat-crop").textContent = crop ? pct(crop.test_accuracy) : "-";
      if (disease) {
        const items = Object.entries(disease.per_class).map(([key, v]) => ({
          label: key.replace("___", " - ").replace(/_/g, " "),
          value: v["f1-score"],
        }));
        $("#chart-disease").textContent = "";
        barRows($("#chart-disease"), items, { format: (v) => v.toFixed(2) });
      }
    } catch (err) {
      toast(err.message, true);
    }
    try {
      const docs = await api("/api/documents", { auth: false });
      $("#stat-docs").textContent = String(docs.length);
    } catch (_) {
      $("#stat-docs").textContent = "-";
    }
    const data = await refreshBell();
    const list = $("#dash-alerts");
    list.textContent = "";
    (data ? data.items.slice(0, 3) : []).forEach((n) => list.appendChild(el("li", "", `${n.title}: ${n.body}`)));
    if (data && !data.items.length) list.appendChild(el("li", "muted", "No alerts yet."));
  }

  // ---------- Ask AI (RAG) ----------
  async function loadAsk() {
    if (state.loadedViews.has("ask")) return;
    state.loadedViews.add("ask");
    await loadDocuments();
  }

  async function loadDocuments() {
    const list = $("#doc-list");
    try {
      const docs = await api("/api/documents", { auth: false });
      list.textContent = "";
      if (!docs.length) list.appendChild(el("li", "muted", "No documents yet."));
      docs.forEach((d) => {
        const li = el("li");
        li.style.display = "flex";
        li.style.justifyContent = "space-between";
        li.style.gap = "8px";
        li.appendChild(el("span", "", d.name));
        li.appendChild(el("span", "muted", `${d.chunks} passage${d.chunks === 1 ? "" : "s"}`));
        list.appendChild(li);
      });
    } catch (err) {
      list.textContent = "";
      list.appendChild(el("li", "muted", err.message));
    }
  }

  function addUserMessage(text) {
    const wrap = el("div", "msg user");
    wrap.appendChild(el("div", "bubble", text));
    $("#chat").appendChild(wrap);
    $("#chat").scrollTop = $("#chat").scrollHeight;
  }

  function appendWithCitations(parent, text) {
    text.split(/(\[\d+\])/).forEach((part) => {
      if (/^\[\d+\]$/.test(part)) parent.appendChild(el("sup", "cite", part));
      else if (part) parent.appendChild(document.createTextNode(part));
    });
  }

  const MODE_LABEL = {
    generative: "AI answer from your documents",
    extractive: "Retrieved guidance (no AI model configured)",
    fallback: "Retrieved guidance (AI model unavailable)",
  };
  const ESCALATION_TITLE = {
    risk: "Please seek urgent help",
    low_confidence: "I could not answer this reliably",
  };

  function addBotMessage(data) {
    const wrap = el("div", "msg bot");
    const bubble = el("div", "bubble");
    wrap.appendChild(bubble);
    if (data.escalated) {
      const card = el("div", "escalate");
      card.appendChild(el("strong", "", ESCALATION_TITLE[data.reason] || "Please contact an expert"));
      card.appendChild(el("p", "", data.message));
      bubble.appendChild(card);
    } else {
      bubble.appendChild(el("span", "badge", MODE_LABEL[data.mode] || "Answer"));
      (data.answer || "").split(/\n\s*\n/).forEach((para) => {
        if (!para.trim()) return;
        const p = el("p");
        appendWithCitations(p, para.trim());
        bubble.appendChild(p);
      });
      if (data.warning) bubble.appendChild(el("p", "warning", data.warning));
      if (data.citations && data.citations.length) {
        const details = el("details", "sources");
        details.appendChild(el("summary", "", `Sources (${data.citations.length})`));
        const list = el("ol");
        data.citations.forEach((c) => {
          const item = el("li");
          item.appendChild(el("strong", "", `[${c.id}] ${c.source}, page ${c.page}`));
          item.appendChild(el("span", "snippet", c.snippet));
          list.appendChild(item);
        });
        details.appendChild(list);
        bubble.appendChild(details);
      }
    }
    $("#chat").appendChild(wrap);
    $("#chat").scrollTop = $("#chat").scrollHeight;
  }

  async function askQuestion(question) {
    question = question.trim();
    if (question.length < 3) return;
    addUserMessage(question);
    $("#question").value = "";
    const form = $("#ask-form");
    const send = $("#send");
    send.disabled = true;
    const typing = el("div", "msg bot typing");
    typing.appendChild(el("div", "bubble", "Searching the guides..."));
    $("#chat").appendChild(typing);
    try {
      const data = await api("/api/ask", { method: "POST", body: { question } });
      typing.remove();
      addBotMessage(data);
    } catch (err) {
      typing.remove();
      addBotMessage({ escalated: true, reason: "low_confidence", message: err.message });
    } finally {
      send.disabled = false;
      form.querySelector("textarea").focus();
    }
  }

  // ---------- disease ----------
  function renderDisease(data) {
    const box = $("#disease-result");
    box.textContent = "";
    const top = data.predictions[0];
    box.appendChild(el("h3", "", `${top.crop} - ${top.condition}`));
    const badge = el("span", top.healthy ? "badge good" : "badge risk", top.healthy ? "Looks healthy" : "Possible disease");
    box.appendChild(badge);
    box.appendChild(el("p", "hint", `Confidence ${pct(top.confidence)} for the top match.`));
    const items = data.predictions.map((p) => ({ label: `${p.crop} - ${p.condition}`, value: p.confidence }));
    barRows(box, items, { format: (v) => pct(v, 0) });
    const metrics = el("div", "metrics");
    metrics.appendChild(metricTile("Model accuracy (held-out test)", pct(data.model_test_accuracy)));
    metrics.appendChild(metricTile("Classes", "10"));
    box.appendChild(metrics);
    box.appendChild(el("p", "disclaimer", data.disclaimer));
  }

  function metricTile(label, value, cls = "") {
    const tile = el("div", "metric " + cls);
    tile.appendChild(el("small", "", label));
    tile.appendChild(el("strong", "", value));
    return tile;
  }

  // ---------- crops ----------
  function renderCrops(data) {
    const box = $("#crop-result");
    box.textContent = "";
    const top = data.recommendations[0];
    box.appendChild(el("h3", "", `Recommended: ${top.crop}`));
    box.appendChild(el("p", "hint", `Model probability ${pct(top.probability)}.`));
    data.recommendations.forEach((r) => {
      const block = el("div", "nutrient");
      block.appendChild(el("div", "nutrient-head"));
      block.firstChild.appendChild(el("strong", "", r.crop));
      block.firstChild.appendChild(el("span", "badge", pct(r.probability)));
      if (r.warnings.length) {
        const ul = el("ul", "warn-list");
        r.warnings.forEach((w) => ul.appendChild(el("li", "", w)));
        block.appendChild(ul);
      } else {
        block.appendChild(el("p", "hint", "All inputs are within the ideal range for this crop."));
      }
      box.appendChild(block);
    });
    box.appendChild(el("p", "disclaimer", "Based on a model trained on the synthetic dataset described in the README. Use local advice before planting."));
  }

  // ---------- soil ----------
  function renderSoil(data) {
    const box = $("#soil-result");
    box.textContent = "";
    const head = el("div", "nutrient-head");
    head.appendChild(el("h3", "", "Soil fertility"));
    const overallClass = data.overall === "Good" ? "good" : data.overall === "Poor" ? "poor" : "needs";
    head.appendChild(el("span", `badge ${overallClass}`, data.overall));
    box.appendChild(head);

    const items = data.nutrients.map((n) => ({ label: n.name, value: n.value, rating: n.rating, advice: n.advice }));
    items.forEach((n) => {
      const block = el("div", "nutrient");
      const h = el("div", "nutrient-head");
      h.appendChild(el("strong", "", `${n.label[0].toUpperCase()}${n.label.slice(1)}: ${num(n.value, 1)} kg/ha`));
      h.appendChild(el("span", `badge ${n.rating}`, n.rating));
      block.appendChild(h);
      block.appendChild(el("p", "hint", n.advice));
      box.appendChild(block);
    });

    const ph = el("div", "nutrient");
    const phHead = el("div", "nutrient-head");
    phHead.appendChild(el("strong", "", `pH: ${num(data.ph.value, 1)}`));
    phHead.appendChild(el("span", `badge ${data.ph.rating}`, data.ph.rating));
    ph.appendChild(phHead);
    ph.appendChild(el("p", "hint", data.ph.advice));
    box.appendChild(ph);

    const oc = el("div", "nutrient");
    const ocHead = el("div", "nutrient-head");
    ocHead.appendChild(el("strong", "", `Organic carbon: ${num(data.organic_carbon.value, 2)}%`));
    ocHead.appendChild(el("span", `badge ${data.organic_carbon.rating}`, data.organic_carbon.rating));
    oc.appendChild(ocHead);
    oc.appendChild(el("p", "hint", data.organic_carbon.advice));
    box.appendChild(oc);

    box.appendChild(el("p", "disclaimer", data.note));
  }

  // ---------- weather ----------
  const DAY = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });

  async function fetchWeather() {
    const form = $("#weather-form");
    const lat = Number(form.lat.value);
    const lon = Number(form.lon.value);
    const box = $("#weather-result");
    box.textContent = "";
    box.appendChild(el("p", "hint", "Fetching forecast..."));
    try {
      const data = await api(`/api/weather?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`);
      renderWeather(data);
      store.set("aa_loc", JSON.stringify({ lat, lon }));
    } catch (err) {
      box.textContent = "";
      const alert = el("div", "alert-box");
      alert.appendChild(el("strong", "", "Weather is unavailable"));
      alert.appendChild(el("span", "", err.message));
      box.appendChild(alert);
    }
  }

  function renderWeather(data) {
    const box = $("#weather-result");
    box.textContent = "";
    const current = data.current || {};
    const card = el("div", "card");
    card.appendChild(el("h3", "", "Right now"));
    const tiles = el("div", "metrics");
    tiles.appendChild(metricTile("Temperature", current.temperature_2m !== undefined ? `${num(current.temperature_2m, 1)} °C` : "-"));
    tiles.appendChild(metricTile("Humidity", current.relative_humidity_2m !== undefined ? `${current.relative_humidity_2m}%` : "-"));
    tiles.appendChild(metricTile("Rain now", current.precipitation !== undefined ? `${num(current.precipitation, 1)} mm` : "-"));
    tiles.appendChild(metricTile("Wind", current.wind_speed_10m !== undefined ? `${num(current.wind_speed_10m, 1)} km/h` : "-"));
    card.appendChild(tiles);
    card.appendChild(el("p", "hint", `Source: ${data.source}`));
    box.appendChild(card);

    data.alerts.forEach((a) => {
      const alert = el("div", "alert-box");
      alert.appendChild(el("strong", "", a.title));
      alert.appendChild(el("span", "", a.body));
      box.appendChild(alert);
    });

    const forecast = el("div", "card");
    forecast.style.marginTop = "16px";
    forecast.appendChild(el("h3", "", "7-day forecast: rainfall (mm)"));
    barRows(forecast, data.daily.map((d) => ({ label: DAY(d.date), value: d.rain_mm })), { unit: " mm", format: (v) => num(v, 1) });
    const wrap = el("div", "table-wrap");
    wrap.style.marginTop = "12px";
    const table = el("table");
    const thead = el("tr");
    ["Day", "Max °C", "Min °C", "Rain mm"].forEach((h, i) => thead.appendChild(el("th", i ? "num" : "", h)));
    table.appendChild(el("thead")).appendChild(thead);
    const tbody = el("tbody");
    data.daily.forEach((d) => {
      const tr = el("tr");
      tr.appendChild(el("td", "", DAY(d.date)));
      tr.appendChild(el("td", "num", num(d.tmax, 1)));
      tr.appendChild(el("td", "num", num(d.tmin, 1)));
      tr.appendChild(el("td", "num", num(d.rain_mm, 1)));
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    forecast.appendChild(wrap);
    box.appendChild(forecast);
  }

  function useMyLocation() {
    if (!navigator.geolocation) {
      toast("Location is not available in this browser. Enter the coordinates instead.", true);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const form = $("#weather-form");
        form.lat.value = pos.coords.latitude.toFixed(4);
        form.lon.value = pos.coords.longitude.toFixed(4);
        fetchWeather();
      },
      () => toast("Location permission was denied. Enter the coordinates instead.", true),
      { enableHighAccuracy: false, timeout: 10000 }
    );
  }

  // ---------- market ----------
  async function searchMarket(commodity) {
    const box = $("#market-result");
    box.textContent = "";
    box.appendChild(el("p", "hint", "Loading prices..."));
    try {
      const data = await api(`/api/market?commodity=${encodeURIComponent(commodity)}`);
      renderMarket(data);
    } catch (err) {
      box.textContent = "";
      const alert = el("div", "alert-box");
      alert.appendChild(el("strong", "", "Prices are unavailable"));
      alert.appendChild(el("span", "", err.message));
      box.appendChild(alert);
    }
  }

  function renderMarket(data) {
    const box = $("#market-result");
    box.textContent = "";
    const s = data.summary;
    const card = el("div", "card");
    card.appendChild(el("h3", "", `${data.commodity}: prices per quintal`));
    const tiles = el("div", "metrics");
    tiles.appendChild(metricTile("Markets reporting", String(s.markets)));
    tiles.appendChild(metricTile("Average modal price", s.avg_modal !== null ? money(s.avg_modal) : "-"));
    tiles.appendChild(metricTile("Lowest modal", s.min_modal !== null ? money(s.min_modal) : "-"));
    tiles.appendChild(metricTile("Highest modal", s.max_modal !== null ? money(s.max_modal) : "-"));
    card.appendChild(tiles);
    card.appendChild(el("p", "hint", `Source: ${data.source}`));

    if (data.records.length) {
      const top = data.records.slice(0, 10).map((r) => ({ label: r.market || "Market", value: r.modal }));
      card.appendChild(el("h3", "", "Top markets by modal price"));
      const chart = el("div");
      barRows(chart, top, { format: (v) => money(v) });
      card.appendChild(chart);

      const wrap = el("div", "table-wrap");
      wrap.style.marginTop = "12px";
      const table = el("table");
      const head = el("tr");
      ["Market", "State", "Date", "Min", "Modal", "Max"].forEach((h, i) => head.appendChild(el("th", i >= 3 ? "num" : "", h)));
      table.appendChild(el("thead")).appendChild(head);
      const tbody = el("tbody");
      data.records.forEach((r) => {
        const tr = el("tr");
        tr.appendChild(el("td", "", r.market));
        tr.appendChild(el("td", "", r.state));
        tr.appendChild(el("td", "", r.date));
        tr.appendChild(el("td", "num", r.min !== null ? money(r.min) : "-"));
        tr.appendChild(el("td", "num", money(r.modal)));
        tr.appendChild(el("td", "num", r.max !== null ? money(r.max) : "-"));
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      wrap.appendChild(table);
      card.appendChild(wrap);
    } else {
      card.appendChild(el("p", "hint", "No mandi records found for this commodity today."));
    }
    box.appendChild(card);

    const watch = el("form", "card toolbar");
    watch.style.marginTop = "16px";
    watch.appendChild(el("h3", "", "Price alert"));
    const label = el("label");
    label.appendChild(el("span", "", "Notify me when the modal price reaches (₹/quintal)"));
    const input = el("input");
    input.type = "number";
    input.min = "1";
    input.step = "any";
    input.required = true;
    input.name = "threshold";
    label.appendChild(input);
    watch.appendChild(label);
    const btn = el("button", "secondary", "Set alert");
    btn.type = "submit";
    watch.appendChild(btn);
    watch.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await api("/api/market/watch", { method: "POST", body: { commodity: data.commodity, threshold: Number(input.value) } });
        toast("Price alert saved. You will see it in Alerts when the price is reached.");
        input.value = "";
      } catch (err) {
        toast(err.message, true);
      }
    });
    box.appendChild(watch);
  }

  // ---------- finance ----------
  function renderFinance(data) {
    const box = $("#finance-result");
    box.textContent = "";
    const card = el("div", "card");
    card.appendChild(el("h3", "", "Season summary"));
    const tiles = el("div", "metrics");
    tiles.appendChild(metricTile("Gross revenue", money(data.gross_revenue)));
    tiles.appendChild(metricTile("Total cost", money(data.total_cost)));
    tiles.appendChild(metricTile(data.profit >= 0 ? "Profit" : "Loss", money(data.profit), data.profit >= 0 ? "good" : "bad"));
    tiles.appendChild(metricTile("Return on cost", `${num(data.roi_pct, 1)}%`, data.roi_pct >= 0 ? "good" : "bad"));
    tiles.appendChild(metricTile("Break-even price", data.break_even_price_per_quintal !== null ? `${money(data.break_even_price_per_quintal)}/q` : "-"));
    tiles.appendChild(metricTile("Break-even yield", data.break_even_yield_per_acre !== null ? `${num(data.break_even_yield_per_acre, 1)} q/acre` : "-"));
    card.appendChild(tiles);

    card.appendChild(el("h3", "", "Where the money goes"));
    barRows(card, data.cost_breakdown.map((c) => ({ label: c.name, value: c.amount })), { format: (v) => money(v) });

    if (data.loan && data.loan.total_repayment > 0) {
      card.appendChild(el("h3", "", "Loan"));
      const loan = el("div", "metrics");
      loan.appendChild(metricTile("Monthly EMI", money(data.loan.monthly_emi)));
      loan.appendChild(metricTile("Total repayment", money(data.loan.total_repayment)));
      loan.appendChild(metricTile("Total interest", money(data.loan.total_interest)));
      loan.appendChild(metricTile("Profit covers a year of EMI", data.loan.profit_covers_annual_emi ? "Yes" : "No",
        data.loan.profit_covers_annual_emi ? "good" : "bad"));
      card.appendChild(loan);
    }
    card.appendChild(el("p", "disclaimer", "Simple season arithmetic. It excludes depreciation, family labour valuation and price risk."));
    box.appendChild(card);
  }

  // ---------- theme ----------
  function setTheme(mode, save) {
    const dark = mode === "dark" || (mode !== "light" && window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    if (save) store.set("aa_theme", dark ? "dark" : "light");
  }

  function initTheme() {
    const saved = store.get("aa_theme");
    setTheme(saved === "dark" || saved === "light" ? saved : "auto", false);
    const toggle = $("#theme-toggle");
    if (toggle) toggle.addEventListener("click", () => {
      const current = document.documentElement.dataset.theme === "dark" ? "dark" : "light";
      setTheme(current === "dark" ? "light" : "dark", true);
    });
  }

  // ---------- event wiring ----------
  function bindEvents() {
    $$(".seg").forEach((b) => b.addEventListener("click", () => setAuthMode(b.dataset.auth)));
    $("#login-form").addEventListener("submit", submitLogin);
    $("#register-form").addEventListener("submit", submitRegister);
    $("#logout-btn").addEventListener("click", () => logout(false));
    $("#lang-select").addEventListener("change", (e) => setLanguage(e.target.value, true));
    $("#bell").addEventListener("click", () => showView("alerts"));
    $("#read-all").addEventListener("click", async () => {
      await api("/api/notifications/read-all", { method: "POST" });
      loadAlerts();
    });

    $$(".tab").forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));
    $$("[data-goto]").forEach((b) => b.addEventListener("click", () => showView(b.dataset.goto)));

    $("#ask-form").addEventListener("submit", (e) => { e.preventDefault(); askQuestion($("#question").value); });
    $("#question").addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#ask-form").requestSubmit(); }
    });
    $("#chips").addEventListener("click", (e) => {
      const chip = e.target.closest(".chip");
      if (chip) askQuestion(chip.dataset.q);
    });
    $("#upload-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const file = $("#file").files[0];
      if (!file) return;
      const body = new FormData();
      body.append("file", file);
      try {
        const result = await api("/api/documents", { method: "POST", form: body });
        toast(`Added ${result.name} (${result.chunks} passages).`);
        $("#file").value = "";
        await loadDocuments();
      } catch (err) {
        toast(err.message, true);
      }
    });

    $("#leaf-file").addEventListener("change", (e) => {
      const file = e.target.files[0];
      const img = $("#leaf-preview");
      if (file) { img.src = URL.createObjectURL(file); img.alt = "Selected leaf photo"; img.hidden = false; }
    });
    $("#disease-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const file = $("#leaf-file").files[0];
      if (!file) { toast("Choose a leaf photo first.", true); return; }
      const body = new FormData();
      body.append("file", file);
      const box = $("#disease-result");
      box.textContent = "";
      box.appendChild(el("p", "hint", "Analysing the photo..."));
      try {
        renderDisease(await api("/api/disease/predict", { method: "POST", form: body }));
      } catch (err) {
        box.textContent = "";
        box.appendChild(el("div", "alert-box", err.message));
      }
    });

    $("#crop-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = e.currentTarget;
      const body = {};
      ["N", "P", "K", "temperature", "humidity", "ph", "rainfall"].forEach((k) => { body[k] = Number(f[k].value); });
      try { renderCrops(await api("/api/crops/recommend", { method: "POST", body })); }
      catch (err) { toast(err.message, true); }
    });

    $("#soil-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = e.currentTarget;
      const body = {};
      ["nitrogen", "phosphorus", "potassium", "ph", "organic_carbon"].forEach((k) => { body[k] = Number(f[k].value); });
      try { renderSoil(await api("/api/soil/analyze", { method: "POST", body })); }
      catch (err) { toast(err.message, true); }
    });

    $("#weather-form").addEventListener("submit", (e) => { e.preventDefault(); fetchWeather(); });
    $("#locate-btn").addEventListener("click", useMyLocation);

    $("#market-form").addEventListener("submit", (e) => {
      e.preventDefault();
      const commodity = e.currentTarget.commodity.value.trim();
      if (commodity.length >= 2) searchMarket(commodity);
    });

    $("#finance-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = e.currentTarget;
      const body = {};
      ["area_acres", "yield_per_acre", "price_per_quintal", "seed_cost", "fertilizer_cost", "pesticide_cost",
        "labour_cost", "irrigation_cost", "other_cost", "lease_per_acre", "loan_amount", "loan_rate_pct"]
        .forEach((k) => { body[k] = Number(f[k].value || 0); });
      body.loan_years = Number(f.loan_years.value || 0);
      try { renderFinance(await api("/api/finance/calculate", { method: "POST", body })); }
      catch (err) { toast(err.message, true); }
    });
  }

  // ---------- start ----------
  async function init() {
    initTheme();
    bindEvents();
    setLanguage(state.lang, false);
    const saved = store.get("aa_loc");
    if (saved) {
      try {
        const loc = JSON.parse(saved);
        $("#weather-form").lat.value = loc.lat;
        $("#weather-form").lon.value = loc.lon;
      } catch (_) { /* ignore a corrupt saved value */ }
    }
    try {
      const h = await api("/api/health", { auth: false });
      const ai = h.llm_configured ? `AI model: ${h.llm_provider}` : "No AI model (retrieval only)";
      const models = `Leaf model ${h.disease_model_loaded ? "ready" : "missing"} · Crop model ${h.crop_model_loaded ? "ready" : "missing"}`;
      $("#status").textContent = `Online · ${ai} · ${models}`;
    } catch (err) {
      $("#status").textContent = "Offline: " + err.message;
    }
    if (!state.token) { logout(true); return; }
    try {
      const me = await api("/api/me");
      startSession(state.token, me);
    } catch (_) {
      logout(true);
    }
  }

  init();
})();
