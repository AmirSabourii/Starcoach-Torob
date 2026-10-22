const PRESETS = [
  { label: "فردوسی", lat: 35.69305, lon: 51.4202 },
  { label: "شیخ هادی", lat: 35.6946, lon: 51.40875 },
  { label: "بهارستان", lat: 35.69176, lon: 51.42568 },
  { label: "آسمان", lat: 35.77746, lon: 51.35373 },
  { label: "باغ فیض", lat: 35.73955, lon: 51.31562 },
  { label: "تجریش", lat: 35.80607, lon: 51.43001 },
];

const DAYS = [
  ["sat", "شنبه"],
  ["sun", "یکشنبه"],
  ["mon", "دوشنبه"],
  ["tue", "سه‌شنبه"],
  ["wed", "چهارشنبه"],
  ["thu", "پنجشنبه"],
  ["fri", "جمعه"],
];

const numberFmt = new Intl.NumberFormat("fa-IR");
const kmFmt = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 1 });

const state = {
  lat: PRESETS[0].lat,
  lon: PRESETS[0].lon,
  locationLabel: PRESETS[0].label,
  products: [],
  catalog: new Map(),
  selected: new Map(),
  selectedShops: new Set(),
  product: null,
  stores: [],
  maxDistanceKm: "",
  chat: [],
  chatBusy: false,
};

document.addEventListener("DOMContentLoaded", init);

function init() {
  restoreLocation();
  renderPresets();
  renderLocation();
  bind();
  loadMeta();
}

function bind() {
  document.addEventListener("click", onClick);
  document.addEventListener("change", onChange);
  document.getElementById("search-form").addEventListener("submit", (event) => {
    event.preventDefault();
    executeSearch();
  });
  document.getElementById("loc-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const lat = parseCoord(document.getElementById("lat").value);
    const lon = parseCoord(document.getElementById("lon").value);
    if (lat === null || lon === null || lat < -90 || lat > 90 || lon < -180 || lon > 180) {
      toast("مختصات نامعتبر است.");
      return;
    }
    setLocation(lat, lon, "موقعیت دستی");
  });
  document.getElementById("chat-form").addEventListener("submit", (event) => {
    event.preventDefault();
    sendChat();
  });
}

async function onClick(event) {
  const el = event.target.closest("[data-action]");
  if (!el) return;
  const action = el.dataset.action;
  if (action === "nav") showView(el.dataset.view);
  else if (action === "quick") {
    document.getElementById("q").value = el.dataset.q || "";
    executeSearch();
  } else if (action === "toggle-filters") {
    const box = document.getElementById("filters");
    box.hidden = !box.hidden;
    el.setAttribute("aria-expanded", String(!box.hidden));
  } else if (action === "preset") {
    setLocation(Number(el.dataset.lat), Number(el.dataset.lon), el.dataset.label);
  } else if (action === "geo") {
    requestGeo();
  } else if (action === "open-product") {
    openProduct(el.dataset.id);
  } else if (action === "back") {
    showView("search");
  } else if (action === "distance") {
    state.maxDistanceKm = el.dataset.km || "";
    document.querySelectorAll("[data-action='distance']").forEach((btn) => {
      btn.setAttribute("aria-pressed", btn === el ? "true" : "false");
    });
    if (state.product) loadStores(state.product.product_id);
  } else if (action === "contact") {
    openContact(el.dataset.shopId);
  } else if (action === "freshness") {
    loadFreshness(el);
  } else if (action === "compare-stores") {
    compareSelectedStores();
  } else if (action === "close-modal") {
    document.getElementById("modal").hidden = true;
  }
}

function onChange(event) {
  const input = event.target;
  if (input.dataset.action === "toggle-product") toggleProduct(input);
  if (input.dataset.action === "toggle-shop") toggleShop(input);
}

function showView(name) {
  for (const view of ["search", "product", "compare", "chat"]) {
    document.getElementById("view-" + view).hidden = view !== name;
  }
  document.querySelectorAll("[data-view]").forEach((btn) => {
    btn.setAttribute("aria-current", btn.dataset.view === name ? "page" : "false");
  });
  if (name === "compare") renderCompareView();
  window.scrollTo(0, 0);
}

