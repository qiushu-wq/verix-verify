"""Agent α T1 增量学习 — GNN 自动微调闭环"""
import os, sys, random, copy, json, time
import numpy as np
sys.path.insert(0, '/opt/verix')
from agent_alpha import AgentAlpha, SceneGenerator, PhysicsScene, MuJoCoSimulator

# ═══════════════════════════════════════════════
# 1. 场景变体生成器
# ═══════════════════════════════════════════════

class SceneVariantGenerator:
    """从 T1 失败场景生成参数变体"""

    def __init__(self, n_variants=8):
        self.n_variants = n_variants
        self.generator = SceneGenerator()

    def generate(self, scene: PhysicsScene) -> list:
        """生成 N 个参数变体"""
        variants = []

        for i in range(self.n_variants):
            new_scene = copy.deepcopy(scene)

            for obj in new_scene.objects:
                # 扰动质量：±30%
                obj['mass'] *= random.uniform(0.7, 1.3)
                # 扰动速度：±50%
                obj['vel'] = [v * random.uniform(0.5, 1.5) for v in obj['vel']]
                # 扰动位置：±10%
                obj['pos'] = [p + random.uniform(-0.05, 0.05) for p in obj['pos']]
                # 扰动尺寸：±20%
                obj['size'] = [s * random.uniform(0.8, 1.2) for s in obj['size']]

            variants.append(new_scene)

        return variants


# ═══════════════════════════════════════════════
# 2. 增量微调器
# ═══════════════════════════════════════════════

class IncrementalTrainer:
    """GNN 增量微调 — 在变体场景上微调"""

    def __init__(self, alpha: AgentAlpha):
        self.alpha = alpha
        self.simulator = MuJoCoSimulator()
        self.training_sessions = []

    def train_on_variants(self, variants: list, epochs=5) -> dict:
        """在变体场景上微调 GNN"""
        total_loss = 0
        n_trained = 0

        for epoch in range(epochs):
            epoch_loss = 0
            random.shuffle(variants)

            for scene in variants:
                try:
                    loss = self.alpha.train_step(scene)
                    epoch_loss += loss
                    n_trained += 1
                except Exception as e:
                    continue

            total_loss += epoch_loss

        avg_loss = total_loss / max(n_trained, 1)

        session = {
            'variants': len(variants),
            'epochs': epochs,
            'avg_loss': round(avg_loss, 6),
            'time': time.time(),
        }
        self.training_sessions.append(session)

        return session


# ═══════════════════════════════════════════════
# 3. 盲区解析器 — 完整闭环
# ═══════════════════════════════════════════════

class BlindSpotResolver:
    """T1 → 隔离 → 变体 → 验证 → 微调 → 重测"""

    def __init__(self, alpha: AgentAlpha):
        self.alpha = alpha
        self.variant_gen = SceneVariantGenerator(n_variants=8)
        self.trainer = IncrementalTrainer(alpha)
        self.resolved = []
        self.unresolved = []

    def resolve(self, scene: PhysicsScene, scene_type: str = 'unknown') -> dict:
        """尝试解析一个 T1 盲区"""
        result = {
            'scene_type': scene_type,
            'n_objects': len(scene.objects),
            'status': 'pending',
            'steps': [],
        }

        # Step 1: 记录基线 RMSE
        is_t1, baseline_rmse = self.alpha.check_t1(scene)
        result['baseline_rmse'] = round(baseline_rmse, 4)
        result['steps'].append(f'基线 RMSE={baseline_rmse:.4f}')

        # Step 2: 生成变体
        variants = self.variant_gen.generate(scene)
        result['n_variants'] = len(variants)
        result['steps'].append(f'生成 {len(variants)} 个变体')

        # Step 3: MuJoCo 批量验证 — 收集训练数据
        training_scenes = []
        for v in variants:
            try:
                _ = self.alpha.simulator.final_state(v)  # 确保模拟器正常
                training_scenes.append(v)
            except Exception:
                continue
        result['valid_variants'] = len(training_scenes)
        result['steps'].append(f'有效变体: {len(training_scenes)}')

        # Step 4: GNN 增量微调
        if len(training_scenes) >= 3:
            session = self.trainer.train_on_variants(training_scenes, epochs=3)
            result['train_loss'] = session['avg_loss']
            result['steps'].append(f'微调 loss={session["avg_loss"]:.6f}')

        self.alpha.save()  # 持久化学习成果
        # Step 5: 重新测试原始场景
        new_is_t1, new_rmse = self.alpha.check_t1(scene)
        result['new_rmse'] = round(new_rmse, 4)
        improvement = baseline_rmse - new_rmse
        result['improvement'] = round(improvement, 4)
        result['steps'].append(f'重测 RMSE={new_rmse:.4f} (改善={improvement:+.4f})')

        # Step 6: 判定
        if not new_is_t1 and new_rmse < 0.15:
            result['status'] = 'resolved'
            result['steps'].append('✅ 盲区已关闭')
            self.resolved.append(result)
        elif improvement > 0.02:
            result['status'] = 'improved'
            result['steps'].append('⚠️ 显著改善但未完全解决')
        else:
            result['status'] = 'unresolved'
            result['steps'].append('❌ 标记为"待研究"')
            self.unresolved.append(result)

        return result

    def status(self):
        return {
            'resolved': len(self.resolved),
            'unresolved': len(self.unresolved),
            'sessions': len(self.trainer.training_sessions),
        }


# ═══════════════════════════════════════════════
# 4. 演示
# ═══════════════════════════════════════════════

if __name__ == '__main__':
    print('Agent α T1 增量学习闭环')
    print('=' * 50)

    alpha = AgentAlpha()
    resolver = BlindSpotResolver(alpha)
    gen = SceneGenerator()

    # 制造一个 T1 场景
    scene = gen.random_scene('collision')
    is_t1, rmse = alpha.check_t1(scene)
    print(f'基线 T1: {is_t1} RMSE={rmse:.4f} (GNN step {alpha.global_step})')

    # 如果 GNN 太强没触发 T1，人为提高阈值
    if not is_t1:
        print('GNN 太稳定了——人为注入扰动')
        for obj in scene.objects:
            obj['mass'] *= 20  # 极端质量比
            obj['vel'] = [v * 10 for v in obj['vel']]

    # 执行增量学习
    result = resolver.resolve(scene)
    for step in result['steps']:
        print(f'  {step}')
    print(f'\n状态: {result["status"]}')
    print(f'改善: {result.get("improvement", 0):+.4f}')
    print(f'盲区: 已解决={resolver.status()["resolved"]} 未解决={resolver.status()["unresolved"]}')
