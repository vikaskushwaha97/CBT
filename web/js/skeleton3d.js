/**
 * skeleton3d.js — Three.js 3D skeleton renderer.
 *
 * Renders multi-person skeletons with color-coded bones,
 * tracker spheres, and a reference grid floor.
 */

const PERSON_COLORS = [
    0x06b6d4,  // Cyan
    0xd946ef,  // Magenta
    0x22c55e,  // Green
    0xf97316,  // Orange
    0xeab308,  // Yellow
];

const BONE_CONNECTIONS = [
    [11, 12], [11, 13], [13, 15], [12, 14], [14, 16],  // shoulders, arms
    [11, 23], [12, 24], [23, 24],                        // torso
    [23, 25], [25, 27], [24, 26], [26, 28],              // legs
    [0, 7], [0, 8],                                       // head
];

const TRACKER_LANDMARKS = {
    hip: [23, 24],
    chest: [11, 12],
    left_foot: [27],
    right_foot: [28],
    left_knee: [25],
    right_knee: [26],
    left_elbow: [13],
    right_elbow: [14],
    head: [0],
};

class SkeletonRenderer {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.scene = new THREE.Scene();
        this.personGroups = {};  // person_id → THREE.Group

        // Camera
        this.camera = new THREE.PerspectiveCamera(50, 1, 0.1, 100);
        this.camera.position.set(0, 1.0, 3.0);
        this.camera.lookAt(0, 0.8, 0);

        // Renderer
        this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        this.renderer.setPixelRatio(window.devicePixelRatio);
        this.renderer.setClearColor(0x0a0e17, 1);
        this.container.appendChild(this.renderer.domElement);

        // Lighting
        const ambient = new THREE.AmbientLight(0x404060, 0.6);
        this.scene.add(ambient);
        const directional = new THREE.DirectionalLight(0xffffff, 0.8);
        directional.position.set(2, 4, 3);
        this.scene.add(directional);

        // Grid floor
        this._addGrid();

        // Mouse orbit
        this._setupOrbit();

        // Resize
        this._resize();
        window.addEventListener('resize', () => this._resize());

