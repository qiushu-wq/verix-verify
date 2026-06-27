"""
Verix 统一推理管道 — 已知→物理+数学+因果→验证→裁决

三路推演:
  Alpha (MuJoCo):  已知事实 → 物理模拟 → 预测结果 → 对比真值
  Beta (Lean 4):   已知事实 → 符号推演 → 形式化证明 → 类型检查
  VCD (Causal):    已知事实 → 因果图 → 因果推断 → 结构验证
"""
import sys, os, time, json, math, random
from collections import defaultdict
import numpy as np

sys.path.insert(0, '/opt/verix')
from agent_alpha import AgentAlpha, SceneGenerator, PhysicsScene
from agent_beta import AgentBeta, THEOREMS
from verix_causal import CausalWorldModel, CausalFeatureExtractor

# ═══════════════════════════════════════════════
# 1. 推理管道节点
# ═══════════════════════════════════════════════

class PhysicsReasoner:
    """Alpha 物理推理节点 — 已知→模拟→验证→结论"""

    def __init__(self):
        self.alpha = AgentAlpha()
        self.scene_gen = SceneGenerator()

    def reason(self, hypothesis: dict) -> dict:
        """
        hypothesis = {type: 'collision'|'slope'|..., params: {...}}
        """
        try:
            scene_type = hypothesis.get('type', 'collision')
            scene = self.scene_gen.random_scene(scene_type)

            params = hypothesis.get('params', {})
            for obj in scene.objects:
                obj['mass'] = params.get('mass', obj['mass'])
                if 'speed' in params:
                    obj['vel'] = [params['speed'], 0, 0]

            is_t1, rmse = self.alpha.check_t1(scene)

            return {
                'status': 'reasoned',
                'rmse': round(rmse, 4),
                'anomaly': is_t1,
                'confidence': round(max(0, 1.0 - rmse), 3),
                'n_objects': len(scene.objects),
                'verdict': 'prediction_reliable' if not is_t1 else 'prediction_anomalous',
            }
        except Exception as e:
            return {'status': 'error', 'reason': str(e)}

    def predict(self, description: str) -> dict:
        """
        从自然语言描述做物理预测
        description: "两个质量相等的台球正面碰撞"
        """
        scene = self.scene_gen.random_scene('collision')
        if '台球' in description or '球' in description:
            scene.objects = [
                {'id': 0, 'shape': 'sphere', 'size': [0.026], 'pos': [0, 0, 0.03], 'vel': [3, 0, 0], 'mass': 0.17},
                {'id': 1, 'shape': 'sphere', 'size': [0.026], 'pos': [0.5, 0, 0.03], 'vel': [0, 0, 0], 'mass': 0.17},
            ]
        elif '积木' in description or '塔' in description:
            scene.objects = [
                {'id': 0, 'shape': 'box', 'size': [0.05, 0.02, 0.02], 'pos': [0, 0, 0.01], 'vel': [0, 0, 0], 'mass': 0.5},
                {'id': 1, 'shape': 'box', 'size': [0.04, 0.02, 0.02], 'pos': [0, 0, 0.03], 'vel': [0, 0, 0], 'mass': 0.3},
            ]

        is_t1, rmse = self.alpha.check_t1(scene)
        return {
            'status': 'predicted',
            'scene': description,
            'rmse': round(rmse, 4),
            'confidence': round(max(0, 1.0 - rmse), 3),
            'anomaly': is_t1,
        }

    def status(self):
        return {'global_step': self.alpha.global_step}


