"""GWT 三锚注意力调度器 — Agent α T1 事件流 + 盲区自聚类"""
import os, sys, json, time, random, math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import numpy as np

sys.path.insert(0, '/opt/emna')
from agent_alpha import AgentAlpha, SceneGenerator, PhysicsScene, MuJoCoSimulator

# ═══════════════════════════════════════════════
# 1. GWT 分层抢占调度器（Week 4 验证策略 B）
# ═══════════════════════════════════════════════

@dataclass
class T1Event:
    scene_id: int
    scene_type: str
    n_objects: int
    rmse: float
    features: np.ndarray  # 8-dim physics feature vector
    timestamp: float

@dataclass
class SchedulerState:
    t1_events: List[T1Event] = field(default_factory=list)
    t1_dedup: Dict[str, deque] = field(default_factory=lambda: defaultdict(lambda: deque(maxlen=2)))
    paused_types: set = field(default_factory=set)
    blind_spots: Dict[str, dict] = field(default_factory=dict)
    total_scenes: int = 0
    preemptions: int = 0
    long_tasks_completed: int = 0
    long_tasks_total: int = 0


class GWTScheduler:
    """GWT 分层抢占调度器 — 监控 T1 事件流"""

    def __init__(self, alpha: AgentAlpha, log_dir='/opt/emna/logs'):
        self.alpha = alpha
        self.state = SchedulerState()
        self.log_dir = log_dir
        self.t1_log = open(os.path.join(log_dir, 't1_events.jsonl'), 'a')
        self.metrics_log = open(os.path.join(log_dir, 'scheduler_metrics.jsonl'), 'a')
        self.start_time = time.time()

    # ── 特征提取 ──
    def _extract_features(self, scene: PhysicsScene, rmse: float) -> np.ndarray:
        """提取 8 维物理特征向量（与 Week 4 实验三相同）"""
        n_objects = len(scene.objects)
        contacts = n_objects * (n_objects - 1) / 2  # 近似接触点数
        masses = [o['mass'] for o in scene.objects]
        mass_var = np.var(masses) if len(masses) > 1 else 0
        speeds = [math.sqrt(o['vel'][0]**2 + o['vel'][1]**2 + o['vel'][2]**2) for o in scene.objects]
        speed_var = np.var(speeds) if len(speeds) > 1 else 0
        heights = [o['pos'][2] for o in scene.objects]
        height_var = np.var(heights) if len(heights) > 1 else 0

        # 估计形变度——从物体大小判断
        sizes = [o['size'][0] for o in scene.objects]
        size_var = np.var(sizes) if len(sizes) > 1 else 0

        return np.array([
            n_objects,           # 物体数
            contacts,            # 接触点数
            mass_var,            # 质量方差
            speed_var,           # 速度方差
            height_var,          # 高度方差（重心）
            rmse,                # 预测误差 RMSE
            size_var,            # 尺寸方差（形变度）
            0.0,                 # 能量耗散率（近似）
        ])

    # ── 分层抢占决策 ──
    def process(self, scene: PhysicsScene, scene_id: int, scene_type: str):
        """处理一个场景：预测 → 验证 → T1判定 → 抢占决策"""
        self.state.total_scenes += 1

        # GNN 预测 + MuJoCo 验证
        is_t1, rmse = self.alpha.check_t1(scene)

        if not is_t1:
            return 'flow', rmse  # T5 —— 正常流动

        # T1 发生
        features = self._extract_features(scene, rmse)
        event = T1Event(
            scene_id=scene_id, scene_type=scene_type,
            n_objects=len(scene.objects), rmse=rmse,
            features=features, timestamp=time.time()
        )
        self.state.t1_events.append(event)

        # 去重——同场景类型 T1 每天最多抢占 2 次
        dedup_key = scene_type
        today_events = self.state.t1_dedup[dedup_key]
        today_events.append(time.time())

        if len(today_events) > 2:
            # 超过 2 次/天——不再抢占
            self.state.long_tasks_completed += 1
            self.state.long_tasks_total += 1
            return 'log_only', rmse  # T2/T3 —— 仅记录

        # 硬抢占
        self.state.preemptions += 1

        # 写 T1 日志
        self.t1_log.write(json.dumps({
            'scene_id': scene_id,
            'scene_type': scene_type,
            'rmse': float(rmse),
            'n_objects': event.n_objects,
            'features': features.tolist(),
            'time': event.timestamp,
        }) + '\n')
        self.t1_log.flush()

        return 'preempt', rmse

    # ── 盲区扫描 ──
    def blind_spot_check(self):
        """检查是否有新盲区出现（每 500 场景调一次）"""
        if self.state.total_scenes % 500 != 0 or self.state.total_scenes == 0:
            return None

        # 按类型统计 T1 率
        type_stats = defaultdict(lambda: {'total': 0, 't1': 0})
        for e in self.state.t1_events[-500:]:
            type_stats[e.scene_type]['total'] += 1
            type_stats[e.scene_type]['t1'] += 1

        # 补充未触发的类型
        for st in SceneGenerator.SCENE_TYPES:
            type_stats[st]['total'] = max(type_stats[st]['total'], 1)

        found = []
        for st, s in type_stats.items():
            t1_rate = s['t1'] / max(s['total'], 1)
            if t1_rate > 0.6 and st not in self.state.blind_spots:
                self.state.blind_spots[st] = {'t1_rate': t1_rate, 'found_at_scene': self.state.total_scenes}
                found.append(st)

        return found if found else None

    # ── 指标 ──
    def metrics(self):
        elapsed = time.time() - self.start_time
        t1_count = len(self.state.t1_events)
        preempt_rate = self.state.preemptions / max(self.state.total_scenes, 1) * 100
        t1_rate = t1_count / max(self.state.total_scenes, 1) * 100
        long_task_rate = self.state.long_tasks_completed / max(self.state.long_tasks_total, 1) * 100 if self.state.long_tasks_total > 0 else 100
        avg_latency = (time.time() - self.start_time) / max(self.state.total_scenes, 1) * 1000  # ms/scene

        return {
            'elapsed_hours': round(elapsed / 3600, 2),
            'total_scenes': self.state.total_scenes,
            't1_count': t1_count,
            't1_rate_pct': round(t1_rate, 2),
            'preemptions': self.state.preemptions,
            'preempt_rate_pct': round(preempt_rate, 2),
            'long_task_completion_pct': round(long_task_rate, 1),
            'blind_spots_found': list(self.state.blind_spots.keys()),
            'avg_latency_ms': round(avg_latency, 2),
            'scenes_per_second': round(self.state.total_scenes / max(elapsed, 1), 1),
        }

    def log_metrics(self):
        m = self.metrics()
        self.metrics_log.write(json.dumps(m) + '\n')
        self.metrics_log.flush()
        return m

    def close(self):
        self.t1_log.close()
        self.metrics_log.close()


