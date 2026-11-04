export class ApiError extends Error {
  constructor(message, status = 0) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function apiRequest(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: { Accept: "application/json", ...(options.headers || {}) },
    ...options,
  });

  if (response.status === 401 || response.redirected && response.url.includes("/login/")) {
    const next = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.assign(`/login/?next=${next}`);
    throw new ApiError("Your session has expired.", response.status);
  }

  let data = null;
  try {
    data = await response.json();
  } catch (_) {
    // An HTML error response is converted into a useful client error below.
  }
  if (!response.ok) throw new ApiError(data?.error || `Request failed (${response.status})`, response.status);
  return data;
}

function csrfToken() {
  const value = document.cookie.split("; ").find((item) => item.startsWith("csrftoken="));
  return value ? decodeURIComponent(value.split("=").slice(1).join("=")) : "";
}

export function postJson(path, body = {}) {
  return apiRequest(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken(),
    },
    body: JSON.stringify(body),
  });
}

export function securityAction(incidentId, action, note = "") {
  return postJson(`/react/api/security/incidents/${incidentId}/action/`, { action, note });
}

export function updateSecuritySettings(settings) {
  return postJson("/react/api/security/settings/", settings);
}

export function scanSecurityNow() {
  return postJson("/react/api/security/scan/");
}

export function getBootstrap(page, search = "") {
  const query = new URLSearchParams(search);
  query.set("_view", page);
  return apiRequest(`/react/api/bootstrap/?${query.toString()}`);
}
