/* ═══════════════════════════════════════════════════════
   Verix Main — App Controller
   Login flow, carousel timer, status polling, DOM wiring
   ═══════════════════════════════════════════════════════ */

import { CAROUSEL_METRICS, fetchStatus } from './api.js';
import { initThreeScene, triggerT1, triggerSageDiscovery } from './three-scene.js';

// ── DOM Refs ────────────────────────────────────────────
const dom = {};

// ── State ───────────────────────────────────────────────
let carouselIndex = 0;
let carouselTimer = null;
let carouselComplete = false; // True after one full rotation in login card
let dashCarouselTimer = null;
let statusPoller = null;
let clockTimer = null;
let loginDotAnimId = null;

// ── Initialization ──────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  cacheDom();
  initThreeScene('verix-canvas');
  initLoginDotMatrix();
  initLoginCarousel();
  bindEvents();
  startClock();
  document.body.classList.remove('loading');
});

function cacheDom() {
  dom.loginOverlay     = document.getElementById('login-overlay');
  dom.loginCard        = document.getElementById('login-card');
  dom.loginDotCanvas   = document.getElementById('login-dot-canvas');
  dom.btnEnter         = document.getElementById('btn-enter');
  dom.carouselSlide    = document.getElementById('carousel-slide');
  dom.carouselLabel    = dom.carouselSlide?.querySelector('.carousel-metric-label');
  dom.carouselValue    = dom.carouselSlide?.querySelector('.carousel-metric-value');
  dom.carouselDetail   = dom.carouselSlide?.querySelector('.carousel-metric-detail');
  dom.carouselDots     = document.getElementById('login-carousel-dots');
  dom.dashboard        = document.getElementById('dashboard');
  dom.dashCarouselSlide  = document.getElementById('dash-carousel-slide');
  dom.dashCarouselLabel  = dom.dashCarouselSlide?.querySelector('.dash-carousel-label');
  dom.dashCarouselValue  = dom.dashCarouselSlide?.querySelector('.dash-carousel-value');
  dom.dashCarouselDetail = dom.dashCarouselSlide?.querySelector('.dash-carousel-detail');
  dom.dashCarouselDots   = document.getElementById('dash-carousel-dots');
  dom.headerClock      = document.getElementById('header-clock');
  dom.headerT1Badge    = document.getElementById('header-t1-badge');
  dom.statusAlpha      = document.getElementById('status-alpha');
  dom.statusBeta       = document.getElementById('status-beta');
  dom.statusGamma      = document.getElementById('status-gamma');
  dom.accAlpha         = document.getElementById('acc-alpha');
  dom.accBeta          = document.getElementById('acc-beta');
  dom.accGamma         = document.getElementById('acc-gamma');
  dom.sbGwt            = document.getElementById('sb-gwt');
  dom.sbTps            = document.getElementById('sb-tps');
  dom.sbT1             = document.getElementById('sb-t1');
  dom.sbBlind          = document.getElementById('sb-blind');
  dom.sbSa             = document.getElementById('sb-sa');
  dom.sbMv             = document.getElementById('sb-mv');
}

// ── Login Dot Matrix ────────────────────────────────────

function initLoginDotMatrix() {
  const canvas = dom.loginDotCanvas;
  if (!canvas) return;

  const ctx = canvas.getContext('2d');
  let dotData = [];

  function resize() {
    const rect = canvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    canvas.style.width = rect.width + 'px';
    canvas.style.height = rect.height + 'px';
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.scale(dpr, dpr);

    // Rebuild dot grid
    const spacing = 14;
    const cols = Math.floor(rect.width / spacing);
    const rows = Math.floor(rect.height / spacing);
    dotData = [];
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        dotData.push({
          x: c * spacing + spacing / 2,
          y: r * spacing + spacing / 2,
          baseAlpha: 0.03 + Math.random() * 0.06,
          phase: Math.random() * Math.PI * 2,
          speed: 0.3 + Math.random() * 0.7,
        });
      }
    }
  }

  function animate() {
    if (!canvas.isConnected) return;
    const rect = canvas.parentElement.getBoundingClientRect();
    const w = rect.width;
    const h = rect.height;

    ctx.clearRect(0, 0, w, h);

    const time = performance.now() * 0.001;
    const gwtLoad = 0.6; // Simulated GWT throughput, 0..1

    for (const dot of dotData) {
      // Alpha pulses with GWT throughput
      const pulse = Math.sin(time * dot.speed + dot.phase) * 0.5 + 0.5;
      const alpha = dot.baseAlpha + pulse * 0.12 * gwtLoad;

      ctx.fillStyle = `rgba(0, 240, 255, ${alpha.toFixed(3)})`;
      ctx.fillRect(dot.x - 0.5, dot.y - 0.5, 1.5, 1.5);
    }
    loginDotAnimId = requestAnimationFrame(animate);
  }

  resize();
  animate();

  // Rebuild on resize
  window.addEventListener('resize', () => {
    if (canvas.isConnected) resize();
  });
}

