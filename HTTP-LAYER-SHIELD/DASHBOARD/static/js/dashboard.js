async function poll() {
    try {
        const res = await fetch('/matrix');
        const data = await res.json();
        render(data);
    } catch(e) {
        console.error("Dashboard polling error", e);
    }
}

function render(d) {
    const s = d.summary;
    document.getElementById('s-total').textContent = s.total;
    document.getElementById('s-allowed').textContent = s.total - s.blocked;
    document.getElementById('s-blocked').textContent = s.blocked;
    document.getElementById('s-banned').textContent = s.banned;
    
    // Calculate captcha counts implicitly (assuming matrix drops this eventually, simplified here)
    
    renderTimeline(d.timeline);
    renderIPMatrix(d.ip_matrix);
    renderFeed(d.recent_requests || []);
}

function renderTimeline(tl) {
    const wrap = document.getElementById('timeline');
    if (!tl || !tl.length) return;
    const maxVal = Math.max(...tl.map(t => (t.allowed || 0) + (t.blocked || 0)), 1);
    wrap.innerHTML = tl.map(t => {
        const total = (t.allowed || 0) + (t.blocked || 0);
        const hTotal = Math.round((total / maxVal) * 76);
        const hBlocked = total > 0 ? Math.round((t.blocked / total) * hTotal) : 0;
        const hAllowed = hTotal - hBlocked;
        return `<div class="tl-bar-wrap">
            ${hBlocked > 0 ? `<div class="tl-bar blocked" style="height:${hBlocked}px"></div>` : ''}
            ${hAllowed > 0 ? `<div class="tl-bar allowed" style="height:${hAllowed}px"></div>` : ''}
            ${total === 0 ? `<div class="tl-bar" style="height:2px;background:var(--border)"></div>` : ''}
        </div>`;
    }).join('');
}

function renderIPMatrix(ips) {
    const tbody = document.getElementById('ip-matrix-body');
    if (!ips || !ips.length) return;
    tbody.innerHTML = ips.map(row => `
        <tr>
            <td style="color:var(--info)">${row.ip}</td>
            <td>${row.total}</td>
            <td style="color:${row.blocked > 0 ? 'var(--danger)' : 'var(--dim)'}">${row.blocked}</td>
            <td><span class="${row.threat.includes('critical') ? 'threat-critical' : row.threat.includes('high') ? 'threat-high' : 'threat-low'}">${row.threat}</span></td>
            <td>${row.banned ? '<span style="color:var(--danger)">🚫 BANNED</span>' : `<button class="ban-btn" onclick="banIP('${row.ip}')">Ban</button>`}</td>
        </tr>
    `).join('');
}

function renderFeed(reqs) {
    const feed = document.getElementById('live-feed');
    if (!reqs || !reqs.length) return;
    feed.innerHTML = reqs.slice().reverse().slice(0, 50).map(r => `
        <div class="feed-entry">
            <span style="color:var(--dim);flex:0 0 70px">${r.time ? r.time.slice(11,19) : ''}</span>
            <span style="color:var(--info);flex:0 0 100px">${r.ip}</span>
            <span style="flex:1">${r.path}</span>
            <span style="color:${r.ml_verdict === 'human' ? 'var(--accent)' : 'var(--danger)'}">ML: ${r.ml_verdict || 'N/A'}</span>
            <span style="color:${r.blocked ? 'var(--danger)' : 'var(--accent)'}; width: 80px; text-align:right;">${r.blocked ? 'BLOCKED' : 'ALLOW'}</span>
        </div>
    `).join('');
}

async function banIP(ip) {
    await fetch('/api/ban', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ip})
    });
    poll();
}

async function runClassifier() {
    const data = {
        click_count: Number(document.getElementById('f_click_count').value),
        avg_click_interval: Number(document.getElementById('f_avg_interval').value),
        click_interval_variance: Number(document.getElementById('f_interval_var').value),
        click_interval_entropy: Number(document.getElementById('f_entropy').value),
        mouse_velocity_variance: Number(document.getElementById('f_mouse_vel').value),
        max_element_click_rate: Number(document.getElementById('f_click_rate').value),
        scroll_events: Number(document.getElementById('f_scroll').value),
        keystroke_count: Number(document.getElementById('f_keystrokes').value)
    };
    const res = await fetch('/predict', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    });
    const result = await res.json();
    document.getElementById('manualVerdict').textContent = result.prediction.toUpperCase();
    document.getElementById('manualVerdict').style.color = result.prediction === 'bot' ? 'var(--danger)' : 'var(--accent)';
    document.getElementById('manualScore').textContent = result.anomaly_score;
}

async function simulateAttack(type) {
    alert(`Starting simulated ${type} attack! Watching matrix...`);
    await fetch('/api/attack', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({type})
    });
}

setInterval(poll, 2000);
poll();
