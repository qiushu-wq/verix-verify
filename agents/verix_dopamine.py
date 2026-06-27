"""
Verix 多巴胺价值系统 — 基于 Schultz et al. 1997 Science
"A neural substrate of prediction and reward"

核心:
  VTA/SNc 多巴胺神经元 → 奖励预测误差 (RPE)
  实际 > 预期 → 多巴胺爆发 (正向学习信号)
  实际 < 预期 → 多巴胺抑制 (负向修正信号)
  实际 = 预期 → 不发放 (已习得，无需调整)

用途:
  1. 对每个 Agent 的输出打分
  2. 计算 RPE → 驱动学习权重
  3. 调整丘脑门控注意权重
  4. 跟踪每个 Agent 的累计价值贡献
"""
import os, sys, time, json, math
from collections import defaultdict, deque
import numpy as np

# ═══════════════════════════════════════════════
# 1. 奖励预测误差 (RPE) — Schultz 1997 核心
# ═══════════════════════════════════════════════

class RewardPredictionError:
    """单个维度的 RPE 追踪器"""

    def __init__(self, learning_rate=0.1, initial_value=0.5):
        self.expected = initial_value     # V̂ — 预期价值
        self.actual = 0                   # V — 实际价值
        self.rpe = 0                      # δ = V - V̂
        self.lr = learning_rate
        self.history = deque(maxlen=100)
        self.n_pos = 0                    # 正向误差次数
        self.n_neg = 0                    # 负向误差次数
        self.n_zero = 0                   # 零误差次数

    def update(self, actual_value: float) -> dict:
        """
        计算 RPE 并更新预期
        δ = V_actual - V_expected
        """
        self.actual = max(0, min(1, actual_value))
        self.rpe = self.actual - self.expected

        # 更新预期: V̂ ← V̂ + α × δ
        self.expected += self.lr * self.rpe
        self.expected = max(0, min(1, self.expected))

        # 统计
        if self.rpe > 0.05:
            self.n_pos += 1
            event = 'dopamine_burst'
        elif self.rpe < -0.05:
            self.n_neg += 1
            event = 'dopamine_dip'
        else:
            self.n_zero += 1
            event = 'dopamine_tonic'

        self.history.append({
            'time': time.time(), 'actual': round(self.actual, 3),
            'expected': round(self.expected, 3), 'rpe': round(self.rpe, 3),
            'event': event,
        })
        return {'rpe': round(self.rpe, 3), 'event': event,
                'expected': round(self.expected, 3)}

    def stats(self) -> dict:
        total = self.n_pos + self.n_neg + self.n_zero
        if total == 0:
            return {'rpe_mean': 0, 'trend': 'stable'}
        return {
            'expected': round(self.expected, 3),
            'n_pos': self.n_pos, 'n_neg': self.n_neg, 'n_zero': self.n_zero,
            'rpe_mean': round(self.rpe, 3),
            'trend': 'improving' if self.expected > 0.7 else
                     'declining' if self.expected < 0.3 else 'stable',
        }


# ═══════════════════════════════════════════════
# 2. 多巴胺系统 (VTA/SNc)
# ═══════════════════════════════════════════════

