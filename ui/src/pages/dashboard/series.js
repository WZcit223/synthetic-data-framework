// The dashboard's demand chart, as data: a SKU's shipped days, then the fitted
// forecast's days with its mean and interval (GET /demand-series). Pure, so tested.

/**
 * `{labels, series, band, total}` for LineChart: the labels run over the history, then the
 * forecast days; the forecast's mean comes first, since a band takes the first series' colour.
 */
export function demandChart(data) {
  const history = data.history ?? [];
  const days = data.forecast?.days ?? [];
  const gap = n => Array(n).fill(null);
  return {
    labels: [...history.map(h => h.date), ...days.map(d => d.date)],
    series: [
      { name: "forecast", values: [...gap(history.length), ...days.map(d => d.mean)] },
      { name: "demand", values: [...history.map(h => h.qty), ...gap(days.length)] },
    ],
    band: days.length
      ? {
          name: `${Math.round((data.forecast.level ?? 0) * 100)} % interval`,
          low: [...gap(history.length), ...days.map(d => d.low)],
          high: [...gap(history.length), ...days.map(d => d.high)],
        }
      : undefined,
    total: days.reduce((s, d) => s + d.mean, 0),
  };
}
