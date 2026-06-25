"""Agent α — GNN 物理预测器 + MuJoCo 外部验证闭环"""
import os, json, time, math, random
from dataclasses import dataclass
from typing import List, Tuple
import numpy as np
import mujoco
import torch
import torch.nn as nn
import torch.optim as optim

# ═══════════════════════════════════════════════
# 1. MuJoCo 场景生成器
# ═══════════════════════════════════════════════

@dataclass
class PhysicsScene:
    """单个物理场景"""
    objects: List[dict]  # [{id, shape, size, pos, vel, mass}]
    duration: float = 1.0
    dt: float = 0.01  # 100Hz simulation

class SceneGenerator:
    """随机生成物理场景"""

    SHAPES = ['sphere', 'box']
    SCENE_TYPES = ['collision', 'slope', 'projectile', 'stack']

    def random_scene(self, scene_type=None):
        """随机生成一个物理场景"""
        if scene_type is None:
            scene_type = random.choice(self.SCENE_TYPES)

        objects = []
        if scene_type == 'collision':
            objects = self._random_collision()
        elif scene_type == 'slope':
            objects = self._random_slope()
        elif scene_type == 'projectile':
            objects = self._random_projectile()
        elif scene_type == 'stack':
            objects = self._random_stack()

        return PhysicsScene(objects=objects)

    def _random_collision(self):
        """两球或多球碰撞"""
        n = random.choice([2, 3])
        objs = []
        for i in range(n):
            obj = {
                'id': i,
                'shape': 'sphere',
                'size': [random.uniform(0.03, 0.08)],  # radius
                'pos': [random.uniform(-0.3, 0.3), random.uniform(-0.2, 0.2), random.uniform(0.03, 0.15)],
                'vel': [random.uniform(-2, 2), random.uniform(-1, 1), 0],
                'mass': random.uniform(0.05, 0.5),
            }
            objs.append(obj)
        return objs

    def _random_slope(self):
        """斜面滑动"""
        angle = random.uniform(10, 60)  # degrees
        obj = {
            'id': 0,
            'shape': random.choice(['sphere', 'box']),
            'size': [random.uniform(0.03, 0.06)] if random.random() > 0.5 else [random.uniform(0.03, 0.06)] * 3,
            'pos': [0, 0, random.uniform(0.1, 0.4)],
            'vel': [random.uniform(0.5, 2.0), 0, 0],
            'mass': random.uniform(0.05, 0.3),
        }
        obj['slope_angle'] = angle
        return [obj]

    def _random_projectile(self):
        """抛射"""
        obj = {
            'id': 0,
            'shape': 'sphere',
            'size': [random.uniform(0.02, 0.05)],
            'pos': [0, 0, random.uniform(0.2, 0.6)],
            'vel': [random.uniform(0.5, 3.0), random.uniform(-0.5, 0.5), random.uniform(1.0, 5.0)],
            'mass': random.uniform(0.02, 0.2),
        }
        return [obj]

    def _random_stack(self):
        """堆叠"""
        n = random.choice([3, 4, 5])
        objs = []
        for i in range(n):
            size = random.uniform(0.04, 0.08)
            x_offset = random.uniform(-0.02, 0.02)
            y_offset = random.uniform(-0.02, 0.02)
            obj = {
                'id': i,
                'shape': 'box',
                'size': [size, size, size],
                'pos': [x_offset, y_offset, 0.02 + i * size * 2],
                'vel': [0, 0, 0],
                'mass': random.uniform(0.05, 0.2),
            }
            objs.append(obj)
        # 推底部
        objs[0]['vel'] = [random.uniform(0.3, 1.0), random.uniform(-0.2, 0.2), 0]
        return objs


# ═══════════════════════════════════════════════
# 2. MuJoCo 模拟器
# ═══════════════════════════════════════════════

