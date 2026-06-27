"""
Verix Intrinsic Curiosity Module — 基于 Pathak et al. 2017 ICML
"Curiosity-driven Exploration by Self-supervised Prediction"

核心:
  内在好奇心模块 (ICM):
    前向模型: state + action → predicted_next_state
    预测误差 = ||next_state - predicted_next_state||² = 好奇心奖励
    误差大 → 模型不理解 → 去探索
    误差小 → 已习得     → 去其他地方

  逆模型: state + next_state → predicted_action
    帮助学习对预测有用的特征表征

  这比 Novelty Search 更进一步:
    Novelty = "我没见过这个"
    Curiosity = "我预测不准这个"
"""
import os, sys, time, json, math, random, copy
from collections import defaultdict, deque
import numpy as np

# ═══════════════════════════════════════════════
# 1. ICM 神经网络 (简化版)
# ═══════════════════════════════════════════════

class IntrinsicCuriosityModule:
    """
    前向动力学模型 + 逆模型
    纯 NumPy 实现, 无需 PyTorch
    """

    def __init__(self, state_dim=12, action_dim=8, hidden=32, lr=0.01):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.hidden = hidden
        self.lr = lr

        # 特征编码层: state → features
        self.W_enc = np.random.randn(state_dim, hidden) * 0.1
        self.b_enc = np.zeros(hidden)

        # 前向模型: features + action → predicted_next_features
        self.W_fwd = np.random.randn(hidden + action_dim, hidden) * 0.1
        self.b_fwd = np.zeros(hidden)
        self.W_fwd_out = np.random.randn(hidden, state_dim) * 0.1
        self.b_fwd_out = np.zeros(state_dim)

        # 逆模型: features + next_features → predicted_action
        self.W_inv = np.random.randn(hidden * 2, hidden) * 0.1
        self.b_inv = np.zeros(hidden)
        self.W_inv_out = np.random.randn(hidden, action_dim) * 0.1
        self.b_inv_out = np.zeros(action_dim)

        # 统计
        self.forward_losses = deque(maxlen=100)
        self.inverse_losses = deque(maxlen=100)
        self.curiosity_history = deque(maxlen=100)
        self.n_updates = 0

    def _relu(self, x):
        return np.maximum(0, x)

    def _relu_deriv(self, x):
        return (x > 0).astype(float)

    def encode(self, state):
        """编码状态到特征空间"""
        return self._relu(state @ self.W_enc + self.b_enc)

    def predict_next(self, state, action):
        """前向模型: 预测下一个状态"""
        phi = self.encode(state)
        combined = np.concatenate([phi, action])
        h = self._relu(combined @ self.W_fwd + self.b_fwd)
        return h @ self.W_fwd_out + self.b_fwd_out

    def predict_action(self, state, next_state):
        """逆模型: 预测采取了什么动作"""
        phi = self.encode(state)
        phi_next = self.encode(next_state)
        combined = np.concatenate([phi, phi_next])
        h = self._relu(combined @ self.W_inv + self.b_inv)
        return h @ self.W_inv_out + self.b_inv_out

    def curiosity(self, state, action, next_state):
        """
        计算好奇心奖励
        = 前向预测误差的 L2 范数
        """
        predicted = self.predict_next(state, action)
        error = np.linalg.norm(next_state - predicted)
        self.curiosity_history.append(error)
        return error

    def update(self, state, action, next_state):
        """
        一步在线学习: 同时更新前向模型和逆模型
        """
        phi = self.encode(state)
        phi_next = self.encode(next_state)

        # ── 前向模型更新 ──
        combined_fwd = np.concatenate([phi, action])
        h_fwd = self._relu(combined_fwd @ self.W_fwd + self.b_fwd)
        pred_next = h_fwd @ self.W_fwd_out + self.b_fwd_out

        fwd_error = pred_next - next_state
        fwd_loss = np.mean(fwd_error ** 2)
        self.forward_losses.append(fwd_loss)

        # 梯度: dL/dW_out = h_fwd^T @ fwd_error (outer product)
        grad_W_out = np.outer(h_fwd, fwd_error)
        grad_b_out = fwd_error.copy()

        # 反向传播到 hidden
        hidden_grad_fwd = fwd_error @ self.W_fwd_out.T
        relu_deriv = self._relu_deriv(combined_fwd @ self.W_fwd + self.b_fwd)
        delta_fwd = hidden_grad_fwd * relu_deriv

        grad_W_fwd = np.outer(combined_fwd, delta_fwd)
        grad_b_fwd = delta_fwd

        self.W_fwd_out -= grad_W_out * self.lr
        self.b_fwd_out -= grad_b_out * self.lr
        self.W_fwd -= grad_W_fwd * self.lr
        self.b_fwd -= grad_b_fwd * self.lr

        # ── 逆模型更新 ──
        combined_inv = np.concatenate([phi, phi_next])
        h_inv = self._relu(combined_inv @ self.W_inv + self.b_inv)
        pred_action = h_inv @ self.W_inv_out + self.b_inv_out

        inv_error = pred_action - action
        inv_loss = np.mean(inv_error ** 2)
        self.inverse_losses.append(inv_loss)

        grad_W_inv_out = np.outer(h_inv, inv_error)
        grad_b_inv_out = inv_error.copy()

        self.W_inv_out -= grad_W_inv_out * self.lr
        self.b_inv_out -= grad_b_inv_out * self.lr

        self.n_updates += 1
        return {'fwd_loss': float(fwd_loss), 'inv_loss': float(inv_loss)}

    def get_curiosity_score(self, state, action, next_state):
        """归一化好奇心分数 (0-1)"""
        raw = self.curiosity(state, action, next_state)
        history = list(self.curiosity_history) + [raw]
        if len(history) < 2:
            return 0.5
        mean_c = np.mean(history)
        std_c = np.std(history) + 1e-8
        normalized = (raw - mean_c) / std_c
        return float(1.0 / (1.0 + math.exp(-normalized)))  # sigmoid

    def status(self) -> dict:
        return {
            'updates': self.n_updates,
            'fwd_loss': round(float(np.mean(self.forward_losses)), 4) if self.forward_losses else 0,
            'inv_loss': round(float(np.mean(self.inverse_losses)), 4) if self.inverse_losses else 0,
            'avg_curiosity': round(float(np.mean(self.curiosity_history)), 4) if self.curiosity_history else 0,
        }


