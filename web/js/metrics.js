/**
 * metrics.js — Performance metrics and tracker status panel updates.
 */

class MetricsPanel {
    constructor() {
        this.fpsEl        = document.getElementById('fps-value');
        this.fpsBar       = document.getElementById('fps-bar');
        this.latencyEl    = document.getElementById('latency-value');
        this.latencyBar   = document.getElementById('latency-bar');
        this.personsBadge = document.getElementById('persons-badge');
        this.trackerItems = document.querySelectorAll('.tracker-item');
        this.calibDot     = document.querySelector('.calib-dot');
        this.calibText    = document.getElementById('calib-text');
        this.sensorList   = document.getElementById('sensor-list');
        this.sensorEmpty  = document.getElementById('sensor-empty');
        this.imuCountBadge = document.getElementById('imu-count-badge');
        this.modeBadge    = document.getElementById('mode-badge');

        // Sensor ID → human label
        this._sensorNames = {
            0: 'Hip', 1: 'Chest',
            2: 'L-Thigh', 3: 'R-Thigh',
            4: 'L-Ankle', 5: 'R-Ankle',
            6: 'L-Wrist',  7: 'R-Wrist',
        };
    }

    updateFPS(fps) {
        this.fpsEl.textContent = Math.round(fps);
        const pct = Math.min(100, (fps / 30) * 100);
        this.fpsBar.style.width = pct + '%';
        // Color based on performance
        if (fps >= 25) {
            this.fpsEl.style.color = '#06b6d4';
            this.fpsBar.style.background = '#06b6d4';
        } else if (fps >= 15) {
            this.fpsEl.style.color = '#eab308';
            this.fpsBar.style.background = '#eab308';
        } else {
            this.fpsEl.style.color = '#ef4444';
            this.fpsBar.style.background = '#ef4444';
        }
    }

    updateLatency(ms) {
        this.latencyEl.textContent = ms.toFixed(1);
        const pct = Math.min(100, (ms / 50) * 100);
        this.latencyBar.style.width = pct + '%';
        if (ms <= 20) {
            this.latencyEl.style.color = '#22c55e';
            this.latencyBar.style.background = '#22c55e';
        } else if (ms <= 35) {
            this.latencyEl.style.color = '#eab308';
            this.latencyBar.style.background = '#eab308';
        } else {
            this.latencyEl.style.color = '#ef4444';
            this.latencyBar.style.background = '#ef4444';
        }
    }

    updatePersons(count) {
        this.personsBadge.textContent = count + (count === 1 ? ' person' : ' persons');
    }

    updateTrackers(trackers) {
        // trackers is dict like { hip: {...}, left_foot: {...}, ... }
        const activeNames = trackers ? Object.keys(trackers) : [];
        this.trackerItems.forEach(item => {
            const name = item.dataset.tracker;
            if (activeNames.includes(name)) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });
    }

    updateCalibration(calibrated) {
        if (calibrated) {
            this.calibDot.classList.remove('uncalibrated');
            this.calibDot.classList.add('calibrated');
            this.calibText.textContent = 'Calibrated ✓';
        } else {
            this.calibDot.classList.remove('calibrated');
            this.calibDot.classList.add('uncalibrated');
            this.calibText.textContent = 'Not calibrated';
        }
    }

    updateIMUSensors(sensors, imuActive) {
        if (!this.sensorList) return;
        const connected = (sensors || []).filter(s => s.connected);
        const total = (sensors || []).length;

        // Update count badge
        if (this.imuCountBadge) {
            this.imuCountBadge.textContent = `${connected.length} / ${total}`;
            this.imuCountBadge.style.color = connected.length > 0 ? '#22c55e' : '#6b7280';
        }

        // Show empty state if no sensors at all
        if (!sensors || sensors.length === 0) {
            if (this.sensorEmpty) this.sensorEmpty.style.display = 'flex';
            // Remove any old sensor cards
            this.sensorList.querySelectorAll('.sensor-card').forEach(el => el.remove());
            return;
        }
        if (this.sensorEmpty) this.sensorEmpty.style.display = 'none';

        // Build / update a card per sensor
        sensors.forEach(sensor => {
            const cardId = `sensor-card-${sensor.id}`;
            let card = document.getElementById(cardId);
            if (!card) {
                card = document.createElement('div');
                card.id = cardId;
                card.className = 'sensor-card';
                this.sensorList.appendChild(card);
            }

            const name  = this._sensorNames[sensor.id] || `Sensor ${sensor.id}`;
            const ok    = sensor.signal_ok;
            const lat   = sensor.latency_ms > 999 ? '---' : sensor.latency_ms.toFixed(0);
            const pkts  = sensor.packets > 999 ? (sensor.packets / 1000).toFixed(1) + 'k' : sensor.packets;

            card.innerHTML = `
                <span class="sensor-dot ${ok ? 'sensor-ok' : 'sensor-lost'}"></span>
                <span class="sensor-name">${name}</span>
                <span class="sensor-id">ID:${sensor.id}</span>
                <span class="sensor-lat">${lat} ms</span>
                <span class="sensor-pkts">${pkts} pkts</span>
            `;
            card.classList.toggle('sensor-connected', ok);
            card.classList.toggle('sensor-disconnected', !ok);
        });

        // Remove stale cards for sensors no longer in list
        const ids = new Set((sensors || []).map(s => `sensor-card-${s.id}`));
        this.sensorList.querySelectorAll('.sensor-card').forEach(el => {
            if (!ids.has(el.id)) el.remove();
        });
    }

    updateMode(imuActive, sourceMode) {
        if (!this.modeBadge) return;
        if (imuActive) {
            this.modeBadge.textContent = 'Hybrid ★';
            this.modeBadge.style.background = 'rgba(139,92,246,0.25)';
            this.modeBadge.style.color = '#a78bfa';
            this.modeBadge.style.borderColor = '#7c3aed';
        } else {
            this.modeBadge.textContent = 'Camera Only';
            this.modeBadge.style.background = '';
            this.modeBadge.style.color = '';
            this.modeBadge.style.borderColor = '';
        }
    }
}

window.MetricsPanel = MetricsPanel;