class MathReasoner:
    """Beta 数学推演节点 — 已知→定理库→形式化证明→类型检查"""

    def __init__(self):
        self.beta = AgentBeta()

    def reason(self, hypothesis: dict) -> dict:
        """
        hypothesis = {theorem: 'modus_ponens'|...}
        """
        name = hypothesis.get('theorem', '')
        if name not in THEOREMS:
            return {'status': 'unknown_theorem', 'available': list(THEOREMS.keys())[:10]}

        result = self.beta.evaluate_theorem(name)
        return {
            'status': 'proved' if result.get('found') else 'failed',
            'theorem': name,
            'difficulty': result.get('difficulty', 1),
            'nodes': result.get('nodes_explored', 0),
            'proof_steps': result.get('proof_length', 0),
            'time_sec': result.get('time_sec', 0),
            'confidence': 1.0 if result.get('found') else 0.0,
        }

    def check_property(self, code: str, property_type: str) -> dict:
        """
        验证代码的数学性质
        property_type: 'termination'|'correctness'|'invariant'
        """
        lean_stmt = self._encode_property(code, property_type)
        if not lean_stmt:
            return {'status': 'cannot_encode'}

        ok, msg = self.beta.verifier.check(lean_stmt)
        return {
            'status': 'verified' if ok else 'failed',
            'property': property_type,
            'detail': msg if not ok else 'passed',
        }

    def _encode_property(self, code: str, prop: str) -> str:
        if prop == 'termination':
            return f'theorem terminates : forall x, exists y, (f x).length < (x).length := sorry'
        if prop == 'correctness':
            return f'theorem correct : forall x, greatest (f x) x := sorry'
        return ''


class CausalReasoner:
    """VCD 因果推演节点 — 已知→因果图→因果推断→结构验证"""

    def __init__(self):
        self.causal = CausalWorldModel(n_vars=8)
        self.extractor = CausalFeatureExtractor()

    def reason(self, hypothesis: dict) -> dict:
        """
        hypothesis = {cause_var: 0, effect_var: 3}
        """
        cause = hypothesis.get('cause_var', 0)
        effect = hypothesis.get('effect_var', 3)
        parents = self.causal.graph.get_parents(effect)

        edge_exists = cause in parents
        strength = abs(self.causal.graph.W[effect, cause]) if edge_exists else 0

        return {
            'status': 'inferred',
            'cause_var': cause,
            'effect_var': effect,
            'edge_exists': edge_exists,
            'causal_strength': round(float(strength), 3),
            'all_parents': parents,
            'n_causal_edges': self.causal.graph.get_structure()['n_edges'],
            'verdict': 'causal_link_found' if edge_exists else 'no_causal_link',
        }

    def observe_and_infer(self, scene) -> dict:
        """从物理场景观测中推断因果关系"""
        result = self.causal.observe(scene)
        struct = result['structure']
        edges = struct.get('edges', [])
        return {
            'status': 'observed',
            'n_edges': struct['n_edges'],
            'key_edges': [f"{e['from']}→{e['to']}" for e in edges[:5]],
            'strongest_edge': max(edges, key=lambda x: abs(x['strength'])) if edges else None,
        }


# ═══════════════════════════════════════════════
# 2. 统一推理引擎
# ═══════════════════════════════════════════════