        // Animation loop
        this._animate();
    }

    _addGrid() {
        const grid = new THREE.GridHelper(4, 20, 0x1a2332, 0x111827);
        this.scene.add(grid);

        // Center axis lines
        const axisGeom = new THREE.BufferGeometry();
        const axisVerts = new Float32Array([
            -2, 0, 0,  2, 0, 0,  // X
            0, 0, -2,  0, 0, 2,  // Z
        ]);
        axisGeom.setAttribute('position', new THREE.BufferAttribute(axisVerts, 3));
        const axisMat = new THREE.LineBasicMaterial({ color: 0x2a3a4a });
        const axisLines = new THREE.LineSegments(axisGeom, axisMat);
        this.scene.add(axisLines);
    }

    _setupOrbit() {
        this._isDragging = false;
        this._prevMouse = { x: 0, y: 0 };
        this._spherical = { theta: 0, phi: Math.PI / 6, radius: 3.0 };

        const el = this.renderer.domElement;

        el.addEventListener('mousedown', (e) => {
            this._isDragging = true;
            this._prevMouse = { x: e.clientX, y: e.clientY };
        });

        el.addEventListener('mousemove', (e) => {
            if (!this._isDragging) return;
            const dx = e.clientX - this._prevMouse.x;
            const dy = e.clientY - this._prevMouse.y;
            this._spherical.theta -= dx * 0.01;
            this._spherical.phi = Math.max(0.1, Math.min(Math.PI - 0.1,
                this._spherical.phi + dy * 0.01));
            this._prevMouse = { x: e.clientX, y: e.clientY };
            this._updateCameraFromSpherical();
        });

        el.addEventListener('mouseup', () => { this._isDragging = false; });
        el.addEventListener('mouseleave', () => { this._isDragging = false; });

        el.addEventListener('wheel', (e) => {
            this._spherical.radius = Math.max(1, Math.min(8,
                this._spherical.radius + e.deltaY * 0.005));
            this._updateCameraFromSpherical();
        });
    }

    _updateCameraFromSpherical() {
        const { theta, phi, radius } = this._spherical;
        this.camera.position.set(
            radius * Math.sin(phi) * Math.sin(theta),
            radius * Math.cos(phi),
            radius * Math.sin(phi) * Math.cos(theta)
        );
        this.camera.lookAt(0, 0.8, 0);
    }

    setView(view) {
        switch (view) {
            case 'front':
                this._spherical = { theta: 0, phi: Math.PI / 6, radius: 3.0 };
                break;
            case 'side':
                this._spherical = { theta: Math.PI / 2, phi: Math.PI / 6, radius: 3.0 };
                break;
            case 'top':
                this._spherical = { theta: 0, phi: 0.15, radius: 4.0 };
                break;
        }
        this._updateCameraFromSpherical();
    }

    _resize() {
        const w = this.container.clientWidth;
        const h = this.container.clientHeight;
        if (w === 0 || h === 0) return;
        this.camera.aspect = w / h;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(w, h);
    }

    _animate() {
        requestAnimationFrame(() => this._animate());
        this.renderer.render(this.scene, this.camera);
    }

    update(persons) {
        // Remove stale person groups
        const activeIds = new Set(persons.map(p => p.id));
        for (const id of Object.keys(this.personGroups)) {
            if (!activeIds.has(parseInt(id))) {
                this.scene.remove(this.personGroups[id]);
                delete this.personGroups[id];
            }
        }

        for (const person of persons) {
            let group = this.personGroups[person.id];
            if (!group) {
                group = new THREE.Group();
                this.scene.add(group);
                this.personGroups[person.id] = group;
            }

            // Clear existing geometry
            while (group.children.length > 0) {
                const child = group.children[0];
                group.remove(child);
                if (child.geometry) child.geometry.dispose();
                if (child.material) child.material.dispose();
            }

            const color = PERSON_COLORS[person.id % PERSON_COLORS.length];
            const lms = person.landmarks;
            if (!lms || lms.length < 33) continue;

            // Draw bones
            const boneMat = new THREE.LineBasicMaterial({ color: color, linewidth: 2 });
            for (const [a, b] of BONE_CONNECTIONS) {
                const la = lms[a], lb = lms[b];
                if (la.vis < 0.3 || lb.vis < 0.3) continue;

                const geom = new THREE.BufferGeometry();
                // Convert: x stays, y = -y (flip up), z = -z (left-handed)
                const verts = new Float32Array([
                    la.x, -la.y, -la.z,
                    lb.x, -lb.y, -lb.z,
                ]);
                geom.setAttribute('position', new THREE.BufferAttribute(verts, 3));
                group.add(new THREE.Line(geom, boneMat));
            }

            // Draw joint spheres
            const jointGeom = new THREE.SphereGeometry(0.012, 8, 8);
            const jointMat = new THREE.MeshPhongMaterial({
                color: color, emissive: color, emissiveIntensity: 0.3
            });
            for (let i = 0; i < lms.length; i++) {
                const lm = lms[i];
                if (lm.vis < 0.3) continue;
                const sphere = new THREE.Mesh(jointGeom, jointMat);
                sphere.position.set(lm.x, -lm.y, -lm.z);
                group.add(sphere);
            }

            // Draw tracker spheres (larger, glowing)
            if (person.trackers) {
                const trackerGeom = new THREE.SphereGeometry(0.025, 12, 12);
                const trackerMat = new THREE.MeshPhongMaterial({
                    color: 0x22c55e, emissive: 0x22c55e, emissiveIntensity: 0.5,
                    transparent: true, opacity: 0.8,
                });
                for (const [name, data] of Object.entries(person.trackers)) {
                    const pos = data.pos;
                    const sphere = new THREE.Mesh(trackerGeom, trackerMat);
                    sphere.position.set(pos[0], pos[1], pos[2]);
                    group.add(sphere);
                }
            }
        }
    }
}

// Export
window.SkeletonRenderer = SkeletonRenderer;