async function loadMeta() {
  const line = document.getElementById("meta-line");
  try {
    const meta = await apiGet("/api/meta");
    if (!meta.db_ready) {
      line.textContent = "پایگاه داده هنوز ساخته نشده";
      document.getElementById("status").textContent = "اول اسکریپت ساخت پایگاه را اجرا کنید.";
      return;
    }
    const bits = [formatNumber(meta.products) + " محصول"];
    if (!meta.llm_configured) bits.push("مدل زبانی خاموش");
    line.textContent = bits.join(" · ");
  } catch (err) {
    line.textContent = "سرور در دسترس نیست";
    document.getElementById("status").textContent = err.message;
  }
}

function restoreLocation() {
  try {
    const saved = JSON.parse(localStorage.getItem("starcoach.location") || "null");
    if (saved && Number.isFinite(saved.lat) && Number.isFinite(saved.lon)) {
      state.lat = saved.lat;
      state.lon = saved.lon;
      state.locationLabel = saved.label || "موقعیت ذخیره‌شده";
    }
  } catch (_err) {
    /* keep the Ferdowsi centroid */
  }
}

function setLocation(lat, lon, label) {
  state.lat = lat;
  state.lon = lon;
  state.locationLabel = label;
  localStorage.setItem("starcoach.location", JSON.stringify({ lat, lon, label }));
  renderLocation();
  renderPresets();
  if (state.product) loadStores(state.product.product_id);
}

function renderPresets() {
  document.getElementById("presets").innerHTML = PRESETS.map((preset) => {
    const pressed = preset.label === state.locationLabel ? "true" : "false";
    return `<button type="button" data-action="preset" data-label="${esc(preset.label)}" data-lat="${preset.lat}" data-lon="${preset.lon}" aria-pressed="${pressed}">${esc(preset.label)}</button>`;
  }).join("");
}

function renderLocation() {
  document.getElementById("loc-label").textContent = state.locationLabel;
  document.getElementById("lat").value = String(state.lat);
  document.getElementById("lon").value = String(state.lon);
}

function requestGeo() {
  if (!navigator.geolocation) {
    toast("مرورگر موقعیت را پشتیبانی نمی‌کند.");
    return;
  }
  navigator.geolocation.getCurrentPosition(
    (pos) => setLocation(pos.coords.latitude, pos.coords.longitude, "موقعیت فعلی"),
    () => toast("دسترسی به موقعیت ممکن نشد."),
    { enableHighAccuracy: true, timeout: 8000 }
  );
}

async function executeSearch() {
  const button = document.getElementById("search-btn");
  const status = document.getElementById("status");
  button.disabled = true;
  status.textContent = "در حال جست‌وجو…";
  const params = new URLSearchParams();
  const q = document.getElementById("q").value.trim();
  const brand = document.getElementById("brand").value.trim();
  const category = document.getElementById("category").value.trim();
  const minPrice = document.getElementById("min-price").value.trim();
  const maxPrice = document.getElementById("max-price").value.trim();
  if (q) params.set("q", q);
  if (brand) params.set("brand", brand);
  if (category) params.set("category", category);
  if (minPrice) params.set("min_price", minPrice);
  if (maxPrice) params.set("max_price", maxPrice);
  try {
    const data = await apiGet("/api/products/search?" + params.toString());
    state.products = data.products || [];
    for (const product of state.products) state.catalog.set(product.product_id, product);
    status.textContent = state.products.length
      ? formatNumber(state.products.length) + " محصول"
      : (data.message_fa || "محصولی پیدا نشد.");
    renderResults();
  } catch (err) {
    status.textContent = err.message;
    document.getElementById("results").innerHTML = "";
  } finally {
    button.disabled = false;
  }
}

function renderResults() {
  document.getElementById("results").innerHTML = state.products.map((product) => {
    const checked = state.selected.has(product.product_id) ? "checked" : "";
    return `<article class="card">
      ${thumb(product.primary_image_url)}
      <div>
        <h3>${esc(product.persian_title || "بدون عنوان")}</h3>
        <p class="muted">${esc([product.brand_name, product.category_name].filter(Boolean).join(" · "))}</p>
        <p class="price">${formatRange(product.min_price_toman, product.max_price_toman)}</p>
        <div class="card-actions">
          <button type="button" data-action="open-product" data-id="${esc(product.product_id)}">فروشگاه‌های حضوری</button>
          <label class="check"><input type="checkbox" data-action="toggle-product" data-id="${esc(product.product_id)}" ${checked} /> مقایسه</label>
        </div>
      </div>
    </article>`;
  }).join("");
  renderTray();
}