# ═══════════════════════════════════════════════
# 2. 好奇心驱动的探索器
# ═══════════════════════════════════════════════

class CuriosityDrivenExplorer:
    """
    好奇心驱动的探索 — 最顶层
    整合 Novelty Search 和 ICM

    决策逻辑:
      新颖度 + 好奇心 = 综合探索价值
      高新颖 + 低好奇 → 可能是噪声, 降低优先级
      低新颖 + 高好奇 → 模型不理解已知区域, 需要深入学习
      高新颖 + 高好奇 → 真正的未知, 最高优先级
    """

    def __init__(self, state_dim=12, action_dim=8):
        self.icm = IntrinsicCuriosityModule(state_dim=state_dim, action_dim=action_dim)
        self.exploration_value = deque(maxlen=200)  # 历史探索价值
        self.state_buffer = deque(maxlen=10)         # 最近的状态
        self.action_buffer = deque(maxlen=10)        # 最近的动作

    def record_transition(self, state, action, next_state):
        """
        记录一次状态转移: s + a → s'
        在线更新 ICM
        """
        self.state_buffer.append(state)
        self.action_buffer.append(action)
        result = self.icm.update(state, action, next_state)
        return result

    def score(self, state, action, predicted_next, novelty_score=0.5) -> dict:
        """
        综合评分: 好奇心 × 新颖度
        好奇心 → 内在动机 (预测误差)
        新颖度 → 外部新奇 (行为空间稀疏)
        """
        curiosity = self.icm.get_curiosity_score(state, action, predicted_next)

        # 组合: 好奇心和新颖度取最大值 (只要有任一理由就该探索)
        # + 乘法项: 两者都高时额外奖励
        combined = max(curiosity, novelty_score) + curiosity * novelty_score * 0.3
        combined = min(1.0, combined)

        self.exploration_value.append(combined)

        return {
            'curiosity': round(curiosity, 3),
            'novelty': round(novelty_score, 3),
            'combined': round(combined, 3),
            'interpretation': (
                'deep_exploration' if curiosity > 0.5 and novelty_score > 0.4
                else 'correct_confusion' if curiosity > 0.5
                else 'surface_novelty' if novelty_score > 0.4
                else 'well_understood'
            ),
        }

    def suggest_action(self, state, n_candidates=5) -> np.ndarray:
        """
        建议探索动作 — 在动作空间随机采样, 选好奇心最高的
        """
        best_action = None
        best_curiosity = -1

        for _ in range(n_candidates):
            candidate_action = np.random.randn(self.icm.action_dim) * 0.5
            predicted_next = self.icm.predict_next(state, candidate_action)
            c = self.icm.curiosity(state, candidate_action, predicted_next)
            if c > best_curiosity:
                best_curiosity = c
                best_action = candidate_action

        return best_action if best_action is not None else np.random.randn(self.icm.action_dim) * 0.3

    def status(self) -> dict:
        icm_status = self.icm.status()
        icm_status['avg_exploration_value'] = round(
            float(np.mean(self.exploration_value)), 3) if self.exploration_value else 0
        return icm_status


# ═══════════════════════════════════════════════
# 3. 自检
# ═══════════════════════════════════════════════

if __name__ == '__main__':
    print("Verix Curiosity Module — Pathak et al. 2017 ICML")

    explorer = CuriosityDrivenExplorer(state_dim=12, action_dim=8)

    print("\n  在线学习 (20 步):")
    for step in range(20):
        state = np.random.randn(12) * 0.3
        state[0] = (step % 5) * 0.6  # 5 种不同区域

        action = explorer.suggest_action(state, n_candidates=5)
        # 模拟: 越陌生区域预测越不准, action只影响前8维
        full_action = np.pad(action, (0, 4))  # 8→12维
        next_state = state + full_action * 0.3 + np.random.randn(12) * (0.1 + 0.2 * (step % 5) / 5)

        result = explorer.record_transition(state, action, next_state)
        c_score = explorer.icm.get_curiosity_score(state, action, next_state)

        if step < 3 or step % 5 == 0:
            print(f"    step{step:2d}: fwd_loss={result['fwd_loss']:.4f} "
                  f"curiosity={c_score:.3f} ICM_updates={explorer.icm.n_updates}")

    # 综合评分
    state = np.random.randn(12) * 0.3
    action = explorer.suggest_action(state)
    full_action = np.pad(action, (0, 4))
    next_state = state + full_action * 0.3 + np.random.randn(12) * 0.1
    score = explorer.score(state, action, next_state, novelty_score=0.6)
    print(f"\n  综合评分: {score}")

    print(f"\n  ICM 状态: {explorer.icm.status()}")
    print(f"  好奇心状态: {explorer.status()}")

    print("\n✓ Curiosity Module 就绪")
