(function () {
    var chartsInitialized = false;
    var BUCKETS = ['Cost Impact Analysis', 'Supplier & Country Risk', 'Duty Optimization & Compliance'];
    var colorMap = { 'Cost Impact Analysis': '#fd7e14', 'Supplier & Country Risk': '#0d6efd', 'Duty Optimization & Compliance': '#198754' };
    let currentBucket = BUCKETS[0];

    function splitCategoryLabel(label) {
        if (!label) return [''];
        if (label.includes(' / ')) { const parts = label.split(' / '); return parts.slice(0, 2); }
        const paren = label.indexOf(' (');
        if (paren !== -1) { const head = label.slice(0, paren).trim(); const tail = label.slice(paren).trim(); return [head, tail]; }
        if (label.length > 18) { const parts = label.match(/.{1,18}(?:\s|$)/g) || [label]; return parts.map(s => s.trim()).filter(Boolean); }
        return [label];
    }

    function activeFileQuery() {
        try {
            const fname = localStorage.getItem('tariff_active_file');
            if (fname) return `?file=${encodeURIComponent(fname)}`;
        } catch (_) {}
        return '';
    }

    let __DASH_CACHE__ = null;
    async function fetchDashboardData() {
        if (__DASH_CACHE__) return __DASH_CACHE__;
        const res = await fetch(`/api/dashboard-llm-run${activeFileQuery()}`);
        if (!res.ok) throw new Error('dashboard-llm-run failed');
        const payload = await res.json();
        __DASH_CACHE__ = (payload && payload.data) ? payload.data : payload;
        return __DASH_CACHE__;
    }

    async function populateSummaryRow() {
        try {
            const parsed = await fetchDashboardData();
            const sc = parsed && parsed.summary_cards ? parsed.summary_cards : {};
            const cards = document.querySelectorAll('.summary-cards-row .card .card-body');
            cards.forEach(function (body) {
                const h6 = body.querySelector('h6');
                const valEl = body.querySelector('.display-6');
                if (!h6 || !valEl) return;
                const heading = (h6.textContent || '').trim();
                let value = '--';
                if (heading === 'Total Tariff Exposure') {
                    const v = sc.total_tariff_exposure; value = isFinite(Number(v)) ? ('$' + Math.round(Number(v)).toLocaleString()) : '$--';
                } else if (heading === 'Total Spend Analyzed') {
                    const v = sc.total_spend_analyzed; value = isFinite(Number(v)) ? ('$' + Math.round(Number(v)).toLocaleString()) : '$--';
                } else if (heading === 'Vendors Analyzed') {
                    const v = sc.vendors_analyzed; value = isFinite(Number(v)) ? String(v) : '--';
                } else if (heading === 'POs Analyzed') {
                    const v = sc.pos_analyzed; value = isFinite(Number(v)) ? String(v) : '--';
                } else if (heading === 'High-Risk Findings') {
                    const v = sc.high_risk_findings; value = isFinite(Number(v)) ? String(v) : '--';
                }
                valEl.textContent = value;
            });
            document.getElementById('summary-row-loading')?.style.setProperty('display', 'none');
            const row = document.querySelector('.summary-cards-row');
            if (row) row.style.display = 'flex';
        } catch (e) {
            console.warn('populateSummaryRow failed', e);
            document.getElementById('summary-row-loading')?.style.setProperty('display', 'none');
            const row = document.querySelector('.summary-cards-row');
            if (row) row.style.display = 'flex';
        }
    }

    async function populateGlamRow() {
        const glamLoader = document.getElementById('glam-row-loading');
        const glamRow = document.getElementById('glamRow');
        try {
            const parsed = await fetchDashboardData();
            const metrics = parsed && parsed.impact_metrics ? parsed.impact_metrics : {};
            const cards = document.querySelectorAll('.glam-card .card-body');
            BUCKETS.forEach((bucket, idx) => {
                const m = metrics[bucket] || {};
                const body = cards[idx];
                if (!body) return;
                const container = body.querySelector('.meter-container');
                const arc = container ? container.querySelector('.meter-arc') : null;
                const valEl = container ? container.querySelector('.meter-value') : null;
                const score = Number(m.score);
                if (container && arc && isFinite(score)) {
                    const radius = 100, semiLength = Math.PI * radius;
                    arc.setAttribute('stroke-dasharray', `${semiLength} ${semiLength}`);
                    arc.setAttribute('stroke-dashoffset', semiLength * (1 - (score / 100)));
                    arc.setAttribute('stroke', score >= 90 ? '#198754' : (score >= 70 ? '#fd7e14' : '#dc3545'));
                    container.dataset.score = String(score);
                    if (valEl) valEl.textContent = String(score);
                } else if (valEl) {
                    valEl.textContent = '--';
                }
                const infoEls = body.querySelectorAll('.text-muted.small');
                let cfEl = null, raEl = null;
                infoEls.forEach(el => {
                    const t = (el.textContent || '').toLowerCase();
                    if (t.includes('checks')) cfEl = el; else if (t.includes('rows')) raEl = el;
                });
                if (cfEl) cfEl.textContent = `${(m.checks_failing != null ? m.checks_failing : '--')} checks failing`;
                if (raEl) raEl.textContent = `${(m.rows_audited != null ? m.rows_audited : '--')} rows audited`;
            });
        } catch (e) {
            console.warn('populateGlamRow failed', e);
        } finally {
            if (glamLoader) glamLoader.style.display = 'none';
            if (glamRow) glamRow.style.display = '';
        }
    }

    async function populateCategorySummary() {
        const dqLoader = document.getElementById('dq-row-loading');
        const dqRow = document.querySelector('.dq-list');
        try {
            const parsed = await fetchDashboardData();
            const list = parsed && parsed.category_summary_list ? parsed.category_summary_list : [];
            if (!dqRow) return;
            const frag = document.createDocumentFragment();
            list.slice(0, 8).forEach(function (item) {
                const title = (item && item.title) ? String(item.title) : 'Unknown';
                const sc = Number(item && item.score_pct);
                const ic = Number(item && item.issue_count);
                const issuesArr = Array.isArray(item && item.issues) ? item.issues : [];
                const threshold = (item && item.threshold) || (isFinite(sc) && sc >= 90 ? 'good' : 'warn');
                const col = document.createElement('div');
                col.className = 'col-12 col-md-6 col-lg-4';
                const titleSuffix = isFinite(sc) ? (' (' + Math.round(sc) + '%)') : '';
                const issuesText = (isFinite(ic) ? String(ic) : '--') + ' ' + (ic === 1 ? 'finding' : 'findings') + ': ' + issuesArr.slice(0, 3).join(', ');
                col.innerHTML = '<div class="card shadow-sm dq-list-card h-100"><div class="card-body">'
                    + '<div class="d-flex align-items-center mb-1">'
                    + '<span class="dq-dot ' + threshold + ' me-2"></span>'
                    + '<span class="dq-list-title">' + title + titleSuffix + '</span>'
                    + '</div>'
                    + '<div class="dq-list-meta">' + issuesText + '</div>'
                    + '</div></div>';
                frag.appendChild(col);
            });
            dqRow.innerHTML = '';
            dqRow.appendChild(frag);
        } catch (e) {
            console.warn('populateCategorySummary failed', e);
        } finally {
            if (dqLoader) dqLoader.style.display = 'none';
            if (dqRow) dqRow.style.display = '';
        }
    }

    async function init() {
        if (chartsInitialized) return;
        if (typeof ApexCharts === 'undefined') {
            var tries = 0;
            var timer = setInterval(function () {
                if (typeof ApexCharts !== 'undefined') { clearInterval(timer); init(); }
                else if (++tries > 50) { clearInterval(timer); console.error('[Dash] ApexCharts never loaded'); }
            }, 100);
            return;
        }
        const pieEl = document.getElementById('issuesPieChart');
        const barEl = document.getElementById('issuesBarChart');
        const fullLineEl = document.getElementById('issuesFullTrendChart');
        if (!pieEl || !barEl || !fullLineEl) return;

        let pieValues = [0, 0, 0];
        let months = ['--', '--', '--', '--', '--', '--'];
        let costImpact = [0, 0, 0, 0, 0, 0];
        let supplierRisk = [0, 0, 0, 0, 0, 0];
        let dutyOpt = [0, 0, 0, 0, 0, 0];
        let treeSeries = BUCKETS.map(b => ({ name: b, data: [] }));
        const bucketData = { [BUCKETS[0]]: [], [BUCKETS[1]]: [], [BUCKETS[2]]: [] };
        const barTitle = document.getElementById('issuesBarTitle');

        const pieConfig = {
            chart: {
                type: 'donut', height: 280, toolbar: { show: false },
                events: {
                    dataPointSelection: function (event, chartContext, config) {
                        const idx = config.dataPointIndex;
                        const bucket = BUCKETS[idx];
                        currentBucket = bucket;
                        if (barTitle) barTitle.textContent = bucket;
                        if (window.barChart) {
                            window.barChart.updateOptions({
                                xaxis: { categories: (bucketData[bucket] || []).map(d => splitCategoryLabel(d.x)), labels: { rotate: -45, rotateAlways: true, trim: false, style: { fontSize: '11px' } } },
                                colors: [colorMap[bucket] || '#6c757d'],
                            });
                            window.barChart.updateSeries([{ name: bucket, data: (bucketData[bucket] || []).map(d => d.y) }]);
                        }
                    },
                },
            },
            series: pieValues, labels: BUCKETS, colors: ['#fd7e14', '#0d6efd', '#198754'],
            legend: { position: 'bottom', horizontalAlign: 'center', fontSize: '12px', markers: { width: 12, height: 12 }, itemMargin: { horizontal: 12, vertical: 8 } },
            dataLabels: { enabled: true, formatter: function (val, opts) { return opts.w.config.series[opts.seriesIndex]; }, style: { fontSize: '11px' } },
            plotOptions: { pie: { donut: { size: '45%' } } },
        };

        function makeBarConfig(bucket) {
            const items = bucketData[bucket] || [];
            return {
                chart: { type: 'bar', height: 280, toolbar: { show: false } },
                series: [{ name: bucket, data: items.map(d => d.y) }],
                colors: [colorMap[bucket] || '#6c757d'],
                xaxis: { categories: items.map(d => splitCategoryLabel(d.x)), labels: { rotate: -45, rotateAlways: true, trim: false, style: { fontSize: '11px' } } },
                plotOptions: { bar: { columnWidth: '45%' } },
                dataLabels: { enabled: true, style: { fontSize: '11px' } },
                legend: { show: false },
            };
        }

        const fullLineConfig = {
            chart: { type: 'line', height: 240, toolbar: { show: false } },
            series: [
                { name: 'Cost Impact', data: costImpact },
                { name: 'Supplier Risk', data: supplierRisk },
                { name: 'Duty Optimization', data: dutyOpt },
            ],
            xaxis: { categories: months, labels: { rotate: -45 } },
            yaxis: { title: { text: 'Duty Paid ($k)' } },
            legend: { position: 'bottom', horizontalAlign: 'center', fontSize: '12px', markers: { width: 12, height: 12 }, itemMargin: { horizontal: 12, vertical: 8 } },
            stroke: { curve: 'straight', width: 3 },
            markers: { size: 3 },
        };

        const pieChart = new ApexCharts(pieEl, pieConfig);
        const barChart = new ApexCharts(barEl, makeBarConfig(currentBucket));
        const fullLineChart = new ApexCharts(fullLineEl, fullLineConfig);
        window.pieChart = pieChart; window.barChart = barChart; window.fullLineChart = fullLineChart;
        pieChart.render(); barChart.render(); fullLineChart.render();
        chartsInitialized = true;

        await populateSummaryRow();
        await populateGlamRow();
        await populateCategorySummary();

        try {
            const parsed = await fetchDashboardData();
            const io = parsed && parsed.issue_overview ? parsed.issue_overview : {};
            if (io.pie && Array.isArray(io.pie.labels) && Array.isArray(io.pie.series)) {
                pieChart.updateOptions({ labels: io.pie.labels });
                pieChart.updateSeries(io.pie.series);
            }
            if (Array.isArray(io.treemap)) {
                treeSeries = io.treemap;
                BUCKETS.forEach(b => { bucketData[b] = (treeSeries.find(s => s.name === b) || {}).data || []; });
                if (bucketData[currentBucket]) {
                    const items = bucketData[currentBucket];
                    barChart.updateOptions({ xaxis: { categories: items.map(d => splitCategoryLabel(d.x)) } });
                    barChart.updateSeries([{ name: currentBucket, data: items.map(d => d.y) }]);
                }
            }
            if (io.trend && Array.isArray(io.trend.months)) {
                months = io.trend.months;
                costImpact = io.trend.cost_impact || [];
                supplierRisk = io.trend.supplier_risk || [];
                dutyOpt = io.trend.duty_optimization || [];
                fullLineChart.updateOptions({ xaxis: { categories: months, labels: { rotate: -45 } } });
                fullLineChart.updateSeries([
                    { name: 'Cost Impact', data: costImpact },
                    { name: 'Supplier Risk', data: supplierRisk },
                    { name: 'Duty Optimization', data: dutyOpt },
                ]);
                const totalEl = document.getElementById('issuesTotalLast6');
                const peakEl = document.getElementById('issuesPeakMonth');
                const avgEl = document.getElementById('issuesAvgPerMonth');
                if (io.six_month_summary) {
                    const sum = io.six_month_summary;
                    if (totalEl && sum.total_duty_last_6 != null) totalEl.textContent = '$' + Number(sum.total_duty_last_6).toLocaleString();
                    if (avgEl && sum.avg_per_month != null) avgEl.textContent = `Avg/Month: $${Number(sum.avg_per_month).toLocaleString()}`;
                    if (peakEl && typeof sum.peak_month_index === 'number' && months[sum.peak_month_index]) {
                        peakEl.textContent = `Peak: ${months[sum.peak_month_index]}`;
                    }
                }
            }
        } catch (e) {
            console.warn('issue overview population failed', e);
        }
    }

    if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', init); } else { init(); }
})();
