(function () {
  const SECTIONS = [
    { key: 'cost-impact', endpoint: '/api/cost-impact-report', title: 'Cost Impact Analysis' },
    { key: 'supplier-risk', endpoint: '/api/supplier-risk-report', title: 'Supplier & Country Risk' },
    { key: 'duty-optimization', endpoint: '/api/duty-optimization-report', title: 'Duty Optimization & Compliance' },
  ];

  function activeFileQuery() {
    try {
      const fname = localStorage.getItem('tariff_active_file');
      if (fname) return `?file=${encodeURIComponent(fname)}`;
    } catch (_) {}
    return '';
  }

  function escapeHtml(s) {
    return (s || '').toString()
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  }

  function toBulletHTML(text) {
    const lines = String(text || '').split(/\r?\n/).map(l => l.trim()).filter(Boolean);
    const bullets = lines.filter(l => /^-\s+/.test(l)).map(l => l.replace(/^-[\s]*/, ''));
    if (bullets.length) return '<ul class="mb-0">' + bullets.map(b => `<li>${escapeHtml(b)}</li>`).join('') + '</ul>';
    return `<div>${escapeHtml(text || '')}</div>`;
  }

  async function loadReport(endpoint) {
    const res = await fetch(`${endpoint}${activeFileQuery()}`);
    if (!res.ok) throw new Error(`Failed to fetch ${endpoint}`);
    return res.json();
  }

  function renderSection(section, data) {
    const summaryEl = document.getElementById(`summary-cards-${section.key}`);
    const container = document.getElementById(`buckets-container-${section.key}`);
    if (!summaryEl || !container) return;

    const buckets = (data.buckets_order || Object.keys(data.issues_by_bucket || {})).map(name => ({
      name, items: (data.issues_by_bucket && data.issues_by_bucket[name]) || [],
    }));
    const totalFindings = buckets.reduce((acc, b) => acc + b.items.length, 0);
    const rowsAudited = (data.summary && data.summary.total_rows) || 0;
    const tablesAnalyzed = (data.summary && data.summary.total_tables) || 0;

    summaryEl.innerHTML = `
      <div class="row g-3">
        <div class="col-6 col-md-3">
          <div class="kpi-card kpi-score hover-card h-100">
            <div class="kpi-title">Total Findings</div>
            <div class="kpi-value">${totalFindings}</div>
          </div>
        </div>
        <div class="col-6 col-md-3">
          <div class="kpi-card kpi-records hover-card h-100">
            <div class="kpi-title">Rows Audited</div>
            <div class="kpi-value">${rowsAudited}</div>
          </div>
        </div>
        <div class="col-6 col-md-3">
          <div class="kpi-card kpi-tables hover-card h-100">
            <div class="kpi-title">Tables Analyzed</div>
            <div class="kpi-value">${tablesAnalyzed}</div>
          </div>
        </div>
        <div class="col-6 col-md-3">
          <div class="kpi-card kpi-fields hover-card h-100">
            <div class="kpi-title">Checks Run</div>
            <div class="kpi-value">${buckets.length}</div>
          </div>
        </div>
      </div>
      <div class="summary-card summary-card--takeaways mt-3">
        <div class="summary-card-title">AI Summary — ${section.title}</div>
        <div class="issue-llm-summary">${toBulletHTML(data.llm_summary || 'Summary unavailable.')}</div>
      </div>
    `;

    container.innerHTML = '';
    const nav = document.createElement('ul');
    nav.className = 'nav nav-tabs mb-2 mt-3';
    const panes = document.createElement('div');
    panes.className = 'tab-content mt-3';

    buckets.forEach((b, idx) => {
      const slug = `${section.key}-${b.name.replace(/[^a-z0-9]/gi, '_')}`;
      const li = document.createElement('li');
      li.className = 'nav-item';
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'nav-link' + (idx === 0 ? ' active' : '');
      btn.setAttribute('data-target', `pane-${slug}`);
      btn.textContent = `${b.name} (${b.items.length})`;
      li.appendChild(btn);
      nav.appendChild(li);

      const pane = document.createElement('div');
      pane.className = 'tab-pane' + (idx === 0 ? ' active' : '');
      pane.id = `pane-${slug}`;
      pane.style.display = idx === 0 ? 'block' : 'none';

      const heading = document.createElement('div');
      heading.className = 'results-summary-heading details-heading mt-2';
      heading.textContent = 'Findings';
      pane.appendChild(heading);

      const tableWrap = document.createElement('div');
      tableWrap.className = 'table-responsive issues-table';
      const headers = ['Table', 'Record ID', 'Field', 'Description', 'Value Found', 'Proposed Action'];
      tableWrap.innerHTML = `
        <table class="table table-sm table-striped table-bordered align-middle">
          <thead><tr>${headers.map(h => `<th>${h}</th>`).join('')}</tr></thead>
          <tbody></tbody>
        </table>
      `;
      const tbody = tableWrap.querySelector('tbody');
      if (!b.items.length) {
        tbody.innerHTML = `<tr><td colspan="${headers.length}" class="text-muted">No findings</td></tr>`;
      } else {
        b.items.forEach(it => {
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td>${escapeHtml(it.table)}</td>
            <td>${escapeHtml(it.record_id)}</td>
            <td>${escapeHtml(it.field)}</td>
            <td>${escapeHtml(it.description)}</td>
            <td>${escapeHtml(it.value_found)}</td>
            <td>${escapeHtml(it.proposed_action)}</td>
          `;
          tbody.appendChild(tr);
        });
      }
      pane.appendChild(tableWrap);
      panes.appendChild(pane);
    });

    container.appendChild(nav);
    container.appendChild(panes);
    nav.querySelectorAll('.nav-link').forEach(link => {
      link.addEventListener('click', () => {
        nav.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
        Array.from(panes.children).forEach(p => { p.classList.remove('active'); p.style.display = 'none'; });
        link.classList.add('active');
        const pane = document.getElementById(link.getAttribute('data-target'));
        if (pane) { pane.classList.add('active'); pane.style.display = 'block'; }
      });
    });
  }

  async function loadAll() {
    for (const section of SECTIONS) {
      try {
        const data = await loadReport(section.endpoint);
        renderSection(section, data);
      } catch (e) {
        console.error(`Failed to load section ${section.key}`, e);
        const container = document.getElementById(`buckets-container-${section.key}`);
        if (container) container.innerHTML = '<div class="text-danger">Failed to load this section.</div>';
      }
    }
  }

  function initTabSwitching() {
    const tabButtons = document.querySelectorAll('#section-tabs .nav-link');
    tabButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        tabButtons.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        document.querySelectorAll('.analysis-section').forEach(s => { s.style.display = 'none'; });
        const target = document.getElementById(`section-${btn.dataset.section}`);
        if (target) target.style.display = 'block';
      });
    });
  }

  function init() {
    initTabSwitching();
    loadAll();
  }

  window.AnalysisDetails = { init };
})();