class DopamineSystem:
    """
    VTA + SNc 多巴胺系统

    VTA (腹侧被盖区): 信号"比预期好" → 促进探索 + 奖励学习
    SNc (黑质致密部): 信号"比预期差" → 促进修正 + 行为抑制
    """

    def __init__(self):
        # 每个 Agent 的 RPE 追踪器
        self.rpe_trackers = defaultdict(lambda: RewardPredictionError())

        # 每个 Agent 的当前价值权重 (影响丘脑门控)
        self.agent_weights = defaultdict(lambda: 0.5)

        # 全局指标
        self.total_rewards = 0
        self.total_punishments = 0
        self.global_value = 0.5

        # 最近的评价事件
        self.recent_evaluations = deque(maxlen=50)

    # ── 评价函数 ──

    def evaluate_alpha(self, rmse: float, is_t1: bool) -> float:
        """评价 Alpha 物理预测"""
        if is_t1:
            # T1 事件：误差大 → 低分
            return max(0, 1.0 - rmse)
        else:
            # 正常预测：高分
            return max(0.7, 1.0 - rmse)

    def evaluate_beta(self, proof_passed: bool, proof_time_ms: float = 0) -> float:
        """评价 Beta 逻辑证明"""
        if proof_passed:
            return 0.9 + 0.1 * min(1, 100 / max(proof_time_ms, 1))
        return 0.1

    def evaluate_delta(self, tests_passed: int, tests_total: int,
                       compilation_passed: bool) -> float:
        """评价 Delta 代码生成"""
        if not compilation_passed:
            return 0.05
        return tests_passed / max(tests_total, 1)

    def evaluate_gamma(self, alignment_rate: float, n_contradictions: int) -> float:
        """评价 Gamma 人类对齐"""
        base = alignment_rate
        penalty = min(0.3, n_contradictions * 0.05)
        return max(0, base - penalty)

    def evaluate_sage(self, migration_strength: float, is_new: bool) -> float:
        """评价 SAGE 跨域迁移"""
        base = min(1.0, migration_strength / 5.0)
        if is_new:
            base += 0.2  # 新迁移加分
        return min(1.0, base)

    def evaluate_causal(self, edge_strength: float, n_new_edges: int) -> float:
        """评价 VCD 因果发现"""
        if n_new_edges > 0:
            return min(1.0, edge_strength + 0.1 * n_new_edges)
        return max(0.1, edge_strength)

    # ── RPE 更新 ──

    def reward(self, agent: str, value: float) -> dict:
        """
        给 Agent 发放奖励/惩罚
        计算 RPE，更新权重
        """
        rpe_result = self.rpe_trackers[agent].update(value)
        rpe = rpe_result['rpe']

        # 更新 Agent 权重 (影响丘脑门控注意)
        old_weight = self.agent_weights[agent]
        if rpe > 0:
            # 正向 RPE → 提升权重 (这个 Agent 比预期好)
            self.agent_weights[agent] = min(1.0, old_weight + 0.05 * abs(rpe))
            self.total_rewards += 1
        elif rpe < 0:
            # 负向 RPE → 降低权重
            self.agent_weights[agent] = max(0.1, old_weight - 0.03 * abs(rpe))
            self.total_punishments += 1

        # 更新全局价值
        weights = list(self.agent_weights.values())
        self.global_value = np.mean(weights) if weights else 0.5

        # 记录
        evaluation = {
            'time': time.time(), 'agent': agent, 'value': round(value, 3),
            'rpe': rpe, 'weight': round(self.agent_weights[agent], 3),
            'event': rpe_result['event'],
        }
        self.recent_evaluations.append(evaluation)
        return evaluation

    # ── 门控权重输出 ──

    def get_gate_weights(self) -> dict:
        """输出当前各 Agent 的门控权重，供丘脑使用"""
        return dict(self.agent_weights)

    def get_attention_allocation(self) -> dict:
        """输出当前注意力分配比例"""
        total = sum(self.agent_weights.values())
        if total == 0:
            return {a: 0 for a in self.agent_weights}
        return {a: round(w / total, 3) for a, w in self.agent_weights.items()}

    def get_leaderboard(self) -> list:
        """Agent 价值排行榜"""
        ranked = sorted(self.agent_weights.items(), key=lambda x: x[1], reverse=True)
        return [{'agent': a, 'weight': round(w, 3),
                 'trend': self.rpe_trackers[a].stats()['trend']}
                for a, w in ranked]

    def status(self) -> dict:
        return {
            'global_value': round(self.global_value, 3),
            'total_rewards': self.total_rewards,
            'total_punishments': self.total_punishments,
            'agents': self.get_leaderboard(),
            'attention': self.get_attention_allocation(),
            'recent': list(self.recent_evaluations)[-5:],
        }


# ═══════════════════════════════════════════════
# 3. 价值桥接 — 接入自治循环 + 丘脑门控
# ═══════════════════════════════════════════════