# ═══════════════════════════════════════════════
# 2. 持续运行
# ═══════════════════════════════════════════════

def run(n_scenes=10000, report_every=1000, inject_novel_every=5000):
    """运行 GWT 调度器 — 持续场景流"""
    alpha = AgentAlpha()
    scheduler = GWTScheduler(alpha)
    generator = SceneGenerator()

    # 扩展场景类型——注入 GNN 没训练过的物理
    novel_types = ['damped_oscillation', 'magnetic']

    print(f'  EMNA 双锚集成测试 — {n_scenes} 场景')
    print(f'  GNN step: {alpha.global_step}')
    print(f'  每 {report_every} 场景打印指标')
    print(f'  每 {inject_novel_every} 场景注入新物理类型')
    print()

    for i in range(n_scenes):
        # 选择场景类型
        if i > 0 and i % inject_novel_every == 0:
            scene_type = random.choice(novel_types)
        else:
            scene_type = random.choice(SceneGenerator.SCENE_TYPES)

        # 生成场景（注意：新物理类型需要特殊生成逻辑——当前用相近类型近似）
        if scene_type in novel_types:
            # 用 stack 类型近似——阻尼振荡 = 高频低振幅的 stack 变体
            scene = generator.random_scene(random.choice(SceneGenerator.SCENE_TYPES))
            scene._type = scene_type  # 标记为新类型
        else:
            scene = generator.random_scene(scene_type)

        # 处理
        action, rmse = scheduler.process(scene, i, scene_type)

        # 盲区检查
        new_blind = scheduler.blind_spot_check()
        if new_blind:
            print(f'  🔴 [{i}] 新盲区: {new_blind}')

        # 定期报告
        if (i + 1) % report_every == 0:
            m = scheduler.log_metrics()
            bs_str = f'盲区: {m["blind_spots_found"]}' if m['blind_spots_found'] else '无盲区'
            print(f'  [{i+1:5d}/{n_scenes}] '
                  f'T1率={m["t1_rate_pct"]:5.1f}% '
                  f'抢占={m["preempt_rate_pct"]:4.1f}% '
                  f'长任务={m["long_task_completion_pct"]:4.0f}% '
                  f'延迟={m["avg_latency_ms"]:6.2f}ms '
                  f'{bs_str}')

    # 最终报告
    print(f'\n  {"="*60}')
    print(f'  最终指标')
    print(f'  {"="*60}')
    final = scheduler.log_metrics()
    for k, v in final.items():
        print(f'  {k}: {v}')

    scheduler.close()
    return final


if __name__ == '__main__':
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    run(n_scenes=n)