function renderTray() {
  const tray = document.getElementById("tray");
  if (state.selected.size < 2) {
    tray.hidden = true;
    updateCompareTab();
    return;
  }
  tray.hidden = false;
  tray.innerHTML = `<span>${formatNumber(state.selected.size)} محصول انتخاب شده</span><button type="button" data-action="nav" data-view="compare">مقایسه کن</button>`;
  updateCompareTab();
}

function toggleProduct(input) {
  const id = input.dataset.id;
  const product = state.catalog.get(id);
  if (input.checked) {
    if (state.selected.size >= 3) {
      input.checked = false;
      toast("حداکثر سه محصول را می‌توان مقایسه کرد.");
      return;
    }
    if (product) state.selected.set(id, product);
  } else {
    state.selected.delete(id);
  }
  renderTray();
}

async function openProduct(productId) {
  state.selectedShops = new Set();
  showView("product");
  document.getElementById("product").innerHTML = "<p class='status'>در حال خواندن محصول…</p>";
  try {
    const data = await apiGet("/api/products/" + encodeURIComponent(productId));
    state.product = data.product;
    state.catalog.set(productId, data.product);
    renderProduct(data.product);
    await loadStores(productId);
  } catch (err) {
    document.getElementById("product").innerHTML = `<p class="status">${esc(err.message)}</p>`;
  }
}

function renderProduct(product) {
  const images = (product.image_urls || []).map(safeUrl).filter(Boolean).slice(0, 4);
  const hero = images[0] ? `<img class="hero-img" alt="" src="${esc(images[0])}" />` : `<div class="thumb hero-img"><span>بدون تصویر</span></div>`;
  document.getElementById("product").innerHTML = `
    ${hero}
    <div class="product-head" style="margin-top:12px">
      <h2>${esc(product.persian_title || "بدون عنوان")}</h2>
    </div>
    <p class="muted">${esc([product.brand_name, product.model, product.category_name].filter(Boolean).join(" · "))}</p>
    <p class="price">${formatRange(product.min_price_toman, product.max_price_toman)}</p>
    <p class="muted">${formatNumber(product.shop_count || 0)} فروشگاه · ${formatNumber(product.offer_count || 0)} پیشنهاد</p>
    ${renderSpecs(product.specs || [])}
    <h3 class="section-title">فروشگاه‌های حضوری</h3>
    <div class="chips" id="distance-chips">
      <button type="button" data-action="distance" data-km="" aria-pressed="${state.maxDistanceKm === "" ? "true" : "false"}">همه</button>
      <button type="button" data-action="distance" data-km="2" aria-pressed="${state.maxDistanceKm === "2" ? "true" : "false"}">۲ کیلومتر</button>
      <button type="button" data-action="distance" data-km="5" aria-pressed="${state.maxDistanceKm === "5" ? "true" : "false"}">۵ کیلومتر</button>
      <button type="button" data-action="distance" data-km="10" aria-pressed="${state.maxDistanceKm === "10" ? "true" : "false"}">۱۰ کیلومتر</button>
    </div>
    <div id="stores"></div>
    <button type="button" id="compare-stores" data-action="compare-stores" disabled>مقایسه فروشگاه‌های انتخاب‌شده</button>
    <div id="store-compare"></div>
  `;
}

function renderSpecs(specs) {
  if (!specs.length) return "<p class='hint'>مشخصاتی ثبت نشده است.</p>";
  const visible = specs.slice(0, 6).map(specRow).join("");
  const rest = specs.slice(6);
  const more = rest.length ? `<details><summary>بقیهٔ مشخصات</summary><ul class="specs">${rest.map(specRow).join("")}</ul></details>` : "";
  return `<ul class="specs">${visible}</ul>${more}`;
}

function specRow(spec) {
  const label = [spec.section, spec.key].filter(Boolean).join(" / ");
  return `<li><span>${esc(label)}</span><strong>${esc(spec.value ?? "—")}</strong></li>`;
}

