"""
Verix 统一自主进化守护进程 v3 — VCD 因果版
整合: 主动探索 + VCD因果发现 + SAGE同构迁移 + Gamma真人验证 + GWT元认知
"""
import os, sys, time, json, random, itertools
from datetime import datetime, timezone
from collections import defaultdict, Counter

sys.path.insert(0, '/opt/verix')
from active_explore import ActiveExplorer
from sage_v3 import SAGEEngineV3
from agent_alpha import AgentAlpha, SceneGenerator, PhysicsScene
from agent_delta import AgentDelta
from agent_gamma import HumanJudgmentDB, LightweightPolicyNet
from delta_auto import AutoExtensionEngine
from alpha_learn import BlindSpotResolver
from verix_causal import CausalWorldModel, CausalBridge, CausalFeatureExtractor
from verix_thalamus import ThalamicGateBridge
from verix_dopamine import DopamineSystem, ValueBridge
from verix_hippocampus import Hippocampus, CorticalConsolidation
from verix_debate import DebateEngine, DebateTopic
from verix_novelty import NoveltyArchive, BehaviorCharacterizer, NoveltyDrivenExplorer
from verix_curiosity import CuriosityDrivenExplorer, IntrinsicCuriosityModule
from verix_emotion import EmotionalBrain, EmotionalBridge
from verix_reason import UnifiedReasoningEngine
from verix_selfarch import SelfArchitectureEngine
import torch
import numpy as np

STATUS_FILE = '/opt/verix/logs/verix_autonomous_status.json'
LOG_FILE    = '/opt/verix/logs/verix_autonomous.log'
GAMMA_DATA  = '/opt/verix/data/gamma_human_judgments.json'

ALL_DOMAINS = ['alpha', 'beta', 'delta', 'epsilon', 'gamma']
ALL_PATTERNS = ['critical_stability', 'type_mismatch', 'predicate_ambiguity',
                'boundary_collapse', 'context_shift', 'analogy_gap']

class GammaValidationBridge:
    """Gamma 真人验证锚 —— 把人类判断注入进化闭环"""

    def __init__(self, data_path=GAMMA_DATA):
        self.db = HumanJudgmentDB(data_path) if os.path.exists(data_path) else HumanJudgmentDB()
        self.data_path = data_path
        self.last_sync = time.time()
        self.alignment_scores = []
        self.contradictions = []

    def sync(self):
        if os.path.exists(self.data_path):
            self.db.load(self.data_path)

    def consensus_map(self) -> dict:
        m = {}
        for j in self.db.judgments:
            if j['human_answers']:
                c = Counter(j['human_answers'])
                majority = c.most_common(1)[0]
                m[j['scenario_id']] = {
                    'answer': majority[0],
                    'agreement': majority[1] / len(j['human_answers']),
                    'total_votes': len(j['human_answers']),
                    'category': j['category'],
                    'text': j['text'],
                    'options': j['options'],
                }
        return m

    def get_physical_scenarios(self) -> list:
        """返回所有物理类场景，供 Alpha 直接测试"""
        self.sync()
        return [j for j in self.db.judgments if j['category'] == 'physical']

    def record_alignment(self, scenario_id: str, scenario_text: str,
                         alpha_pred: int, alpha_confidence: float = 0) -> dict:
        """记录一次 Alpha vs 人类共识的对齐检查"""
        self.sync()
        cmap = self.consensus_map()
        info = cmap.get(scenario_id)
        if not info:
            return {'aligned': None, 'reason': 'scenario_not_found'}

        aligned = (alpha_pred == info['answer'])
        self.alignment_scores.append({
            'time': datetime.now().isoformat(),
            'scenario': scenario_text[:60],
            'alpha_pred': alpha_pred,
            'human_consensus': info['answer'],
            'agreement_rate': info['agreement'],
            'aligned': aligned,
        })
        if not aligned:
            self.contradictions.append({
                'type': 'alpha_human_mismatch',
                'scenario': scenario_text[:60],
                'scenario_id': scenario_id,
                'alpha_said': alpha_pred,
                'humans_said': info['answer'],
                'human_agreement': info['agreement'],
            })
        return {'aligned': aligned, 'human_consensus': info['answer'],
                'agreement_rate': info['agreement']}

    def alignment_stats(self) -> dict:
        total = len(self.alignment_scores)
        if not total:
            return {'total_checks': 0}
        aligned = sum(1 for a in self.alignment_scores if a['aligned'])
        return {
            'total_checks': total,
            'aligned': aligned,
            'misaligned': total - aligned,
            'alignment_rate': round(aligned / total, 3) if total else 0,
            'contradictions': len(self.contradictions),
        }

    def status(self) -> dict:
        return {
            'scenarios': self.db.stats(),
            'alignment': self.alignment_stats(),
            'recent_contradictions': self.contradictions[-5:],
        }


