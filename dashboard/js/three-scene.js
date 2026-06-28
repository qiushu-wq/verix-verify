/* ═══════════════════════════════════════════════════════
   Verix Three.js Scene — 3D Wireframe Anchor Triangle
   "Grown from architecture, not painted"
   ═══════════════════════════════════════════════════════ */

import * as THREE from 'three';

// ── Color Constants ─────────────────────────────────────
const CYAN    = new THREE.Color('#00f0ff');
const EMERALD = new THREE.Color('#00ff88');
const PURPLE  = new THREE.Color('#b088ff');
const AMBER   = new THREE.Color('#ffaa00');
const GOLD    = new THREE.Color('#C0A060');
const DIM     = new THREE.Color('#445566');

// ── Shared State ────────────────────────────────────────
let scene, camera, renderer;
let anchorTriangle;
let edgeParticles = [];
let vertexGlows = [];
let ambientParticles;
let gridPlane;
let clock;
let animationId;

// Public state for external modules to trigger events
export const ThreeState = {
  t1Active: false,
  sageActive: false,
  t1Intensity: 0,    // 0..1, ramps up/down
  sageIntensity: 0,  // 0..1
};

// ── Scene Initialization ────────────────────────────────

/**
 * Initialize the Three.js 3D scene.
 * @param {string} canvasId - ID of the canvas element
 */
export function initThreeScene(canvasId) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) {
    console.error('[Verix 3D] Canvas not found:', canvasId);
    return;
  }

  // WebGL support check
  if (!testWebGL()) {
    document.body.classList.add('no-webgl');
    console.warn('[Verix 3D] WebGL not supported — falling back to CSS background');
    return;
  }

  // ── Renderer ──────────────────────────────────────────
  renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.2;

  // ── Scene ─────────────────────────────────────────────
  scene = new THREE.Scene();

  // ── Camera ────────────────────────────────────────────
  camera = new THREE.PerspectiveCamera(
    55,                                          // FOV
    window.innerWidth / window.innerHeight,       // Aspect
    0.1,                                         // Near
    100                                           // Far
  );
  camera.position.set(0, 0.5, 9);
  camera.lookAt(0, 0, 0);

  // ── Clock ─────────────────────────────────────────────
  clock = new THREE.Clock();

  // ── Build Scene Elements ──────────────────────────────
  buildGridPlane();
  buildAnchorTriangle();
  buildVertexGlows();
  buildAmbientParticles();
  buildEdgeParticles();

  // ── Resize Handler ────────────────────────────────────
  window.addEventListener('resize', onResize);

  // ── Start Render Loop ─────────────────────────────────
  animate();

  console.log('[Verix 3D] Scene initialized. Anchors: α cyan, β emerald, γ purple.');
}

// ── WebGL Check ─────────────────────────────────────────

function testWebGL() {
  try {
    const c = document.createElement('canvas');
    return !!(c.getContext('webgl2') || c.getContext('webgl'));
  } catch {
    return false;
  }
}

// ── Grid Plane ──────────────────────────────────────────

function buildGridPlane() {
  const size = 16;
  const divisions = 32;
  const geometry = new THREE.PlaneGeometry(size, size, divisions, divisions);
  const material = new THREE.MeshBasicMaterial({
    color: DIM,
    wireframe: true,
    transparent: true,
    opacity: 0.08,
    depthWrite: false,
  });
  gridPlane = new THREE.Mesh(geometry, material);
  gridPlane.rotation.x = -Math.PI / 2;
  gridPlane.position.y = -4.5;
  scene.add(gridPlane);
}

// ── Anchor Triangle ─────────────────────────────────────

