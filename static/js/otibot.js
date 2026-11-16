// Shared helpers for every OtiBot page: formatting, theme toggle and a small line chart.
const O = {};

O.esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
O.money = (v, digits = 2) => v == null ? '–' : (v < 0 ? '-$' : '$') +
    Math.abs(v).toLocaleString(undefined, {minimumFractionDigits: digits, maximumFractionDigits: digits});
O.signed = (v, digits = 2) => v == null ? '–' : (v > 0 ? '+' : '') + O.money(v, digits);
O.pct = (v, digits = 1) => v == null ? '–' : (v * 100).toFixed(digits) + '%';
O.signedPct = (v, digits = 1) => v == null ? '–' : (v > 0 ? '+' : '') + O.pct(v, digits);
O.cls = v => v > 0 ? 'pos' : v < 0 ? 'neg' : '';
O.price = v => v == null ? '–' : Number(v).toPrecision(6).replace(/\.?0+$/, '');
O.date = t => t ? new Date(t).toLocaleString(undefined, {month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'}) : '';
O.day = t => t ? new Date(t).toLocaleDateString(undefined, {month: 'short', day: 'numeric', year: 'numeric'}) : '';

// the thin bar at the top of the page shows while any request is running
O._busy = 0;
O.busy = delta => {
    O._busy = Math.max(0, O._busy + delta);
    document.documentElement.classList.toggle('o-loading', O._busy > 0);
};

// pass {quiet: true} for background polling so the bar doesn't flicker
O.getJSON = async (url, options = {}) => {
    const {quiet, ...fetchOptions} = options;
    if (!quiet) O.busy(1);
    try {
        const res = await fetch(url, fetchOptions);
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || res.statusText);
        return data;
    } finally {
        if (!quiet) O.busy(-1);
    }
};
O.postJSON = (url, body) => O.getJSON(url, {method: 'POST', headers: {'Content-Type': 'application/json'},
                                             body: JSON.stringify(body || {})});

// removes the shimmering placeholders inside root once its data is in
O.ready = root => (root || document).querySelectorAll('.o-skel').forEach(el => el.classList.remove('o-skel'));

// sets innerHTML only when it changed, so unchanged parts don't flicker
O.setHTML = (el, html) => {
    if (el._html === html) return false;
    el._html = html;
    el.innerHTML = html;
    return true;
};

// counts a number up or down to its new value instead of jumping
O.tween = (el, to, fmt, ms = 700) => {
    cancelAnimationFrame(el._raf);
    if (to == null || Number.isNaN(to)) { el._v = null; el.textContent = fmt(to); return; }
    const from = el._v ?? to;
    el._v = to;
    if (from === to || matchMedia('(prefers-reduced-motion: reduce)').matches) { el.textContent = fmt(to); return; }
    const t0 = performance.now();
    const step = now => {
        const k = Math.min(1, (now - t0) / ms);
        el.textContent = fmt(from + (to - from) * (1 - Math.pow(1 - k, 3)));
        if (k < 1) el._raf = requestAnimationFrame(step);
    };
    el._raf = requestAnimationFrame(step);
    el.classList.remove('o-flash'); void el.offsetWidth; el.classList.add('o-flash');
};

// buttons show a spinner while their action runs
O.withSpinner = async (btn, fn) => {
    const html = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
    btn.style.minWidth = btn.offsetWidth + 'px';
    try { return await fn(); } finally { btn.disabled = false; btn.innerHTML = html; }
};

// theme: saved choice, else the system setting
O.setTheme = theme => {
    document.documentElement.setAttribute('data-bs-theme', theme);
    try { localStorage.setItem('otibot-theme', theme); } catch (e) {}
    document.querySelectorAll('.theme-icon').forEach(i => i.className = 'theme-icon bi ' + (theme === 'dark' ? 'bi-sun' : 'bi-moon-stars'));
};
O.toggleTheme = () => O.setTheme(document.documentElement.getAttribute('data-bs-theme') === 'dark' ? 'light' : 'dark');

/**
 * Line chart drawn as inline SVG. Colors are CSS variables so it follows the theme.
 *   el: container element (gets an svg and a tooltip)
 *   series: [{name, color: 'var(--o-accent)', points: [{t, v}]}], first series gets the area fill
 *   opts: {height, format, spark (no axes or hover), empty}
 */
O.lineChart = (el, series, opts = {}) => {
    const height = opts.height || 240;
    const fmt = opts.format || (v => O.money(v));
    const spark = !!opts.spark;
    el.classList.add('o-chart');
    const draw = () => {
        const w = el.clientWidth || 300;
        const all = series.flatMap(s => s.points);
        if (all.length < 2) {
            el.innerHTML = `<div class="o-empty" style="height:${height}px;display:grid;place-items:center">${opts.empty || 'No data yet'}</div>`;
            return;
        }
        const pad = spark ? {l: 2, r: 2, t: 4, b: 4} : {l: 4, r: 70, t: 10, b: 26};
        const ts = all.map(p => +new Date(p.t));
        const t0 = Math.min(...ts), t1 = Math.max(...ts);
        let lo = Math.min(...all.map(p => p.v)), hi = Math.max(...all.map(p => p.v));
        if (hi - lo < 1e-9) { lo -= 1; hi += 1; }
        const padV = (hi - lo) * 0.06; lo -= padV; hi += padV;
        const x = t => pad.l + (+new Date(t) - t0) / Math.max(t1 - t0, 1) * (w - pad.l - pad.r);
        const y = v => pad.t + (hi - v) / (hi - lo) * (height - pad.t - pad.b);
        const path = pts => pts.map((p, i) => `${i ? 'L' : 'M'}${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join('');
        const base = height - pad.b;
        const gid = 'g' + Math.random().toString(36).slice(2);

        let svg = `<svg height="${height}" viewBox="0 0 ${w} ${height}" role="img" aria-label="${O.esc(series.map(s => s.name).join(', '))}">`;
        svg += `<defs><linearGradient id="${gid}" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" style="stop-color:${series[0].color};stop-opacity:.22"/>
            <stop offset="1" style="stop-color:${series[0].color};stop-opacity:0"/></linearGradient></defs>`;
        if (!spark) {
            for (let i = 0; i <= 3; i++) {
                const v = lo + (hi - lo) * i / 3;
                svg += `<line x1="${pad.l}" x2="${w - pad.r}" y1="${y(v)}" y2="${y(v)}" style="stroke:var(--o-grid)"/>
                        <text x="${w - pad.r + 8}" y="${y(v) + 4}" style="fill:var(--o-muted)" font-size="11">${O.esc(fmt(v))}</text>`;
            }
            const ticks = Math.max(2, Math.min(6, Math.floor(w / 140)));
            for (let i = 0; i < ticks; i++) {
                const t = t0 + (t1 - t0) * i / (ticks - 1);
                const anchor = i === 0 ? 'start' : i === ticks - 1 ? 'end' : 'middle';
                const label = (t1 - t0) > 3 * 864e5 ? new Date(t).toLocaleDateString(undefined, {month: 'short', day: 'numeric'})
                    : new Date(t).toLocaleTimeString(undefined, {hour: '2-digit', minute: '2-digit'});
                svg += `<text x="${x(t)}" y="${height - 6}" text-anchor="${anchor}" style="fill:var(--o-muted)" font-size="11">${label}</text>`;
            }
        }
        const first = series[0].points;
        if (first.length > 1) {
            svg += `<path d="${path(first)}L${x(first[first.length - 1].t)},${base}L${x(first[0].t)},${base}Z" fill="url(#${gid})"/>`;
        }
        series.slice().reverse().forEach(s => {
            if (s.points.length > 1) svg += `<path d="${path(s.points)}" fill="none" style="stroke:${s.color}" stroke-width="2"
                stroke-linejoin="round" stroke-linecap="round" ${s.dashed ? 'stroke-dasharray="5 4"' : ''}/>`;
        });
        const last = first[first.length - 1];
        if (last) svg += `<circle cx="${x(last.t)}" cy="${y(last.v)}" r="4" style="fill:${series[0].color};stroke:var(--o-surface)" stroke-width="2"/>`;
        if (!spark) {
            svg += `<line class="cross" y1="${pad.t}" y2="${base}" style="stroke:var(--o-text-2)" stroke-dasharray="3 3" visibility="hidden"/>`;
            series.forEach((s, i) => svg += `<circle class="hover-dot" data-i="${i}" r="4" style="fill:${s.color};stroke:var(--o-surface)" stroke-width="2" visibility="hidden"/>`);
            svg += `<rect class="hit" x="0" y="0" width="${w}" height="${height}" fill="transparent"/>`;
        }
        svg += '</svg>';
        el.innerHTML = svg + (spark ? '' : '<div class="o-tip"></div>');
        if (spark) return;

        const tip = el.querySelector('.o-tip'), cross = el.querySelector('.cross');
        const dots = el.querySelectorAll('.hover-dot');
        const nearest = (pts, t) => pts.reduce((a, b) => Math.abs(+new Date(b.t) - t) < Math.abs(+new Date(a.t) - t) ? b : a);
        const hit = el.querySelector('.hit');
        const move = ev => {
            const rect = hit.getBoundingClientRect();
            const mx = (ev.touches ? ev.touches[0].clientX : ev.clientX) - rect.left;
            const t = t0 + (mx - pad.l) / (w - pad.l - pad.r) * (t1 - t0);
            const p0 = nearest(first, t);
            cross.setAttribute('x1', x(p0.t)); cross.setAttribute('x2', x(p0.t)); cross.setAttribute('visibility', 'visible');
            let rows = `<div class="muted mb-1">${O.date(p0.t)}</div>`;
            series.forEach((s, i) => {
                if (!s.points.length) return;
                const p = nearest(s.points, +new Date(p0.t));
                dots[i].setAttribute('cx', x(p.t)); dots[i].setAttribute('cy', y(p.v)); dots[i].setAttribute('visibility', 'visible');
                rows += `<div class="row-item"><span style="width:10px;height:3px;border-radius:2px;background:${s.color}"></span>
                         ${O.esc(s.name)} <b class="ms-auto ps-2">${O.esc(fmt(p.v))}</b></div>`;
            });
            tip.innerHTML = rows;
            tip.style.display = 'block';
            const left = x(p0.t) + 14;
            tip.style.left = Math.min(left, w - tip.offsetWidth - 4) + 'px';
            tip.style.top = Math.max(0, y(p0.v) - tip.offsetHeight - 10) + 'px';
        };
        const leave = () => {
            tip.style.display = 'none'; cross.setAttribute('visibility', 'hidden');
            dots.forEach(d => d.setAttribute('visibility', 'hidden'));
        };
        hit.addEventListener('mousemove', move);
        hit.addEventListener('touchmove', move, {passive: true});
        hit.addEventListener('mouseleave', leave);
        hit.addEventListener('touchend', leave);
    };
    draw();
    if (!el._oResize) {
        el._oResize = true;
        let pending;
        window.addEventListener('resize', () => { clearTimeout(pending); pending = setTimeout(() => el._oDraw && el._oDraw(), 100); });
    }
    el._oDraw = draw;
};

/**
 * Candlestick chart of one pair's trades, laid out like a trading platform:
 * buy arrows under the bar, sell arrows over it, the chosen trade's exit
 * levels as dashed lines with price tags on the axis, and a volume pane
 * below with the spike threshold the entry rule uses.
 *   el: container element
 *   d: /api/agents/chart response
 *   opts: {trade (index into d.trades), onSelect(index), height}
 */
O.RULE_TAGS = {'take profit': 'TP', 'stop loss': 'SL', 'trailing stop': 'TRAIL',
               'went nowhere': 'STALE', 'time limit': 'TIME', 'end of test': 'END', 'market close': 'CLOSE'};
O.candleChart = (el, d, opts = {}) => {
    el.classList.add('o-chart');
    const sel = opts.trade ?? d.trades.length - 1;
    const draw = () => {
        const n = d.t.length, w = el.clientWidth || 300;
        if (n < 2) { el.innerHTML = `<div class="o-empty" style="height:200px;display:grid;place-items:center">No candles for this pair</div>`; return; }
        const priceH = opts.height || 280, volH = 72, gap = 14;
        const pad = {l: 4, r: 76, t: 22, b: 24};
        const volTop = pad.t + priceH + gap, H = volTop + volH + pad.b;
        const tr = d.trades[sel];

        // the window: the chosen trade with room either side, at least enough candles to fill the width
        const want = Math.max(40, Math.min(180, Math.floor((w - pad.l - pad.r) / 7)));
        let a, b;
        if (tr) {
            const room = Math.max(16, Math.round((tr.exit_i - tr.entry_i) * 0.6));
            a = tr.entry_i - room; b = tr.exit_i + room;
        } else { b = n - 1; a = b - want; }
        if (b - a + 1 < want) { const more = want - (b - a + 1); a -= Math.floor(more / 2); b += Math.ceil(more / 2); }
        if (a < 0) { b -= a; a = 0; }
        if (b > n - 1) { a = Math.max(0, a - (b - n + 1)); b = n - 1; }
        const idx = [];
        for (let i = a; i <= b; i++) idx.push(i);

        const levels = tr ? [tr.entry_price, tr.stop, tr.target] : [];
        let lo = Math.min(...idx.map(i => d.l[i]), ...levels), hi = Math.max(...idx.map(i => d.h[i]), ...levels);
        const padV = (hi - lo) * 0.1 || hi * 0.01; lo -= padV; hi += padV;
        const cw = (w - pad.l - pad.r) / idx.length;
        const x = i => pad.l + (i - a + 0.5) * cw;
        const y = v => pad.t + (hi - v) / (hi - lo) * priceH;
        const vmax = Math.max(...idx.map(i => Math.max(d.v[i] || 0, d.threshold[i] || 0))) * 1.15 || 1;
        const vy = v => volTop + volH - (v || 0) / vmax * volH;
        const right = w - pad.r, bodyW = Math.max(1, Math.min(12, cw * 0.66));
        const fmtP = v => O.price(v);

        let s = `<svg height="${H}" viewBox="0 0 ${w} ${H}" role="img" aria-label="Candles with trade entries and exits">`;
        // grid and price axis
        const gridLabels = [];
        for (let k = 0; k <= 4; k++) {
            const v = lo + (hi - lo) * k / 4;
            s += `<line x1="${pad.l}" x2="${right}" y1="${y(v)}" y2="${y(v)}" style="stroke:var(--o-grid)"/>`;
            gridLabels.push(v);
        }
        s += `<line x1="${pad.l}" x2="${right}" y1="${volTop + volH}" y2="${volTop + volH}" style="stroke:var(--o-grid)"/>
              <text x="${pad.l + 2}" y="${volTop + 10}" style="fill:var(--o-muted)" font-size="10">VOLUME</text>`;
        const ticks = Math.max(2, Math.min(7, Math.floor(w / 130)));
        const span = +new Date(d.t[b]) - +new Date(d.t[a]);
        for (let k = 0; k < ticks; k++) {
            const i = Math.round(a + (b - a) * k / (ticks - 1)), t = new Date(d.t[i]);
            const anchor = k === 0 ? 'start' : k === ticks - 1 ? 'end' : 'middle';
            const label = span > 2 * 864e5 ? t.toLocaleDateString(undefined, {month: 'short', day: 'numeric'})
                : t.toLocaleString(undefined, {month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'});
            s += `<line x1="${x(i)}" x2="${x(i)}" y1="${pad.t}" y2="${volTop + volH}" style="stroke:var(--o-grid)" stroke-dasharray="2 4"/>
                  <text x="${x(i)}" y="${H - 6}" text-anchor="${anchor}" style="fill:var(--o-muted)" font-size="11">${label}</text>`;
        }

        // the chosen trade: its span shaded, then the levels each exit rule watched
        const tags = [];
        if (tr) {
            const x0 = x(tr.entry_i) - cw / 2, x1 = x(Math.min(tr.exit_i, b)) + cw / 2;
            s += `<rect x="${x0}" y="${pad.t}" width="${x1 - x0}" height="${priceH}" style="fill:var(${tr.pnl >= 0 ? '--o-good-soft' : '--o-bad-soft'})"/>`;
            const pct = (p) => O.signedPct(p, 1);
            const level = (v, color, dash, label, tag) => {
                s += `<line x1="${x0}" x2="${x1}" y1="${y(v)}" y2="${y(v)}" style="stroke:${color}" stroke-width="1.4" ${dash ? `stroke-dasharray="${dash}"` : ''}/>
                      <text x="${x0 + 4}" y="${y(v) - 4}" style="fill:${color}" font-size="10" font-weight="600">${O.esc(label)}</text>`;
                tags.push({v, color, text: tag ?? fmtP(v)});
            };
            const side = tr.side === 'short' ? -1 : 1, st = d.settings;
            level(tr.target, 'var(--o-good)', '6 4', `Take profit ${pct(side * st.take_profit)}`);
            level(tr.stop, 'var(--o-bad)', '6 4', `Stop loss ${pct(-side * st.stop_loss)}`);
            level(tr.trail_on, 'var(--o-info)', '2 3', `Trail turns on ${pct(side * st.trail_trigger)}`);
            level(tr.entry_price, 'var(--o-text-2)', '', 'Entry');
            // the trailing stop follows the best price once it turns on
            let path = '', open = false, lastTrail = null;
            tr.trail.forEach((v, k) => {
                const i = tr.trail_start + k;
                if (v == null || i > b) { open = false; return; }
                path += `${open ? 'L' : 'M'}${(x(i) - cw / 2).toFixed(1)},${y(v).toFixed(1)}L${(x(i) + cw / 2).toFixed(1)},${y(v).toFixed(1)}`;
                open = true; lastTrail = v;
            });
            if (path) {
                s += `<path d="${path}" fill="none" style="stroke:var(--o-accent)" stroke-width="1.6" stroke-dasharray="4 3"/>`;
                tags.push({v: lastTrail, color: 'var(--o-accent)', text: fmtP(lastTrail)});
            }
        }

        // volume, with spike candles in the accent color and the threshold as a dashed step line
        idx.forEach(i => {
            const up = d.c[i] >= d.o[i], spike = d.threshold[i] != null && d.v[i] >= d.threshold[i];
            s += `<rect x="${x(i) - bodyW / 2}" y="${vy(d.v[i])}" width="${bodyW}" height="${volTop + volH - vy(d.v[i])}"
                   style="fill:${spike ? 'var(--o-accent)' : up ? 'var(--o-good)' : 'var(--o-bad)'}" opacity="${spike ? .95 : .35}"/>`;
        });
        let th = '', on = false;
        idx.forEach(i => {
            const v = d.threshold[i];
            if (v == null) { on = false; return; }
            th += `${on ? 'L' : 'M'}${(x(i) - cw / 2).toFixed(1)},${vy(v).toFixed(1)}L${(x(i) + cw / 2).toFixed(1)},${vy(v).toFixed(1)}`;
            on = true;
        });
        if (th) {
            s += `<path d="${th}" fill="none" style="stroke:var(--o-accent)" stroke-width="1.2" stroke-dasharray="5 3"/>`;
            const lastTh = d.threshold[b] ?? d.threshold.slice(a, b + 1).filter(v => v != null).pop();
            if (lastTh != null) s += `<text x="${right + 8}" y="${Math.max(volTop + 8, vy(lastTh) + 4)}" style="fill:var(--o-accent)" font-size="10" font-weight="600">${d.min_spike}× median</text>`;
        }

        // candles
        idx.forEach(i => {
            const up = d.c[i] >= d.o[i], color = up ? 'var(--o-good)' : 'var(--o-bad)';
            const top = y(Math.max(d.o[i], d.c[i])), bot = y(Math.min(d.o[i], d.c[i]));
            s += `<line x1="${x(i)}" x2="${x(i)}" y1="${y(d.h[i])}" y2="${y(d.l[i])}" style="stroke:${color}"/>
                  <rect x="${x(i) - bodyW / 2}" y="${top}" width="${bodyW}" height="${Math.max(1, bot - top)}" style="fill:${color}"/>`;
        });

        // spikes the entry rule scored but did not trade: a hollow ring above the volume bar
        const skipped = d.signals.filter(g => !g.traded && g.spike_i >= a && g.spike_i <= b);
        skipped.forEach(g => s += `<circle cx="${x(g.spike_i)}" cy="${Math.max(volTop + 4, vy(d.v[g.spike_i]) - 6)}" r="3.2"
            fill="none" style="stroke:var(--o-text-2)" stroke-width="1.3"/>`);

        // entry and exit markers: buys (and short covers) point up from under the bar, sells point down from over it
        const arrow = (i, up, color, label, faded) => {
            const cx = x(i), size = Math.max(4, Math.min(7, cw * 0.55));
            const tip = up ? y(d.l[i]) + 5 : y(d.h[i]) - 5;
            const base = up ? tip + size * 1.6 : tip - size * 1.6;
            const ly = up ? base + 13 : base - 6;
            s += `<g opacity="${faded ? .45 : 1}"><path d="M${cx},${tip}L${cx - size},${base}L${cx + size},${base}Z" style="fill:${color}"/>
                  <text x="${cx}" y="${ly}" text-anchor="middle" style="fill:${color}" font-size="10" font-weight="700">${O.esc(label)}</text></g>`;
        };
        d.trades.forEach((t, k) => {
            const faded = k !== sel, long = t.side !== 'short';
            if (t.entry_i >= a && t.entry_i <= b) arrow(t.entry_i, long, long ? 'var(--o-good)' : 'var(--o-bad)', long ? 'BUY' : 'SHORT', faded);
            if (t.exit_i >= a && t.exit_i <= b) arrow(t.exit_i, !long, long ? 'var(--o-bad)' : 'var(--o-good)', O.RULE_TAGS[t.reason] || t.reason, faded);
        });

        // price tags on the axis for the chosen trade's levels, nudged apart so they don't overlap
        tags.sort((p, q) => y(p.v) - y(q.v));
        let last = -Infinity;
        const tagYs = [];
        tags.forEach(g => {
            const ty = Math.max(y(g.v), last + 17); last = ty; tagYs.push(ty);
            s += `<rect x="${right + 2}" y="${ty - 8}" width="${pad.r - 4}" height="16" rx="3" style="fill:${g.color}"/>
                  <text x="${right + 8}" y="${ty + 4}" style="fill:var(--o-surface)" font-size="10.5" font-weight="700">${O.esc(g.text)}</text>`;
        });
        // axis prices, minus any a tag already covers
        gridLabels.filter(v => tagYs.every(ty => Math.abs(ty - y(v)) > 20)).forEach(v =>
            s += `<text x="${right + 8}" y="${y(v) + 4}" style="fill:var(--o-muted)" font-size="11">${O.esc(fmtP(v))}</text>`);

        s += `<line class="cross" y1="${pad.t}" y2="${volTop + volH}" style="stroke:var(--o-text-2)" stroke-dasharray="3 3" visibility="hidden"/>
              <line class="cross-h" x1="${pad.l}" x2="${right}" style="stroke:var(--o-text-2)" stroke-dasharray="3 3" visibility="hidden"/>
              <g class="cross-tag" visibility="hidden"><rect x="${right + 2}" width="${pad.r - 4}" height="16" rx="3" style="fill:var(--o-text-2)"/>
              <text x="${right + 8}" style="fill:var(--o-surface)" font-size="10.5" font-weight="700"></text></g>
              <rect class="hit" x="0" y="0" width="${right}" height="${volTop + volH}" fill="transparent" style="cursor:crosshair"/></svg>`;
        el.innerHTML = s + '<div class="o-tip"></div>';

        const tip = el.querySelector('.o-tip'), hit = el.querySelector('.hit');
        const cross = el.querySelector('.cross'), crossH = el.querySelector('.cross-h'), crossTag = el.querySelector('.cross-tag');
        const at = ev => {
            const r = hit.getBoundingClientRect(), p = ev.touches ? ev.touches[0] : ev;
            const i = Math.max(a, Math.min(b, a + Math.floor((p.clientX - r.left - pad.l) / cw)));
            return {i, my: p.clientY - r.top};
        };
        const move = ev => {
            const {i, my} = at(ev);
            cross.setAttribute('x1', x(i)); cross.setAttribute('x2', x(i)); cross.setAttribute('visibility', 'visible');
            const inPrice = my >= pad.t && my <= pad.t + priceH;
            [crossH, crossTag].forEach(e => e.setAttribute('visibility', inPrice ? 'visible' : 'hidden'));
            if (inPrice) {
                crossH.setAttribute('y1', my); crossH.setAttribute('y2', my);
                crossTag.querySelector('rect').setAttribute('y', my - 8);
                const t = crossTag.querySelector('text');
                t.setAttribute('y', my + 4); t.textContent = fmtP(hi - (my - pad.t) / priceH * (hi - lo));
            }
            const ratio = d.threshold[i] ? d.v[i] / d.threshold[i] * d.min_spike : null;
            let rows = `<div class="muted mb-1">${O.date(d.t[i])}</div>
                <div>O <b>${fmtP(d.o[i])}</b> H <b>${fmtP(d.h[i])}</b> L <b>${fmtP(d.l[i])}</b> C <b>${fmtP(d.c[i])}</b></div>
                <div class="muted">Volume ${Number(d.v[i]).toLocaleString(undefined, {maximumFractionDigits: 0})}${ratio == null ? '' : ` · ${ratio.toFixed(1)}× median`}</div>`;
            d.trades.forEach(t => {
                const long = t.side !== 'short';
                if (t.entry_i === i) rows += `<div class="row-item mt-1"><b class="${long ? 'pos' : 'neg'}">${long ? '▲ Buy' : '▼ Short'}</b> at ${fmtP(t.entry_price)}</div>`;
                if (t.exit_i === i) rows += `<div class="row-item mt-1"><b class="${long ? 'neg' : 'pos'}">${long ? '▼ Sell' : '▲ Cover'}</b> ${O.esc(t.reason)} at ${fmtP(t.exit_price)}
                    <b class="ms-auto ps-2 ${O.cls(t.pnl)}">${O.signed(t.pnl)}</b></div>`;
            });
            d.signals.filter(g => g.spike_i === i).forEach(g => rows += `<div class="mt-1 text-2">Entry rule: ${O.esc(g.text)}</div>`);
            tip.innerHTML = rows;
            tip.style.display = 'block';
            const left = x(i) + 14;
            tip.style.left = Math.max(0, left + tip.offsetWidth > w - 4 ? x(i) - tip.offsetWidth - 14 : left) + 'px';
            tip.style.top = Math.max(0, Math.min(my - tip.offsetHeight / 2, H - tip.offsetHeight)) + 'px';
        };
        const leave = () => {
            tip.style.display = 'none';
            [cross, crossH, crossTag].forEach(e => e.setAttribute('visibility', 'hidden'));
        };
        hit.addEventListener('mousemove', move);
        hit.addEventListener('touchmove', move, {passive: true});
        hit.addEventListener('mouseleave', leave);
        hit.addEventListener('touchend', leave);
        // clicking inside another trade picks it
        hit.addEventListener('click', ev => {
            const {i} = at(ev);
            const k = d.trades.findIndex(t => i >= t.entry_i && i <= t.exit_i);
            if (k >= 0 && k !== sel && opts.onSelect) opts.onSelect(k);
        });
    };
    draw();
    if (!el._oResize) {
        el._oResize = true;
        let pending;
        window.addEventListener('resize', () => { clearTimeout(pending); pending = setTimeout(() => el._oDraw && el._oDraw(), 100); });
    }
    el._oDraw = draw;
};