class VerixAutonomousDaemon:
    """统一自主进化守护进程 — v2 激进探索"""

    def __init__(self):
        self.explorer = ActiveExplorer()
        self.sage = SAGEEngineV3()
        self.alpha = AgentAlpha()
        self.delta = AgentDelta()
        self.gamma = GammaValidationBridge()
        self.resolver = BlindSpotResolver(self.alpha)
        self.extender = AutoExtensionEngine(self.delta)
        self.scene_gen = SceneGenerator()

        # VCD 因果引擎
        self.causal = CausalWorldModel(n_vars=8)
        self.causal_bridge = CausalBridge()
        self.causal_bridge.register_domain('alpha_physics', self.causal)

        # Gamma 训练模型 — 0.5M 参数预测人类判断
        self.gamma_model = None
        self.gamma_model_loaded = False
        try:
            from agent_gamma import LightweightPolicyNet, extract_features
            self.gamma_model = LightweightPolicyNet()
            ckpt = torch.load('/opt/verix/models/gamma_trained.pt')
            self.gamma_model.load_state_dict(ckpt['model'])
            self.gamma_model.eval()
            self.gamma_model_loaded = True
            self.log(f'Gamma策略网络加载: {ckpt["n_scenarios"]}场景, '
                     f'{ckpt["n_judgments"]}条判断, step{ckpt["global_step"]}')
        except Exception as e:
            self.log(f'Gamma模型加载失败(将跳过): {e}', 'WARN')

        # 丘脑门控
        self.thalamus = ThalamicGateBridge(window_duration=45)
        # 多巴胺价值系统
        self.dopamine = DopamineSystem()
        self.value_bridge = ValueBridge(self.dopamine, thalamus=self.thalamus)
        # 海马体记忆系统
        self.hippocampus = Hippocampus(capacity=300, replay_batch=5, replay_interval=10)
        self.cortex = CorticalConsolidation(self.hippocampus, alpha=self.alpha)
        # 三角色对抗引擎
        self.debate = DebateEngine(alpha=self.alpha, causal=self.causal,
                                   gamma=self.gamma, hippocampus=self.hippocampus,
                                   delta=self.delta)
        # Novelty Search + Curiosity — 双引擎探索
        self.novelty_explorer = NoveltyDrivenExplorer(self.explorer, capacity=300)
        self.curiosity = CuriosityDrivenExplorer(state_dim=12, action_dim=8)
        # 情感系统
        self.emotion = EmotionalBridge(
            dopamine=self.dopamine, thalamus=self.thalamus, hippocampus=self.hippocampus)
        # 统一推理引擎
        self.reasoner = UnifiedReasoningEngine()
        # 递归自架构
        self.selfarch = SelfArchitectureEngine(daemon=self)
        self.last_state = np.zeros(12)
        self.last_action = np.zeros(8)

        self.start_time = time.time()
        self.cycles = 0
        self.milestones = []
        self.recent_events = []
        self.sage_pair_idx = 0

        os.makedirs('/opt/verix/logs', exist_ok=True)

    def log(self, msg: str, level='INFO'):
        t = datetime.now().strftime('%H:%M:%S')
        line = f'[{t}] [{level}] {msg}'
        print(line)
        with open(LOG_FILE, 'a') as f:
            f.write(line + '\n')

    # ═══════════════════════════════════════
    # 强制探索 — 确保每周期都有产出
    # ═══════════════════════════════════════

    def _force_explore(self) -> dict:
        """激进探索：最多试 5 次，直到产生至少 1 个探测"""
        for attempt in range(5):
            result = self.explorer.run_cycle()
            if result.get('probes'):
                return result
            # 如果 explorer 没产出，手动注入探索目标
            self._inject_probe_target()
        return self.explorer.run_cycle()

    def _inject_probe_target(self):
        """手动给能力地图注入一个未测试区域，强制探测"""
        untested = self.explorer.cmap.get_untested()
        if not untested:
            # 所有区域都测试过了，找最低置信度的
            low = self.explorer.cmap.get_low_confidence(threshold=0.6)
            if low:
                region = max(low, key=lambda x: x[1])[0]
            else:
                return
        else:
            region = random.choice(untested)

        # 强制标记为需要探测
        scene = self.scene_gen.random_scene('collision')
        for obj in scene.objects:
            obj['mass'] *= random.uniform(3, 15)
            obj['vel'] = [v * random.uniform(2, 6) for v in obj['vel']]

        learn = self.resolver.resolve(scene, region)
        self.explorer.cmap.update(region, learn.get('status') == 'resolved',
                                  learn.get('new_rmse', 0))
        self.explorer.probes_launched += 1

        if learn.get('status') == 'resolved':
            self.explorer.discoveries.append({
                'type': 'forced_probe',
                'region': region,
            })

    # ═══════════════════════════════════════
    # Gamma 主动对齐 — 每周期用真人数据验 Alpha
    # ═══════════════════════════════════════

    def _gamma_align(self) -> dict:
        """用 Gamma 场景让 Alpha 物理预测 + 训练好的策略网络双重验证"""
        physical = self.gamma.get_physical_scenarios()
        if not physical:
            return {'aligned': None, 'reason': 'no_physical_scenarios'}

        scenario = random.choice(physical)

        # ── 策略网络预测人类共识 ──
        nn_pred = None
        if self.gamma_model_loaded:
            try:
                from agent_gamma import extract_features
                feat = extract_features(scenario['text'], scenario['options'], scenario['category'])
                with torch.no_grad():
                    logits = self.gamma_model(feat.unsqueeze(0)).squeeze(0)
                    probs = torch.softmax(logits, dim=-1).tolist()
                    nn_pred = int(np.argmax(probs))
                    nn_conf = float(probs[nn_pred])
            except Exception:
                pass

        # ── Alpha 物理预测 ──
        scene = self.scene_gen.random_scene('collision')
        if '台球' in scenario['text'] or '碰撞' in scenario['text']:
            scene.objects = [
                {'id': 0, 'shape': 'sphere', 'size': [0.026], 'pos': [0, 0, 0.03], 'vel': [3, 0, 0], 'mass': 0.17},
                {'id': 1, 'shape': 'sphere', 'size': [0.026], 'pos': [0.5, 0, 0.03], 'vel': [0, 0, 0], 'mass': 0.17},
            ]
        elif '积木' in scenario['text'] or '塔' in scenario['text']:
            scene.objects = [
                {'id': 0, 'shape': 'box', 'size': [0.05, 0.02, 0.02], 'pos': [0, 0, 0.01], 'vel': [0, 0, 0], 'mass': 0.5},
                {'id': 1, 'shape': 'box', 'size': [0.04, 0.02, 0.02], 'pos': [0, 0, 0.03], 'vel': [0, 0, 0], 'mass': 0.3},
                {'id': 2, 'shape': 'box', 'size': [0.02, 0.02, 0.02], 'pos': [0, 0, 0.05], 'vel': [3, 0, 0], 'mass': 0.1},
            ]
        elif '水' in scenario['text'] or '杯' in scenario['text']:
            scene.objects = [
                {'id': 0, 'shape': 'sphere', 'size': [0.01], 'pos': [0, 0.3, 0], 'vel': [0, -1, 0], 'mass': 0.01},
                {'id': 1, 'shape': 'box', 'size': [0.05, 0.05, 0.06], 'pos': [0, 0, 0], 'vel': [0, 0, 0], 'mass': 0.2},
            ]

        try:
            is_t1, rmse = self.alpha.check_t1(scene)
            if rmse < 0.1:
                alpha_pred = 0
            elif rmse < 0.3:
                alpha_pred = 1
            else:
                alpha_pred = 2
            alpha_conf = max(0, 1.0 - rmse)

            # 记录对齐（优先使用策略网络预测）
            result = self.gamma.record_alignment(
                scenario['scenario_id'], scenario['text'],
                alpha_pred, alpha_conf
            )

            # 如果策略网络预测了且与 Alpha 不一致 → 标记矛盾
            if nn_pred is not None and nn_pred != alpha_pred:
                self.log(f'Gamma NN矛盾: Alpha={alpha_pred}(rmse={rmse:.3f}) '
                         f'vs NN={nn_pred}(conf={nn_conf:.2f}) '
                         f' | {scenario["text"][:30]}')
                result['nn_contradiction'] = True
                result['nn_pred'] = nn_pred
                result['alpha_pred'] = alpha_pred

            result['nn_pred'] = nn_pred
            return result
        except Exception as e:
            self.log(f'Gamma对齐异常: {e}', 'WARN')
            return {'aligned': None, 'reason': str(e)}

    # ═══════════════════════════════════════
    # SAGE 全对迁移 — 不再只走 4 对
    # ═══════════════════════════════════════

    def _sage_migrate_all(self) -> dict:
        """轮换所有可能的跨域迁移对"""
        all_pairs = list(itertools.product(ALL_DOMAINS, repeat=2))
        # 去掉自己到自己
        all_pairs = [(s, p, t) for s, t in all_pairs if s != t
                     for p in random.sample(ALL_PATTERNS, min(2, len(ALL_PATTERNS)))]

        # 每 5 周期轮换 6 对
        batch_size = 6
        start = (self.sage_pair_idx % (len(all_pairs) // batch_size)) * batch_size
        batch = all_pairs[start:start + batch_size]

        migrations = 0
        new_pairs = []
        for src_d, src_p, tgt_d in batch:
            try:
                r = self.sage.migrate(src_d, src_p, tgt_d)
                if r.get('status') == 'migrated':
                    migrations += 1
                    strength = r.get('strength', 0)
                    if strength > 3:  # 只记录高强度的新迁移
                        new_pairs.append(f'{src_d}/{src_p}→{tgt_d}')
            except Exception:
                pass

        self.sage_pair_idx += 1
        return {'migrations': migrations, 'new_pairs': new_pairs}

    # ═══════════════════════════════════════
    # 主导循环
    # ═══════════════════════════════════════

    def cycle(self) -> dict:
        self.cycles += 1
        result = {'cycle': self.cycles, 'timestamp': datetime.now().isoformat(),
                  'explore': None, 'sage': None, 'gamma': None, 'events': []}

        # ── 1. 强制探索（保证每周期至少产出）──
        if self.cycles % 2 == 0:  # 每 2 周期探索一次，避免过拟合
            explore = self._force_explore()
        else:
            explore = self.explorer.run_cycle()
        result['explore'] = {
            'probes': len(explore.get('probes', [])),
            'discoveries': len(explore.get('discoveries', [])),
            'new_capabilities': len(explore.get('new_capabilities', [])),
        }

        # Novelty 记录 — 每个发现评估新颖度
        novelty_results = []
        for d in explore.get('discoveries', [])[:3]:
            nr = self.novelty_explorer.record_behavior(
                discovery_type=str(d.get('type', 'unknown')),
                region=str(d.get('region', 'unknown')),
                metadata={'cycle': self.cycles},
            )
            novelty_results.append(nr)
        if novelty_results:
            result['novelty'] = {
                'recorded': len(novelty_results),
                'novel': sum(1 for nr in novelty_results if nr['is_new']),
            }

        # ── 2. Gamma 主动对齐（每周期！不是每 3 周期）──
        gamma_result = self._gamma_align()
        self.gamma.sync()
        gamma_status = self.gamma.status()
        result['gamma'] = {
            'scenarios': gamma_status['scenarios']['total_scenarios'],
            'total_judgments': gamma_status['scenarios']['total_judgments'],
            'alignment_rate': gamma_status['alignment'].get('alignment_rate', 0),
            'contradictions': gamma_status['alignment'].get('contradictions', 0),
            'last_check': gamma_result.get('aligned'),
        }

        # Gamma 矛盾 → 丘脑紧急信号
        for contradiction in self.gamma.contradictions[-3:]:
            if contradiction not in result['events']:
                self.log(f'Gamma矛盾: {contradiction["scenario"]} '
                         f'Alpha={contradiction["alpha_said"]} vs Human={contradiction["humans_said"]}')
                result['events'].append({
                    'type': 'gamma_contradiction',
                    'detail': contradiction['scenario'],
                })
                self.thalamus.submit(
                    agent='gamma', signal_type='contradiction', strength=0.85,
                    content={'summary': contradiction['scenario'][:60]})

        # Curiosity 记录 — 状态转移学习 (gamma_result 已定义)
        aligned_val = 1.0 if (gamma_result.get('aligned') or gamma_result.get('aligned') == 0) else 0.0
        current_state = np.array([
            float(len(explore.get('probes', []))),
            float(len(explore.get('discoveries', []))),
            float(len(explore.get('new_capabilities', []))),
            float(aligned_val),
            float(len(self.gamma.contradictions)),
            float(self.causal.graph.get_structure()['n_edges']),
            float(self.dopamine.global_value),
            float(self.hippocampus.n_encoded % 10),
            0.0, 0.0, 0.0, 0.0,
        ])
        # 确保 action 正好 8 维
        action_vals = [float(hash(str(d)) % 100) / 100 for d in explore.get('discoveries', [])]
        while len(action_vals) < 8:
            action_vals.append(0.0)
        current_action = np.array(action_vals[:8])
        if np.sum(np.abs(self.last_state)) > 0:
            icm_result = self.curiosity.record_transition(
                self.last_state, self.last_action, current_state)
            c_score = self.curiosity.score(
                self.last_state, self.last_action, current_state,
                novelty_score=novelty_results[0]['novelty'] if novelty_results else 0.5)
            result['curiosity'] = {
                'fwd_loss': icm_result['fwd_loss'],
                'score': c_score['combined'],
                'mode': c_score['interpretation'],
            }
        self.last_state = current_state.copy()
        self.last_action = current_action.copy()

        # 探索发现 → 丘脑信号 + 海马体编码
        for d in explore.get('discoveries', [])[:2]:
            self.thalamus.submit(
                agent='alpha', signal_type='discovery', strength=0.55,
                content={'summary': str(d.get('type', 'unknown'))[:60]})
            # 编码到海马体
            features = np.random.randn(16) * 0.3
            features[0] = 0.7  # 发现信号
            is_novel, novelty, _ = self.hippocampus.is_novel(features)
            if is_novel:
                self.hippocampus.encode(
                    event_type='discovery', agent='alpha', features=features,
                    content={'detail': str(d)[:100]}, salience=0.5 + novelty * 0.3)

        # ── 3. VCD 因果观测（每周期）──
        # 从最近的物理场景提取特征，更新因果图
        causal_obs = None
        for probe in explore.get('probes', [])[:2]:
            if 'scene' in probe:
                causal_obs = self.causal.observe(probe['scene'])
            elif 'result' in probe and hasattr(probe['result'], 'get'):
                # 手动构建一个近似场景用于因果观测
                pass

        if causal_obs:
            result['causal'] = {
                'edges': causal_obs['structure']['n_edges'],
                'sparsity': causal_obs['structure']['sparsity'],
            }

        # ── 4. 因果同构扫描（每 15 周期）──
        if self.cycles % 15 == 0 and self.cycles > 0:
            homologies = self.causal_bridge.scan_homologies()
            if homologies:
                self.log(f'因果同构发现: {len(homologies)} 对, '
                         f'sim={[h["similarity"] for h in homologies]}')
                result['events'].append({
                    'type': 'causal_homology',
                    'count': len(homologies),
                })

        # ── 5. SAGE 全对迁移（每 5 周期）──
        if self.cycles % 5 == 0:
            sage_result = self._sage_migrate_all()
            result['sage'] = sage_result
            if sage_result['new_pairs']:
                self.log(f'SAGE新高强度迁移: {", ".join(sage_result["new_pairs"])}')
                for pair in sage_result['new_pairs'][:2]:
                    self.thalamus.submit(
                        agent='sage', signal_type='homology', strength=0.6,
                        content={'summary': f'跨域同构: {pair}'})

        # ── 6. 里程碑检测 ──
        total_judgments = gamma_status['scenarios']['total_judgments']
        total_checks = gamma_status['alignment'].get('total_checks', 0)
        if total_judgments > 0 and total_judgments % 50 == 0:
            self.milestones.append({
                'type': 'human_judgments', 'count': total_judgments,
                'time': datetime.now().isoformat(),
            })
            self.log(f'里程碑: {total_judgments} 条真人判断', 'MILESTONE')
        if total_checks > 0 and total_checks % 20 == 0:
            self.log(f'里程碑: {total_checks} 次Gamma对齐检查', 'MILESTONE')

        if self.cycles % 100 == 0:
            self.milestones.append({
                'type': 'cycle', 'cycles': self.cycles,
                'uptime_hours': round((time.time() - self.start_time) / 3600, 1),
                'time': datetime.now().isoformat(),
            })
            self.log(f'运行里程碑: {self.cycles} 周期')

        # ── 7. 海马体回放 + 皮层巩固 ──
        if self.hippocampus.should_replay():
            memories = self.hippocampus.replay()
            if memories:
                cons_result = self.cortex.consolidate_batch(memories)
                self.log(f'海马回放: {len(memories)}条 → 巩固{cons_result["consolidated"]}条 '
                         f'({self.hippocampus.n_consolidated}累计)')

        # ── 8. 丘脑门控裁决 ──
        thalamus_result = self.thalamus.tick()
        if thalamus_result['n_passed'] > 0:
            result['thalamus'] = {
                'broadcasted': thalamus_result['broadcasted'],
                'inhibited': thalamus_result['inhibited'],
            }
            for s in thalamus_result['broadcasted']:
                self.recent_events.append({
                    'type': 'gwt_broadcast',
                    'agent': s['agent'],
                    'signal': s['type'],
                    'salience': s['salience'],
                })
                # 高显著性信号 → 触发三角色辩论
                if s['salience'] > 0.5:
                    topic = DebateTopic(
                        source_agent=s['agent'],
                        source_signal=s['type'],
                        claim=s.get('content', f'{s["agent"]}/{s["type"]}: salience={s["salience"]}'),
                        evidence_for={'salience': s['salience']},
                        evidence_against={},
                        salience=s['salience'],
                    )
                    try:
                        debate_result = self.debate.debate(topic)
                        result['events'].append({
                            'type': 'debate',
                            'verdict': debate_result.verdict,
                            'confidence': debate_result.confidence,
                            'finding': debate_result.key_finding[:100],
                        })
                        if debate_result.verdict in ['confirmed', 'falsified']:
                            self.log(f'辩论裁决: {debate_result.verdict} '
                                     f'(conf={debate_result.confidence}) '
                                     f'{debate_result.key_finding[:60]}')
                    except Exception as e:
                        self.log(f'辩论异常: {e}', 'WARN')

        # ── 9. 运行已部署模块（每 20 周期）──
        if self.cycles % 20 == 0 and self.cycles > 0:
            deployed_results = self.selfarch.run_deployed_modules()
            if deployed_results:
                ok = sum(1 for r in deployed_results if r.get('result', {}).get('success'))
                result['events'].append({
                    'type': 'deployed_modules_run',
                    'total': len(deployed_results),
                    'ok': ok,
                })

        # ── 10. 自架构突破（每 15 周期）──
        if self.cycles % 15 == 0 and self.cycles > 0:
            # 收集最近的盲区
            recent_blind_spots = []
            for e in result.get('events', [])[-5:]:
                if e.get('type') in ['blind_spot', 'gamma_contradiction']:
                    recent_blind_spots.append({
                        'task': e.get('detail', '')[:80],
                        'why_failed': e.get('type', 'unknown'),
                    })
            if recent_blind_spots:
                arch_results = self.selfarch.handle_backlog(recent_blind_spots)
                deployed = sum(1 for r in arch_results if r['action'] == 'DEPLOYED')
                if deployed > 0:
                    self.log(f'自架构: {deployed}/{len(arch_results)} 新模块部署 '
                             f'(成功率{self.selfarch.status()["success_rate"]})')
                    result['events'].append({
                        'type': 'self_architecture',
                        'deployed': deployed,
                        'modules': [r['module_name'] for r in arch_results if r['action'] == 'DEPLOYED'],
                    })

        # ── 10. 统一推理（每 10 周期）──
        if self.cycles % 10 == 0 and self.cycles > 0:
            try:
                question = random.choice([
                    '两个台球碰撞，哪个会改变方向？',
                    '为什么质量越大的物体越难推动？',
                    '证明modus_ponens逻辑推理',
                ])
                reasoning = self.reasoner.reason(question)
                result['reasoning'] = {
                    'question': question[:40],
                    'verdict': reasoning['verdict']['verdict'],
                    'confidence': reasoning['verdict']['confidence'],
                }
                if reasoning['verdict']['verdict'] == 'confirmed':
                    self.log(f'统一推理: {question[:30]}... → {reasoning["verdict"]["verdict"]} '
                             f'(conf={reasoning["verdict"]["confidence"]})')
            except Exception as e:
                self.log(f'推理异常: {e}', 'WARN')

        # ── 11. 情感评估 ──
        emotional = self.emotion.feed(result)
        result['emotion'] = {
            'active': emotional['triggered_emotions'],
            'exploration_boost': emotional['exploration_boost'],
            'gate_mod': emotional['gate_modifiers'],
        }

        # ── 12. 多巴胺价值评估 ──
        value_result = self.value_bridge.evaluate_cycle(result)
        result['dopamine'] = {
            'global_value': self.dopamine.global_value,
            'leaderboard': value_result['leaderboard'],
        }
        if self.cycles % 5 == 0 and value_result['leaderboard']:
            top = value_result['leaderboard'][0]
            self.log(f'价值排行: {top["agent"]}={top["weight"]:.3f}({top["trend"]}) '
                     f'| 全局={self.dopamine.global_value:.3f}')

        # ── 13. 保存状态 ──
        if self.cycles % 5 == 0:
            self._save_status()

        return result

    def _save_status(self):
        explorer_status = self.explorer.status()
        s = {
            'uptime_hours': round((time.time() - self.start_time) / 3600, 1),
            'cycles': self.cycles,
            'explorer': explorer_status,
            'gamma': self.gamma.status(),
            'sage_migrations': self.sage.status().get('migrations', 0) if hasattr(self.sage, 'status') else 0,
            'causal': self.causal.status(),
            'causal_bridge': self.causal_bridge.status(),
            'thalamus': self.thalamus.status(),
            'dopamine': self.dopamine.status(),
            'hippocampus': self.hippocampus.status(),
            'debate': self.debate.status(),
            'novelty': self.novelty_explorer.status(),
            'curiosity': self.curiosity.status(),
            'emotion': self.emotion.status(),
            'milestones': len(self.milestones),
            'recent_events': self.recent_events[-10:],
            'last_update': datetime.now().isoformat(),
        }
        with open(STATUS_FILE, 'w') as f:
            json.dump(s, f, ensure_ascii=False, indent=2)

    def run(self, interval=45):
        self.log(f'Verix v2 激进进化引擎启动 · {interval}s 周期')
        self.gamma.sync()
        self.log(f'Gamma 验证锚: {self.gamma.db.stats()["total_scenarios"]} 场景, '
                 f'{self.gamma.db.stats()["total_judgments"]} 条真人判断')
        self.log(f'SAGE 跨域对池: {len(ALL_DOMAINS)**2 * len(ALL_PATTERNS)} 对可选')

        try:
            while True:
                result = self.cycle()

                if self.cycles % 5 == 0:
                    parts = [f'周期 {self.cycles}']
                    e = result['explore']
                    parts.append(f'探索: {e["probes"]}探/{e["discoveries"]}发现')
                    g = result['gamma']
                    parts.append(f'Gamma对齐: {g["alignment_rate"]} ({g["total_judgments"]}判断)')
                    c = result.get('causal', {})
                    if c:
                        parts.append(f'因果图: {c["edges"]}边')
                    s = result.get('sage', {})
                    parts.append(f'SAGE: {s.get("migrations", 0)}迁移')
                    t = result.get('thalamus', {})
                    if t:
                        parts.append(f'门控: {t["n_passed"]}通/{t["inhibited"]}抑')
                    self.log(' | '.join(parts))

                time.sleep(interval)

        except KeyboardInterrupt:
            self.log('引擎已停止（用户中断）')
        except Exception as e:
            self.log(f'引擎异常退出: {e}', 'ERROR')
            raise

    def status(self):
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE) as f:
                s = json.load(f)
            print(f'运行时间: {s["uptime_hours"]}h  |  周期: {s["cycles"]}')
            print(f'能力地图: {s["explorer"].get("capability_map",{}).get("total_regions",0)} 区域')
            ar = s["gamma"]["alignment"].get("alignment_rate", 0)
            tc = s["gamma"]["alignment"].get("total_checks", 0)
            print(f'Gamma 场景: {s["gamma"]["scenarios"]["total_scenarios"]}  |  '
                  f'判断: {s["gamma"]["scenarios"]["total_judgments"]}  |  '
                  f'对齐检查: {tc}  |  对齐率: {ar}')
            print(f'SAGE 迁移: {s["sage_migrations"]}  |  里程碑: {s["milestones"]}')
            print(f'最后更新: {s["last_update"]}')
        else:
            print('引擎未运行')


if __name__ == '__main__':
    daemon = VerixAutonomousDaemon()

    if '--status' in sys.argv:
        daemon.status()
    elif '--once' in sys.argv:
        for _ in range(5):
            daemon.cycle()
            time.sleep(1)
        daemon.status()
    else:
        daemon.run(interval=45)
