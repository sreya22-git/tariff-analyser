// Guided tour engine, a generic port of demo (1).html's step-tooltip walkthrough.
// Each page defines window.TOUR_STEPS = [{sel, title, body, pos, on}, ...] before this script loads.
(function () {
    function $(sel) { return document.querySelector(sel); }
    function $$(sel) { return Array.from(document.querySelectorAll(sel)); }

    let steps = [];
    let ti = 0;

    function place(el) {
        const r = el.getBoundingClientRect();
        const card = $('#tCard');
        card.style.display = 'block';
        const ch = card.offsetHeight, cw = card.offsetWidth;
        const s = steps[ti];
        let top = r.bottom + 12, left = r.left;
        if (s.pos === 'right') { left = r.right + 14; top = Math.max(12, r.top); }
        if (s.pos === 'left') { left = r.left - cw - 14; top = Math.max(12, r.top); }
        if (s.pos === 'below') { top = r.bottom + 12; left = r.left; }
        if (left + cw > innerWidth - 8) left = innerWidth - cw - 8;
        if (left < 8) left = 8;
        if (top + ch > innerHeight - 8) top = Math.max(8, innerHeight - ch - 8);
        card.style.top = top + 'px';
        card.style.left = left + 'px';
    }

    function showStep() {
        $$('.t-hi').forEach(e => e.classList.remove('t-hi'));
        const s = steps[ti];
        if (s.on) { try { s.on(); } catch (_) {} }
        setTimeout(() => {
            const el = $(s.sel) || document.body;
            el.classList.add('t-hi');
            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            $('#tStep').textContent = 'Step ' + (ti + 1) + ' of ' + steps.length;
            $('#tTitle').textContent = s.title;
            $('#tBody').textContent = s.body;
            $('#tDots').innerHTML = steps.map((_, i) => `<i class="${i === ti ? 'on' : ''}"></i>`).join('');
            $('#tBack2').style.visibility = ti ? 'visible' : 'hidden';
            $('#tNext').textContent = ti === steps.length - 1 ? 'Done' : 'Next';
            setTimeout(() => place(el), 260);
        }, 120);
    }

    function startTour(customSteps) {
        steps = customSteps || window.TOUR_STEPS || [];
        if (!steps.length) return;
        ti = 0;
        $('#tBack').style.display = 'block';
        $('#tCard').style.display = 'block';
        showStep();
    }

    function endTour() {
        $('#tBack').style.display = 'none';
        $('#tCard').style.display = 'none';
        $$('.t-hi').forEach(e => e.classList.remove('t-hi'));
    }

    function init() {
        const tourBtn = $('#tourBtn');
        const skip = $('#tSkip'), back = $('#tBack2'), next = $('#tNext'), backdrop = $('#tBack');
        if (!tourBtn || !skip || !back || !next) return;
        tourBtn.addEventListener('click', () => startTour());
        skip.addEventListener('click', endTour);
        backdrop?.addEventListener('click', endTour);
        back.addEventListener('click', () => { if (ti) { ti--; showStep(); } });
        next.addEventListener('click', () => { ti < steps.length - 1 ? (ti++, showStep()) : endTour(); });
        document.addEventListener('keydown', (e) => {
            if (e.key !== 'Escape') return;
            if (backdrop && backdrop.style.display === 'block') endTour();
        });
    }

    if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', init); } else { init(); }

    window.GuidedTour = { start: startTour, end: endTour };
})();
