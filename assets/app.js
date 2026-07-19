(() => {
  'use strict';
  const COLORS = ['#63e6be','#74c0fc','#ffd43b','#ff8787','#b197fc','#ffa94d','#66d9e8','#8ce99a','#f783ac','#a9e34b'];
  const RANGE_MAX_POINTS = 900;
  let payload, pulseChart, comparisonChart;
  let activeRange = '1Y';

  const $ = id => document.getElementById(id);
  const pct = value => value == null ? '—' : `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
  const level = value => value == null ? '—' : new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value);
  const dateLabel = value => new Intl.DateTimeFormat('en', { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC' }).format(new Date(value + 'T00:00:00Z'));
  const cssSign = value => value > 0 ? 'positive' : value < 0 ? 'negative' : 'flat';
  const latestDate = () => payload.indices.map(s => s.points.at(-1)?.[0]).filter(Boolean).sort().at(-1);

  function chartDefaults() {
    Chart.defaults.color = '#8f98a8';
    Chart.defaults.borderColor = 'rgba(255,255,255,.08)';
    Chart.defaults.font.family = 'Inter, ui-sans-serif, system-ui, sans-serif';
    Chart.defaults.animation.duration = 350;
  }

  function lineOptions(showLegend = false) {
    return {
      responsive: true, maintainAspectRatio: false, normalized: true,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: showLegend, position: 'bottom', labels: { usePointStyle: true, pointStyle: 'circle', boxWidth: 7, boxHeight: 7, padding: 18, font: { size: 11 } } },
        tooltip: { backgroundColor: '#171b22', titleColor: '#f7f8fa', bodyColor: '#c8ced8', borderColor: 'rgba(255,255,255,.12)', borderWidth: 1, padding: 12,
          callbacks: { label: ctx => ` ${ctx.dataset.label}: ${ctx.parsed.y.toFixed(2)}` } }
      },
      scales: {
        x: { grid: { display: false }, ticks: { maxTicksLimit: window.innerWidth < 600 ? 4 : 7, maxRotation: 0, callback(value) { const raw = this.getLabelForValue(value); return raw ? raw.slice(0, 7) : ''; } } },
        y: { position: 'right', grid: { color: 'rgba(255,255,255,.06)' }, ticks: { callback: v => v.toFixed(0) } }
      },
      elements: { point: { radius: 0, hoverRadius: 4 }, line: { borderWidth: 2, tension: .08 } }
    };
  }

  function renderUpdateTime() {
    const date = new Date(payload.updatedAt);
    $('updated-exact').dateTime = payload.updatedAt;
    $('updated-exact').textContent = new Intl.DateTimeFormat('en', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC', timeZoneName: 'short' }).format(date);
    const mins = Math.max(0, Math.round((Date.now() - date.getTime()) / 60000));
    $('updated-relative').textContent = mins < 2 ? 'just now' : mins < 60 ? `${mins}m ago` : mins < 1440 ? `${Math.round(mins/60)}h ago` : `${Math.round(mins/1440)}d ago`;
    $('market-count').textContent = payload.indices.length;
  }

  function renderMetrics() {
    const selected = $('comparison-date').value;
    const stats = MarketMath.aggregateChanges(payload.indices, selected);
    $('average-change').textContent = pct(stats.mean);
    $('average-change').className = cssSign(stats.mean);
    $('average-period').textContent = `equal-weighted since ${dateLabel(selected)}`;
    $('advancing-count').textContent = `${stats.advancing} / ${stats.coverage}`;
    $('coverage-detail').textContent = `${stats.coverage} of ${payload.indices.length} markets have history`;
    $('median-change').textContent = pct(stats.median);
    $('median-change').className = cssSign(stats.median);
    $('leader-name').textContent = stats.leader?.name || '—';
    $('leader-change').textContent = stats.leader ? pct(stats.leader.change) : '—';
    $('leader-change').className = `metric-detail ${cssSign(stats.leader?.change)}`;
    return new Map(stats.changes.map(x => [x.id, x]));
  }

  function renderCards(changes) {
    $('market-grid').innerHTML = payload.indices.map((s, index) => {
      const latest = s.points.at(-1), move = s.latest?.dayChangePct, selected = changes.get(s.id);
      return `<article class="market-card" data-market="${s.id}">
        <div class="market-top"><span class="market-number">${String(index + 1).padStart(2,'0')}</span>${s.kind === 'proxy' ? '<span class="proxy-badge">Proxy</span>' : '<span class="index-badge">Index</span>'}</div>
        <div class="market-name"><h3>${s.name}</h3><span>${s.region}</span></div>
        <div class="market-level"><strong>${level(latest?.[1])}</strong><span>${s.currency || ''}</span></div>
        <div class="market-changes">
          <div><span>Daily</span><b class="${cssSign(move)}">${pct(move)}</b></div>
          <div><span>Since selected date</span><b class="${cssSign(selected?.change)}">${pct(selected?.change)}</b></div>
        </div>
        <div class="spark-wrap"><canvas id="spark-${s.id}" aria-label="${s.name} one year sparkline" role="img"></canvas></div>
        <div class="market-source">${s.kind === 'proxy' ? s.instrument : 'Benchmark level'} · ${latest ? dateLabel(latest[0]) : 'Unavailable'}</div>
      </article>`;
    }).join('');
    payload.indices.forEach((s, i) => {
      const pts = MarketMath.downsample(MarketMath.slicePoints(s.points, MarketMath.rangeStart('1Y', latestDate())), 150);
      new Chart($(`spark-${s.id}`), { type: 'line', data: { labels: pts.map(p=>p[0]), datasets: [{ data: pts.map(p=>p[1]), borderColor: COLORS[i], fill: false }] }, options: {
        responsive:true, maintainAspectRatio:false, animation:false, plugins:{legend:{display:false},tooltip:{enabled:false}}, scales:{x:{display:false},y:{display:false}}, elements:{point:{radius:0},line:{borderWidth:1.7,tension:.2}}
      }});
    });
  }

  function renderCharts() {
    const start = MarketMath.rangeStart(activeRange, latestDate());
    const pulse = MarketMath.aggregateHistory(payload.indices, start, RANGE_MAX_POINTS);
    if (pulseChart) pulseChart.destroy();
    pulseChart = new Chart($('pulse-chart'), { type:'line', data:{ labels:pulse.map(p=>p[0]), datasets:[{label:'Global pulse',data:pulse.map(p=>p[1]),borderColor:'#63e6be',backgroundColor:'rgba(99,230,190,.08)',fill:true}] }, options:lineOptions(false) });

    const datasets = payload.indices.map((s,i) => {
      const pts = MarketMath.downsample(MarketMath.rebase(MarketMath.slicePoints(s.points,start)), RANGE_MAX_POINTS);
      return { label:s.name, data:pts.map(p=>({x:Date.parse(`${p[0]}T00:00:00Z`),y:p[1]})), parsing:false, borderColor:COLORS[i], backgroundColor:COLORS[i] };
    });
    if (comparisonChart) comparisonChart.destroy();
    const opts = lineOptions(true);
    opts.scales.x.type='linear';
    opts.scales.x.ticks.callback = value => new Date(value).toISOString().slice(0,7);
    opts.plugins.tooltip.callbacks.title = items => items.length ? new Date(items[0].parsed.x).toISOString().slice(0,10) : '';
    comparisonChart = new Chart($('comparison-chart'), { type:'line', data:{datasets}, options:opts });
  }

  function renderAll() {
    const changes = renderMetrics();
    renderCards(changes);
    renderCharts();
  }

  function bindControls() {
    $('range-buttons').addEventListener('click', event => {
      const button = event.target.closest('button[data-range]'); if (!button) return;
      activeRange = button.dataset.range;
      document.querySelectorAll('[data-range]').forEach(b => { const active=b===button; b.classList.toggle('active',active); b.setAttribute('aria-pressed',String(active)); });
      renderCharts();
    });
    $('comparison-date').addEventListener('change', () => { const changes=renderMetrics(); renderCards(changes); });
    $('reset-date').addEventListener('click', () => { $('comparison-date').value=MarketMath.oneYearAgo(latestDate()); $('comparison-date').dispatchEvent(new Event('change')); });
  }

  async function init() {
    try {
      const response = await fetch(`data/market-data.json?v=${Date.now()}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      payload = await response.json();
      if (!payload.indices?.length) throw new Error('No market series');
      chartDefaults(); renderUpdateTime();
      const maxDate=latestDate(), minDate=payload.indices.flatMap(s=>s.points[0]?.[0]||[]).sort()[0];
      $('comparison-date').max=maxDate; $('comparison-date').min=minDate; $('comparison-date').value=MarketMath.oneYearAgo(maxDate);
      bindControls(); renderAll();
      document.documentElement.dataset.ready='true';
    } catch (error) {
      console.error('Dashboard initialization failed', error); $('error-banner').hidden=false;
    }
  }
  init();
})();
