"""
Verix 丘脑门控 — 基于 Fang et al. 2025 Science
"Human high-order thalamic nuclei gate conscious perception
 through the thalamofrontal loop"

架构:
  Agent信号 → 丘脑门控 (imTha) → GWT工作空间 (PFC)

  1. 丘脑髓板内核群先激活 (~200ms)，比前额叶更早、更强
  2. θ相驱动：每窗口只放行最强信号
  3. 赢者抑制：被放行的信号抑制其他竞争者
"""
import os, sys, time, json, math, random
from collections import defaultdict, deque
from dataclasses import dataclass, field
import numpy as np

# ═══════════════════════════════════════════════
# 1. Agent 信号
# ═══════════════════════════════════════════════

@dataclass
class AgentSignal:
    """一个 Agent 的输出信号，竞争进入 GWT"""
    agent: str          # 'alpha', 'beta', 'delta', 'gamma', 'epsilon'
    signal_type: str    # 't1_event', 'blind_spot', 'discovery', 'contradiction', 'homology'
    strength: float     # 0-1, 信号强度 (相当于 ERP 振幅)
    latency: float      # seconds, 信号产生延迟
    content: dict       # 信号载荷
    timestamp: float
    novelty: float = 0.5     # 新颖度 (新出现的信号更强)
    urgency: float = 0.5     # 紧急度 (矛盾/盲区信号更强)

    @property
    def salience(self) -> float:
        """综合显著性 = 强度×0.4 + 新颖度×0.3 + 紧急度×0.3 - 延迟惩罚"""
        latency_penalty = max(0, self.latency * 0.1)
        return max(0, min(1,
            self.strength * 0.4 +
            self.novelty * 0.3 +
            self.urgency * 0.3 -
            latency_penalty
        ))


# ═══════════════════════════════════════════════
# 2. 丘脑核团 — 髓板内核群 (imTha)
# ═══════════════════════════════════════════════

class IntralaminarMedialThalamus:
    """
    imTha = CM + Pf + MDm 核团
    丘脑髓板内核群 — 意识的门

    特性:
    - 比皮层先激活 (earlier latency)
    - 激活更强 (stronger response)
    - 只放行最强的信号进入 PFC
    """

    def __init__(self, gate_threshold=0.4, refractory_period=2):
        self.gate_threshold = gate_threshold       # 显著性阈值
        self.refractory_period = refractory_period  # 同一 Agent 放行后的抑制期(秒)
        self.last_gated = defaultdict(float)        # {agent: last_gate_time}
        self.gate_history = []                      # 门控历史
        self.n_gated = 0
        self.n_rejected = 0

    def evaluate(self, signal: AgentSignal) -> (bool, float):
        """
        评估一个信号是否能通过丘脑门

        Returns: (passed, gating_score)
        """
        salience = signal.salience

        # 1. 显著性必须超过阈值
        if salience < self.gate_threshold:
            self.n_rejected += 1
            return False, salience

        # 2. 同一 Agent 的抑制期检查
        time_since_last = time.time() - self.last_gated[signal.agent]
        if time_since_last < self.refractory_period:
            # 抑制期内，提高阈值
            adjusted_threshold = self.gate_threshold + 0.15 * (1 - time_since_last / self.refractory_period)
            if salience < adjusted_threshold:
                self.n_rejected += 1
                return False, salience

        return True, salience

    def gate(self, signal: AgentSignal) -> bool:
        """放行信号"""
        passed, score = self.evaluate(signal)
        if passed:
            self.last_gated[signal.agent] = time.time()
            self.n_gated += 1
            self.gate_history.append({
                'time': time.time(),
                'agent': signal.agent,
                'signal_type': signal.signal_type,
                'salience': score,
            })
        return passed


# ═══════════════════════════════════════════════
# 3. θ 相位窗口 — 节律性注意采样
# ═══════════════════════════════════════════════

