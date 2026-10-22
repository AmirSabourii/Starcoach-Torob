const AREAS = {
  "فردوسی": [35.69305, 51.4202],
  "شیخ هادی": [35.6946, 51.40875],
  "بهارستان": [35.69176, 51.42568],
  "آسمان": [35.77746, 51.35373],
  "باغ فیض": [35.73955, 51.31562],
  "تجریش": [35.80607, 51.43001],
};

const state = {
  tab: "chat",
  area: "فردوسی",
  lat: AREAS["فردوسی"][0],
  lon: AREAS["فردوسی"][1],
  messages: [],
  compare: [],
  sheet: null,
  guided: null,
  view: "home",
};

const scrollEl = document.getElementById("scroll");
const areaBtn = document.getElementById("area-btn");

function faNum(n) {
  if (n === null || n === undefined || n === "") return "—";
  const num = Number(n);
  if (!Number.isFinite(num)) return "—";
  return Math.round(num).toLocaleString("fa-IR");
}
function faDigits(s) {
  return String(s ?? "").replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);
}
function money(n) {
  if (n === null || n === undefined) return "قیمت نامعتبر";
  return faNum(n);
}
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function priceLine(row) {
  const lo = row.min_price ?? row.cheapest_plausible_price ?? row.price_toman;
  const hi = row.max_price;
  if (lo == null && hi == null) return "قیمت معتبری ثبت نشده";
  if (hi != null && lo != null && hi !== lo) return `<b>${money(lo)}</b> تا <b>${money(hi)}</b> تومان`;
  return `<b>${money(lo)}</b> تومان`;
}
function freshLine(row) {
  const when = row.latest_price_change || row.price_updated;
  if (!when && row.days_since_update == null) return "";
  const stale = row.stale_price === true;
  const days = row.days_since_update;
  let text = when ? `آخرین تغییر قیمت: ${faDigits(when)}` : "تاریخ تغییر قیمت ثبت نشده";
  if (days != null) text += ` · ${faNum(days)} روز پیش`;
  if (stale) text += " · این قیمت قدیمی است و ممکن است تغییر کرده باشد";
  return `<div class="fresh${stale ? " warn" : ""}">${esc(text)}</div>`;
}

function stepsFrom(query, calls) {
  const steps = [{ title: "فهمیدم چه می‌خواهی", sub: query }];
  for (const call of calls || []) {
    const r = call.result || {};
    const args = call.args || {};
    if (call.name === "search_products") {
      const n = r.n_results ?? (r.results || []).length;
      const extra = r.n_candidates != null ? ` از ${faNum(r.n_candidates)} نامزد` : "";
      steps.push({ title: "جست‌وجو در محصولات", sub: `${faNum(n)} محصول مرتبط${extra}` });
    } else if (call.name === "browse_catalog") {
      const brands = (r.brands || []).length;
      steps.push({ title: "مرور دسته", sub: `${faNum(r.n_items || 0)} کالای اصلی در ${faNum(brands)} برند` });
    } else if (call.name === "find_stores_for_product") {
      const after = r.n_shops_after_filters ?? (r.shops || []).length;
      const all = r.n_shops_carrying_with_valid_price;
      const sub = all != null ? `${faNum(after)} فروشگاه بعد از فیلتر فاصله از ${faNum(all)}` : `${faNum(after)} فروشگاه`;
      steps.push({ title: "فیلتر فاصله", sub });
      const stale = (r.shops || []).filter((s) => s.stale_price).length;
      const sort = args.sort_by === "price" ? "قیمت" : "فاصله";
      steps.push({ title: "رتبه‌بندی", sub: `بر اساس ${sort} · ${faNum(stale)} قیمت قدیمی در همین فهرست` });
    } else if (call.name === "search_stores") {
      const n = r.n_matches ?? r.n_shops_with_installment ?? (r.shops || []).length;
      steps.push({ title: "فروشگاه‌ها", sub: `${faNum(n)} فروشگاه` });
      if (r.shops_per_provider) {
        const bits = Object.entries(r.shops_per_provider).map(([k, v]) => `${k} ${faNum(v)}`).join("، ");
        steps.push({ title: "قسط و پرداخت", sub: bits || "سرویسی ثبت نشده" });
      }
    } else if (call.name === "compare_products") {
      steps.push({ title: "مقایسه", sub: `${faNum((r.products || []).length)} محصول` });
    }
  }
  return steps;
}