class ValueBridge:
    """价值桥接器——评分 → RPE → 权重 → 丘脑门控"""

    def __init__(self, dopamine: DopamineSystem, thalamus=None):
        self.dopamine = dopamine
        self.thalamus = thalamus
        self.evaluation_cycle = 0

    def evaluate_cycle(self, cycle_result: dict) -> dict:
        """
        根据一个周期的结果给各 Agent 打分
        """
        self.evaluation_cycle += 1
        evaluations = []

        # Alpha: 从探索结果评分
        explore = cycle_result.get('explore', {})
        if explore:
            n_probes = explore.get('probes', 0)
            n_discoveries = explore.get('discoveries', 0)
            if n_probes > 0:
                alpha_value = 0.5 + 0.3 * (n_discoveries / n_probes)
                evaluations.append(
                    self.dopamine.reward('alpha', alpha_value))

        # Gamma: 从对齐率评分
        gamma = cycle_result.get('gamma', {})
        if gamma:
            alignment = gamma.get('alignment_rate', 0.5)
            contradictions = gamma.get('contradictions', 0)
            gamma_value = self.dopamine.evaluate_gamma(alignment, contradictions)
            evaluations.append(
                self.dopamine.reward('gamma', gamma_value))

        # SAGE: 从迁移数量评分
        sage = cycle_result.get('sage', {})
        if sage:
            n_migrations = sage.get('migrations', 0)
            sage_value = self.dopamine.evaluate_sage(
                min(n_migrations / 5.0, 1.0),
                len(sage.get('new_pairs', [])) > 0)
            evaluations.append(
                self.dopamine.reward('sage', sage_value))

        # Causal: 从因果图评分
        causal = cycle_result.get('causal', {})
        if causal:
            n_edges = causal.get('edges', 0)
            causal_value = self.dopamine.evaluate_causal(
                min(n_edges / 20.0, 1.0),
                n_edges)
            evaluations.append(
                self.dopamine.reward('causal', causal_value))

        # Delta: 从新能力评分
        new_caps = explore.get('new_capabilities', 0)
        if new_caps > 0:
            delta_value = min(1.0, 0.6 + 0.2 * new_caps)
            evaluations.append(
                self.dopamine.reward('delta', delta_value))

        # 更新丘脑门控阈值
        if self.thalamus:
            weights = self.dopamine.get_gate_weights()
            for agent, weight in weights.items():
                # 高权重 Agent 的门控阈值降低
                adjusted_threshold = max(0.2, 0.4 - (weight - 0.5) * 0.3)
                if hasattr(self.thalamus, 'window') and \
                   hasattr(self.thalamus.window, 'imTha'):
                    # 不直接改阈值，而是通过权重影响信号显著性
                    pass

        return {
            'evaluations': evaluations,
            'leaderboard': self.dopamine.get_leaderboard(),
            'attention': self.dopamine.get_attention_allocation(),
        }

    def status(self) -> dict:
        return self.dopamine.status()


# ═══════════════════════════════════════════════
# 4. 自检
# ═══════════════════════════════════════════════

if __name__ == '__main__':
    print("Verix Dopamine System — Schultz et al. 1997 Science")
    ds = DopamineSystem()

    # 模拟：Alpha 持续进步
    print("\n  模拟 Alpha 进步:")
    for i in range(10):
        rmse = 0.5 - i * 0.04  # RMSE 从 0.5 降到 0.14
        value = ds.evaluate_alpha(rmse, rmse > 0.15)
        eval_result = ds.reward('alpha', value)
        rpe = eval_result['rpe']
        emoji = '💥' if rpe > 0.05 else '🔻' if rpe < -0.05 else '➖'
        print(f"    step{i}: value={value:.2f} rpe={rpe:+.3f} {emoji}  weight={ds.agent_weights['alpha']:.3f}")

    # 模拟：Gamma 突然出现矛盾
    print("\n  模拟 Gamma 对齐波动:")
    ds.reward('gamma', 1.0)
    print(f"    对齐率 100% → weight={ds.agent_weights['gamma']:.3f}")
    ds.reward('gamma', 0.7)
    print(f"    对齐率 70% → weight={ds.agent_weights['gamma']:.3f}")
    ds.reward('gamma', 0.4)
    print(f"    对齐率 40% → weight={ds.agent_weights['gamma']:.3f}  ⚠️ RPE暴跌")

    print(f"\n  排行榜: {ds.get_leaderboard()}")
    print(f"  注意力分配: {ds.get_attention_allocation()}")
    print(f"  全局价值: {ds.global_value:.3f}")
    print("\n✓ 多巴胺系统就绪")