// ── Carousel ────────────────────────────────────────────

function initLoginCarousel() {
  // Build dots
  if (dom.carouselDots) {
    dom.carouselDots.innerHTML = '';
    for (let i = 0; i < CAROUSEL_METRICS.length; i++) {
      const dot = document.createElement('span');
      dot.className = 'carousel-dot';
      dot.dataset.index = i;
      dom.carouselDots.appendChild(dot);
    }
  }

  // Show first metric
  showLoginMetric(0);

  // Start rotation
  carouselTimer = setInterval(() => {
    carouselIndex++;
    if (carouselIndex >= CAROUSEL_METRICS.length) {
      // One full rotation complete — hide carousel in login card
      carouselComplete = true;
      clearInterval(carouselTimer);
      carouselTimer = null;
      fadeOutLoginCarousel();
      return;
    }
    showLoginMetric(carouselIndex);
  }, 3000);
}

function showLoginMetric(index) {
  const metric = CAROUSEL_METRICS[index];
  if (!metric || !dom.carouselSlide) return;

  // Fade out
  dom.carouselSlide.classList.add('fading');

  setTimeout(() => {
    // Update content
    dom.carouselLabel.textContent = metric.label;
    dom.carouselLabel.style.color = metric.color;
    dom.carouselValue.textContent = metric.value;
    dom.carouselValue.style.color = metric.color;
    dom.carouselDetail.textContent = metric.detail;

    // Update border glow
    const carousel = document.getElementById('login-carousel');
    if (carousel) {
      carousel.style.borderColor = metric.color + '33';
    }

    // Fade in
    dom.carouselSlide.classList.remove('fading');

    // Update dots
    updateCarouselDots(dom.carouselDots, index);
  }, 250);
}

function fadeOutLoginCarousel() {
  const carousel = document.getElementById('login-carousel');
  if (!carousel) return;
  carousel.style.transition = 'opacity 0.6s ease-out, max-height 0.6s ease-out';
  carousel.style.opacity = '0';
  carousel.style.maxHeight = '0px';
  carousel.style.margin = '0';
  carousel.style.padding = '0';
  carousel.style.border = 'none';
  carousel.style.overflow = 'hidden';
}

function updateCarouselDots(container, activeIndex) {
  if (!container) return;
  const dots = container.querySelectorAll('.carousel-dot');
  dots.forEach((dot, i) => {
    dot.classList.remove('active', 'visited');
    if (i === activeIndex) dot.classList.add('active');
    else if (i < activeIndex) dot.classList.add('visited');
  });
}

// ── Dashboard Carousel (post-login) ─────────────────────

function initDashboardCarousel() {
  if (dom.dashCarouselDots) {
    dom.dashCarouselDots.innerHTML = '';
    for (let i = 0; i < CAROUSEL_METRICS.length; i++) {
      const dot = document.createElement('span');
      dot.className = 'carousel-dot';
      dot.dataset.index = i;
      dom.dashCarouselDots.appendChild(dot);
    }
  }

  let dashIndex = 0;
  showDashboardMetric(dashIndex);

  dashCarouselTimer = setInterval(() => {
    dashIndex = (dashIndex + 1) % CAROUSEL_METRICS.length;
    showDashboardMetric(dashIndex);
  }, 3000);
}

function showDashboardMetric(index) {
  const metric = CAROUSEL_METRICS[index];
  if (!metric || !dom.dashCarouselSlide) return;

  dom.dashCarouselSlide.classList.add('fading');

  setTimeout(() => {
    dom.dashCarouselLabel.textContent = metric.label;
    dom.dashCarouselLabel.style.color = metric.color;
    dom.dashCarouselValue.textContent = metric.value;
    dom.dashCarouselValue.style.color = metric.color;
    dom.dashCarouselDetail.textContent = metric.detail;

    // Update border accent
    const carousel = document.getElementById('dashboard-carousel');
    if (carousel) {
      carousel.style.borderTop = `2px solid ${metric.color}33`;
    }

    dom.dashCarouselSlide.classList.remove('fading');
    updateCarouselDots(dom.dashCarouselDots, index);
  }, 250);
}

// ── Login Flow ──────────────────────────────────────────

function bindEvents() {
  if (dom.btnEnter) {
    dom.btnEnter.addEventListener('click', onEnterVerix);
  }
}