class MuJoCoSimulator:
    """MuJoCo 物理模拟器 — 外部验证源"""

    def __init__(self):
        self.model = None
        self.data = None

    def _build_model(self, scene: PhysicsScene):
        """从场景描述构建 MuJoCo 模型"""
        spec = mujoco.MjSpec()

        for obj in scene.objects:
            if obj['shape'] == 'sphere':
                radius = obj['size'][0]
                body = spec.worldbody.add_body(
                    pos=obj['pos'], name=f"obj_{obj['id']}")
                geom = body.add_geom(
                    type=mujoco.mjtGeom.mjGEOM_SPHERE,
                    size=[radius, 0, 0],
                    mass=obj['mass'])
                body.add_freejoint()

            elif obj['shape'] == 'box':
                half_size = obj['size'][0] / 2
                body = spec.worldbody.add_body(
                    pos=obj['pos'], name=f"obj_{obj['id']}")
                geom = body.add_geom(
                    type=mujoco.mjtGeom.mjGEOM_BOX,
                    size=[half_size, half_size, half_size],
                    mass=obj['mass'])
                body.add_freejoint()

        self.model = spec.compile()
        self.data = mujoco.MjData(self.model)

        # 设初速度 — 通过 data.qvel（编译后设置）
        for i, obj in enumerate(scene.objects):
            body_id = self.model.body(f"obj_{obj['id']}").id
            jnt_id = self.model.body_jntadr[body_id]
            dof_start = self.model.jnt_dofadr[jnt_id]
            self.data.qvel[dof_start:dof_start+3] = obj['vel'][:3]

    def simulate(self, scene: PhysicsScene):
        """运行模拟，返回各物体的轨迹"""
        self._build_model(scene)

        n_steps = int(scene.duration / scene.dt)
        trajectories = {obj['id']: {'pos': [], 'vel': []} for obj in scene.objects}

        for step in range(n_steps):
            mujoco.mj_step(self.model, self.data)
            for obj in scene.objects:
                body_id = self.model.body(f"obj_{obj['id']}").id
                pos = self.data.xpos[body_id].copy()
                # Get linear velocity from cvel (3:6 is angular, 0:3 is linear for free joints)
                dof_start = self.model.jnt_dofadr[self.model.body_jntadr[body_id]]
                vel = self.data.qvel[dof_start:dof_start+3].copy()
                trajectories[obj['id']]['pos'].append(pos)
                trajectories[obj['id']]['vel'].append(vel)

        return trajectories

    def final_state(self, scene: PhysicsScene):
        """只返回最终状态（用于训练标签）"""
        traj = self.simulate(scene)
        final = {}
        for obj_id, t in traj.items():
            final[obj_id] = {
                'pos': t['pos'][-1].tolist(),
                'vel': t['vel'][-1].tolist(),
            }
        return final


# ═══════════════════════════════════════════════
# 3. GNN 模型
# ═══════════════════════════════════════════════

