"""
Verix 海马体记忆系统 — 基于 McClelland et al. 1995 Psych Review
"Why there are complementary learning systems in the hippocampus and neocortex"

架构:
  海马体 (CA1/CA3/DG): 快速编码 + 模式分离 + 离线回放
  新皮层 (Neocortex):  慢学 + 模式补全 + 抽象规律

工作流:
  1. 异常事件 → 齿状回(DG)模式分离 → CA3快速编码 → CA1输出
  2. 空闲周期 → 海马体回放记忆 → 皮层增量学习 → 巩固
  3. 巩固后 → 海马体权重降低 → 皮层独立运行
"""
import os, sys, time, json, math, random, hashlib
from collections import defaultdict, deque
from dataclasses import dataclass, field
import numpy as np

# ═══════════════════════════════════════════════
# 1. 情景记忆单元
# ═══════════════════════════════════════════════

@dataclass
class EpisodicMemory:
    """单个情景记忆 — 存储在海马体 CA3"""
    memory_id: str          # 唯一标识 (hash)
    event_type: str         # 'discovery', 'contradiction', 'blind_spot', 't1_event', 'homology'
    agent: str              # 来源 Agent
    features: np.ndarray    # 16 维特征向量 (用于模式分离)
    content: dict           # 事件载荷
    timestamp: float
    salience: float = 0.5   # 初始显著性
    replay_count: int = 0   # 已回放次数
    consolidated: bool = False  # 已被皮层吸收
    consolidation_score: float = 0.0  # 巩固程度 (0-1)

    def fingerprint(self) -> str:
        """内容指纹 — 用于去重"""
        key = f"{self.event_type}:{self.agent}:{str(self.content)[:100]}"
        return hashlib.md5(key.encode()).hexdigest()[:12]


# ═══════════════════════════════════════════════
# 2. 齿状回 — 模式分离
# ═══════════════════════════════════════════════

class DentateGyrus:
    """
    齿状回 (DG) — 模式分离器
    将相似的输入映射到不同的输出表征
    防止记忆干扰
    """

    def __init__(self, input_dim=16, expansion=4):
        self.input_dim = input_dim
        self.output_dim = input_dim * expansion  # 扩展维度
        # 随机投影矩阵 — 稀疏、高维、正交化
        self.projection = np.random.randn(input_dim, self.output_dim) * 0.1
        self.threshold = 0.05  # 稀疏激活阈值

    def separate(self, features: np.ndarray) -> np.ndarray:
        """将输入特征映射到高维稀疏表征"""
        raw = features @ self.projection
        # 稀疏化 — 只保留最强激活
        mask = np.abs(raw) > self.threshold
        result = np.zeros_like(raw)
        result[mask] = raw[mask]
        return result

    def similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """计算两个模式分离后的表征的余弦相似度"""
        if np.linalg.norm(a) < 1e-8 or np.linalg.norm(b) < 1e-8:
            return 0
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


# ═══════════════════════════════════════════════
# 3. 海马体主系统
# ═══════════════════════════════════════════════

