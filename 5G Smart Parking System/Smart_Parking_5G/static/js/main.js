(() => {
    let currentFrameNum = 1;
    let pollInterval = null;

    const feed = document.getElementById('dashboard-feed');
    const summary = document.getElementById('summary');
    const paths = document.getElementById('paths');
    const frameIndicator = document.getElementById('frame-indicator');

    // UI Elements
    const modeText = document.getElementById('ui-mode-text');
    const toggleBtn = document.getElementById('btn-toggle-mode');
    const staticControls = document.getElementById('static-controls');
    const liveControls = document.getElementById('live-controls');

    // --- CORE FUNCTIONS ---
    function stopPolling() {
        if (pollInterval) {
            clearInterval(pollInterval);
            pollInterval = null;
        }
    }

    function startPolling() {
        stopPolling();
        // Loop every 1.5 seconds to grab the newest camera frame
        pollInterval = setInterval(() => {
            if (feed) feed.src = `/process_image?img=latest.jpg&t=${Date.now()}`;
        }, 1500);
        // Force the first load immediately
        if (feed) feed.src = `/process_image?img=latest.jpg&t=${Date.now()}`;
    }

    async function refreshSummary() {
        if (!summary) return;
        try {
            const res = await fetch('/api/slot_summary');
            const data = await res.json();
            summary.innerText = `Status: ${data.status} | Free: ${data.free_slots} | Occupied: ${data.occupied_slots} | Unknown: ${data.unknown_slots} | FPS: ${data.fps}`;
        } catch (_e) {
            summary.innerText = 'Status API unavailable';
        }
    }

    async function refreshPaths() {
        if (!paths) return;
        try {
            const res = await fetch('/api/path_details');
            const data = await res.json();
            if (!data.paths || data.paths.length === 0) {
                paths.innerText = 'No active routed vehicles.';
                return;
            }
            const lines = data.paths.map((p) => {
                const steps = (p.instructions || []).join(' -> ');
                return `Track ${p.track_id} | Target: ${p.target} | Route: ${steps}`;
            });
            paths.innerText = lines.join('\n');
        } catch (_e) {
            paths.innerText = 'Path details API unavailable';
        }
    }

    // --- EVENT LISTENERS ---

    // 1. Mode Toggle
    if (toggleBtn) {
        toggleBtn.addEventListener('click', async () => {
            const targetMode = IS_LIVE_MODE ? 'static' : 'live';
            await fetch('/api/switch_mode', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({mode: targetMode})
            });

            alert(`Switching to ${targetMode.toUpperCase()} Mode. Server is restarting...`);
            setTimeout(() => location.reload(), 3000);
        });
    }

    // 2. Frame Navigation (Static Mode)
    const btnPrev = document.getElementById('btn-prev');
    const btnNext = document.getElementById('btn-next');

    if (btnPrev && btnNext) {
        btnPrev.addEventListener('click', () => {
            if (IS_LIVE_MODE) return;
            if (currentFrameNum > 1) {
                currentFrameNum--;
                if (feed) feed.src = `/process_image?img=frame${currentFrameNum}.png&t=${Date.now()}`;
                if (frameIndicator) frameIndicator.innerText = `Frame ${currentFrameNum}`;
            }
        });

        btnNext.addEventListener('click', () => {
            if (IS_LIVE_MODE) return;
            currentFrameNum++;
            if (feed) feed.src = `/process_image?img=frame${currentFrameNum}.png&t=${Date.now()}`;
            if (frameIndicator) frameIndicator.innerText = `Frame ${currentFrameNum}`;
        });
    }

    // 3. Calibration
    const btnCapture = document.getElementById('btn-capture-base');
    const btnDraw = document.getElementById('btn-draw-roi');

    if (btnCapture) {
        btnCapture.addEventListener('click', async () => {
            try {
                const res = await fetch('/api/capture_baseline', { method: 'POST' });
                if (res.ok) alert("Live Baseline captured! You can now Calibrate.");
                else alert("Error capturing baseline.");
            } catch (e) {
                alert("Network error capturing baseline.");
            }
        });
    }

    if (btnDraw) {
        btnDraw.addEventListener('click', async () => {
            alert("Check your taskbar! The OpenCV Calibrator is opening.");
            await fetch('/api/launch_calibrator', { method: 'POST' });
        });
    }

    // --- INITIALIZATION ---
    refreshSummary();
    refreshPaths();
    setInterval(refreshSummary, 2000);
    setInterval(refreshPaths, 2000);

    // Apply Mode-Specific UI and Logic
    if (IS_LIVE_MODE) {
        if (modeText) {
            modeText.innerText = "LIVE POLLING";
            modeText.style.color = "#ff4757";
        }
        if (toggleBtn) toggleBtn.innerText = "🔄 Switch to STATIC Mode";
        if (staticControls) staticControls.style.display = "none";
        if (liveControls) liveControls.style.display = "block";

        startPolling();
    } else {
        // Static Mode defaults
        if (feed) feed.src = `/process_image?img=baseline.png&t=${Date.now()}`;
        if (frameIndicator) frameIndicator.innerText = "Baseline";
    }
})();