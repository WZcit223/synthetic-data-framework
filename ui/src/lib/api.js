// The one way to reach the backend. The pages talk to it only through api(), so
// the base URL is configurable (set window.SDF_API_BASE before the page's module
// loads to host the UI elsewhere) and every path they use can be checked
// against the OpenAPI schema.
// UI rule: reshape what the API returned (sort, filter, group, pivot, chart);
// never compute a business number here.
export const API = globalThis.SDF_API_BASE ?? "/api/v1";

export async function api(path, options) {
  const res = await fetch(API + path, options);
  if (!res.ok) {
    const err = new Error(`${path}: ${res.status}`);
    err.status = res.status;
    try {
      err.detail = describeDetail((await res.json()).detail);
    } catch {
      err.detail = null; // not a JSON error body
    }
    throw err;
  }
  return res.json();
}

// FastAPI's error detail as one line: a message, or the list a 422 carries.
export function describeDetail(detail) {
  if (detail == null) return null;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map(d => (d.loc ? `${d.loc.filter(p => p !== "body").join(".")}: ${d.msg}` : String(d.msg ?? d))).join("; ");
  }
  return JSON.stringify(detail);
}