async function loadStores(productId) {
  const host = document.getElementById("stores");
  if (!host) return;
  host.innerHTML = "<p class='status'>در حال پیدا کردن فروشگاه…</p>";
  const params = new URLSearchParams({ lat: String(state.lat), lon: String(state.lon) });
  if (state.maxDistanceKm) params.set("max_distance_km", state.maxDistanceKm);
  try {
    const data = await apiGet(`/api/products/${encodeURIComponent(productId)}/stores?` + params.toString());
    state.stores = data.stores || [];
    host.innerHTML = state.stores.length
      ? state.stores.map(renderStore).join("")
      : `<p class="status">${esc(data.message_fa || "فروشگاهی پیدا نشد.")}</p>`;
  } catch (err) {
    host.innerHTML = `<p class="status">${esc(err.message)}</p>`;
  }
}

function renderStore(store) {
  const checked = state.selectedShops.has(store.shop_id) ? "checked" : "";
  const pays = (store.payment_options || []).map((item) => {
    const channel = item.channel === "in_person" ? "حضوری" : "";
    const text = [item.provider_name, channel].filter(Boolean).join(" · ");
    return text ? `<span class="badge pay">${esc(text)}</span>` : "";
  }).join("");
  const fast = store.supports_fast_delivery ? `<span class="badge">ارسال فوری</span>` : "";
  return `<article class="store ${store.cheapest_is_stale ? "stale" : ""}">
    <div class="store-top">
      <h3>${esc(store.name || "فروشگاه")}</h3>
      <span class="dist">${formatKm(store.distance_km)}</span>
    </div>
    <p class="muted">${esc([store.location_label, store.address].filter(Boolean).join(" · "))}</p>
    <p class="price">${formatToman(store.best_price_toman)}</p>
    <div class="card-actions">${pays}${fast}</div>
    ${(store.offers || []).map(renderOffer).join("")}
    <div class="store-actions">
      ${geoLink(store)}
      <button type="button" data-action="contact" data-shop-id="${esc(store.shop_id)}">اطلاعات تماس</button>
      <label class="check"><input type="checkbox" data-action="toggle-shop" data-shop-id="${esc(store.shop_id)}" ${checked} /> مقایسه</label>
    </div>
  </article>`;
}

function renderOffer(offer) {
  const badge = !offer.last_price_changed_at
    ? `<span class="badge warn">تاریخ نامشخص</span>`
    : offer.is_stale
      ? `<span class="badge stale">قیمت کهنه</span>`
      : `<span class="badge fresh">قیمت تازه</span>`;
  const warranty = warrantyText(offer.warranty);
  return `<div class="offer">
    <strong>${formatToman(offer.price_toman)}</strong>
    <p class="muted">${esc(offer.seller_title || "")}</p>
    ${offer.description ? `<p class="clamp">${esc(offer.description)}</p>` : ""}
    ${warranty ? `<p class="muted">گارانتی: ${esc(warranty)}</p>` : ""}
    <div class="offer-actions" data-fresh>
      ${badge}
      <span class="muted">${esc(offer.freshness_label_fa || "")}</span>
      <button type="button" data-action="freshness" data-offer-id="${esc(offer.offer_id)}">تازگی قیمت</button>
    </div>
  </div>`;
}

function toggleShop(input) {
  const id = input.dataset.shopId;
  if (input.checked) {
    if (state.selectedShops.size >= 3) {
      input.checked = false;
      toast("حداکثر سه فروشگاه را می‌توان مقایسه کرد.");
      return;
    }
    state.selectedShops.add(id);
  } else {
    state.selectedShops.delete(id);
  }
  const button = document.getElementById("compare-stores");
  if (button) button.disabled = state.selectedShops.size < 2;
}

async function compareSelectedStores() {
  if (!state.product || state.selectedShops.size < 2) return;
  const host = document.getElementById("store-compare");
  host.innerHTML = "<p class='status'>در حال مقایسه…</p>";
  const params = new URLSearchParams({
    product_id: state.product.product_id,
    shop_ids: [...state.selectedShops].join(","),
    lat: String(state.lat),
    lon: String(state.lon),
  });
  try {
    const data = await apiGet("/api/compare/stores?" + params.toString());
    host.innerHTML = `<div class="table-wrap"><table>
      <tr><th>فروشگاه</th><th>فاصله</th><th>قیمت</th><th>تازگی</th><th>پرداخت</th></tr>
      ${(data.stores || []).map((store) => `<tr>
        <td>${esc(store.name || "")}</td>
        <td>${formatKm(store.distance_km)}</td>
        <td>${formatToman(store.best_price_toman)}</td>
        <td>${store.cheapest_is_stale ? "کهنه" : "تازه"}</td>
        <td>${esc((store.payment_options || []).map((item) => item.provider_name).filter(Boolean).join("، "))}</td>
      </tr>`).join("")}
    </table></div>`;
  } catch (err) {
    host.innerHTML = `<p class="status">${esc(err.message)}</p>`;
  }
}

