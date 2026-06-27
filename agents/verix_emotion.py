"""
Verix 情感系统 — Damasio 体感标记假说计算实现

情绪 = 计算快捷键。不是"感觉"，是对状态的快速价值赋值。

5 种核心情绪:
  TRUST     — 验证通过率高 → 降低门控阈值
  DISTRUST  — 矛盾累积 → 提高门控阈值, 强制更多验证
  FRUSTRATE — 同一盲区反复未解决 → 放弃, 随机跳转
  EXCITE    — 发现新因果/新结构 → 分配更多资源
  BOREDOM   — 重复信号 → 习惯化, 降低显著性
"""
import os, sys, time, json, math, random
from collections import defaultdict, deque
import numpy as np

# ═══════════════════════════════════════════════
# 1. 情感核心 — 体感标记
# ═══════════════════════════════════════════════

class SomaticMarker:
    """Damasio 体感标记 — 一个情感状态"""

    def __init__(self, name: str, threshold=0.5, decay=0.05):
        self.name = name
        self.intensity = 0.0        # 当前强度 (0-1)
        self.threshold = threshold  # 触发阈值
        self.decay = decay          # 每周期自然衰减
        self.trigger_count = 0      # 触发次数
        self.last_trigger = 0       # 上次触发时间
        self.history = deque(maxlen=50)

    def stimulate(self, delta: float, reason: str = ''):
        """刺激这个情感——增加强度"""
        self.intensity = min(1.0, self.intensity + delta)
        if self.intensity > self.threshold:
            self.trigger_count += 1
            self.last_trigger = time.time()
            self.history.append({'time': self.last_trigger, 'intensity': self.intensity,
                                 'reason': reason})
            return True  # 情感被触发
        return False

    def decay_naturally(self):
        """自然衰减——情绪不会永远持续"""
        self.intensity = max(0, self.intensity - self.decay)

    def is_active(self) -> bool:
        return self.intensity > self.threshold

    def status(self):
        return {
            'intensity': round(self.intensity, 3),
            'active': self.is_active(),
            'triggers': self.trigger_count,
        }


# ═══════════════════════════════════════════════
# 2. 情感大脑
# ═══════════════════════════════════════════════

