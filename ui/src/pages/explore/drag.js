// What is being dragged across the Explore page (native HTML5 drag and drop): a field
// from the field list, `{field}`, or a chip from a shelf, `{shelf, index}`.
export const DRAG = "application/x-sdf-pivot";
export const drag = { current: null };

/** Where on a shelf a drop at (x, y) lands: the index of the chip it falls before. */
export function dropIndex(shelfEl, x, y) {
  const chips = [...shelfEl.querySelectorAll(".pchip")];
  for (let i = 0; i < chips.length; i++) {
    const r = chips[i].getBoundingClientRect();
    if (y < r.top) return i;
    if (y <= r.bottom && x < r.left + r.width / 2) return i;
  }
  return chips.length;
}