function productsFrom(calls) {
  const out = [];
  for (const call of calls || []) {
    const r = call.result || {};
    if (call.name === "search_products") out.push(...(r.results || []));
    if (call.name === "browse_catalog") out.push(...(r.items || []));
  }
  return out.slice(0, 8);
}
function storesFrom(calls) {
  for (const call of [...(calls || [])].reverse()) {
    if (call.name === "find_stores_for_product" || call.name === "search_stores" || call.name === "compare_stores") {
      const shops = (call.result || {}).shops || [];
      return [...shops].sort((a, b) => (a.distance_km ?? 1e9) - (b.distance_km ?? 1e9));
    }
  }
  return [];
}
function noticeFrom(calls) {
  for (const call of calls || []) {
    const r = call.result || {};
    if (r.closest_non_matching_alternatives) return { kind: "none", alt: r.closest_non_matching_alternatives, note: r.note, clarify: r.suggested_clarifying_question };
    if (r.category_warning) return { kind: "guided", note: r.category_warning, clarify: r.note };
    if (r.note && /NO (EXACT )?MATCH|NO CATEGORY|NO ITEMS|NO SHOPS|NO MATCHING/i.test(r.note)) return { kind: "none", note: r.note, alt: r["not_matching_request (do not present as the requested item)"] || [] };
  }
  return null;
}

async function getJSON(url) {
  const res = await fetch(url);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "درخواست انجام نشد.");
  return data;
}
function locQuery() {
  return `lat=${encodeURIComponent(state.lat)}&lon=${encodeURIComponent(state.lon)}`;
}

async function toolPreview(action) {
  if (action.kind === "browse") {
    const q = new URLSearchParams({ category: action.category, sort_by: action.sort || "popularity", limit: "6" });
    if (action.max_price) q.set("max_price", action.max_price);
    if (action.exclude_basic_phones) q.set("exclude_basic_phones", "true");
    if (action.exclude_brand) q.set("exclude_brand", action.exclude_brand);
    const data = await getJSON("/api/browse?" + q.toString());
    return { calls: [{ name: "browse_catalog", args: Object.fromEntries(q), result: data }] };
  }
  if (action.kind === "search") {
    const q = new URLSearchParams({ q: action.q, limit: "8" });
    const data = await getJSON("/api/products/search?" + q.toString());
    return { calls: [{ name: "search_products", args: { query: action.q }, result: data }] };
  }
  if (action.kind === "stores") {
    const q = new URLSearchParams();
    if (action.address) q.set("address_contains", action.address);
    if (action.category) q.set("sells_category", action.category);
    if (action.installment) q.set("installment_any", "true");
    q.set("lat", state.lat);
    q.set("lon", state.lon);
    const data = await getJSON("/api/stores/search?" + q.toString());
    return { calls: [{ name: "search_stores", args: Object.fromEntries(q), result: data }] };
  }
  if (action.kind === "installment") {
    const data = await getJSON(`/api/stores/search?installment_any=true&${locQuery()}`);
    return { calls: [{ name: "search_stores", args: { installment_any: true }, result: data }] };
  }
  return { calls: [] };
}

function pushUser(text) {
  state.messages.push({ role: "user", text });
}
function pushAssistant(partial) {
  const msg = { role: "assistant", text: "", stepsOpen: true, steps: [], products: [], stores: [], notice: null, ...partial };
  state.messages.push(msg);
  return msg;
}

async function askAgent(text, preview) {
  state.view = "chat";
  pushUser(text);
  const msg = pushAssistant({ text: "در حال پرسیدن از دستیار…" });
  render();
  try {
    const res = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, lat: state.lat, lon: state.lon }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      msg.text = data.detail || "پاسخ دستیار نرسید.";
      if (res.status === 503 && preview) {
        msg.text += "\nکارت‌های زیر مستقیم از ابزارهای کاتالوگ‌اند، نه از مدل.";
        const tool = await toolPreview(preview);
        msg.steps = stepsFrom(text, tool.calls);
        msg.products = productsFrom(tool.calls);
        msg.stores = storesFrom(tool.calls);
        msg.notice = noticeFrom(tool.calls);
      }
    } else {
      msg.text = data.answer || "پاسخی برنگشت.";
      msg.steps = stepsFrom(text, data.tool_calls || []);
      msg.products = productsFrom(data.tool_calls || []);
      msg.stores = storesFrom(data.tool_calls || []);
      msg.notice = noticeFrom(data.tool_calls || []);
    }
  } catch (err) {
    msg.text = err.message || "ارتباط با سرور برقرار نشد.";
  }
  render();
}

