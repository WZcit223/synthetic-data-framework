// The generation sliders' arithmetic, kept out of the component so it is tested.

/**
 * The value a range input holds for `v` once its bounds change: the nearest step
 * counted from the new minimum, within the maximum, as the browser moves it. Set
 * as the state, it keeps the label and the request equal to what the slider shows.
 */
export function onGrid(v, { min, max }, step) {
  const s = min + Math.round((v - min) / step) * step;
  return s > max ? min + Math.floor((max - min) / step) * step : Math.max(min, s);
}
