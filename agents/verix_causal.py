"""
Verix Causal — 简化 VCD 因果发现引擎
基于: Lei, Schölkopf, Posner (2022) Variational Causal Dynamics
核心: 可学习因果图 + 稀疏机制偏移检测 + 跨域因果同构
"""
import os, sys, json, time, math, random
from collections import defaultdict
import numpy as np

# ═══════════════════════════════════════════════
# 1. 可学习因果图 (Differentiable Causal Graph)
# ═══════════════════════════════════════════════

class CausalGraph:
    """
    可学习的有向因果图
    使用 NOTEARS 启发的稀疏正则化 + 结构约束
    """
    def __init__(self, n_vars=8, sparsity_lambda=0.1):
        self.n_vars = n_vars
        self.sparsity_lambda = sparsity_lambda
        # 邻接矩阵 W[i,j] = 从 j→i 的因果强度
        self.W = np.random.randn(n_vars, n_vars) * 0.01
        self.mask = np.ones((n_vars, n_vars)) - np.eye(n_vars)  # 禁止自环
        self.history = []  # 记录 W 的变化历史

    def get_parents(self, i: int) -> list:
        """返回变量 i 的因果父节点（强度 > 阈值）"""
        threshold = 0.1
        parents = np.where(np.abs(self.W[i]) > threshold)[0]
        return [int(p) for p in parents]

    def get_children(self, i: int) -> list:
        """返回变量 i 的因果子节点"""
        threshold = 0.1
        children = np.where(np.abs(self.W[:, i]) > threshold)[0]
        return [int(c) for c in children]

    def get_structure(self) -> dict:
        """返回当前因果结构"""
        edges = []
        for i in range(self.n_vars):
            for j in self.get_parents(i):
                edges.append({'from': j, 'to': i, 'strength': float(self.W[i, j])})
        return {
            'n_vars': self.n_vars,
            'n_edges': len(edges),
            'edges': edges,
            'sparsity': 1.0 - len(edges) / (self.n_vars * (self.n_vars - 1)),
        }

    def update(self, data: np.ndarray, lr=0.01):
        """
        从数据更新因果图
        data: (n_samples, n_vars) 观测数据
        使用简化 NOTEARS: 最小化 ||X - XW||² + λ||W||₁
        约束: W 必须是无环的 (dagness penalty)
        """
        n = data.shape[0]
        if n < 2:
            return

        # 标准化
        X = (data - data.mean(axis=0)) / (data.std(axis=0) + 1e-8)

        # 梯度: W ← W - lr * (-2Xᵀ(X - XW)/n + λ*sign(W))
        residual = X - X @ self.W
        grad = -2 * X.T @ residual / n + self.sparsity_lambda * np.sign(self.W)

        # DAG 约束: trace(e^W) - n_vars 的梯度
        # 简化: 用 W @ W @ W 近似惩罚长路径
        dag_penalty = self.W @ self.W
        grad += 0.01 * dag_penalty

        self.W -= lr * grad * self.mask
        self.W = np.clip(self.W, -1, 1)

        self.history.append({
            'time': time.time(),
            'n_edges': len(self.get_structure()['edges']),
            'max_strength': float(np.max(np.abs(self.W))),
        })

    def detect_shift(self, data_new: np.ndarray, data_old: np.ndarray) -> dict:
        """
        检测哪些因果机制在旧/新环境之间发生了变化
        (Sparse Mechanism Shift detection)
        """
        if data_old.shape[0] < 2 or data_new.shape[0] < 2:
            return {'shifted_vars': [], 'shift_magnitude': 0}

        X_old = (data_old - data_old.mean(axis=0)) / (data_old.std(axis=0) + 1e-8)
        X_new = (data_new - data_new.mean(axis=0)) / (data_new.std(axis=0) + 1e-8)

        # 比较每个变量的残差方差
        shifts = []
        for i in range(self.n_vars):
            parents = self.get_parents(i)
            if not parents:
                continue
            # 旧环境残差
            pred_old = X_old[:, parents] @ self.W[i, parents]
            resid_old = np.var(X_old[:, i] - pred_old)
            # 新环境残差
            pred_new = X_new[:, parents] @ self.W[i, parents]
            resid_new = np.var(X_new[:, i] - pred_new)

            ratio = resid_new / (resid_old + 1e-8)
            if ratio > 2.0 or ratio < 0.5:  # 显著变化
                shifts.append({
                    'var': i, 'parents': parents,
                    'old_resid': float(resid_old), 'new_resid': float(resid_new),
                    'ratio': float(ratio),
                })

        return {
            'shifted_vars': shifts,
            'n_shifted': len(shifts),
            'shift_magnitude': sum(s['ratio'] for s in shifts) if shifts else 0,
        }

    def compare_to(self, other: 'CausalGraph') -> dict:
        """比较两个因果图的相似度 (用于跨域同构发现)"""
        my_edges = set()
        other_edges = set()
        for i in range(self.n_vars):
            for j in self.get_parents(i):
                my_edges.add((j, i))
        for i in range(other.n_vars):
            for j in other.get_parents(i):
                other_edges.add((min(j, i), max(j, i)))  # 对齐不同维度

        if not my_edges or not other_edges:
            return {'similarity': 0, 'shared': 0}

        shared = my_edges & other_edges
        # 放宽: 允许1偏移
        relaxed_shared = set()
        for (a, b) in my_edges:
            for (c, d) in other_edges:
                if abs(a - c) <= 1 and abs(b - d) <= 1:
                    relaxed_shared.add((a, b))

        similarity = len(relaxed_shared) / max(len(my_edges), 1)
        return {
            'similarity': round(similarity, 3),
            'shared_edges': len(shared),
            'relaxed_shared': len(relaxed_shared),
            'my_edges': len(my_edges),
            'other_edges': len(other_edges),
        }