async function openStores(product) {
  const ids = [product.product_id, ...(product.same_title_other_product_ids || [])].join(",");
  const data = await getJSON(`/api/products/${encodeURIComponent(product.product_id)}/stores?sort_by=distance&${locQuery()}&limit=10`);
  state.view = "chat";
  state.tab = "map";
  document.querySelectorAll(".seg button").forEach((b) => b.classList.toggle("on", b.dataset.tab === "map"));
  const calls = [{ name: "find_stores_for_product", args: { sort_by: "distance", product_id: ids }, result: data }];
  pushAssistant({
    text: `فروشگاه‌های «${product.title}» بر اساس فاصله از ${state.area}.`,
    steps: stepsFrom(product.title, calls),
    stores: storesFrom(calls),
    products: [],
  });
  render();
}

async function openCompare() {
  if (state.compare.length < 2) return;
  const ids = state.compare.map((p) => p.product_id).join(",");
  const data = await getJSON("/api/compare/products?ids=" + encodeURIComponent(ids));
  state.sheet = { kind: "compare", data };
  render();
}

async function openContact(shopId) {
  const data = await getJSON("/api/shops/" + encodeURIComponent(shopId) + "/contact");
  state.sheet = { kind: "contact", data };
  render();
}

function toggleCompare(product) {
  const i = state.compare.findIndex((p) => p.product_id === product.product_id);
  if (i >= 0) state.compare.splice(i, 1);
  else if (state.compare.length < 2) state.compare.push({ product_id: product.product_id, title: product.title });
  else state.compare.splice(0, 1, { product_id: product.product_id, title: product.title });
  render();
}

function cardHTML(p) {
  const flags = (p.flags || []).map((f) => `<span class="badge b-amber">${esc(f.split(" ")[0])}</span>`).join(" ");
  const img = p.image ? `<img src="${esc(p.image)}" alt="" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'muted',textContent:'بدون تصویر'}))">` : `<span class="muted">بدون تصویر</span>`;
  const on = state.compare.some((x) => x.product_id === p.product_id);
  return `<article class="card pcard">
    <div class="col">
      <div class="ttl">${esc(p.title)}</div>
      <div class="muted">${esc(p.brand || "")} ${esc(p.category || "")}</div>
      <div class="prange">${priceLine(p)}</div>
      ${freshLine(p)}
      <div class="chips">${flags}<span class="badge b-gray">${faNum(p.n_shops || p.n_shops_priced || 0)} فروشگاه</span></div>
      <div class="row"><span>فروشگاه‌های نزدیک</span><button type="button" data-act="stores" data-id="${esc(p.product_id)}">فاصله</button></div>
      <div class="row"><span>مقایسه</span><button type="button" data-act="cmp" data-id="${esc(p.product_id)}">${on ? "برداشته شد" : "انتخاب"}</button></div>
    </div>
    <div class="tile">${img}</div>
  </article>`;
}

function storeHTML(s) {
  const pay = (s.payment_options || []).slice(0, 3).map((p) => `<span class="badge b-gray">${esc(String(p).replace(":in_person", " حضوری").replace(":unknown", ""))}</span>`).join(" ");
  const dist = s.distance_km != null ? `${faNum(s.distance_km)} کیلومتر` : "فاصله نامشخص";
  const stale = s.stale_price ? `<span class="badge b-amber">قیمت قدیمی</span>` : `<span class="badge b-green">قیمت در بازهٔ ۹۰ روز</span>`;
  return `<article class="card store">
    <div class="name">${esc(s.shop_name || s.name || "")}</div>
    <div class="meta">${esc(s.area || "")} · ${dist}</div>
    <div class="prange">${s.price_toman != null ? money(s.price_toman) + " تومان" : ""}</div>
    ${freshLine(s)}
    <div class="chips">${stale}${s.suspicious_price ? '<span class="badge b-pink">قیمت غیرعادی</span>' : ""}${pay}</div>
    <div class="meta">${esc((s.address || "").slice(0, 110))}</div>
    ${s.shop_id ? `<button class="linkish" type="button" data-act="contact" data-id="${esc(s.shop_id)}">اطلاعات تماس (شماره ساختگی است)</button>` : ""}
  </article>`;
}

