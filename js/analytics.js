(() => {
    const CLICK_ENDPOINT = '/api/stats/click';
    const CLICK_SELECTOR = 'a, button, [role="button"], [onclick], .job-card, .company-card, .radar-job-main';

    function getToken() {
        return localStorage.getItem('token') || localStorage.getItem('jd_token') || '';
    }

    function cleanText(value, max = 180) {
        return String(value || '').replace(/\s+/g, ' ').trim().slice(0, max);
    }

    function trackClick(event) {
        const target = event.target.closest(CLICK_SELECTOR);
        if (!target) return;

        const payload = {
            page_path: `${window.location.pathname}${window.location.search}${window.location.hash}`,
            target_text: cleanText(target.innerText || target.getAttribute('aria-label') || target.title),
            target_href: target.href || target.getAttribute('href') || '',
            target_id: target.id || '',
            target_class: cleanText(target.className, 240)
        };

        const headers = { 'Content-Type': 'application/json' };
        const token = getToken();
        if (token) headers.Authorization = `Bearer ${token}`;

        fetch(CLICK_ENDPOINT, {
            method: 'POST',
            headers,
            body: JSON.stringify(payload),
            keepalive: true
        }).catch(() => {});
    }

    document.addEventListener('click', trackClick, { capture: true });
})();
