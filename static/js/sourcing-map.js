// Global Sourcing Map: self-contained dot map (no external map/CDN dependency),
// ported from demo.html's renderMap()/openCountry()/partDecision() for real workbook data.
(function () {
    console.log('[sourcing-map] loaded, choosable alt rows + re-source actions build');
    // Approximate country centroids (lat, lon). Extend as new countries show up in the data.
    var COORD = {
        China: [35, 105], Taiwan: [23.7, 121], 'South Korea': [36.5, 127.8], Japan: [36, 138],
        Vietnam: [16, 108], Malaysia: [4.2, 102], Thailand: [15, 101], Mexico: [23, -102],
        Germany: [51, 10], USA: [39, -98], India: [22, 79], Philippines: [13, 122],
        Canada: [56, -106], Brazil: [-10, -55], 'United Kingdom': [54, -2], France: [46, 2],
        Italy: [43, 12], Spain: [40, -4], Poland: [52, 20], Indonesia: [-2, 118],
        Bangladesh: [24, 90], Pakistan: [30, 70], Turkey: [39, 35], Egypt: [26, 30],
        'South Africa': [-29, 24], Australia: [-25, 133], Singapore: [1.35, 103.8],
        'Hong Kong': [22.3, 114.2], Netherlands: [52, 5.75], Switzerland: [47, 8],
        Sweden: [62, 15], 'Czech Republic': [50, 15], Romania: [46, 25], Israel: [31, 35],
        'Saudi Arabia': [24, 45], UAE: [24, 54], Argentina: [-34, -64], Colombia: [4, -72],
        Chile: [-30, -71], Nigeria: [10, 8], Kenya: [1, 38], Russia: [62, 94],
    };
    var PLANT = [39, -98];
    var W = 680, H = 360;
    var px = function (lon) { return (lon + 180) / 360 * W; };
    var py = function (lat) { return (90 - lat) / 180 * H; };

    var decisions = {}; // in-memory only, like demo.html. Resets on reload.
    var selCountry = null;
    var lastPayload = null;
    var lastDrilldown = null;
    var openParts = new Set();

    function $(sel) { return document.querySelector(sel); }
    function $$(sel) { return Array.from(document.querySelectorAll(sel)); }

    function activeFileQuery() {
        try {
            var fname = localStorage.getItem('tariff_active_file');
            if (fname) return '?file=' + encodeURIComponent(fname);
        } catch (_) {}
        return '';
    }
    function fileParam() {
        try { return localStorage.getItem('tariff_active_file') || ''; } catch (_) { return ''; }
    }

    function bandColor(band) {
        if (band === 'Red') return '#dc3545';
        if (band === 'Amber') return '#fd7e14';
        return '#198754';
    }
    function bandClass(band) { return band === 'Red' ? 'red' : (band === 'Amber' ? 'amber' : 'clear'); }
    function riskPillClass(band) {
        if (band === 'Red') return 'risk-high';
        if (band === 'Amber') return 'risk-medium';
        return 'risk-low';
    }
    function money(v) {
        var n = Number(v);
        if (!isFinite(n)) return '--';
        return '$' + Math.round(n).toLocaleString();
    }
    function escapeHtml(s) {
        return (s || '').toString()
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
    }

    function renderTable(byCountry) {
        var host = $('#sourcingMapTable');
        if (!host) return;
        if (!byCountry.length) {
            host.innerHTML = '<div class="text-muted">No country-of-origin data found in the active workbook.</div>';
            return;
        }
        var rows = byCountry.map(function (c) {
            return '<tr data-country="' + escapeHtml(c.country) + '" style="cursor:pointer">' +
                '<td>' + escapeHtml(c.country) + '</td>' +
                '<td>' + money(c.spend) + '</td>' +
                '<td>' + money(c.impact) + '</td>' +
                '<td>' + (c.vendors != null ? c.vendors : '--') + '</td>' +
                '<td><span class="risk-pill ' + riskPillClass(c.band) + '">' + escapeHtml(c.band) + '</span></td>' +
                '</tr>';
        }).join('');
        host.innerHTML =
            '<div class="table-responsive"><table class="table table-sm table-hover align-middle">' +
            '<thead class="table-light"><tr><th>Country</th><th>Spend</th><th>Tariff Impact</th><th>Vendors</th><th>Risk</th></tr></thead>' +
            '<tbody>' + rows + '</tbody></table></div>';
        $$('#sourcingMapTable tr[data-country]').forEach(function (tr) {
            tr.addEventListener('click', function () { openCountry(tr.getAttribute('data-country')); });
        });
    }

    function renderMap(payload) {
        var svg = $('#sourcingMap');
        var loading = $('#sourcingMapLoading');
        if (!svg) return;

        var byCountry = {};
        (payload.by_country || []).forEach(function (c) { byCountry[c.country] = c; });
        var spends = (payload.by_country || []).map(function (c) { return c.spend; });
        var maxSp = Math.max.apply(null, spends.length ? spends : [1]) || 1;

        var cx = px(PLANT[1]), cy = py(PLANT[0]);

        var grat = '';
        for (var lat = -60; lat <= 75; lat += 30) grat += '<line class="grat" x1="0" y1="' + py(lat) + '" x2="' + W + '" y2="' + py(lat) + '"/>';
        for (var lon = -150; lon <= 150; lon += 30) grat += '<line class="grat" x1="' + px(lon) + '" y1="0" x2="' + px(lon) + '" y2="' + H + '"/>';

        var arcs = '';
        Object.keys(byCountry).forEach(function (c) {
            var coord = COORD[c];
            if (!coord || c === 'USA') return;
            var x = px(coord[1]), y = py(coord[0]);
            var mx = (x + cx) / 2, my = Math.min(y, cy) - 46;
            arcs += '<path class="arc" d="M' + x + ' ' + y + ' Q' + mx + ' ' + my + ' ' + cx + ' ' + cy + '"/>';
        });

        var nodes = '';
        Object.entries(byCountry).forEach(function (entry) {
            var c = entry[0], a = entry[1];
            var coord = COORD[c];
            if (!coord) return;
            var x = px(coord[1]), y = py(coord[0]);
            var r = 7 + 15 * Math.sqrt((a.spend || 0) / maxSp);
            var col = bandColor(a.band);
            nodes += '<g class="cnode ' + bandClass(a.band) + '" data-c="' + escapeHtml(c) + '">' +
                '<circle class="halo" cx="' + x + '" cy="' + y + '" r="12" fill="' + col + '"/>' +
                '<circle cx="' + x + '" cy="' + y + '" r="' + r + '" fill="' + col + '" fill-opacity=".85" stroke="#fff" stroke-width="1.5"/>' +
                '<text class="clabel" x="' + x + '" y="' + (y + r + 12) + '" text-anchor="middle">' + escapeHtml(c) + '</text>' +
                '</g>';
        });

        var plant = '<g><path class="plant" d="M' + cx + ' ' + (cy - 11) + ' L' + (cx + 10) + ' ' + cy + ' L' + cx + ' ' + (cy + 11) + ' L' + (cx - 10) + ' ' + cy + ' Z" stroke="#fff" stroke-width="1.5"/>' +
            '<text class="clabel" x="' + cx + '" y="' + (cy + 24) + '" text-anchor="middle" style="fill:#6d5bd0;font-weight:700">Your plant</text></g>';

        svg.innerHTML = '<rect class="ocean" x="0" y="0" width="' + W + '" height="' + H + '"/>' + grat + arcs + nodes + plant;
        $$('#sourcingMap .cnode').forEach(function (n) {
            n.addEventListener('click', function () { openCountry(n.getAttribute('data-c')); });
        });

        if (loading) loading.style.display = 'none';
        svg.style.display = 'block';
    }

    function partHtml(rec) {
        var alts = rec.alternatives || [];
        var dcsAlready = decisions[rec.invoice_id];
        var rows = alts.map(function (a, i) {
            var best = i === 0 && a.estimated_annual_saving > 0;
            var clickable = !dcsAlready;
            return '<div class="alt' + (best ? ' best' : '') + (clickable ? ' choosable' : '') + '"' +
                (clickable ? ' data-id="' + escapeHtml(rec.invoice_id) + '" data-country="' + escapeHtml(a.country) + '" role="button" tabindex="0"' : '') + '>' +
                '<div class="ac">' + escapeHtml(a.country) + (best ? '<span class="rec">recommended</span>' : '') +
                '<div class="faint mono" style="font-size:11px">' + a.duty_rate_pct + '% duty rate' + (clickable ? '. Click to choose.' : '') + '</div></div>' +
                '<div class="am">vs ' + (rec.duty_rate_pct != null ? rec.duty_rate_pct : '--') + '% today</div>' +
                '<div class="save ' + (a.estimated_annual_saving > 0 ? 'up' : 'down') + '">' +
                (a.estimated_annual_saving > 0 ? 'save ' : '+') + money(Math.abs(a.estimated_annual_saving)) + '</div>' +
                '</div>';
        }).join('');
        var dcs = decisions[rec.invoice_id];
        var best = alts[0];
        var rec_line = best && best.estimated_annual_saving > 0
            ? 'Re-source to <b>' + escapeHtml(best.country) + '</b> to save ' + money(best.estimated_annual_saving) + '/yr, or add it as a second source to de-risk.'
            : 'No cheaper origin found for this HS code. Consider a second source or a tariff exclusion filing.';
        var actions = dcs
            ? '<div class="logged">&#10003; Decision logged: ' + escapeHtml(dcs) + '</div>'
            : '<div class="actions">' +
              '<button class="abtn prim" data-act="Re-source" data-id="' + escapeHtml(rec.invoice_id) + '">Re-source</button>' +
              '<button class="abtn" data-act="Add second source" data-id="' + escapeHtml(rec.invoice_id) + '">Add second source</button>' +
              '<button class="abtn" data-act="File exclusion" data-id="' + escapeHtml(rec.invoice_id) + '">File exclusion</button>' +
              '<button class="abtn" data-act="Accept &amp; monitor" data-id="' + escapeHtml(rec.invoice_id) + '">Accept &amp; monitor</button>' +
              '</div>';
        return '<div class="dhelp">' +
            '<div class="dh">Sourcing options for HS ' + escapeHtml(rec.hs_code) + ', current duty ' + (rec.duty_rate_pct != null ? rec.duty_rate_pct + '%' : '--') + '</div>' +
            (rows || '<div class="text-muted small">No alternate-country duty rate on file for this HS code.</div>') +
            '<div style="font-size:12.5px;margin-top:10px" class="muted">' + rec_line + '</div>' +
            actions +
            '</div>';
    }

    async function openCountry(country) {
        selCountry = country;
        openParts = new Set();
        lastDrilldown = null;
        var mapView = $('#mapView'), cview = $('#cview'), backBtn = $('#backBtn'), stageTitle = $('#stageTitle');
        if (mapView) mapView.style.display = 'none';
        if (cview) { cview.style.display = 'block'; cview.innerHTML = '<div class="text-muted">Loading ' + escapeHtml(country) + '...</div>'; }
        if (backBtn) backBtn.style.display = 'inline-block';
        if (stageTitle) stageTitle.textContent = 'Sourcing from ' + country;

        try {
            var res = await fetch('/api/country-drilldown?country=' + encodeURIComponent(country) + (fileParam() ? '&file=' + encodeURIComponent(fileParam()) : ''));
            if (!res.ok) throw new Error('country-drilldown failed');
            var data = await res.json();
            lastDrilldown = data;
            renderCountry(data);
        } catch (e) {
            console.warn('country drilldown failed', e);
            if (cview) cview.innerHTML = '<div class="text-danger">Could not load details for ' + escapeHtml(country) + '.</div>';
        }
    }

    function rerenderCountry() {
        if (lastDrilldown) renderCountry(lastDrilldown);
    }

    function renderCountry(data) {
        var cview = $('#cview');
        if (!cview) return;
        var s = data.summary || {};
        var records = data.records || [];
        var parts = records.map(function (rec) {
            var dcs = decisions[rec.invoice_id];
            var isOpen = openParts.has(rec.invoice_id);
            return '<div class="part' + (isOpen ? ' open' : '') + '" data-id="' + escapeHtml(rec.invoice_id) + '">' +
                '<div class="parthead"><span class="chev">&#9654;</span>' +
                '<span class="pnm">' + escapeHtml(rec.category || rec.hs_code) + '</span>' +
                '<span class="pm"><span>HS <b>' + escapeHtml(rec.hs_code) + '</b></span>' +
                '<span>duty <b>' + (rec.duty_rate_pct != null ? rec.duty_rate_pct + '%' : '--') + '</b></span>' +
                '<span>impact <b>' + (rec.impact > 0 ? money(rec.impact) : '--') + '</b></span>' +
                (rec.single_source ? '<span class="faint">single-source</span>' : '') + '</span>' +
                '<span class="band ' + rec.band + '">' + rec.band + (dcs ? ' &#10003;' : '') + '</span></div>' +
                '<div class="decision">' + partHtml(rec) + '</div>' +
                '</div>';
        }).join('');

        cview.innerHTML =
            '<div class="chead"><div class="flag">' + escapeHtml((data.country || '').slice(0, 2).toUpperCase()) + '</div>' +
            '<div><h2>' + escapeHtml(data.country) + '</h2><div class="csub">' + records.length + ' invoice line(s) &middot; ' + s.pos + ' PO(s) &middot; ' + s.vendors + ' vendor(s)</div></div></div>' +
            '<div class="cstats">' +
            '<div class="cstat red"><div class="cn">' + money(s.impact) + '</div><div class="cl">annual tariff cost</div></div>' +
            '<div class="cstat"><div class="cn">' + money(s.spend) + '</div><div class="cl">spend from ' + escapeHtml(data.country) + '</div></div>' +
            '<div class="cstat"><div class="cn">' + (s.single_source_count || 0) + '</div><div class="cl">single-source</div></div>' +
            '</div>' +
            '<div class="partlist">' + (parts || '<div class="text-muted p-3">No invoice detail found for this country.</div>') + '</div>';

        bindCountry();
    }

    function bindCountry() {
        $$('#cview .parthead').forEach(function (h) {
            h.addEventListener('click', function () {
                var part = h.parentElement;
                var id = part.dataset.id;
                if (openParts.has(id)) openParts.delete(id); else openParts.add(id);
                part.classList.toggle('open');
            });
        });
        $$('#cview .abtn').forEach(function (b) {
            b.addEventListener('click', function (e) {
                e.stopPropagation();
                decisions[b.dataset.id] = b.dataset.act;
                openParts.add(b.dataset.id);
                rerenderCountry();
            });
        });
        $$('#cview .alt.choosable').forEach(function (a) {
            a.addEventListener('click', function (e) {
                e.stopPropagation();
                decisions[a.dataset.id] = 'Re-source to ' + a.dataset.country;
                openParts.add(a.dataset.id);
                rerenderCountry();
            });
            a.addEventListener('keydown', function (e) {
                if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); a.click(); }
            });
        });
    }

    function backToMap() {
        selCountry = null;
        var mapView = $('#mapView'), cview = $('#cview'), backBtn = $('#backBtn'), stageTitle = $('#stageTitle');
        if (cview) { cview.style.display = 'none'; cview.innerHTML = ''; }
        if (mapView) mapView.style.display = 'block';
        if (backBtn) backBtn.style.display = 'none';
        if (stageTitle) stageTitle.textContent = 'Global Sourcing Map';
    }

    async function init() {
        var loading = $('#sourcingMapLoading');
        $('#backBtn')?.addEventListener('click', backToMap);
        try {
            var res = await fetch('/api/sourcing-map-report' + activeFileQuery());
            if (!res.ok) throw new Error('sourcing-map-report failed');
            var payload = await res.json();
            lastPayload = payload;
            renderTable(payload.by_country || []);
            renderMap(payload);
        } catch (e) {
            console.warn('Sourcing map failed to load', e);
            if (loading) loading.textContent = 'Map data unavailable right now.';
            renderTable([]);
        }
    }

    if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', init); } else { init(); }
})();