function stepsHTML(msg) {
  if (!msg.steps || !msg.steps.length) return "";
  const body = msg.stepsOpen ? `<div class="steps">${msg.steps.map((s) => `<div class="step"><div><b>${esc(s.title)}</b><span>${esc(s.sub)}</span></div></div>`).join("")}</div>` : "";
  return `<button type="button" class="pill" data-act="toggle-steps">${faNum(msg.steps.length)} گام · ${msg.stepsOpen ? "بستن" : "نمایش اعداد"}</button>${body}`;
}

function noticeHTML(n) {
  if (!n) return "";
  if (n.kind === "none") {
    const alt = (n.alt || []).map((a) => `<div class="row"><span>${esc(a.title || a.product_id)}</span></div>`).join("");
    return `<div class="note"><b>این مورد در داده پیدا نشد.</b><div class="muted">${esc(n.clarify || n.note || "")}</div>${alt}<div class="chips"><button class="chip" type="button" data-act="guided">راهنمایی انتخاب</button></div></div>`;
  }
  return `<div class="note">${esc(n.note || "")}<div class="chips"><button class="chip" type="button" data-act="guided">سؤال‌های راهنما</button></div></div>`;
}

function homeHTML() {
  return `<section class="hero">
    <img src="/assets/mascot_hero.png" alt="">
    <h1>امروز دنبال چی می‌گردی؟</h1>
    <p>با دستیار خرید حضوری، فروشگاه و قیمت را از دادهٔ ترب ببین.</p>
  </section>
  <div class="grid">
    <button class="sug" type="button" data-suggest="phone"><img src="/assets/ic_phone_in.png" alt=""><div><b>گوشی عکاسی</b><span>تا ۲۰ میلیون</span></div></button>
    <button class="sug" type="button" data-suggest="head"><img src="/assets/ic_headphone_in.png" alt=""><div><b>هدفون بی‌سیم</b><span>تا ۳ میلیون</span></div></button>
    <button class="sug" type="button" data-suggest="near"><img src="/assets/ic_pin_in.png" alt=""><div><b>فروشگاه‌های</b><span>نزدیک ${esc(state.area)}</span></div></button>
    <button class="sug" type="button" data-suggest="laptop"><img src="/assets/ic_laptop_in.png" alt=""><div><b>لپ‌تاپ سبک</b><span>مرور دسته</span></div></button>
    <button class="sug" type="button" data-suggest="installment"><img src="/assets/ic_pin.png" alt=""><div><b>خرید قسطی</b><span>سرویس‌های ثبت‌شده</span></div></button>
    <button class="sug" type="button" data-suggest="guided"><img src="/assets/mascot_avatar.png" alt=""><div><b>نمی‌دونم</b><span>چی بخرم</span></div></button>
  </div>
  <a class="design-link" href="/screens/overview.html">نمونه‌های طراحی</a>`;
}

function guidedHTML() {
  const g = state.guided || { step: 0, category: "", budget: "", sort: "popularity" };
  state.guided = g;
  const cats = ["گوشی", "لپ تاپ", "هدفون", "تلویزیون", "ساعت هوشمند"];
  const budgets = [["زیر ۵ میلیون", 5e6], ["تا ۲۰ میلیون", 2e7], ["تا ۵۰ میلیون", 5e7], ["فرقی نمی‌کند", ""]];
  if (g.step === 0) {
    return `<h2>چه دسته‌ای؟</h2><div class="chips">${cats.map((c) => `<button class="chip" type="button" data-gcat="${esc(c)}">${esc(c)}</button>`).join("")}</div>`;
  }
  if (g.step === 1) {
    return `<h2>بودجه؟</h2><div class="chips">${budgets.map(([l, v]) => `<button class="chip" type="button" data-gbudget="${v}">${esc(l)}</button>`).join("")}</div>`;
  }
  return `<h2>اولویت؟</h2><div class="chips">
    <button class="chip" type="button" data-gsort="price">ارزان‌تر</button>
    <button class="chip" type="button" data-gsort="popularity">پر فروشگاه‌تر</button>
  </div>`;
}