class ThetaPhaseWindow:
    """
    θ 节律门控窗口 (4-8 Hz in brain, ~45s cycle in Verix)

    每个 θ 周期:
    1. 收集所有 Agent 信号
    2. imTha 评估每个信号
    3. 只放行 top K 个信号
    4. 赢者广播到 GWT，抑制其他
    """

    def __init__(self, window_duration=45, max_signals_per_window=3):
        self.window_duration = window_duration
        self.max_signals_per_window = max_signals_per_window
        self.imTha = IntralaminarMedialThalamus(gate_threshold=0.35)
        self.current_window_start = time.time()
        self.pending_signals = []      # 当前窗口等待评估的信号
        self.broadcasted = []          # 已广播到 GWT 的信号
        self.inhibited = []            # 被抑制的信号
        self.window_count = 0

    def submit(self, signal: AgentSignal):
        """提交一个信号到当前窗口"""
        self.pending_signals.append(signal)

    def tick(self) -> dict:
        """
        θ 窗口结束 — 门控裁决
        返回: {broadcasted: [...], inhibited: [...], n_passed: int}
        """
        now = time.time()
        elapsed = now - self.current_window_start

        if elapsed < self.window_duration * 0.8:
            return {'broadcasted': [], 'inhibited': [], 'n_passed': 0,
                    'window_open': True, 'elapsed': elapsed}

        # 窗口到期 — 裁决
        self.window_count += 1
        self.current_window_start = now

        # 按显著性排序
        ranked = sorted(self.pending_signals, key=lambda s: s.salience, reverse=True)

        broadcasted = []
        inhibited = []
        for signal in ranked:
            if len(broadcasted) < self.max_signals_per_window:
                if self.imTha.gate(signal):
                    broadcasted.append(signal)
                    continue
            inhibited.append(signal)

        self.broadcasted.extend(broadcasted)
        self.inhibited.extend(inhibited)
        self.pending_signals = []

        return {
            'broadcasted': [{'agent': s.agent, 'type': s.signal_type,
                             'salience': round(s.salience, 3),
                             'content': s.content.get('summary', '')[:50]}
                            for s in broadcasted],
            'inhibited': len(inhibited),
            'n_passed': len(broadcasted),
            'window_open': False,
            'elapsed': elapsed,
        }

    def status(self) -> dict:
        return {
            'windows': self.window_count,
            'pending': len(self.pending_signals),
            'broadcasted_total': len(self.broadcasted),
            'inhibited_total': len(self.inhibited),
            'gated': self.imTha.n_gated,
            'rejected': self.imTha.n_rejected,
            'threshold': self.imTha.gate_threshold,
        }


# ═══════════════════════════════════════════════
# 4. 丘脑门控桥接 — 接入自治循环
# ═══════════════════════════════════════════════

class ThalamicGateBridge:
    """
    丘脑门控桥接器 — 连接所有 Agent 信号到 θ 窗口

    使用方式:
      bridge.submit(agent='alpha', signal_type='t1_event',
                    strength=rmse, content={'scene': ...})
      bridge.submit(agent='gamma', signal_type='contradiction',
                    strength=0.9, content={'scenario': ...})

      每个周期: result = bridge.tick()
    """

    def __init__(self, window_duration=45):
        self.window = ThetaPhaseWindow(window_duration=window_duration)
        self.signal_history = deque(maxlen=200)

    def submit(self, agent: str, signal_type: str, strength: float,
               content: dict = None, latency: float = 0,
               novelty: float = None, urgency: float = None):
        """Agent 提交信号"""
        # 自动计算新颖度（同类型信号最近没出现过 → 更新颖）
        if novelty is None:
            recent_same_type = sum(1 for s in self.signal_history
                                   if s.agent == agent and s.signal_type == signal_type)
            novelty = 1.0 - min(recent_same_type / 10, 1.0)

        # 自动计算紧急度
        if urgency is None:
            urgency_map = {
                'contradiction': 0.95,
                't1_event': 0.7,
                'blind_spot': 0.8,
                'discovery': 0.6,
                'homology': 0.5,
                'observation': 0.3,
            }
            urgency = urgency_map.get(signal_type, 0.4)

        signal = AgentSignal(
            agent=agent, signal_type=signal_type,
            strength=min(1.0, strength), latency=latency,
            content=content or {}, timestamp=time.time(),
            novelty=novelty, urgency=urgency,
        )
        self.window.submit(signal)
        self.signal_history.append(signal)

    def tick(self) -> dict:
        """θ 窗口裁决"""
        return self.window.tick()

    def status(self) -> dict:
        return self.window.status()


# ═══════════════════════════════════════════════
# 5. 自检
# ═══════════════════════════════════════════════

if __name__ == '__main__':
    print("Verix Thalamic Gate — Fang et al. 2025 Science")
    bridge = ThalamicGateBridge(window_duration=3)  # 3s 用于测试

    # 模拟 Agent 信号
    bridge.submit('alpha', 't1_event', strength=0.6,
                  content={'rmse': 0.15, 'scene': 'collision_42'})
    bridge.submit('gamma', 'contradiction', strength=0.85,
                  content={'scenario': '台球碰撞, Alpha≠人类'})
    bridge.submit('delta', 'discovery', strength=0.4,
                  content={'template': 'list_sort'})
    bridge.submit('alpha', 'blind_spot', strength=0.75,
                  content={'region': 'projectile_high_speed'})

    print(f'  待处理信号: {len(bridge.window.pending_signals)}')
    for s in bridge.window.pending_signals:
        print(f'    {s.agent}/{s.signal_type}: salience={s.salience:.3f} '
              f'(strength={s.strength}, novelty={s.novelty:.2f}, urgency={s.urgency})')

    # 等待窗口到期
    print('\n  等待 θ 窗口到期...')
    time.sleep(3)

    result = bridge.tick()
    print(f'\n  θ窗口 #{bridge.window.window_count}:')
    print(f'    通过: {result["n_passed"]}')
    for s in result['broadcasted']:
        print(f'      → {s["agent"]}/{s["type"]} (salience={s["salience"]})')
    print(f'    抑制: {result["inhibited"]}')

    print('\n✓ 丘脑门控就绪')