function onEnterVerix() {
  // Clean up login carousel timer
  if (carouselTimer) {
    clearInterval(carouselTimer);
    carouselTimer = null;
  }
  if (loginDotAnimId) {
    cancelAnimationFrame(loginDotAnimId);
    loginDotAnimId = null;
  }

  // Dismiss login overlay
  dom.loginOverlay.classList.add('dismissed');

  // Reveal dashboard after transition
  setTimeout(() => {
    dom.dashboard.classList.remove('hidden');
    dom.dashboard.classList.add('revealing');

    // Start dashboard systems
    initDashboardCarousel();
    fetchAndUpdateStatus();
    statusPoller = setInterval(fetchAndUpdateStatus, 5000);

    // Remove revealing class after animation
    setTimeout(() => {
      dom.dashboard.classList.remove('revealing');
    }, 800);
  }, 400);
}

// ── Status Polling ──────────────────────────────────────

async function fetchAndUpdateStatus() {
  try {
    const data = await fetchStatus();
    updateAgentPanels(data);
    updateStatusBar(data);
    checkT1Events(data);
    checkSageEvents(data);
  } catch (err) {
    console.warn('[Verix] Status update failed:', err.message);
  }
}

function updateAgentPanels(data) {
  const agents = data.agents || {};

  // Alpha
  if (dom.statusAlpha && agents.alpha) {
    dom.statusAlpha.className = 'agent-status-dot ' + (agents.alpha.online ? 'online' : 'offline');
  }
  if (dom.accAlpha && agents.alpha) {
    dom.accAlpha.textContent = agents.alpha.accuracy;
  }

  // Beta
  if (dom.statusBeta && agents.beta) {
    dom.statusBeta.className = 'agent-status-dot ' + (agents.beta.online ? 'online' : 'offline');
  }
  if (dom.accBeta && agents.beta) {
    dom.accBeta.textContent = agents.beta.accuracy;
  }

  // Gamma
  if (dom.statusGamma && agents.gamma) {
    dom.statusGamma.className = 'agent-status-dot ' + (agents.gamma.online ? 'online' : 'offline');
  }
  if (dom.accGamma && agents.gamma) {
    dom.accGamma.textContent = agents.gamma.accuracy;
  }
}

function updateStatusBar(data) {
  const sch = data.scheduler || {};

  if (dom.sbGwt) dom.sbGwt.textContent = sch.total_tasks != null ? `${sch.total_tasks} tasks` : '--';
  if (dom.sbTps) dom.sbTps.textContent = sch.tasks_per_sec != null ? sch.tasks_per_sec : '--';
  if (dom.sbT1)  dom.sbT1.textContent  = sch.t1_events != null ? sch.t1_events : '0';
  if (dom.sbBlind) dom.sbBlind.textContent = sch.blind_spots != null ? sch.blind_spots : '0';
  if (dom.sbSa)  dom.sbSa.textContent  = '5/5';
  if (dom.sbMv)  dom.sbMv.textContent  = '3/3';
}

function checkT1Events(data) {
  const sch = data.scheduler || {};
  if (sch.t1_events > 0 && dom.headerT1Badge) {
    dom.headerT1Badge.classList.remove('hidden');
    triggerT1();
  } else if (sch.t1_events === 0 && dom.headerT1Badge) {
    dom.headerT1Badge.classList.add('hidden');
  }
}

// Last SAGE state for edge detection
let lastBlindSpots = null;
function checkSageEvents(data) {
  const sch = data.scheduler || {};
  // SAGE discovery: blind spots resolved
  if (lastBlindSpots !== null && sch.blind_spots < lastBlindSpots) {
    triggerSageDiscovery();
  }
  lastBlindSpots = sch.blind_spots;
}

// ── Clock ───────────────────────────────────────────────

function startClock() {
  function tick() {
    if (dom.headerClock) {
      const now = new Date();
      dom.headerClock.textContent = now.toISOString().slice(11, 19) + ' UTC';
    }
  }
  tick();
  clockTimer = setInterval(tick, 1000);
}

// ── Cleanup ─────────────────────────────────────────────

window.addEventListener('beforeunload', () => {
  if (carouselTimer) clearInterval(carouselTimer);
  if (dashCarouselTimer) clearInterval(dashCarouselTimer);
  if (statusPoller) clearInterval(statusPoller);
  if (clockTimer) clearInterval(clockTimer);
  if (loginDotAnimId) cancelAnimationFrame(loginDotAnimId);
});

// ── Keyboard shortcut ───────────────────────────────────

document.addEventListener('keydown', (e) => {
  if (e.key === 'Enter'
      && dom.dashboard.classList.contains('hidden')
      && !dom.loginOverlay.classList.contains('dismissed')) {
    e.preventDefault();
    onEnterVerix();
  }
});
