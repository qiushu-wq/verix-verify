"""
Verix Novelty Search — 基于 Lehman & Stanley 2011
"Abandoning Objectives: Evolution through the Search for Novelty Alone"

核心洞察:
  优化目标函数 → 陷入局部最优 → 错过更好的解
  只搜索新行为 → 自然覆盖全部解空间 → 最终找到更多解

实现:
  1. 行为存档 (Archive): 记录所有历史行为特征
  2. 新颖度评分: 到 k 个最近邻居的平均距离
  3. 新行为入档: 距离 > 阈值 → 加入存档
  4. 探索驱动: 新颖度最高 → 最优先探索
"""
import os, sys, time, json, math, random
from collections import defaultdict, deque
import numpy as np
from scipy.spatial import KDTree

# ═══════════════════════════════════════════════
# 1. 行为特征空间
# ═══════════════════════════════════════════════

class BehaviorCharacterizer:
    """将探索结果映射到行为特征空间"""

    FEATURE_DIMS = 12

    @staticmethod
    def from_scene(scene) -> np.ndarray:
        """从物理场景提取行为特征"""
        if scene is None:
            return np.zeros(BehaviorCharacterizer.FEATURE_DIMS)

        objects = scene.objects if hasattr(scene, 'objects') else []
        n = len(objects)
        masses = [o.get('mass', 0) for o in objects]
        speeds = [math.sqrt(sum(v**2 for v in o.get('vel', [0,0,0]))) for o in objects]
        heights = [o.get('pos', [0,0,0])[2] for o in objects]
        sizes = [o.get('size', [0])[0] for o in objects]

        return np.array([
            n / 10,                                     # 物体数
            np.mean(masses) if masses else 0,           # 平均质量
            np.var(masses) if len(masses) > 1 else 0,   # 质量方差
            np.mean(speeds) if speeds else 0,           # 平均速度
            np.var(speeds) if len(speeds) > 1 else 0,   # 速度方差
            np.var(heights) if len(heights) > 1 else 0, # 高度方差
            n * (n-1) / 20,                             # 接触密度
            np.mean(sizes) if sizes else 0,             # 平均尺寸
            np.var(sizes) if len(sizes) > 1 else 0,     # 尺寸方差
            np.abs(np.mean(heights)) if heights else 0, # 平均高度
            sum(0.5*m*s*s for m,s in zip(masses, speeds)) / 10,  # 动能
            random.random() * 0.01,                     # 微小噪音防退化
        ])

    @staticmethod
    def from_discovery(discovery_type: str, region: str, rmse: float = 0) -> np.ndarray:
        """从发现结果提取行为特征"""
        type_hash = sum(ord(c) for c in discovery_type) % 100 / 100.0
        region_hash = sum(ord(c) for c in region) % 100 / 100.0
        return np.array([
            type_hash, region_hash, rmse,
            random.random() * 0.01, 0, 0, 0, 0, 0, 0, 0, 0,
        ])


# ═══════════════════════════════════════════════
# 2. 新颖度存档
# ═══════════════════════════════════════════════

class NoveltyArchive:
    """
    行为存档 — 记录所有见过的行为特征
    新行为距离 = 到 k 个最近存档行为的平均距离
    """

    def __init__(self, k=5, add_threshold=0.3, max_size=500):
        self.k = k                      # k 近邻
        self.add_threshold = add_threshold  # 入档阈值
        self.max_size = max_size        # 存档上限

        self.archive = []               # 所有已存档行为
        self.archive_features = []      # 对应的特征向量 (用于 KDTree)
        self.kdtree = None              # 快速最近邻搜索
        self.needs_rebuild = True

        self.n_added = 0
        self.n_rejected = 0
        self.novelty_history = []       # 最近的新颖度分数

    def _rebuild_tree(self):
        if len(self.archive_features) < self.k:
            return
        features = np.array(self.archive_features)
        self.kdtree = KDTree(features)
        self.needs_rebuild = False

    def novelty(self, features: np.ndarray) -> (float, int):
        """
        计算一个行为的新颖度
        = 到 k 个最近邻居的平均距离

        Returns: (novelty_score, n_neighbors_found)
        """
        if len(self.archive_features) < self.k:
            return 1.0, len(self.archive_features)  # 样本太少 → 高新颖度

        if self.needs_rebuild or self.kdtree is None:
            self._rebuild_tree()

        if self.kdtree is None:
            return 1.0, 0

        features = np.nan_to_num(features, nan=0.0)
        k_eff = min(self.k, len(self.archive_features))
        distances, _ = self.kdtree.query(features, k=k_eff)
        novelty_score = float(np.mean(distances)) if k_eff > 0 else 1.0
        return novelty_score, k_eff

    def add(self, features: np.ndarray, metadata: dict = None) -> bool:
        """
        尝试将行为加入存档
        只有新颖度 > 阈值的才入档（保证存档多样性）
        """
        nov, _ = self.novelty(features)

        if nov < self.add_threshold and len(self.archive) > self.k:
            self.n_rejected += 1
            return False

        self.archive.append({
            'features': features.tolist(),
            'novelty': nov,
            'time': time.time(),
            'metadata': metadata or {},
        })
        self.archive_features.append(features.copy())
        self.needs_rebuild = True
        self.n_added += 1

        # 容量管理: 移除最旧的
        if len(self.archive) > self.max_size:
            oldest = min(self.archive, key=lambda x: x['time'])
            idx = self.archive.index(oldest)
            self.archive.pop(idx)
            self.archive_features.pop(idx)
            self.needs_rebuild = True

        self.novelty_history.append(nov)
        return True

    def get_most_novel(self, candidates: list) -> list:
        """
        从候选列表中返回新颖度最高的
        candidates: [(features, metadata), ...]
        """
        scored = []
        for features, meta in candidates:
            nov, _ = self.novelty(features)
            scored.append((nov, features, meta))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    def status(self) -> dict:
        recent_nov = np.mean(self.novelty_history[-20:]) if self.novelty_history else 0
        return {
            'archive_size': len(self.archive),
            'added': self.n_added,
            'rejected': self.n_rejected,
            'threshold': self.add_threshold,
            'avg_recent_novelty': round(float(recent_nov), 3),
            'diversity': round(len(self.archive) / max(self.n_added, 1), 3),
        }