function buildAnchorTriangle() {
  // Equilateral triangle vertices — three anchors
  const radius = 3.2;
  const vertices = [];
  for (let i = 0; i < 3; i++) {
    const angle = (i * Math.PI * 2) / 3 - Math.PI / 2; // Start from top
    vertices.push(new THREE.Vector3(
      Math.cos(angle) * radius,
      Math.sin(angle) * radius,
      0
    ));
  }

  // Wireframe edge geometry
  const edgePoints = [
    vertices[0], vertices[1],
    vertices[1], vertices[2],
    vertices[2], vertices[0],
  ];
  const edgeGeometry = new THREE.BufferGeometry().setFromPoints(edgePoints);
  const edgeMaterial = new THREE.LineBasicMaterial({
    color: CYAN,
    transparent: true,
    opacity: 0.25,
    linewidth: 1,
    depthWrite: false,
  });
  const edgeLines = new THREE.LineSegments(edgeGeometry, edgeMaterial);

  // Group to hold triangle + rotate
  anchorTriangle = new THREE.Group();
  anchorTriangle.add(edgeLines);

  // Store vertex positions for particle systems
  anchorTriangle.userData = { vertices, edgeLines, edgeMaterial };
  scene.add(anchorTriangle);
}

// ── Vertex Glow Spheres ─────────────────────────────────

function buildVertexGlows() {
  if (!anchorTriangle) return;

  const colors = [CYAN, EMERALD, PURPLE]; // α, β, γ
  const vertices = anchorTriangle.userData.vertices;

  vertices.forEach((pos, i) => {
    // Inner bright core
    const coreGeo = new THREE.SphereGeometry(0.08, 16, 16);
    const coreMat = new THREE.MeshBasicMaterial({
      color: colors[i],
      transparent: true,
      opacity: 0.9,
      depthWrite: false,
    });
    const core = new THREE.Mesh(coreGeo, coreMat);
    core.position.copy(pos);

    // Outer glow halo
    const haloGeo = new THREE.SphereGeometry(0.2, 16, 16);
    const haloMat = new THREE.MeshBasicMaterial({
      color: colors[i],
      transparent: true,
      opacity: 0.2,
      depthWrite: false,
    });
    const halo = new THREE.Mesh(haloGeo, haloMat);
    halo.position.copy(pos);

    const group = new THREE.Group();
    group.add(core);
    group.add(halo);
    group.userData = { core, halo, coreMat, haloMat, color: colors[i] };

    vertexGlows.push(group);
    anchorTriangle.add(group);
  });
}

// ── Edge Particles ──────────────────────────────────────

function buildEdgeParticles() {
  if (!anchorTriangle) return;

  const verts = anchorTriangle.userData.vertices;
  const edges = [
    [verts[0], verts[1]],
    [verts[1], verts[2]],
    [verts[2], verts[0]],
  ];

  const particlesPerEdge = 80;
  const totalParticles = particlesPerEdge * 3;

  const positions = new Float32Array(totalParticles * 3);
  const colors = new Float32Array(totalParticles * 3);
  const edgeIndices = new Float32Array(totalParticles); // which edge, for animation

  for (let e = 0; e < 3; e++) {
    const [a, b] = edges[e];
    for (let p = 0; p < particlesPerEdge; p++) {
      const idx = e * particlesPerEdge + p;
      const t = Math.random(); // Random position along edge
      const pos = new THREE.Vector3().lerpVectors(a, b, t);

      positions[idx * 3]     = pos.x;
      positions[idx * 3 + 1] = pos.y;
      positions[idx * 3 + 2] = pos.z;

      // Color is a mix of the two vertex colors
      const colorA = [CYAN, EMERALD, PURPLE][e];
      const colorB = [CYAN, EMERALD, PURPLE][(e + 1) % 3];
      const mixed = colorA.clone().lerp(colorB, t);
      colors[idx * 3]     = mixed.r;
      colors[idx * 3 + 1] = mixed.g;
      colors[idx * 3 + 2] = mixed.b;

      edgeIndices[idx] = e;
    }
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));

  const mat = new THREE.PointsMaterial({
    size: 0.04,
    vertexColors: true,
    transparent: true,
    opacity: 0.7,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });

  const points = new THREE.Points(geo, mat);
  points.userData = {
    particlesPerEdge,
    edges,
    positions,
    colors,
    edgeIndices,
    basePositions: new Float32Array(positions), // Snapshot for animation reference
  };

  edgeParticles = [points];
  anchorTriangle.add(points);
}