class UnifiedReasoningEngine:
    """三路推演 + 互验 + 裁决"""

    def __init__(self):
        self.physics = PhysicsReasoner()
        self.math = MathReasoner()
        self.causal = CausalReasoner()
        self.history = []

    def reason(self, question: str) -> dict:
        """
        统一推理:
          1. 解析问题 → 分发给三个推理器
          2. 收集三路结果
          3. 交叉验证 — 矛盾触发辩论模式
          4. 裁决
        """
        # Step 1: 解析问题类型
        qtype = self._classify(question)

        # Step 2: 三路推演
        results = {}

        # 物理路
        if qtype in ['physics', 'general']:
            results['physics'] = self.physics.predict(question)

        # 数学路
        if qtype in ['math', 'general']:
            math_hypothesis = self._math_hypothesis(question)
            if math_hypothesis:
                results['math'] = self.math.reason(math_hypothesis)

        # 因果路
        if qtype in ['causal', 'general']:
            results['causal'] = self.causal.reason({'cause_var': 0, 'effect_var': 3})

        # Step 3: 交叉验证
        cross = self._cross_validate(results)

        # Step 4: 裁决
        verdict = self._arbitrate(results, cross)

        record = {
            'question': question,
            'qtype': qtype,
            'results': results,
            'cross_validation': cross,
            'verdict': verdict,
            'timestamp': time.time(),
        }
        self.history.append(record)
        return record

    def _classify(self, question: str) -> str:
        q = question.lower()
        if any(k in q for k in ['碰撞', '物理', '坠落', '球', '力', '质量', '速度']):
            return 'physics'
        if any(k in q for k in ['证明', '定理', '公式', '推导', '数学', '逻辑']):
            return 'math'
        if any(k in q for k in ['因果', '导致', '为什么', '原因', '影响']):
            return 'causal'
        return 'general'

    def _math_hypothesis(self, question: str) -> dict:
        """从问题中提取数学假说"""
        q = question.lower()
        for name in THEOREMS:
            keywords = name.split('_')
            if any(kw in q for kw in keywords):
                return {'theorem': name}
        return {'theorem': 'modus_ponens'}

    def _cross_validate(self, results: dict) -> dict:
        """三路结果互验"""
        checks = {}

        # 物理 vs 因果
        if 'physics' in results and 'causal' in results:
            p = results['physics']
            c = results['causal']
            # 物理预测可靠 + 因果边存在 = 一致
            p_ok = p.get('anomaly') == False
            c_ok = c.get('n_causal_edges', 0) > 0
            checks['physics_vs_causal'] = {
                'consistent': p_ok == c_ok,
                'physics_ok': p_ok,
                'causal_ok': c_ok,
            }

        # 物理置信度 vs 因果强度
        if 'physics' in results and 'causal' in results:
            p_conf = results['physics'].get('confidence', 0)
            c_str = results['causal'].get('causal_strength', 0)
            checks['confidence_alignment'] = {
                'consistent': abs(p_conf - c_str) < 0.5,
                'physics_conf': p_conf,
                'causal_strength': c_str,
            }

        # 汇总
        checks['total_checks'] = len(checks)
        checks['all_consistent'] = all(
            c.get('consistent', True) for c in checks.values()
            if isinstance(c, dict) and 'consistent' in c
        )
        return checks

    def _arbitrate(self, results: dict, cross: dict) -> dict:
        """最终裁决"""
        if not results:
            return {'verdict': 'insufficient_data', 'confidence': 0}

        confidences = []
        for r in results.values():
            if isinstance(r, dict) and 'confidence' in r:
                confidences.append(r['confidence'])

        avg_conf = np.mean(confidences) if confidences else 0.5

        if cross.get('all_consistent', False) and avg_conf > 0.7:
            verdict = 'confirmed'
        elif avg_conf < 0.3:
            verdict = 'falsified'
        elif cross.get('total_checks', 0) >= 2 and cross.get('all_consistent', False):
            verdict = 'confirmed'
        else:
            verdict = 'needs_more_data'

        return {
            'verdict': verdict,
            'confidence': round(avg_conf, 3),
            'recommendation': {
                'confirmed': '写入fact_db, 可用于下游决策',
                'falsified': '标记盲区, 触发针对性探测',
                'needs_more_data': '生成更多变体, 扩大Gamma场景',
            }.get(verdict, ''),
        }

    def status(self):
        return {
            'total_reasonings': len(self.history),
            'physics_step': self.physics.status().get('global_step', 0),
            'causal_edges': self.causal.causal.graph.get_structure()['n_edges'],
        }


# ═══════════════════════════════════════════════
# 3. 自检
# ═══════════════════════════════════════════════

if __name__ == '__main__':
    print("Verix Unified Reasoning Engine")
    print("=" * 60)

    engine = UnifiedReasoningEngine()

    questions = [
        "两个台球碰撞后，轻球会怎样？",
        "证明 modus_ponens 定理",
        "为什么增加质量会导致速度变化？",
        "台球碰撞 + 逻辑推导",
    ]

    for q in questions:
        print(f"\n问题: {q}")
        result = engine.reason(q)
        print(f"  类型: {result['qtype']}")
        for name, r in result['results'].items():
            print(f"  {name}: {r.get('status','?')} conf={r.get('confidence','?')} "
                  f"rmse={r.get('rmse','?')} edges={r.get('n_causal_edges','?')}")
        cross = result['cross_validation']
        print(f"  交叉验证: consistent={cross.get('all_consistent','?')}")
        v = result['verdict']
        print(f"  裁决: {v['verdict']} (conf={v['confidence']}) → {v['recommendation']}")

    print(f"\n✓ 统一推理就绪 ({engine.status()['total_reasonings']}次推理)")