# ═══════════════════════════════════════════════
# 3. 新颖度驱动的探索器
# ═══════════════════════════════════════════════

class NoveltyDrivenExplorer:
    """
    替代 ActiveExplorer 的置信度评分
    用新颖度决定探索方向
    """

    def __init__(self, active_explorer, capacity=500):
        self.explorer = active_explorer
        self.archive = NoveltyArchive(k=5, add_threshold=0.25, max_size=capacity)
        self.char = BehaviorCharacterizer()
        self.forced_novelty_checks = 0

    def rank_targets(self, targets: list) -> list:
        """
        对探索目标按新颖度排序（替代置信度排序）
        """
        scored_targets = []
        for target in targets:
            # 从 target 提取行为特征
            features = self.char.from_discovery(
                target.get('type', 'unknown'),
                target.get('region', 'unknown'),
                target.get('rmse', 0),
            )
            nov, _ = self.archive.novelty(features)
            scored_targets.append((nov, target, features))

        # 新颖度高的优先
        scored_targets.sort(key=lambda x: x[0], reverse=True)
        return scored_targets

    def record_behavior(self, scene=None, discovery_type='unknown',
                        region='unknown', rmse=0.0, metadata=None) -> dict:
        """
        记录一个行为到存档
        """
        if scene:
            features = self.char.from_scene(scene)
        else:
            features = self.char.from_discovery(discovery_type, region, rmse)

        nov, k = self.archive.novelty(features)
        is_new = nov > self.archive.add_threshold

        self.archive.add(features, metadata or {
            'type': discovery_type, 'region': region, 'rmse': rmse})

        if is_new:
            self.forced_novelty_checks += 1

        return {'novelty': round(nov, 3), 'is_new': is_new,
                'neighbors': k, 'archive_size': len(self.archive.archive)}

    def suggest_exploration(self, n_suggestions=3) -> list:
        """
        建议下一步探索方向 — 基于行为空间空白
        在存档的稀疏区域生成新目标
        """
        suggestions = []
        if len(self.archive.archive_features) < 3:
            # 存档太少 → 随机探索
            return [{'type': 'random', 'reason': 'insufficient_archive'}]

        features = np.array(self.archive.archive_features)
        # 找离所有存档点最远的区域
        centroid = features.mean(axis=0)
        distances = np.linalg.norm(features - centroid, axis=1)
        far_idx = np.argmax(distances)

        # 在最远点附近生成变体
        far_point = features[far_idx]
        for i in range(n_suggestions):
            variation = far_point + np.random.randn(len(far_point)) * 0.2
            nov, _ = self.archive.novelty(variation)
            suggestions.append({
                'type': 'novelty_driven',
                'novelty': round(nov, 3),
                'base_region': self.archive.archive[far_idx].get('metadata', {}).get('region', 'unknown'),
            })
            far_point = variation

        return suggestions

    def status(self) -> dict:
        return {
            'archive': self.archive.status(),
            'forced_checks': self.forced_novelty_checks,
        }


# ═══════════════════════════════════════════════
# 4. 自检
# ═══════════════════════════════════════════════

if __name__ == '__main__':
    print("Verix Novelty Search — Lehman & Stanley 2011")

    archive = NoveltyArchive(k=3, add_threshold=0.3)

    # 模拟探索 20 步
    print("\n  模拟探索:")
    for i in range(20):
        # 随机行为（模拟探索产出）
        behavior = np.random.randn(12) * 0.3
        behavior[0] = (i % 4) * 0.5  # 4 种不同模式

        nov, k = archive.novelty(behavior)
        added = archive.add(behavior, {'step': i})
        status = '★ 新' if added else '·'
        print(f"    step{i:2d}: novelty={nov:.3f} (k={k}) {status}  archive={len(archive.archive)}")

    # 测试：找最稀疏区域
    print(f"\n  存档: {archive.status()}")

    # 候选排序
    candidates = [(np.random.randn(12), {'id': f'test_{i}'}) for i in range(5)]
    ranked = archive.get_most_novel(candidates)
    print(f"\n  候选排序 (按新颖度):")
    for nov, feat, meta in ranked[:3]:
        print(f"    {meta['id']}: novelty={nov:.3f}")

    print("\n✓ Novelty Search 就绪")
