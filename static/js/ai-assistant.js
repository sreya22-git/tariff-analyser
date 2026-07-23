// AI Assistant chat panel (Analysis Details page)
(function () {
    function activeFile() {
        try { return localStorage.getItem('tariff_active_file') || null; } catch (_) { return null; }
    }

    function escapeHtml(s) {
        return (s || '').toString()
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
    }

    function addBubble(chat, who, text) {
        var empty = chat.querySelector('.aiask-empty');
        if (empty) empty.remove();
        var bubble = document.createElement('div');
        bubble.className = 'aiask-bubble ' + (who === 'user' ? 'user' : 'assistant');
        bubble.innerHTML = escapeHtml(text).replace(/\n/g, '<br>');
        chat.appendChild(bubble);
        chat.scrollTop = chat.scrollHeight;
        return bubble;
    }

    async function ask(question) {
        const res = await fetch('/api/ask', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question: question, file: activeFile() }),
        });
        if (!res.ok) throw new Error('ask failed');
        const data = await res.json();
        return data.answer || "I don't have an answer for that.";
    }

    function init() {
        const chat = document.getElementById('aiaskChat');
        const input = document.getElementById('aiaskInput');
        const send = document.getElementById('aiaskSend');
        const chips = document.getElementById('aiaskChips');
        if (!chat || !input || !send) return;

        let busy = false;
        async function handleSend(questionOverride) {
            const question = (questionOverride != null ? questionOverride : input.value).trim();
            if (!question || busy) return;
            busy = true;
            addBubble(chat, 'user', question);
            input.value = '';
            const thinking = addBubble(chat, 'assistant', 'Thinking...');
            try {
                const answer = await ask(question);
                thinking.innerHTML = escapeHtml(answer).replace(/\n/g, '<br>');
            } catch (e) {
                thinking.innerHTML = 'Sorry, I could not reach the analysis service just now.';
                console.warn('AI assistant ask failed', e);
            } finally {
                busy = false;
                chat.scrollTop = chat.scrollHeight;
            }
        }

        send.addEventListener('click', () => handleSend());
        input.addEventListener('keydown', function (e) { if (e.key === 'Enter') handleSend(); });
        chips?.querySelectorAll('.aiask-chip').forEach(function (chip) {
            chip.addEventListener('click', function () { handleSend(chip.textContent); });
        });
    }

    if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', init); } else { init(); }
})();