class InteractionNetwork(nn.Module):
    """GNN 物理预测器 — DeepMind Interaction Networks 风格"""

    def __init__(self, node_dim=9, edge_dim=4, hidden=128):
        super().__init__()
        self.node_encoder = nn.Sequential(
            nn.Linear(node_dim, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
        )
        self.edge_encoder = nn.Sequential(
            nn.Linear(edge_dim, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
        )
        self.relation_net = nn.Sequential(
            nn.Linear(hidden * 3, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, 1),  # scalar effect
        )
        self.node_updater = nn.Sequential(
            nn.Linear(hidden + hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, 6),  # pos(3) + vel(3)
        )

    def _object_to_node(self, obj):
        """物体 → 节点特征"""
        shape = obj['shape']
        shape_code = 0 if shape == 'sphere' else 1
        size = obj['size'][0]
        mass = obj['mass']
        px, py, pz = obj['pos']
        vx, vy, vz = obj['vel']
        return torch.tensor([shape_code, size, mass, px, py, pz, vx, vy, vz], dtype=torch.float32)

    def _pair_to_edge(self, obj_a, obj_b):
        """物体对 → 边特征"""
        dx = obj_a['pos'][0] - obj_b['pos'][0]
        dy = obj_a['pos'][1] - obj_b['pos'][1]
        dz = obj_a['pos'][2] - obj_b['pos'][2]
        dist = math.sqrt(dx*dx + dy*dy + dz*dz)
        return torch.tensor([dx, dy, dz, dist], dtype=torch.float32)

    def forward(self, scene: PhysicsScene):
        """前向传播：预测各物体下一时刻的状态变化"""
        objects = scene.objects
        n = len(objects)

        if n == 1:
            # 单物体——无相互作用
            node = self._object_to_node(objects[0])
            h = self.node_encoder(node)
            delta = self.node_updater(torch.cat([h, torch.zeros_like(h)]))
            return [delta]

        # 编码节点
        nodes = [self._object_to_node(obj) for obj in objects]
        h_nodes = [self.node_encoder(n) for n in nodes]

        # 编码边 + 关系推理
        effects = {i: torch.zeros(h_nodes[0].shape[0]) for i in range(n)}
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                edge = self._pair_to_edge(objects[i], objects[j])
                h_edge = self.edge_encoder(edge)
                # 关系：(sender, receiver, edge)
                rel = torch.cat([h_nodes[i], h_nodes[j], h_edge])
                effect = self.relation_net(rel)  # scalar
                effects[j] = effects[j] + effect * h_nodes[i]

        # 更新节点
        deltas = []
        for i in range(n):
            delta = self.node_updater(torch.cat([h_nodes[i], effects[i]]))
            deltas.append(delta)

        return deltas


# ═══════════════════════════════════════════════
# 4. 训练闭环
# ═══════════════════════════════════════════════

class AgentAlpha:
    """Agent α — GNN + MuJoCo 训练与推理"""

    def __init__(self, model_dir='/opt/emna/models'):
        self.model = InteractionNetwork()
        self.optimizer = optim.Adam(self.model.parameters(), lr=1e-4)
        self.simulator = MuJoCoSimulator()
        self.generator = SceneGenerator()
        self.model_dir = model_dir
        self.global_step = 0
        self.t1_events = []  # 记录 T1 不一致事件

        # 尝试加载已有模型
        self.ckpt_path = os.path.join(model_dir, 'alpha.pt')
        if os.path.exists(self.ckpt_path):
            ckpt = torch.load(self.ckpt_path)
            self.model.load_state_dict(ckpt['model'])
            self.optimizer.load_state_dict(ckpt['optimizer'])
            self.global_step = ckpt['global_step']
            print(f'  Agent α 加载: step {self.global_step}')

    def train_step(self, scene: PhysicsScene):
        """单步训练：预测 vs. MuJoCo 真实结果 → 反向传播"""
        self.model.train()

        # MuJoCo 真实结果
        ground_truth = self.simulator.final_state(scene)

        # GNN 预测
        deltas = self.model(scene)

        # 计算损失
        loss = 0
        for i, obj in enumerate(scene.objects):
            gt = ground_truth[obj['id']]
            delta = deltas[i]
            pred_pos = torch.tensor(obj['pos'][:3]) + delta[:3]
            pred_vel = torch.tensor(obj['vel'][:3]) + delta[3:6]
            gt_pos = torch.tensor(gt['pos'][:3])
            gt_vel = torch.tensor(gt['vel'][:3])
            loss += nn.functional.mse_loss(pred_pos, gt_pos)
            loss += 0.1 * nn.functional.mse_loss(pred_vel, gt_vel)

        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        self.global_step += 1
        return loss.item() / len(scene.objects)

    def train(self, n_scenes=1000, batch_size=32, save_every=500):
        """训练循环"""
        print(f'  Agent α 训练: {n_scenes} 场景, batch={batch_size}')
        losses = []

        for i in range(n_scenes):
            scene_type = random.choice(SceneGenerator.SCENE_TYPES)
            scene = self.generator.random_scene(scene_type)
            loss = self.train_step(scene)
            losses.append(loss)

            if (i + 1) % 100 == 0:
                avg = np.mean(losses[-100:])
                print(f'    [{i+1}/{n_scenes}] loss={avg:.6f}')

            if (self.global_step) % save_every == 0:
                self.save()

        self.save()
        print(f'  训练完成。最终 loss={np.mean(losses[-100:]):.6f}')
        return losses

    def predict(self, scene: PhysicsScene):
        """推理：预测场景结果"""
        self.model.eval()
        with torch.no_grad():
            deltas = self.model(scene)
        predictions = {}
        for i, obj in enumerate(scene.objects):
            delta = deltas[i]
            predictions[obj['id']] = {
                'pos': (np.array(obj['pos'][:3]) + delta[:3].numpy()).tolist(),
                'vel': (np.array(obj['vel'][:3]) + delta[3:6].numpy()).tolist(),
            }
        return predictions

    def check_t1(self, scene: PhysicsScene, rmse_threshold=0.15):
        """检测 T1 不一致——模拟器 vs. GNN 预测"""
        pred = self.predict(scene)
        truth = self.simulator.final_state(scene)

        total_rmse = 0
        for obj in scene.objects:
            p_pos = np.array(pred[obj['id']]['pos'][:3])
            t_pos = np.array(truth[obj['id']]['pos'][:3])
            rmse = np.sqrt(np.mean((p_pos - t_pos) ** 2))
            total_rmse += rmse

        avg_rmse = total_rmse / len(scene.objects)
        is_t1 = avg_rmse > rmse_threshold

        if is_t1:
            self.t1_events.append({
                'step': self.global_step,
                'scene_type': scene.__dict__.get('_type', 'unknown'),
                'n_objects': len(scene.objects),
                'rmse': float(avg_rmse),
                'time': time.time(),
            })

        return is_t1, avg_rmse

    def blind_spot_scan(self, n_per_type=20):
        """盲区扫描——按场景类型检测 T1 不一致率"""
        results = {}
        for st in SceneGenerator.SCENE_TYPES:
            t1_count = 0
            rmses = []
            for _ in range(n_per_type):
                scene = self.generator.random_scene(st)
                is_t1, rmse = self.check_t1(scene)
                if is_t1:
                    t1_count += 1
                rmses.append(rmse)
            results[st] = {
                't1_rate': t1_count / n_per_type,
                'avg_rmse': np.mean(rmses),
                'max_rmse': np.max(rmses),
            }
        return results

    def save(self):
        torch.save({
            'model': self.model.state_dict(),
            'optimizer': self.optimizer.state_dict(),
            'global_step': self.global_step,
        }, self.ckpt_path)


# ═══════════════════════════════════════════════
# 5. 入口
# ═══════════════════════════════════════════════

if __name__ == '__main__':
    import sys

    alpha = AgentAlpha()

    if '--train' in sys.argv:
        n = int(sys.argv[sys.argv.index('--train') + 1]) if '--train' in sys.argv and len(sys.argv) > sys.argv.index('--train') + 1 else 2000
        alpha.train(n_scenes=n)

    elif '--blindspot' in sys.argv:
        print('  盲区扫描...')
        results = alpha.blind_spot_scan(n_per_type=30)
        print(f'\n  {"类型":12} {"T1率":>7} {"均RMSE":>9} {"最大RMSE":>9}')
        print(f'  {"─"*40}')
        for st, r in results.items():
            flag = '🔴 >60%' if r['t1_rate'] > 0.6 else '🟡 >30%' if r['t1_rate'] > 0.3 else '🟢'
            print(f'  {st:12} {r["t1_rate"]:6.0%} {r["avg_rmse"]:8.4f} {r["max_rmse"]:8.4f}  {flag}')

        # 检查是否有系统性盲区
        blind_spots = [(st, r) for st, r in results.items() if r['t1_rate'] > 0.6]
        if blind_spots:
            print(f'\n  🔴 系统性盲区 ({len(blind_spots)}类):')
            for st, r in blind_spots:
                print(f'    {st}: T1率={r["t1_rate"]:.0%} → 标记为"需要新世界模型"')
        else:
            print(f'\n  ✅ 无系统性盲区')

    elif '--demo' in sys.argv:
        print('  演示：Agent α 预测 + 验证')
        scene = alpha.generator.random_scene('collision')
        pred = alpha.predict(scene)
        truth = alpha.simulator.final_state(scene)
        is_t1, rmse = alpha.check_t1(scene)
        print(f'  场景: 碰撞, {len(scene.objects)}物体')
        print(f'  RMSE: {rmse:.4f}  → {"🔴 T1不一致" if is_t1 else "🟢 一致"}')
        for obj in scene.objects:
            print(f'    obj_{obj["id"]}: ')
            print(f'      预测: pos={pred[obj["id"]]["pos"]} vel={pred[obj["id"]]["vel"]}')
            print(f'      真实: pos={truth[obj["id"]]["pos"]} vel={truth[obj["id"]]["vel"]}')

    else:
        print('Agent α — GNN + MuJoCo 闭环')
        print('  --train N     训练 N 场景')
        print('  --blindspot   盲区扫描')
        print('  --demo        演示预测+验证')
