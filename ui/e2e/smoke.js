// The smoke check every page shares: it loads with no console error and no
// failed request, and its first load makes exactly the API calls listed.
import { expect } from "@playwright/test";

export async function smoke(page, path, calls) {
  const errors = [];
  const made = new Set();
  page.on("console", m => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", e => errors.push(String(e)));
  page.on("requestfailed", r => errors.push(`failed: ${r.url()}`));
  page.on("response", r => r.status() >= 400 && errors.push(`${r.status()}: ${r.url()}`));
  page.on("request", r => {
    const url = new URL(r.url());
    if (url.pathname.startsWith("/api/")) made.add(`${r.method()} ${url.pathname}${url.search}`);
  });
  await page.goto(path, { waitUntil: "networkidle" });
  expect(errors).toEqual([]);
  expect([...made].sort()).toEqual([...calls].sort());
}