# ═══════════════════════════════════════════════
# 2. 因果特征提取器
# ═══════════════════════════════════════════════

class CausalFeatureExtractor:
    """从物理场景提取因果相关特征"""

    FEATURE_NAMES = [
        'n_objects',       # 0: 物体数量
        'mass_mean',       # 1: 平均质量
        'mass_var',        # 2: 质量方差
        'speed_mean',      # 3: 平均速度
        'speed_var',       # 4: 速度方差
        'height_var',      # 5: 高度方差
        'contact_density', # 6: 接触密度
        'energy',          # 7: 总动能
    ]

    @staticmethod
    def extract(scene) -> np.ndarray:
        """从 PhysicsScene 提取 8 维因果特征向量"""
        objects = scene.objects
        n = len(objects)
        masses = [o['mass'] for o in objects]
        speeds = [math.sqrt(o['vel'][0]**2 + o['vel'][1]**2 + o['vel'][2]**2) for o in objects]
        heights = [o['pos'][2] for o in objects]

        features = np.array([
            n,
            np.mean(masses) if masses else 0,
            np.var(masses) if len(masses) > 1 else 0,
            np.mean(speeds) if speeds else 0,
            np.var(speeds) if len(speeds) > 1 else 0,
            np.var(heights) if len(heights) > 1 else 0,
            n * (n - 1) / 2,  # 近似接触密度
            sum(0.5 * m * s**2 for m, s in zip(masses, speeds)),  # 总动能
        ])
        return features

    @staticmethod
    def extract_batch(scenes: list) -> np.ndarray:
        """批量提取特征"""
        return np.array([CausalFeatureExtractor.extract(s) for s in scenes])


# ═══════════════════════════════════════════════
# 3. 因果世界模型 (VCD 简化版)
# ═══════════════════════════════════════════════