// ── Ambient Particles ───────────────────────────────────

function buildAmbientParticles() {
  const count = 200;
  const positions = new Float32Array(count * 3);
  const spreadRadius = 6;

  for (let i = 0; i < count; i++) {
    // Random in a sphere
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    const r = 2 + Math.random() * spreadRadius;
    positions[i * 3]     = Math.sin(phi) * Math.cos(theta) * r;
    positions[i * 3 + 1] = Math.sin(phi) * Math.sin(theta) * r;
    positions[i * 3 + 2] = Math.cos(phi) * r;
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));

  const mat = new THREE.PointsMaterial({
    size: 0.025,
    color: CYAN,
    transparent: true,
    opacity: 0.35,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });

  ambientParticles = new THREE.Points(geo, mat);
  ambientParticles.userData = { positions, baseRadius: spreadRadius };
  scene.add(ambientParticles);
}

// ── Animation Loop ──────────────────────────────────────

function animate() {
  animationId = requestAnimationFrame(animate);

  const dt = Math.min(clock.getDelta(), 0.1); // Cap delta
  const elapsed = clock.elapsedTime;

  // ── Base rotation speed ──────────────────────────────
  let rotSpeed = 0.15; // radians per second

  // T1 acceleration
  if (ThreeState.t1Active) {
    ThreeState.t1Intensity = Math.min(1, ThreeState.t1Intensity + dt * 2);
    rotSpeed += ThreeState.t1Intensity * 2.5;
  } else {
    ThreeState.t1Intensity = Math.max(0, ThreeState.t1Intensity - dt * 1.5);
    rotSpeed += ThreeState.t1Intensity * 2.5;
  }

  // ── Rotate anchor triangle ────────────────────────────
  if (anchorTriangle) {
    anchorTriangle.rotation.y += rotSpeed * dt;
    anchorTriangle.rotation.x += Math.sin(elapsed * 0.3) * 0.003;
    anchorTriangle.rotation.z += Math.cos(elapsed * 0.4) * 0.002;

    // T1 amber streak: pulse edge opacity
    if (anchorTriangle.userData.edgeMaterial) {
      const baseAlpha = 0.25 + ThreeState.t1Intensity * 0.4;
      anchorTriangle.userData.edgeMaterial.opacity = baseAlpha;

      // Shift toward amber during T1
      const t1Mix = ThreeState.t1Intensity;
      const baseColor = new THREE.Color().lerpColors(CYAN, AMBER, t1Mix);
      anchorTriangle.userData.edgeMaterial.color.copy(baseColor);
    }

    // SAGE rainbow bridge: vertex glow oscillation
    vertexGlows.forEach((glow, i) => {
      if (glow.userData.haloMat) {
        const baseAlpha = 0.2 + Math.sin(elapsed * 2 + i) * 0.1;
        const sageBoost = ThreeState.sageIntensity * 0.5;
        glow.userData.haloMat.opacity = baseAlpha + sageBoost;

        // During SAGE: cycle halo colors
        if (ThreeState.sageIntensity > 0.1) {
          const hue = (elapsed * 0.5 + i * 0.333) % 1;
          const rainbow = new THREE.Color().setHSL(hue, 0.8, 0.6);
          glow.userData.haloMat.color.copy(rainbow);
        } else {
          glow.userData.haloMat.color.copy(glow.userData.color);
        }
      }
    });

    // SAGE intensity decay
    if (!ThreeState.sageActive) {
      ThreeState.sageIntensity = Math.max(0, ThreeState.sageIntensity - dt * 0.8);
    } else {
      ThreeState.sageIntensity = Math.min(1, ThreeState.sageIntensity + dt * 1.5);
    }
  }

  // ── Animate edge particles ────────────────────────────
  edgeParticles.forEach(pts => {
    const geo = pts.geometry;
    const posArr = geo.attributes.position.array;
    const baseArr = pts.userData.basePositions;
    const { edges, particlesPerEdge } = pts.userData;

    for (let e = 0; e < 3; e++) {
      const [a, b] = edges[e];
      for (let p = 0; p < particlesPerEdge; p++) {
        const idx = e * particlesPerEdge + p;
        // Flow along edge: base position + drift
        let t = ((elapsed * 0.3 + p * 0.05 + e * 0.33) % 1.5) / 1.5;
        t = Math.abs(Math.sin(t * Math.PI)); // Ping-pong for flow

        // During T1, particles move faster
        const speedup = 1 + ThreeState.t1Intensity * 4;
        t = ((elapsed * 0.3 * speedup + p * 0.05 + e * 0.33) % 1.5) / 1.5;
        t = Math.abs(Math.sin(t * Math.PI));

        const pos = new THREE.Vector3().lerpVectors(a, b, t);

        // Add slight perpendicular dispersion
        const dir = new THREE.Vector3().subVectors(b, a).normalize();
        const perp = new THREE.Vector3(-dir.y, dir.x, 0).normalize();
        const disp = Math.sin(elapsed * 1.5 + p * 0.2) * 0.15;

        posArr[idx * 3]     = pos.x + perp.x * disp;
        posArr[idx * 3 + 1] = pos.y + perp.y * disp;
        posArr[idx * 3 + 2] = pos.z + perp.z * disp + Math.cos(elapsed + p) * 0.05;
      }
    }
    geo.attributes.position.needsUpdate = true;
  });

  // ── Animate ambient particles ─────────────────────────
  if (ambientParticles) {
    ambientParticles.rotation.y += dt * 0.03;
    ambientParticles.rotation.x += dt * 0.015;
    // Subtle drift
    ambientParticles.position.y += Math.sin(elapsed * 0.5) * 0.002;
  }

  // ── Subtle camera orbit ───────────────────────────────
  const orbitR = 9;
  const orbitSpeed = 0.08;
  camera.position.x = Math.sin(elapsed * orbitSpeed) * orbitR * 0.25;
  camera.position.y = 0.5 + Math.sin(elapsed * orbitSpeed * 1.3) * 0.5;
  camera.position.z = orbitR + Math.cos(elapsed * orbitSpeed) * 0.5;
  camera.lookAt(0, 0, 0);

  // ── Render ────────────────────────────────────────────
  renderer.render(scene, camera);
}