async function openContact(shopId) {
  const modal = document.getElementById("modal");
  document.getElementById("modal-title").textContent = "اطلاعات تماس";
  document.getElementById("modal-body").innerHTML = "<p class='status'>در حال خواندن…</p>";
  modal.hidden = false;
  try {
    const data = await apiGet("/api/shops/" + encodeURIComponent(shopId) + "/contact");
    const contacts = (data.contacts || []).map((item) => `<li>${esc(item.channel || "تماس")}: ${esc(item.display_number || "—")}</li>`).join("");
    document.getElementById("modal-body").innerHTML = `
      <p class="warning">${esc(data.disclaimer_fa || "")}</p>
      <h3>${esc(data.name || "")}</h3>
      <p class="muted">${esc([data.location_label, data.address].filter(Boolean).join(" · "))}</p>
      <ul class="specs">${contacts || "<li>تماسی ثبت نشده</li>"}</ul>
      ${data.instagram ? `<p>اینستاگرام: ${esc(data.instagram)}</p>` : ""}
      ${data.website_url ? `<p>وب‌سایت: ${esc(data.website_url)}</p>` : ""}
      ${formatHours(data.weekly_hours)}
    `;
  } catch (err) {
    document.getElementById("modal-body").innerHTML = `<p class="status">${esc(err.message)}</p>`;
  }
}

async function loadFreshness(button) {
  const slot = button.closest("[data-fresh]");
  try {
    const data = await apiGet("/api/offers/" + encodeURIComponent(button.dataset.offerId) + "/freshness");
    const note = document.createElement("span");
    note.className = "muted";
    note.textContent = data.freshness_label_fa || data.label_fa || "";
    slot.appendChild(note);
    button.remove();
  } catch (err) {
    toast(err.message);
  }
}

async function renderCompareView() {
  const host = document.getElementById("compare-body");
  const products = [...state.selected.values()];
  if (products.length < 2) {
    host.innerHTML = "<p class='status'>از نتیجهٔ جست‌وجو حداقل دو محصول را برای مقایسه علامت بزنید.</p>";
    return;
  }
  host.innerHTML = "<p class='status'>در حال مقایسه…</p>";
  try {
    const data = await apiGet("/api/compare/products?ids=" + encodeURIComponent(products.map((item) => item.product_id).join(",")));
    const cols = data.products || [];
    const head = cols.map((product) => `<th>${esc(product.persian_title || "")}</th>`).join("");
    const price = cols.map((product) => `<td>${formatRange(product.min_price_toman, product.max_price_toman)}</td>`).join("");
    const brand = cols.map((product) => `<td>${esc(product.brand_name || "—")}</td>`).join("");
    const rows = (data.rows || []).map((row) => {
      const cells = cols.map((product) => `<td>${esc(cellValue(row.values?.[product.product_id]))}</td>`).join("");
      return `<tr><th>${esc([row.section, row.key].filter(Boolean).join(" / "))}</th>${cells}</tr>`;
    }).join("");
    host.innerHTML = `<div class="table-wrap"><table>
      <tr><th>مورد</th>${head}</tr>
      <tr><th>قیمت</th>${price}</tr>
      <tr><th>برند</th>${brand}</tr>
      ${rows}
    </table></div>`;
  } catch (err) {
    host.innerHTML = `<p class="status">${esc(err.message)}</p>`;
  }
}

async function sendChat() {
  const input = document.getElementById("chat-input");
  const message = input.value.trim();
  if (!message || state.chatBusy) return;
  state.chatBusy = true;
  state.chat.push({ role: "user", content: message, products: [] });
  input.value = "";
  renderChat();
  const history = state.chat.slice(0, -1).slice(-8).map((item) => ({
    role: item.role,
    content: String(item.content || "").slice(0, 4000),
  }));
  try {
    const data = await apiPost("/chat", {
      message,
      lat: state.lat,
      lon: state.lon,
      history,
    });
    for (const product of data.products || []) state.catalog.set(product.product_id, product);
    state.chat.push({
      role: "assistant",
      content: data.reply || "",
      products: data.products || [],
    });
  } catch (err) {
    state.chat.push({ role: "assistant", content: err.message, products: [] });
  } finally {
    state.chatBusy = false;
    renderChat();
  }
}

