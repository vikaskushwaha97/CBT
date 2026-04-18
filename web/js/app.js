/**
 * app.js — Main application: WebSocket connection, event routing, UI bindings.
 */

(function () {
    'use strict';

    // ── Init components ─────────────────────────────────────────────────
    const skeleton3d = new SkeletonRenderer('skeleton-canvas-container');
    const metrics = new MetricsPanel();

    // ── DOM refs ─────────────────────────────────────────────────────────
    const cameraFeed = document.getElementById('camera-feed');
    const noCameraOverlay = document.getElementById('no-camera-overlay');
    const connectionDot = document.getElementById('connection-dot');
    const connectionText = document.getElementById('connection-text');
    const calibrateBtn = document.getElementById('calibrate-btn');
    const filterCutoff = document.getElementById('filter-cutoff');
    const filterBeta = document.getElementById('filter-beta');
    const cutoffVal = document.getElementById('cutoff-val');
    const betaVal = document.getElementById('beta-val');
    const oscToggle = document.getElementById('osc-toggle');
    const oscIp = document.getElementById('osc-ip');
    const oscPort = document.getElementById('osc-port');
    const oscStatusText = document.getElementById('osc-status-text');

    // ── View buttons ────────────────────────────────────────────────────
    document.querySelectorAll('.view-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.view-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            skeleton3d.setView(btn.dataset.view);
        });
    });

    // ── WebSocket ────────────────────────────────────────────────────────
    let ws = null;
    let reconnectTimer = null;

    function connect() {
        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${proto}//${location.host}/ws`;

        ws = new WebSocket(url);

        ws.onopen = () => {
            connectionDot.classList.add('connected');
            connectionText.textContent = 'Connected';
            if (reconnectTimer) {
                clearTimeout(reconnectTimer);
                reconnectTimer = null;
            }
        };

        ws.onclose = () => {
            connectionDot.classList.remove('connected');
            connectionText.textContent = 'Disconnected';
            noCameraOverlay.classList.remove('hidden');
            cameraFeed.classList.remove('active');
            // Auto-reconnect after 2s
            reconnectTimer = setTimeout(connect, 2000);
        };

        ws.onerror = () => {
            ws.close();
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleFrame(data);
            } catch (e) {
                // Ignore parse errors (e.g. event responses)
            }
        };
    }

    function handleFrame(data) {
        // ── Events (calibration result, OSC status) ─────────────────
        if (data.event) {
            if (data.event === 'calibration_result') {
                calibrateBtn.disabled = false;
                calibrateBtn.textContent = data.success ? '✓ Calibrated!' : '✗ Failed — try again';
                setTimeout(() => {
                    calibrateBtn.innerHTML = `
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
                        </svg>
                        Calibrate (T-Pose)`;
                }, 2000);
            }
            if (data.event === 'osc_status') {
                oscStatusText.textContent = data.active ? 'Active' : 'Disabled';
                oscStatusText.style.color = data.active ? '#22c55e' : '#9ca3af';
            }
            return;
        }

        // ── Frame data ──────────────────────────────────────────────
        // Camera frame
        if (data.frame) {
            cameraFeed.src = 'data:image/jpeg;base64,' + data.frame;
            cameraFeed.classList.add('active');
            noCameraOverlay.classList.add('hidden');
        }

        // 3D Skeleton
        if (data.persons) {
            skeleton3d.update(data.persons);
        }

        // Metrics
        metrics.updateFPS(data.fps || 0);
        metrics.updateLatency(data.latency_ms || 0);
        metrics.updatePersons(data.num_persons || 0);
        metrics.updateCalibration(data.calibrated || false);

        // Tracker status (from primary person)
        if (data.persons && data.persons.length > 0) {
            metrics.updateTrackers(data.persons[0].trackers);
        } else {
            metrics.updateTrackers(null);
        }
    }

    function sendCommand(cmd) {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify(cmd));
        }
    }

    // ── Calibrate button ────────────────────────────────────────────────
    calibrateBtn.addEventListener('click', () => {
        calibrateBtn.disabled = true;
        calibrateBtn.textContent = 'Hold T-Pose…';
        // Wait 3 seconds then capture
        setTimeout(() => {
            sendCommand({ action: 'calibrate' });
        }, 3000);
    });

    // ── Filter sliders ──────────────────────────────────────────────────
    filterCutoff.addEventListener('input', () => {
        cutoffVal.textContent = filterCutoff.value;
        sendCommand({ action: 'update_filter', min_cutoff: filterCutoff.value });
    });

    filterBeta.addEventListener('input', () => {
        betaVal.textContent = filterBeta.value;
        sendCommand({ action: 'update_filter', beta: filterBeta.value });
    });

    // ── OSC toggle ──────────────────────────────────────────────────────
    oscToggle.addEventListener('change', () => {
        sendCommand({
            action: 'toggle_osc',
            enabled: oscToggle.checked,
            ip: oscIp.value,
            port: parseInt(oscPort.value) || 9000,
        });
    });

    // ── Start ───────────────────────────────────────────────────────────
    connect();

})();
