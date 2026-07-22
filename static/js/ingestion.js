// Upload interactions
(function () {
  const fileInput = document.getElementById('fileInput');
  const fileName = document.getElementById('fileName');
  const browseBtn = document.getElementById('browseBtn');
  const form = document.getElementById('uploadForm');
  const uploadError = document.getElementById('uploadError');
  const useDemoBtn = document.getElementById('useDemoBtn');

  browseBtn.addEventListener('click', function () { fileInput.click(); });
  fileInput.addEventListener('change', function () {
    fileName.value = (this.files && this.files.length > 0) ? this.files[0].name : 'No file chosen';
    fileName.classList.remove('is-invalid');
    uploadError?.classList.add('d-none');
  });

  async function analyzeFile(file) {
    const titleEl = document.getElementById('resultsTitle');
    const headerSpinner = document.getElementById('resultsSpinner');
    if (titleEl) titleEl.textContent = 'Generating Results';
    headerSpinner?.classList.remove('d-none');
    const resultsCard = document.getElementById('resultsCard');
    resultsCard?.classList.remove('d-none');
    document.getElementById('modeling-tabs')?.classList.add('d-none');
    document.getElementById('modeling-tabs-content')?.classList.add('d-none');
    try {
      const fd = new FormData();
      fd.append('file', file, file.name);
      const res = await fetch('/api/upload/analyze', { method: 'POST', body: fd });
      if (!res.ok) throw new Error('Analyze request failed');
      const data = await res.json();
      try { localStorage.setItem('tariff_active_file', file.name); } catch (_) {}

      if (data && Array.isArray(data.sheets)) {
        const map = {};
        data.sheets.forEach(s => { map[s.name] = Array.isArray(s.columns) ? s.columns : []; });
        CURRENT_SCHEMA = map;
        renderTables();
        if (Array.isArray(data.relationships)) {
          rels = data.relationships;
          renderRelationships();
          buildDiagram();
        }
      }
    } catch (err) {
      console.error(err);
    } finally {
      const titleEl2 = document.getElementById('resultsTitle');
      const headerSpinner2 = document.getElementById('resultsSpinner');
      if (titleEl2) titleEl2.textContent = 'Generated Results';
      headerSpinner2?.classList.add('d-none');
      document.getElementById('modeling-tabs')?.classList.remove('d-none');
      document.getElementById('modeling-tabs-content')?.classList.remove('d-none');
    }
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    if (!fileInput.files || fileInput.files.length === 0) {
      fileName.classList.add('is-invalid');
      uploadError?.classList.remove('d-none');
      return;
    }
    fileName.classList.remove('is-invalid');
    analyzeFile(fileInput.files[0]);
  });

  useDemoBtn?.addEventListener('click', async function () {
    try {
      const res = await fetch('/demo-data/procurement_demo.xlsx');
      const blob = await res.blob();
      const file = new File([blob], 'procurement_demo.xlsx', { type: blob.type });
      fileName.value = file.name;
      await analyzeFile(file);
    } catch (e) {
      console.error('Failed to load bundled demo data', e);
    }
  });

  // Sample schema shown before any upload
  const SAMPLE_SCHEMA = {
    'Vendor Master': [
      { name: 'VendorID', type: 'STRING', nullable: false, desc: 'Primary key' },
      { name: 'VendorName', type: 'STRING', nullable: false, desc: 'Supplier name' },
      { name: 'Country', type: 'STRING', nullable: false, desc: "Vendor's registered country" },
      { name: 'Category', type: 'STRING', nullable: false, desc: 'Primary item category supplied' },
    ],
    'PO Master': [
      { name: 'PONumber', type: 'STRING', nullable: false, desc: 'Primary key' },
      { name: 'VendorID', type: 'STRING', nullable: false, desc: 'FK to Vendor Master' },
      { name: 'HSCode', type: 'STRING', nullable: false, desc: 'Tariff classification code' },
      { name: 'CountryOfOrigin', type: 'STRING', nullable: true, desc: 'Country goods were manufactured in' },
      { name: 'POValue', type: 'DECIMAL', nullable: false, desc: 'Purchase order value (USD)' },
    ],
    'HS Code Tariff Rates': [
      { name: 'HSCode', type: 'STRING', nullable: false, desc: 'Tariff classification code' },
      { name: 'CountryOfOrigin', type: 'STRING', nullable: false, desc: 'Origin side of the trade lane' },
      { name: 'DutyRatePct', type: 'DECIMAL', nullable: false, desc: 'Current duty rate percentage' },
      { name: 'FTAEligible', type: 'BOOLEAN', nullable: false, desc: 'Eligible for a free trade agreement' },
    ],
    'Spend Invoice Detail': [
      { name: 'InvoiceID', type: 'STRING', nullable: false, desc: 'Primary key' },
      { name: 'PONumber', type: 'STRING', nullable: false, desc: 'FK to PO Master' },
      { name: 'HSCode', type: 'STRING', nullable: false, desc: 'Tariff classification code' },
      { name: 'DutyPaid', type: 'DECIMAL', nullable: false, desc: 'Actual duty paid (USD)' },
    ],
  };
  let CURRENT_SCHEMA = SAMPLE_SCHEMA;
  const SAMPLE_RELATIONSHIPS = [
    { fromTable: 'Vendor Master', fromColumn: 'VendorID', toTable: 'PO Master', toColumn: 'VendorID', card: 'One -> Many' },
    { fromTable: 'PO Master', fromColumn: 'PONumber', toTable: 'Spend Invoice Detail', toColumn: 'PONumber', card: 'One -> Many' },
    { fromTable: 'HS Code Tariff Rates', fromColumn: 'HSCode', toTable: 'PO Master', toColumn: 'HSCode', card: 'One -> Many' },
  ];

  // Schema Overview logic
  const tablesList = document.getElementById('tables-list');
  const tableCount = document.getElementById('table-count');
  const tableTitle = document.getElementById('table-title');
  const colCount = document.getElementById('col-count');
  const columnsTable = document.getElementById('columns-table');

  function renderTables() {
    const names = Object.keys(CURRENT_SCHEMA);
    tableCount.textContent = names.length;
    tablesList.innerHTML = '';
    names.forEach((t, idx) => {
      const a = document.createElement('button');
      a.className = 'list-group-item list-group-item-action d-flex justify-content-between align-items-center' + (idx === 0 ? ' active' : '');
      a.type = 'button';
      a.dataset.table = t;
      a.innerHTML = `<span>${t}</span><span class="badge text-bg-light">${CURRENT_SCHEMA[t].length}</span>`;
      a.addEventListener('click', (e) => selectTable(e.currentTarget.dataset.table, e.currentTarget));
      tablesList.appendChild(a);
    });
    if (names.length) selectTable(names[0], tablesList.firstChild);
  }

  function selectTable(name, btnEl) {
    Array.from(tablesList.children).forEach(el => el.classList.remove('active'));
    if (btnEl) btnEl.classList.add('active');
    tableTitle.textContent = name;
    const cols = CURRENT_SCHEMA[name] || [];
    colCount.textContent = `${cols.length} cols`;
    columnsTable.innerHTML = cols.map(c => `
      <tr>
        <td><span class="badge bg-light text-dark">${c.name}</span></td>
        <td>${c.type}</td>
        <td>${c.nullable ? 'Yes' : 'No'}</td>
        <td class="text-muted">${c.desc || ''}</td>
      </tr>
    `).join('');
  }

  // Relationships logic
  const relationshipsTable = document.getElementById('relationships-table');
  let rels = [...SAMPLE_RELATIONSHIPS];

  function renderRelationships() {
    relationshipsTable.innerHTML = rels.map(r => `
      <tr>
        <td>${r.fromTable}</td>
        <td>${r.fromColumn}</td>
        <td>${r.toTable}</td>
        <td>${r.toColumn}</td>
        <td>${r.card}</td>
      </tr>
    `).join('');
  }

  // ER Diagram (GoJS)
  let diagram;
  const resetLayoutBtn = document.getElementById('reset-layout-btn');
  function initDiagram() {
    const $ = go.GraphObject.make;
    diagram = $(go.Diagram, 'er-diagram', {
      initialContentAlignment: go.Spot.Center,
      layout: $(go.ForceDirectedLayout, { defaultSpringLength: 80, defaultElectricalCharge: 100 }),
      'undoManager.isEnabled': false,
    });
    diagram.nodeTemplate = $(go.Node, 'Auto',
      $(go.Shape, 'RoundedRectangle', { fill: '#f8f9fa', stroke: '#adb5bd' }),
      $(go.Panel, 'Table', { margin: 6 },
        $(go.TextBlock, { row: 0, font: 'bold 12pt Segoe UI', margin: new go.Margin(2, 2, 6, 2) }, new go.Binding('text', 'key')),
        $(go.Panel, 'Table', { row: 1 }, new go.Binding('itemArray', 'cols'),
          { itemTemplate: $(go.Panel, 'TableRow',
            $(go.TextBlock, { column: 0, margin: new go.Margin(1, 2), font: '10pt Segoe UI' }, new go.Binding('text', 'name')),
            $(go.TextBlock, { column: 1, margin: new go.Margin(1, 2), font: '10pt Segoe UI', stroke: '#6c757d' }, new go.Binding('text', 'type')),
            $(go.TextBlock, { column: 2, margin: new go.Margin(1, 2), font: '10pt Segoe UI' }, new go.Binding('text', 'suffix'))
          ) }
        )
      )
    );
    diagram.linkTemplate = $(go.Link,
      { routing: go.Link.AvoidsNodes, corner: 8 },
      $(go.Shape, { stroke: '#6c757d', strokeWidth: 2 }),
      $(go.Shape, { toArrow: 'Standard', stroke: '#6c757d', fill: '#6c757d' }),
      $(go.Panel, 'Auto',
        $(go.Shape, { fill: 'white', stroke: '#6c757d', strokeWidth: 1, parameter1: 8 }),
        $(go.TextBlock, { margin: new go.Margin(2, 6), font: '10pt Segoe UI' }, new go.Binding('text', 'label'))
      )
    );
    buildDiagram();
  }

  function buildDiagram() {
    if (!diagram) return;
    const pkMap = new Map();
    const fkMap = new Map();
    (rels || []).forEach(r => {
      const fset = fkMap.get(r.fromTable) || new Set(); fset.add(r.fromColumn); fkMap.set(r.fromTable, fset);
      const tset = pkMap.get(r.toTable) || new Set(); tset.add(r.toColumn); pkMap.set(r.toTable, tset);
    });
    const nodes = Object.entries(CURRENT_SCHEMA).map(([name, cols]) => ({
      key: name,
      cols: (cols || []).map(c => {
        const isPK = pkMap.get(name)?.has(c.name);
        const isFK = fkMap.get(name)?.has(c.name);
        const suffix = isPK ? '(PK)' : (isFK ? '(FK)' : '');
        return { name: c.name, type: c.type ? String(c.type) : '', suffix };
      }),
    }));
    const links = (rels || []).map(r => ({ from: r.fromTable, to: r.toTable, label: `${r.card}: ${r.fromColumn} -> ${r.toColumn}` }));
    diagram.model = new go.GraphLinksModel(nodes, links);
  }

  document.getElementById('er-tab-btn')?.addEventListener('shown.bs.tab', () => { diagram?.requestUpdate?.(); });
  resetLayoutBtn?.addEventListener('click', () => { if (diagram) diagram.layoutDiagram(true); });

  renderTables();
  renderRelationships();
  initDiagram();
})();