function renderChat() {
  const log = document.getElementById("log");
  log.innerHTML = state.chat.map((item) => {
    const cards = (item.products || []).map((product) => `
      <button type="button" class="card" data-action="open-product" data-id="${esc(product.product_id)}">
        ${thumb(product.primary_image_url)}
        <span>
          <strong>${esc(product.persian_title || "")}</strong>
          <span class="price">${formatRange(product.min_price_toman, product.max_price_toman)}</span>
        </span>
      </button>`).join("");
    return `<div class="bubble ${item.role === "user" ? "user" : ""}">${esc(item.content)}</div>${cards}`;
  }).join("");
  log.scrollTop = log.scrollHeight;
}

function updateCompareTab() {
  const button = document.querySelector("[data-view='compare']");
  button.textContent = state.selected.size
    ? "مقایسه (" + formatNumber(state.selected.size) + ")"
    : "مقایسه";
}

function thumb(url) {
  const safe = safeUrl(url);
  if (!safe) return `<div class="thumb"><span>بدون تصویر</span></div>`;
  return `<div class="thumb"><img alt="" src="${esc(safe)}" /></div>`;
}

function geoLink(store) {
  if (store.lat === null || store.lat === undefined || store.lon === null || store.lon === undefined) return "";
  return `<a class="text-btn" href="geo:${Number(store.lat)},${Number(store.lon)}">مسیریابی</a>`;
}

function formatHours(hours) {
  if (!hours || typeof hours !== "object") return "";
  const lines = DAYS.map(([key, label]) => {
    const day = hours[key];
    if (!day) return "";
    if (day.status === "closed") return `${label}: تعطیل`;
    const shifts = (day.shifts || []).filter((shift) => shift.start_time && !(String(shift.start_time).startsWith("00:00") && String(shift.end_time || "").startsWith("00:00")));
    if (!shifts.length || day.status === "unsupported") return `${label}: نامشخص`;
    const text = shifts.map((shift) => `${String(shift.start_time).slice(0, 5)}–${String(shift.end_time).slice(0, 5)}`).join("، ");
    return `${label}: ${text}`;
  }).filter(Boolean);
  return lines.length ? `<ul class="specs">${lines.map((line) => `<li>${esc(line)}</li>`).join("")}</ul>` : "";
}

function warrantyText(warranty) {
  if (!warranty) return "";
  const bits = [];
  if (warranty.provider) bits.push(warranty.provider);
  if (warranty.period_months) bits.push(formatNumber(warranty.period_months) + " ماه");
  if (warranty.description) bits.push(warranty.description);
  return bits.join(" · ");
}

function formatNumber(value) {
  return numberFmt.format(Number(value) || 0);
}

function formatToman(value) {
  if (value === null || value === undefined) return "قیمت نامشخص";
  return numberFmt.format(value) + " تومان";
}

function formatRange(min, max) {
  if (min == null && max == null) return "قیمت نامشخص";
  if (min == null || max == null || min === max) return formatToman(min ?? max);
  return "از " + numberFmt.format(min) + " تا " + numberFmt.format(max) + " تومان";
}

function formatKm(km) {
  if (km === null || km === undefined) return "فاصله نامشخص";
  if (km < 1) return numberFmt.format(Math.round(km * 1000)) + " متر";
  return kmFmt.format(km) + " کیلومتر";
}

function cellValue(value) {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

function parseCoord(value) {
  const ascii = toAsciiDigits(String(value)).replace(/[^\d.-]/g, "");
  if (!ascii) return null;
  const number = Number(ascii);
  return Number.isFinite(number) ? number : null;
}

function toAsciiDigits(value) {
  return value
    .replace(/[۰-۹]/g, (digit) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(digit)))
    .replace(/[٠-٩]/g, (digit) => String("٠١٢٣٤٥٦٧٨٩".indexOf(digit)));
}

function safeUrl(url) {
  return typeof url === "string" && /^https?:\/\//i.test(url) ? url : "";
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));
}

let toastTimer;
function toast(text) {
  const el = document.getElementById("toast");
  el.hidden = false;
  el.textContent = text;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.hidden = true;
  }, 3200);
}