function sheetHTML() {
  const s = state.sheet;
  if (!s) return "";
  if (s.kind === "areas") {
    const chips = Object.keys(AREAS).map((name) => `<button class="chip${name === state.area ? " on" : ""}" type="button" data-area="${esc(name)}">${esc(name)}</button>`).join("");
    return `<div class="sheet"><button class="x" type="button" data-act="close">×</button><h3>محله</h3><p class="muted">فاصله از مرکز همین محله در داده حساب می‌شود.</p><div class="chips">${chips}</div></div>`;
  }
  if (s.kind === "contact") {
    const shop = (s.data.shops || [])[0];
    if (!shop) return `<div class="sheet"><button class="x" data-act="close" type="button">×</button><p>فروشگاه در داده نیست.</p></div>`;
    const hours = shop.weekly_hours && typeof shop.weekly_hours === "object"
      ? Object.entries(shop.weekly_hours).map(([d, h]) => `<div class="row"><span>${esc(d)}</span><span>${esc(faDigits(h))}</span></div>`).join("")
      : `<div class="muted">ساعات ثبت نشده</div>`;
    const web = shop.website ? `<div class="row"><a href="${esc(shop.website)}" rel="noopener">${esc(shop.website)}</a></div>` : "";
    const ig = shop.instagram ? `<div class="row"><span>اینستاگرام</span><span>${esc(shop.instagram)}</span></div>` : "";
    return `<div class="sheet"><button class="x" type="button" data-act="close">×</button>
      <h3>${esc(shop.name)}</h3>
      <p>${esc(shop.address || "")}</p>
      <div class="warnbox">این شماره در دادهٔ نمایشی ساختگی است و باید جداگانه تأیید شود. تماسی گرفته نمی‌شود.</div>
      <div class="row"><span>شمارهٔ نمایشی</span><span>${esc(faDigits(shop.phone || "ثبت نشده"))}</span></div>
      ${web}${ig}<div class="sec">ساعات</div>${hours}
      <div class="sec">پرداخت ثبت‌شده</div>
      <div class="muted">${esc(Array.isArray(shop.payment_options) ? shop.payment_options.join("، ") : "ثبت نشده")}</div>
    </div>`;
  }
  if (s.kind === "compare") {
    const products = s.data.products || [];
    const keys = [...new Set(products.flatMap((p) => Object.keys(p.specs && typeof p.specs === "object" ? p.specs : {})))];
    const head = products.map((p) => `<td><b>${esc(p.title || "")}</b><div>${priceLine(p)}</div>${freshLine(p)}</td>`).join("");
    const body = keys.map((k) => {
      const vals = products.map((p) => (p.specs && p.specs[k]) || "—");
      if (vals.every((v) => v === vals[0])) return "";
      return `<tr><td>${esc(k)}</td>${vals.map((v) => `<td>${esc(v)}</td>`).join("")}</tr>`;
    }).join("");
    return `<div class="sheet"><button class="x" type="button" data-act="close">×</button><h3>مقایسه</h3>
      <table><tr><td></td>${head}</tr>${body || `<tr><td colspan="3">مشخصات بیشتری در داده نیست.</td></tr>`}</table>
    </div>`;
  }
  return "";
}

function render() {
  areaBtn.textContent = state.area;
  let html = "";
  if (state.view === "home" && state.tab === "chat" && state.messages.length === 0) html = homeHTML();
  else if (state.view === "guided") html = guidedHTML();
  else if (state.tab === "map" && state.messages.every((m) => !(m.stores || []).length)) {
    html = `<p class="sec">فروشگاهی از این گفتگو انتخاب نشده. یک کالا را باز کنید یا فروشگاه‌های ${esc(state.area)} را ببینید.</p>
      <button class="chip" type="button" data-suggest="near">فروشگاه‌های ${esc(state.area)}</button>`;
  }
  for (const msg of state.messages) {
    if (state.tab === "map" && msg.role === "assistant" && !(msg.stores || []).length && state.messages.some((m) => (m.stores || []).length)) continue;
    if (msg.role === "user") {
      html += `<div class="urow"><div class="ububble">${esc(msg.text)}</div></div>`;
      continue;
    }
    const showProducts = state.tab !== "map";
    html += `<div class="arow"><img class="aav" src="/assets/mascot_avatar.png" alt=""><div>
      ${stepsHTML(msg)}
      <div class="abubble">${esc(msg.text)}</div>
      ${noticeHTML(msg.notice)}
      ${showProducts ? (msg.products || []).map(cardHTML).join("") : ""}
      ${(msg.stores || []).map(storeHTML).join("")}
    </div></div>`;
  }
  if (state.compare.length) {
    html += `<div class="chips"><span class="badge b-pink">${faNum(state.compare.length)} برای مقایسه</span>
      <button class="chip on" type="button" data-act="open-compare" ${state.compare.length < 2 ? "disabled" : ""}>مقایسه</button></div>`;
  }
  scrollEl.innerHTML = html + sheetHTML();
  scrollEl.scrollTop = scrollEl.scrollHeight;
}

