(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.MarketMath = api;
})(typeof self !== 'undefined' ? self : this, function () {
  const DAY = 86400000;
  const parse = (value) => new Date(value + 'T00:00:00Z');
  const iso = (date) => date.toISOString().slice(0, 10);

  function findBasePoint(points, targetDate) {
    if (!points || !points.length) return null;
    let lo = 0, hi = points.length - 1, answer = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (points[mid][0] <= targetDate) { answer = mid; lo = mid + 1; }
      else hi = mid - 1;
    }
    return answer >= 0 ? points[answer] : null;
  }

  function changePct(base, latest) {
    return Number.isFinite(base) && Number.isFinite(latest) && base !== 0
      ? ((latest / base) - 1) * 100 : null;
  }

  function seriesChange(series, targetDate) {
    const points = series.points || [];
    const base = findBasePoint(points, targetDate);
    const latest = points.length ? points[points.length - 1] : null;
    if (!base || !latest || base[0] === latest[0]) return null;
    return { id: series.id, name: series.name, baseDate: base[0], latestDate: latest[0], change: changePct(base[1], latest[1]) };
  }

  function aggregateChanges(seriesList, targetDate) {
    const changes = seriesList.map(s => seriesChange(s, targetDate)).filter(Boolean).filter(x => Number.isFinite(x.change));
    if (!changes.length) return { mean: null, median: null, advancing: 0, coverage: 0, leader: null, laggard: null, changes: [] };
    const values = changes.map(x => x.change).sort((a, b) => a - b);
    const mid = Math.floor(values.length / 2);
    const median = values.length % 2 ? values[mid] : (values[mid - 1] + values[mid]) / 2;
    const ordered = [...changes].sort((a, b) => b.change - a.change);
    return {
      mean: values.reduce((a, b) => a + b, 0) / values.length,
      median,
      advancing: values.filter(v => v > 0).length,
      coverage: values.length,
      leader: ordered[0],
      laggard: ordered[ordered.length - 1],
      changes
    };
  }

  function rangeStart(range, latestDate) {
    const d = parse(latestDate);
    if (range === 'MAX') return null;
    if (range === 'YTD') return `${d.getUTCFullYear()}-01-01`;
    const copy = new Date(d);
    const days = { '1D': 1, '5D': 7 }[range];
    if (days) copy.setUTCDate(copy.getUTCDate() - days);
    const months = { '1M': 1, '3M': 3, '6M': 6, '1Y': 12, '3Y': 36, '5Y': 60 }[range];
    if (months) copy.setUTCMonth(copy.getUTCMonth() - months);
    return iso(copy);
  }

  function slicePoints(points, startDate) {
    if (!startDate) return points.slice();
    let index = points.findIndex(p => p[0] >= startDate);
    if (index < 0) return points.slice(-1);
    if (index > 0) index -= 1;
    return points.slice(index);
  }

  function downsample(points, maxPoints) {
    if (points.length <= maxPoints) return points;
    const out = [], step = (points.length - 1) / (maxPoints - 1);
    for (let i = 0; i < maxPoints; i++) out.push(points[Math.round(i * step)]);
    return out;
  }

  function rebase(points) {
    if (!points.length || !points[0][1]) return [];
    const base = points[0][1];
    return points.map(p => [p[0], (p[1] / base) * 100]);
  }

  function aggregateHistory(seriesList, startDate, maxPoints = 700) {
    const prepared = seriesList.map(s => {
      const pts = slicePoints(s.points || [], startDate);
      return pts.length ? { points: pts, base: pts[0][1] } : null;
    }).filter(Boolean);
    let dates = [...new Set(prepared.flatMap(s => s.points.map(p => p[0])))].sort();
    dates = downsample(dates.map(d => [d, 0]), maxPoints).map(p => p[0]);
    return dates.map(date => {
      const values = prepared.map(s => {
        const p = findBasePoint(s.points, date);
        return p && s.base ? (p[1] / s.base) * 100 : null;
      }).filter(Number.isFinite);
      return values.length >= 3 ? [date, values.reduce((a, b) => a + b, 0) / values.length] : null;
    }).filter(Boolean);
  }

  function oneYearAgo(latestDate) {
    const d = parse(latestDate); d.setUTCFullYear(d.getUTCFullYear() - 1); return iso(d);
  }

  return { findBasePoint, changePct, seriesChange, aggregateChanges, rangeStart, slicePoints, downsample, rebase, aggregateHistory, oneYearAgo };
});