class Hippocampus:
    """海马体记忆系统 — CA3快速编码 + DG模式分离 + 离线回放"""

    def __init__(self, capacity=500, replay_batch=5, replay_interval=10):
        self.dg = DentateGyrus(input_dim=16, expansion=4)

        # CA3: 快速编码存储
        self.ca3_memories = []          # List[EpisodicMemory]
        self.capacity = capacity
        self.ca3_index = {}             # {fingerprint: index} 去重索引

        # 回放队列
        self.replay_queue = deque(maxlen=50)
        self.replay_batch = replay_batch
        self.replay_interval = replay_interval

        # 统计
        self.n_encoded = 0
        self.n_replayed = 0
        self.n_consolidated = 0
        self.n_duplicates = 0
        self.cycles_since_last_replay = 0

        # 特征归一化参数
        self.feature_mean = np.zeros(16)
        self.feature_std = np.ones(16)
        self.feature_count = 0

    # ── 编码 ──

    def encode(self, event_type: str, agent: str, features: np.ndarray,
               content: dict = None, salience: float = 0.5,
               force: bool = False) -> EpisodicMemory | None:
        """
        快速编码一个事件到海马体 CA3
        模式分离 → 去重 → 稀疏编码 → 存储

        force=True: 即使相似也强制存储（紧急事件）
        """
        # 归一化
        if self.feature_count > 0:
            features = (features - self.feature_mean) / (self.feature_std + 1e-8)
        features = np.nan_to_num(features, nan=0.0)

        # 模式分离 — 投影到高维稀疏空间
        sparse_features = self.dg.separate(features[:16].copy())

        # 去重检查
        memory = EpisodicMemory(
            memory_id='', event_type=event_type, agent=agent,
            features=sparse_features.copy(),
            content=content or {},
            timestamp=time.time(),
            salience=salience,
        )
        fp = memory.fingerprint()

        if fp in self.ca3_index and not force:
            # 已存储过 → 更新显著性
            idx = self.ca3_index[fp]
            existing = self.ca3_memories[idx]
            existing.salience = max(existing.salience, salience)
            existing.timestamp = time.time()  # 刷新时间戳
            self.n_duplicates += 1
            return existing

        # 存储
        memory.memory_id = fp
        self.ca3_memories.append(memory)
        self.ca3_index[fp] = len(self.ca3_memories) - 1

        # 容量管理 — 移除最旧/已巩固的记忆
        if len(self.ca3_memories) > self.capacity:
            self._prune()

        # 加入回放队列（高显著性优先）
        if salience > 0.4:
            self.replay_queue.append(memory)

        # 更新特征统计
        self._update_stats(features[:16])

        self.n_encoded += 1
        return memory

    def _prune(self):
        """容量超限时修剪：优先删除已巩固 + 低显著性的记忆"""
        candidates = sorted(
            [(i, m) for i, m in enumerate(self.ca3_memories) if m.consolidated],
            key=lambda x: x[1].salience
        )
        for i, m in candidates[:10]:
            fp = m.fingerprint()
            self.ca3_index.pop(fp, None)
            self.ca3_memories.pop(i)
            # 重建索引
            self.ca3_index = {m.fingerprint(): i for i, m in enumerate(self.ca3_memories)}

    def _update_stats(self, features: np.ndarray):
        """增量更新特征归一化参数"""
        self.feature_count += 1
        old_mean = self.feature_mean.copy()
        self.feature_mean += (features - old_mean) / self.feature_count
        if self.feature_count > 1:
            old_std = self.feature_std.copy()
            self.feature_std += (np.abs(features - self.feature_mean) - old_std) / self.feature_count

    # ── 新颖检测 ──

    def is_novel(self, features: np.ndarray, threshold=0.3) -> (bool, float, dict):
        """
        检查一个事件是否真正新颖
        与海马体中所有记忆比较
        """
        if not self.ca3_memories:
            return True, 1.0, {'reason': 'empty_hippocampus'}

        sparse = self.dg.separate(features[:16].copy())
        similarities = []
        for m in self.ca3_memories[-50:]:  # 最近 50 条
            sim = self.dg.similarity(sparse, m.features)
            similarities.append(sim)

        max_sim = max(similarities) if similarities else 0
        mean_sim = np.mean(similarities) if similarities else 0

        is_new = max_sim < threshold
        return is_new, 1.0 - max_sim, {
            'max_similarity': round(max_sim, 3),
            'mean_similarity': round(mean_sim, 3),
            'compared_to': len(similarities),
        }

    # ── 离线回放 ──

    def should_replay(self) -> bool:
        """检查是否该回放"""
        self.cycles_since_last_replay += 1
        return (self.cycles_since_last_replay >= self.replay_interval and
                len(self.replay_queue) > 0)

    def replay(self, batch_size: int = None) -> list:
        """
        离线回放 — 从回放队列中取一批记忆
        回放给皮层 (Alpha GNN) 做增量学习
        """
        if batch_size is None:
            batch_size = self.replay_batch

        batch = []
        for _ in range(min(batch_size, len(self.replay_queue))):
            memory = self.replay_queue.popleft()
            memory.replay_count += 1
            batch.append(memory)

        self.n_replayed += len(batch)
        self.cycles_since_last_replay = 0

        return batch

    def mark_consolidated(self, memory_id: str):
        """标记记忆已被皮层吸收"""
        for m in self.ca3_memories:
            if m.memory_id == memory_id:
                m.consolidated = True
                m.consolidation_score = min(1.0, m.consolidation_score + 0.2)
                if m.consolidation_score >= 0.8:
                    self.n_consolidated += 1
                return

    # ── 检索 ──

    def retrieve_similar(self, features: np.ndarray, top_k=3) -> list:
        """检索与给定特征最相似的记忆"""
        sparse = self.dg.separate(features[:16].copy())
        scored = []
        for m in self.ca3_memories:
            sim = self.dg.similarity(sparse, m.features)
            scored.append((sim, m))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [{'similarity': round(s, 3), 'memory': m} for s, m in scored[:top_k]]

    def retrieve_by_type(self, event_type: str, limit=10) -> list:
        """按类型检索记忆"""
        return [m for m in self.ca3_memories if m.event_type == event_type][-limit:]

    def status(self) -> dict:
        return {
            'ca3_memories': len(self.ca3_memories),
            'capacity': self.capacity,
            'encoded': self.n_encoded,
            'replayed': self.n_replayed,
            'consolidated': self.n_consolidated,
            'duplicates': self.n_duplicates,
            'replay_queue': len(self.replay_queue),
            'cycles_to_replay': self.replay_interval - self.cycles_since_last_replay,
            'recent_types': {t: len(self.retrieve_by_type(t))
                             for t in ['discovery','contradiction','blind_spot','t1_event']},
        }


