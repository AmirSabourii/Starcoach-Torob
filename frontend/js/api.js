function apiBase() {
  return String(window.STARCOACH_API_BASE || "").replace(/\/$/, "");
}

function errorText(body, fallback) {
  if (body && typeof body.detail === "string") return body.detail;
  return fallback || "خطا در دریافت داده";
}

async function readBody(response) {
  try {
    return await response.json();
  } catch (_err) {
    return {};
  }
}

async function apiGet(path) {
  let response;
  try {
    response = await fetch(apiBase() + path);
  } catch (_err) {
    throw new Error("ارتباط با سرور برقرار نشد.");
  }
  const body = await readBody(response);
  if (!response.ok) {
    throw new Error(errorText(body));
  }
  return body;
}

async function apiPost(path, payload) {
  let response;
  try {
    response = await fetch(apiBase() + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (_err) {
    throw new Error("ارتباط با سرور برقرار نشد.");
  }
  const body = await readBody(response);
  if (!response.ok) {
    throw new Error(errorText(body));
  }
  return body;
}
