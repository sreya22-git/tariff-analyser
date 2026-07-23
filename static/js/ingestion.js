// Upload interactions: save the workbook and mark it active for the Sourcing Data map and AI Assistant.
(function () {
  const fileInput = document.getElementById('fileInput');
  const fileName = document.getElementById('fileName');
  const browseBtn = document.getElementById('browseBtn');
  const form = document.getElementById('uploadForm');
  const uploadError = document.getElementById('uploadError');
  const useDemoBtn = document.getElementById('useDemoBtn');
  const uploadStatus = document.getElementById('uploadStatus');

  browseBtn.addEventListener('click', function () { fileInput.click(); });
  fileInput.addEventListener('change', function () {
    fileName.value = (this.files && this.files.length > 0) ? this.files[0].name : 'No file chosen';
    fileName.classList.remove('is-invalid');
    uploadError?.classList.add('d-none');
  });

  function showStatus(message, ok) {
    if (!uploadStatus) return;
    uploadStatus.textContent = message;
    uploadStatus.className = 'mt-3 text-center ' + (ok ? 'text-success' : 'text-danger');
  }

  async function analyzeFile(file, opts) {
    opts = opts || {};
    showStatus('Uploading and saving ' + file.name + '...', true);
    try {
      const fd = new FormData();
      fd.append('file', file, file.name);
      const res = await fetch('/api/upload/analyze', { method: 'POST', body: fd });
      if (!res.ok) throw new Error('Upload request failed');
      try { localStorage.setItem('tariff_active_file', file.name); } catch (_) {}
      if (opts.redirect) {
        showStatus(file.name + ' is loaded. Opening Sourcing Data...', true);
        window.location.href = '/dashboard';
        return;
      }
      showStatus(file.name + ' is loaded. Head to Sourcing Data or AI Assistant to explore it.', true);
    } catch (err) {
      console.error(err);
      showStatus('Could not upload ' + file.name + '. Please try again.', false);
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
      await analyzeFile(file, { redirect: true });
    } catch (e) {
      console.error('Failed to load bundled demo data', e);
      showStatus('Could not load the bundled sample data.', false);
    }
  });
})();