// ── Resize Handler ──────────────────────────────────────

function onResize() {
  if (!camera || !renderer) return;
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
}

// ── Public API ──────────────────────────────────────────

/**
 * Trigger a T1 learning event — triangle accelerates, amber streak.
 */
export function triggerT1() {
  ThreeState.t1Active = true;
  // Auto-reset after 2 seconds
  clearTimeout(ThreeState._t1Timer);
  ThreeState._t1Timer = setTimeout(() => {
    ThreeState.t1Active = false;
  }, 2000);
}

/**
 * Trigger a SAGE discovery event — rainbow bridge between vertices.
 */
export function triggerSageDiscovery() {
  ThreeState.sageActive = true;
  // Auto-reset after 3 seconds
  clearTimeout(ThreeState._sageTimer);
  ThreeState._sageTimer = setTimeout(() => {
    ThreeState.sageActive = false;
  }, 3000);
}

/**
 * Stop the animation loop and dispose resources.
 */
export function dispose() {
  if (animationId) cancelAnimationFrame(animationId);
  window.removeEventListener('resize', onResize);
  if (scene) {
    scene.traverse((obj) => {
      if (obj.geometry) obj.geometry.dispose();
      if (obj.material) {
        if (Array.isArray(obj.material)) {
          obj.material.forEach((m) => m.dispose());
        } else {
          obj.material.dispose();
        }
      }
    });
    scene.clear();
  }
  if (renderer) {
    renderer.dispose();
    renderer.forceContextLoss();
  }
  console.log('[Verix 3D] Scene disposed.');
}