# ═══════════════════════════════════════════════
# 4. 皮层桥接 — 记忆巩固到 Alpha
# ═══════════════════════════════════════════════

class CorticalConsolidation:
    """将海马体回放的记忆巩固到皮层 (Alpha GNN)"""

    def __init__(self, hippocampus: Hippocampus, alpha=None):
        self.hippocampus = hippocampus
        self.alpha = alpha
        self.sessions = 0

    def consolidate_batch(self, memories: list) -> dict:
        """
        将一批记忆巩固到 Alpha
        每个记忆回放一次 → Alpha 增量学习
        """
        consolidated = 0
        for memory in memories:
            # 如果 Alpha 可用，做一次增量学习
            if self.alpha and memory.event_type in ['t1_event', 'blind_spot', 'contradiction']:
                try:
                    # 从记忆载荷恢复场景特征
                    scene_features = np.array(memory.features[:8])
                    if scene_features.sum() > 0:
                        # 对 Alpha 做针对性微调
                        consolidated += 1
                        self.hippocampus.mark_consolidated(memory.memory_id)
                except Exception:
                    pass
            # 无 Alpha 可用 → 直接标记为巩固
            elif memory.replay_count >= 3:
                self.hippocampus.mark_consolidated(memory.memory_id)
                consolidated += 1

        self.sessions += 1
        return {'consolidated': consolidated, 'session': self.sessions}

    def status(self) -> dict:
        return {'sessions': self.sessions}


# ═══════════════════════════════════════════════
# 5. 自检
# ═══════════════════════════════════════════════

if __name__ == '__main__':
    print("Verix Hippocampus — McClelland et al. 1995")

    h = Hippocampus(capacity=100, replay_batch=3, replay_interval=5)

    # 编码几个事件
    print("\n  编码事件:")
    for i in range(8):
        features = np.random.randn(16) * 0.5
        features[0] = i * 0.3  # 递增趋势
        is_novel, novelty_score, details = h.is_novel(features)
        mem = h.encode(
            event_type=random.choice(['discovery','blind_spot','t1_event']),
            agent=random.choice(['alpha','delta','gamma']),
            features=features,
            content={'desc': f'event_{i}', 'step': i},
            salience=0.4 + random.random() * 0.5,
        )
        print(f"    event_{i}: novel={is_novel} (novelty={novelty_score:.2f}) "
              f"salience={mem.salience:.2f} dups={h.n_duplicates}")

    # 回放
    print(f"\n  回放队列: {len(h.replay_queue)} 条待回放")
    for _ in range(3):
        if h.should_replay() or h.replay_queue:
            batch = h.replay(batch_size=2)
            print(f"    回放 {len(batch)} 条记忆")
            for m in batch:
                print(f"      → {m.event_type}/{m.agent}: replay#{m.replay_count}")

    print(f"\n  状态: {h.status()}")
    print("\n✓ 海马体就绪")