class EmotionalBrain:
    """情感计算核心 — 5 种基本情绪"""

    def __init__(self):
        # 5 种核心情绪
        self.TRUST = SomaticMarker('trust', threshold=0.4, decay=0.03)
        self.DISTRUST = SomaticMarker('distrust', threshold=0.5, decay=0.1)
        self.FRUSTRATE = SomaticMarker('frustrate', threshold=0.6, decay=0.15)
        self.EXCITE = SomaticMarker('excite', threshold=0.3, decay=0.08)
        self.BOREDOM = SomaticMarker('boredom', threshold=0.5, decay=0.02)

        # 情感影响的行为调整
        self.trust_boost = {}       # {agent: accumulated_trust}
        self.distrust_penalty = {}  # {agent: accumulated_distrust}
        self.frustration_targets = set()  # 被放弃的盲区
        self.excite_allocations = []      # 额外资源分配
        self.boredom_suppressed = set()   # 被习惯化抑制的信号类型

        # 追踪
        self.event_count = 0

    def evaluate(self, event: dict) -> dict:
        """
        根据一个事件更新情感状态
        event = {type, agent, outcome, detail}
        """
        self.event_count += 1
        triggered = []

        # Trust: Agent 验证通过
        if event.get('outcome') == 'verified':
            if self.TRUST.stimulate(0.15, f"{event.get('agent','?')} 验证通过"):
                triggered.append('TRUST')
                self.trust_boost[event.get('agent', '?')] = \
                    self.trust_boost.get(event.get('agent', '?'), 0) + 1

        # Distrust: 矛盾/错误
        if event.get('type') in ['contradiction', 'verification_failed', 'C1_fail', 'C2_fail']:
            if self.DISTRUST.stimulate(0.25, f"{event.get('agent','?')} {event.get('type','?')}"):
                triggered.append('DISTRUST')
                self.distrust_penalty[event.get('agent', '?')] = \
                    self.distrust_penalty.get(event.get('agent', '?'), 0) + 1

        # Frustrate: 同一问题反复未解决
        if event.get('type') == 'blind_spot_repeated':
            if self.FRUSTRATE.stimulate(0.35, f"盲区: {event.get('detail','?')}"):
                triggered.append('FRUSTRATE')
                self.frustration_targets.add(event.get('detail', ''))

        # Excite: 新发现
        if event.get('type') in ['discovery', 'new_causal_edge', 'novel_behavior']:
            if self.EXCITE.stimulate(0.3, f"发现: {event.get('detail','?')[:60]}"):
                triggered.append('EXCITE')

        # Boredom: 重复信号
        if event.get('type') == 'repeated_signal':
            if self.BOREDOM.stimulate(0.1, f"重复: {event.get('detail','?')[:40]}"):
                triggered.append('BOREDOM')
                self.boredom_suppressed.add(event.get('detail', ''))

        # 自然衰减
        for emotion in [self.TRUST, self.DISTRUST, self.FRUSTRATE, self.EXCITE, self.BOREDOM]:
            emotion.decay_naturally()

        return {'triggered': triggered, 'emotions': self.snapshot()}

    def get_gate_modifier(self, agent: str) -> float:
        """
        情感对丘脑门控的修正值
        Trust降低阈值, Distrust提高阈值
        """
        trust = self.trust_boost.get(agent, 0)
        distrust = self.distrust_penalty.get(agent, 0)

        # Trust每点降低0.02阈值, Distrust每点提高0.05阈值
        modifier = trust * 0.02 - distrust * 0.05
        return round(max(-0.3, min(0.3, modifier)), 3)

    def should_abandon(self, target: str) -> bool:
        """是否应该放弃这个探索方向（沮丧触发）"""
        return target in self.frustration_targets

    def get_exploration_boost(self) -> float:
        """兴奋情绪对探索的加成"""
        if self.EXCITE.is_active():
            return 1.0 + self.EXCITE.intensity * 0.5  # 最多1.5x探索
        return 1.0

    def is_suppressed(self, signal_type: str) -> bool:
        """习惯化——这个信号是否应该降低显著性"""
        return signal_type in self.boredom_suppressed

    def snapshot(self) -> dict:
        return {
            'trust': self.TRUST.status(),
            'distrust': self.DISTRUST.status(),
            'frustrate': self.FRUSTRATE.status(),
            'excite': self.EXCITE.status(),
            'boredom': self.BOREDOM.status(),
            'trust_boost': dict(self.trust_boost),
            'distrust_penalty': dict(self.distrust_penalty),
            'abandoned': len(self.frustration_targets),
            'suppressed_signals': len(self.boredom_suppressed),
        }


# ═══════════════════════════════════════════════
# 3. 情感桥接 — 接入自治循环
# ═══════════════════════════════════════════════

