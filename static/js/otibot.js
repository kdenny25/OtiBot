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

O.getJSON = async (url, options) => {
    const res = await fetch(url, options);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || res.statusText);
    return data;
};
O.postJSON = (url, body) => O.getJSON(url, {method: 'POST', headers: {'Content-Type': 'application/json'},
                                             body: JSON.stringify(body || {})});

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
