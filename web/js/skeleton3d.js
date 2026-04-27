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
        const directional = new THREE.DirectionalLight(0xffffff, 0.9);
        directional.position.set(2, 4, 3);
        this.scene.add(directional);
        const hemisphere = new THREE.HemisphereLight(0x9fb8d8, 0x101827, 0.35);
        this.scene.add(hemisphere);

        // Shared geometry for performance
        this.boneGeometry = new THREE.CylinderGeometry(1.0, 1.0, 1.0, 10, 1, true);
        this.jointGeometry = new THREE.SphereGeometry(1.0, 16, 16);
        this.trackerGeometry = new THREE.SphereGeometry(1.0, 16, 16);

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

    _createBoneMesh(a, b, color) {
        const dir = new THREE.Vector3().subVectors(b, a);
        const length = dir.length();
        if (length < 0.01) return null;

        const mesh = new THREE.Mesh(this.boneGeometry, new THREE.MeshStandardMaterial({
            color,
            metalness: 0.15,
            roughness: 0.45,
            emissive: color,
            emissiveIntensity: 0.06,
        }));
        mesh.scale.set(0.018, length, 0.018);
        mesh.position.copy(a).addScaledVector(dir, 0.5);
        mesh.quaternion.setFromUnitVectors(
            new THREE.Vector3(0, 1, 0),
            dir.clone().normalize()
        );
        return mesh;
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

            // Draw bones as solid segments
            for (const [a, b] of BONE_CONNECTIONS) {
                const la = lms[a], lb = lms[b];
                if (la.vis < 0.3 || lb.vis < 0.3) continue;
                const p1 = new THREE.Vector3(la.x, -la.y, -la.z);
                const p2 = new THREE.Vector3(lb.x, -lb.y, -lb.z);
                const bone = this._createBoneMesh(p1, p2, color);
                if (bone) group.add(bone);
            }

            // Draw joint spheres
            const jointMat = new THREE.MeshStandardMaterial({
                color: 0xffffff,
                emissive: color,
                emissiveIntensity: 0.2,
                metalness: 0.1,
                roughness: 0.3,
            });
            for (let i = 0; i < lms.length; i++) {
                const lm = lms[i];
                if (lm.vis < 0.3) continue;
                const sphere = new THREE.Mesh(this.jointGeometry, jointMat);
                sphere.scale.setScalar(0.018);
                sphere.position.set(lm.x, -lm.y, -lm.z);
                group.add(sphere);
            }

            // Draw tracker spheres (larger, glowing)
            if (person.trackers) {
                const trackerMat = new THREE.MeshStandardMaterial({
                    color: 0x22c55e,
                    emissive: 0x22c55e,
                    emissiveIntensity: 0.55,
                    transparent: true,
                    opacity: 0.85,
                    metalness: 0.2,
                    roughness: 0.25,
                });
                for (const [name, data] of Object.entries(person.trackers)) {
                    const pos = data.pos;
                    const sphere = new THREE.Mesh(this.trackerGeometry, trackerMat);
                    sphere.scale.setScalar(0.03);
                    sphere.position.set(pos[0], pos[1], pos[2]);
                    group.add(sphere);
                }
            }
        }
    }
}

// Export
window.SkeletonRenderer = SkeletonRenderer;