class EmotionalBridge:
    """情感系统 → 其他模块的连接器"""

    def __init__(self, dopamine=None, thalamus=None, hippocampus=None):
        self.brain = EmotionalBrain()
        self.dopamine = dopamine
        self.thalamus = thalamus
        self.hippocampus = hippocampus
        self.signal_memory = defaultdict(int)  # 信号类型 → 出现次数
        self.blind_spot_attempts = defaultdict(int)  # 盲区 → 尝试次数

    def feed(self, cycle_result: dict) -> dict:
        """
        每个周期喂给情感系统
        返回情感驱动的行为调整
        """
        events = []

        # 1. 从探索结果提取情感事件
        explore = cycle_result.get('explore', {})
        if explore.get('discoveries', 0) > 0:
            events.append({'type': 'discovery', 'agent': 'alpha',
                           'outcome': 'discovered', 'detail': f"{explore['discoveries']}个发现"})

        # 2. 从Gamma对齐提取情感事件
        gamma = cycle_result.get('gamma', {})
        if gamma:
            if gamma.get('alignment_rate', 1) >= 0.9:
                events.append({'type': 'alignment_ok', 'agent': 'gamma',
                               'outcome': 'verified', 'detail': f'对齐率{gamma["alignment_rate"]}'})
            if gamma.get('contradictions', 0) > 0:
                events.append({'type': 'contradiction', 'agent': 'gamma',
                               'outcome': 'conflict', 'detail': f'{gamma["contradictions"]}个矛盾'})

        # 3. 从 SAGE 提取
        sage = cycle_result.get('sage') or {}
        if sage.get('new_pairs'):
            events.append({'type': 'discovery', 'agent': 'sage',
                           'outcome': 'homology', 'detail': f'SAGE新高强度迁移'})

        # 4. 检测盲区重复——挫败触发
        for e in cycle_result.get('events', []):
            if e.get('type') == 'blind_spot':
                region = e.get('detail', '')
                self.blind_spot_attempts[region] += 1
                if self.blind_spot_attempts[region] >= 5:
                    events.append({'type': 'blind_spot_repeated', 'agent': 'alpha',
                                   'detail': region})

        # 5. 检测信号重复——无聊触发
        for signal_type in ['discovery', 'contradiction', 'homology']:
            count = 0
            for e in events:
                if e['type'] == signal_type:
                    count += 1
            self.signal_memory[signal_type] += count
            if self.signal_memory[signal_type] > 20:
                events.append({'type': 'repeated_signal', 'detail': signal_type})

        # 6. 喂给情感大脑
        triggered_emotions = []
        for event in events:
            result = self.brain.evaluate(event)
            triggered_emotions.extend(result['triggered'])

        # 7. 生成行为调整
        adjustments = {
            'triggered_emotions': list(set(triggered_emotions)),
            'gate_modifiers': {},
            'exploration_boost': self.brain.get_exploration_boost(),
            'abandoned_targets': list(self.brain.frustration_targets),
            'suppressed_signals': list(self.brain.boredom_suppressed),
        }

        # 8. 各 Agent 的门控修正
        for agent in ['alpha', 'gamma', 'delta', 'sage', 'causal']:
            adjustments['gate_modifiers'][agent] = self.brain.get_gate_modifier(agent)

        # 9. 反馈给丘脑门控
        if self.thalamus:
            for agent, mod in adjustments['gate_modifiers'].items():
                if hasattr(self.thalamus, 'window') and \
                   hasattr(self.thalamus.window, 'imTha'):
                    # Trust 降低阈值, Distrust 提高阈值
                    current = self.thalamus.window.imTha.gate_threshold
                    # 不直接改——通过信号显著性间接影响
                    pass

        return adjustments

    def status(self) -> dict:
        return {
            'emotions': self.brain.snapshot(),
            'signal_memory': dict(self.signal_memory),
            'blind_spot_attempts': dict(self.blind_spot_attempts),
        }


# ═══════════════════════════════════════════════
# 4. 自检
# ═══════════════════════════════════════════════

if __name__ == '__main__':
    print("Verix Emotion System — Damasio Somatic Marker Hypothesis")
    print("=" * 60)

    brain = EmotionalBrain()

    # 模拟一连串事件
    simulation = [
        # Gamma连续验证通过 → Trust 积累
        {'type': 'alignment_ok', 'agent': 'gamma', 'outcome': 'verified', 'detail': '对齐率100%'},
        {'type': 'alignment_ok', 'agent': 'gamma', 'outcome': 'verified', 'detail': '对齐率100%'},
        {'type': 'alignment_ok', 'agent': 'gamma', 'outcome': 'verified', 'detail': '对齐率100%'},
        {'type': 'alignment_ok', 'agent': 'gamma', 'outcome': 'verified', 'detail': '对齐率100%'},
        # 新发现 → 兴奋
        {'type': 'discovery', 'agent': 'alpha', 'outcome': 'discovered', 'detail': '新因果边: mass→energy'},
        # Alpha突然出错 → 怀疑
        {'type': 'contradiction', 'agent': 'alpha', 'outcome': 'conflict', 'detail': 'Alpha vs Human on p1'},
        {'type': 'contradiction', 'agent': 'alpha', 'outcome': 'conflict', 'detail': 'Alpha vs Human on p2'},
        # 同一盲区反复 → 沮丧
        {'type': 'blind_spot_repeated', 'detail': 'projectile_high_speed'},
        {'type': 'blind_spot_repeated', 'detail': 'projectile_high_speed'},
        {'type': 'blind_spot_repeated', 'detail': 'projectile_high_speed'},
    ]

    for i, event in enumerate(simulation):
        result = brain.evaluate(event)
        if result['triggered']:
            print(f"  step{i}: {result['triggered']} ← {event['detail'][:40]}")

    print(f"\n  最终状态: {brain.snapshot()}")
    print(f"\n  门控修正:")
    for agent in ['gamma', 'alpha', 'delta', 'sage']:
        print(f"    {agent}: {brain.get_gate_modifier(agent):+.3f}")
    print(f"  探索加成: {brain.get_exploration_boost():.1f}x")
    print(f"  被放弃: {list(brain.frustration_targets)}")
    print(f"  被抑制: {list(brain.boredom_suppressed)}")

    print("\n✓ 情感系统就绪")