class CausalWorldModel:
    """VCD 简化版——因果结构化的世界模型"""

    def __init__(self, n_vars=8, history_size=200):
        self.graph = CausalGraph(n_vars=n_vars)
        self.feature_extractor = CausalFeatureExtractor()
        self.n_vars = n_vars
        self.feature_history = []  # 最近的特征（用于训练因果图）
        self.history_size = history_size
        self.invariant_mechanisms = set()  # 跨环境不变机制
        self.environments = {}  # {env_name: CausalGraph snapshot}

    def observe(self, scene) -> dict:
        """观察一个场景，提取特征并更新因果图"""
        features = self.feature_extractor.extract(scene)
        self.feature_history.append(features)
        if len(self.feature_history) > self.history_size:
            self.feature_history.pop(0)

        # 每积累 10 个样本更新一次因果图
        if len(self.feature_history) >= 10 and len(self.feature_history) % 5 == 0:
            data = np.array(self.feature_history[-50:])
            self.graph.update(data)

        return {
            'features': features.tolist(),
            'structure': self.graph.get_structure(),
        }

    def snapshot_environment(self, env_name: str):
        """保存当前环境的因果快照"""
        import copy
        self.environments[env_name] = {
            'W': self.graph.W.copy(),
            'structure': self.graph.get_structure(),
            'time': time.time(),
        }

    def detect_cross_env_shift(self, env_a: str, env_b: str) -> dict:
        """检测两个环境之间的稀疏机制偏移"""
        if env_a not in self.environments or env_b not in self.environments:
            return {'shifted_vars': [], 'error': 'environment not found'}

        W_a = self.environments[env_a]['W']
        W_b = self.environments[env_b]['W']

        # 比较哪些因果边权重大幅变化
        shifts = []
        for i in range(self.n_vars):
            for j in range(self.n_vars):
                if i == j:
                    continue
                diff = abs(W_a[i, j] - W_b[i, j])
                if diff > 0.15:
                    shifts.append({
                        'from': j, 'to': i,
                        'strength_a': float(W_a[i, j]),
                        'strength_b': float(W_b[i, j]),
                        'delta': float(diff),
                    })

        # 找出不变的部分
        invariant_edges = []
        for i in range(self.n_vars):
            for j in range(self.n_vars):
                if i == j:
                    continue
                if abs(W_a[i, j] - W_b[i, j]) < 0.05 and abs(W_a[i, j]) > 0.1:
                    invariant_edges.append({
                        'from': j, 'to': i,
                        'strength': float(W_a[i, j]),
                    })

        return {
            'n_shifted': len(shifts),
            'shifts': shifts,
            'n_invariant': len(invariant_edges),
            'invariant_edges': invariant_edges,
        }

    def find_causal_homology(self, other_model: 'CausalWorldModel') -> dict:
        """与另一个因果世界模型比较，发现因果同构（供 SAGE 使用）"""
        comparison = self.graph.compare_to(other_model.graph)
        return {
            'similarity': comparison['similarity'],
            'shared_edges': comparison['shared_edges'],
            'homology': comparison['similarity'] > 0.3,  # 阈值
        }

    def status(self) -> dict:
        s = self.graph.get_structure()
        s['n_environments'] = len(self.environments)
        s['n_invariant'] = len(self.invariant_mechanisms)
        s['feature_buffer'] = len(self.feature_history)
        return s


# ═══════════════════════════════════════════════
# 4. 因果桥接 — 连接 SAGE 跨域迁移
# ═══════════════════════════════════════════════

class CausalBridge:
    """因果桥接器——把 VCD 因果发现接入 SAGE 跨域迁移"""

    def __init__(self):
        self.models = {}  # {domain_name: CausalWorldModel}
        self.homologies = []  # 已发现的因果同构

    def register_domain(self, name: str, model: CausalWorldModel):
        self.models[name] = model

    def scan_homologies(self) -> list:
        """扫描所有域对，发现因果同构"""
        domains = list(self.models.keys())
        new_homologies = []
        for i in range(len(domains)):
            for j in range(i + 1, len(domains)):
                a, b = domains[i], domains[j]
                result = self.models[a].find_causal_homology(self.models[b])
                if result['homology']:
                    h = {
                        'domain_a': a, 'domain_b': b,
                        'similarity': result['similarity'],
                        'shared_edges': result['shared_edges'],
                        'time': time.time(),
                    }
                    new_homologies.append(h)
                    # 去重
                    existing = [e for e in self.homologies
                                if set([e['domain_a'], e['domain_b']]) == set([a, b])]
                    if not existing:
                        self.homologies.append(h)
        return new_homologies

    def status(self) -> dict:
        return {
            'domains': list(self.models.keys()),
            'n_homologies': len(self.homologies),
            'homologies': self.homologies[-5:],
        }


# ═══════════════════════════════════════════════
# 5. 自检
# ═══════════════════════════════════════════════

if __name__ == '__main__':
    print("Verix Causal Engine — VCD Simplified")
    cwm = CausalWorldModel(n_vars=8)
    print(f"  变量: {cwm.n_vars}")
    print(f"  因果图: {cwm.graph.get_structure()['n_edges']} 边")

    # 模拟观测数据
    for _ in range(30):
        features = np.random.randn(8)
        cwm.feature_history.append(features)
    cwm.graph.update(np.array(cwm.feature_history))
    print(f"  训练后: {cwm.graph.get_structure()['n_edges']} 边")
    print(f"  父节点: {dict((i, cwm.graph.get_parents(i)) for i in range(8))}")
    print("✓ Causal Engine 就绪")