document.querySelectorAll(".seg button").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".seg button").forEach((b) => b.classList.remove("on"));
    btn.classList.add("on");
    state.tab = btn.dataset.tab;
    if (state.view === "guided") state.view = "chat";
    render();
  });
});

areaBtn.addEventListener("click", () => {
  state.sheet = state.sheet && state.sheet.kind === "areas" ? null : { kind: "areas" };
  render();
});

document.getElementById("composer").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const input = document.getElementById("q");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  askAgent(text, { kind: "search", q: text });
});

scrollEl.addEventListener("click", async (ev) => {
  const t = ev.target.closest("[data-suggest],[data-act],[data-area],[data-gcat],[data-gbudget],[data-gsort],[data-id]");
  if (!t) return;
  if (t.dataset.area) {
    state.area = t.dataset.area;
    [state.lat, state.lon] = AREAS[state.area];
    state.sheet = null;
    render();
    return;
  }
  if (t.dataset.act === "close") { state.sheet = null; render(); return; }
  if (t.dataset.act === "toggle-steps") {
    const idx = [...scrollEl.querySelectorAll("[data-act=toggle-steps]")].indexOf(t);
    const assistants = state.messages.filter((m) => m.role === "assistant");
    if (assistants[idx]) assistants[idx].stepsOpen = !assistants[idx].stepsOpen;
    render();
    return;
  }
  if (t.dataset.act === "guided" || t.dataset.suggest === "guided") {
    state.view = "guided";
    state.guided = { step: 0 };
    render();
    return;
  }
  if (t.dataset.gcat) { state.guided.category = t.dataset.gcat; state.guided.step = 1; render(); return; }
  if (t.dataset.gbudget != null && t.hasAttribute("data-gbudget")) {
    state.guided.budget = t.dataset.gbudget;
    state.guided.step = 2;
    render();
    return;
  }
  if (t.dataset.gsort) {
    const g = state.guided;
    state.view = "chat";
    const text = `در دستهٔ ${g.category} با بودجهٔ ${g.budget ? faNum(g.budget) : "آزاد"} چه چیزی پیشنهاد می‌کنی؟`;
    askAgent(text, { kind: "browse", category: g.category, max_price: g.budget || undefined, sort: t.dataset.gsort, exclude_basic_phones: g.category === "گوشی" });
    return;
  }
  const suggest = {
    phone: { text: "یه گوشی عکاسی تا ۲۰ میلیون نزدیک من", preview: { kind: "browse", category: "گوشی", max_price: "20000000", sort: "price_desc", exclude_basic_phones: true } },
    head: { text: "یه هدفون بی‌سیم خوب تا ۳ میلیون", preview: { kind: "browse", category: "هدفون", max_price: "3000000", sort: "popularity" } },
    near: { text: `فروشگاه‌های نزدیک ${state.area} که گوشی دارند`, preview: { kind: "stores", address: state.area, category: "گوشی موبایل" } },
    laptop: { text: "یه لپ‌تاپ سبک برای دانشجو", preview: { kind: "browse", category: "لپ تاپ", sort: "popularity" } },
    installment: { text: "کدوم فروشگاه‌ها خرید قسطی دارند؟", preview: { kind: "installment" } },
  }[t.dataset.suggest];
  if (suggest) { askAgent(suggest.text, suggest.preview); return; }
  if (t.dataset.act === "stores") {
    const product = state.messages.flatMap((m) => m.products || []).find((p) => p.product_id === t.dataset.id);
    if (product) openStores(product).catch((e) => alert(e.message));
    return;
  }
  if (t.dataset.act === "cmp") {
    const product = state.messages.flatMap((m) => m.products || []).find((p) => p.product_id === t.dataset.id);
    if (product) toggleCompare(product);
    return;
  }
  if (t.dataset.act === "open-compare") openCompare().catch((e) => alert(e.message));
  if (t.dataset.act === "contact") openContact(t.dataset.id).catch((e) => alert(e.message));
});

render();
