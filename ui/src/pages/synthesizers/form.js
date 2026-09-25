// The Synthesizers page's run form, as data: what each parameter's field holds, and
// the request it makes. Pure (no DOM); the checks are lib/synthesis.js readParam, the
// same the server makes.
import { readParam } from "../../lib/synthesis.js";

/**
 * A parameter field's starting state from its default. `text` is a text or number
 * field, `checked` a checkbox, `choice` the none/true/false select of a nullable bool,
 * `none` the "none" box of a nullable string, `bad` a number field holding text it
 * cannot parse (the browser reports such text as "").
 */
export function initialEntry(p) {
  return {
    text: p.default == null ? "" : String(p.default),
    checked: p.default === true,
    choice: p.default == null ? "" : String(p.default),
    none: p.type === "str" && p.nullable && p.default == null,
    bad: false,
  };
}

// What readParam reads for one field.
export function rawOf(p, e) {
  if (p.type === "bool") return p.nullable ? e.choice : e.checked;
  if (p.type === "str" && p.nullable && e.none) return null;
  return e.text;
}

/**
 * The run's parameters and each field's error.
 * @returns {{values: Record<string, any>, errors: Record<string, string>, ok: boolean}}
 */
export function readForm(params, entries) {
  /** @type {Record<string, any>} */
  const values = {};
  /** @type {Record<string, string>} */
  const errors = {};
  for (const p of params) {
    const e = entries[p.name] ?? initialEntry(p);
    const read = e.bad ? { error: `${p.name}: enter a number` } : readParam(p, rawOf(p, e));
    if (read.error) errors[p.name] = read.error;
    else values[p.name] = read.value;
  }
  return { values, errors, ok: Object.keys(errors).length === 0 };
}
