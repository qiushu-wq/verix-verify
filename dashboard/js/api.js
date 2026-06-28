/* ═══════════════════════════════════════════════════════
   Verix API Module — fetch /api/status with mock fallback
   ═══════════════════════════════════════════════════════ */

/**
 * Carousel metrics data. Mirrors CAROUSEL_METRICS from tui_dashboard.py.
 * Each metric has an id, label, value, detail, and anchor color.
 */
export const CAROUSEL_METRICS = [
  {
    id: '01',
    label: 'AGENT α · PHYSICS REASONING',
    value: '99.93%',
    detail: 'GNN 0.5M params · MuJoCo 2.3.7 · 3.3ms latency',
    color: '#00f0ff',
  },
  {
    id: '02',
    label: 'AGENT β · FORMAL LOGIC',
    value: '28 / 28',
    detail: 'Lean 4 type checker · 100% pass rate · All theorems verified',
    color: '#00ff88',
  },
  {
    id: '03',
    label: 'AGENT γ · HUMAN ALIGNMENT',
    value: '92.9%',
    detail: '67 scenarios · 1,475 judgments · MLP 0.5M · Consensus anchored',
    color: '#b088ff',
  },
  {
    id: '04',
    label: 'AGENT δ · CODE GENERATION',
    value: '211 / 211',
    detail: 'AST parse + test exec · 100% pass · Template + mutation coverage',
    color: '#ffaa00',
  },
  {
    id: '05',
    label: 'EVOLUTION ENGINE',
    value: '180,000+',
    detail: 'Training steps · 45s autonomous cycle · Novelty + Curiosity driven',
    color: '#00f0ff',
  },
  {
    id: '06',
    label: 'CAUSAL DISCOVERY · VCD',
    value: '22 edges',
    detail: 'Cross-environment invariant · NOTEARS sparse prior · Lei et al. 2022',
    color: '#00ff88',
  },
  {
    id: '07',
    label: 'THALAMUS GATE · imTha',
    value: 'θ-window',
    detail: 'Signal competition · Winner-takes-all broadcast · Fang 2025 Science',
    color: '#b088ff',
  },
  {
    id: '08',
    label: 'SELF-ARCHITECTURE',
    value: '5 / 5',
    detail: 'Modules deployed · 3/3 meta-validators · Recursive blind-spot assembly',
    color: '#ffaa00',
  },
  {
    id: '09',
    label: 'VERIX · SYSTEM READY',
    value: '0.5M > 70B',
    detail: '150× faster · 4-core CPU · No GPU · AGPL v3 · Multi-anchor verified',
    color: '#00f0ff',
  },
];

/**
 * Mock status data matching the /api/status JSON contract.
 * Used as fallback when the server is unreachable.
 */
const MOCK_STATUS = {
  timestamp: new Date().toISOString(),
  agents: {
    alpha: {
      name: 'Agent Alpha',
      anchor: 'physics',
      model: 'GNN 0.5M + MuJoCo 2.3.7',
      accuracy: '99.93%',
      latency: '3.3ms',
      online: true,
    },
    beta: {
      name: 'Agent Beta',
      anchor: 'logic',
      model: 'Lean 4 + BFS',
      accuracy: '28/28',
      latency: '250ms',
      online: true,
    },
    gamma: {
      name: 'Agent Gamma',
      anchor: 'social',
      model: 'MLP 0.5M + Survey',
      accuracy: '92.9%',
      latency: '<1ms',
      online: true,
    },
  },
  scheduler: {
    total_tasks: 3000,
    preemptions: 0,
    tasks_per_sec: 248,
    t1_events: 0,
    blind_spots: 0,
  },
};

/**
 * Fetch live status from /api/status.
 * Falls back to mock data if the server is unreachable.
 * @returns {Promise<Object>} Status data
 */
export async function fetchStatus() {
  try {
    const res = await fetch('/api/status', {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
      signal: AbortSignal.timeout(3000),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.debug('[Verix API] Server unreachable, using mock data:', err.message);
    const mock = structuredClone(MOCK_STATUS);
    mock.timestamp = new Date().toISOString();
    return mock;
  }
}
