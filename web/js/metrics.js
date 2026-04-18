/**
 * metrics.js — Performance metrics and tracker status panel updates.
 */

class MetricsPanel {
    constructor() {
        this.fpsEl = document.getElementById('fps-value');
        this.fpsBar = document.getElementById('fps-bar');
        this.latencyEl = document.getElementById('latency-value');
        this.latencyBar = document.getElementById('latency-bar');
        this.personsBadge = document.getElementById('persons-badge');
        this.trackerItems = document.querySelectorAll('.tracker-item');
        this.calibDot = document.querySelector('.calib-dot');
        this.calibText = document.getElementById('calib-text');
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
}

window.MetricsPanel = MetricsPanel;
