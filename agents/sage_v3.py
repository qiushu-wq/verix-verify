"""SAGE v3 — CRAG 4阶段结构同构迁移引擎"""
import sys
from typing import Optional

sys.path.insert(0, '/opt/verix')
from sage_engine import SAGEEngineV2

# ═══════════════════════════════════════════════
# 1. 问题结构提取器 — 从域问题中提取形式结构
# ═══════════════════════════════════════════════

def extract_structure(domain: str, problem_type: str) -> Optional[dict]:
    """提取问题的形式结构：输入空间、输出空间、约束、变换规则"""
    structures = {
        ('alpha', 'collision'): {
            'input_space': {'type': 'vector', 'dims': ['mass[1..N]', 'velocity[1..N]', 'position[1..N]']},
            'output_space': {'type': 'vector', 'dims': ['final_velocity', 'final_position']},
            'constraints': ['momentum_conservation', 'energy_conservation'],
            'transform': 'linear_system(N_equations, N_unknowns)',
            'failure_mode': '当N>2时，解析解不存在，需数值逼近',
        },
        ('delta', 'template_boundary'): {
            'input_space': {'type': 'vector', 'dims': ['param_type[1..N]', 'param_value[1..N]', 'param_range[1..N]']},
            'output_space': {'type': 'vector', 'dims': ['test_case[1..M]']},
            'constraints': ['type_safety', 'boundary_condition'],
            'transform': 'combinatorial_generation(N_params)',
            'failure_mode': '当N参数组合数超过M_test_limit时，穷举不可行',
        },
        ('alpha', 'critical_stability'): {
            'input_space': {'type': 'scalar_vector', 'dims': ['threshold[1..K]']},
            'output_space': {'type': 'binary', 'dims': ['stable|unstable']},
            'constraints': ['threshold_crossing'],
            'transform': 'decision_boundary(K_dims)',
            'failure_mode': '临界边界附近的微小扰动导致状态翻转',
        },
        ('delta', 'edge_case'): {
            'input_space': {'type': 'scalar_vector', 'dims': ['input_boundary[1..K]']},
            'output_space': {'type': 'binary', 'dims': ['pass|fail']},
            'constraints': ['boundary_proximity'],
            'transform': 'decision_boundary(K_dims)',
            'failure_mode': '输入在边界值附近时，微小变化导致输出翻转',
        },
        # ── Agent β (Lean 4) ──
        ('beta', 'proof_search'): {
            'input_space': {'type': 'vector', 'dims': ['branching_factor', 'depth', 'lemma_count']},
            'output_space': {'type': 'binary', 'dims': ['proved|unproved']},
            'constraints': ['termination', 'combinatorial_explosion'],
            'transform': 'decision_boundary(depth)',
            'failure_mode': '搜索空间指数爆炸——深度每增加1，节点数乘M倍。与多体碰撞的N增长同构',
        },
        ('beta', 'type_mismatch'): {
            'input_space': {'type': 'scalar_vector', 'dims': ['type_var[1..K]']},
            'output_space': {'type': 'binary', 'dims': ['match|mismatch']},
            'constraints': ['unification_constraint'],
            'transform': 'decision_boundary(K_dims)',
            'failure_mode': '类型变量在边界附近微小差异导致匹配失败——与临界稳定性同构',
        },
        # ── Agent ε (KB) ──
        ('epsilon', 'predicate_ambiguity'): {
            'input_space': {'type': 'scalar_vector', 'dims': ['predicate[1..K]']},
            'output_space': {'type': 'binary', 'dims': ['match|mismatch']},
            'constraints': ['semantic_boundary'],
            'transform': 'decision_boundary(K_dims)',
            'failure_mode': '谓词在语义边界附近的微小变化导致映射错误——与模板边界同构',
        },
        ('epsilon', 'knowledge_gap'): {
            'input_space': {'type': 'vector', 'dims': ['entity_count', 'entity_freq[1..N]']},
            'output_space': {'type': 'binary', 'dims': ['covered|uncovered']},
            'constraints': ['coverage_threshold'],
            'transform': 'linear_system(N_entities, coverage)',
            'failure_mode': '覆盖率随实体数指数衰减——与多体碰撞的组合爆炸同构',
        },
    }
    return structures.get((domain, problem_type))


# ═══════════════════════════════════════════════
# 2. 结构同构检测器
# ═══════════════════════════════════════════════

class StructuralIsomorphismDetector:
    """检测两个域问题之间的结构同构"""

    def detect(self, s1: dict, s2: dict) -> Optional[dict]:
        """返回同构映射，或 None"""
        score = 0
        mapping = {}

        # 输出空间同构
        if s1.get('output_space', {}).get('type') == s2.get('output_space', {}).get('type'):
            score += 1
            mapping['output'] = f'{s1["output_space"]["type"]} ↔ {s2["output_space"]["type"]}'

        # 变换规则同构
        if s1.get('transform') == s2.get('transform'):
            score += 2  # 加权——变换同构比输出同构更重要
            mapping['transform'] = s1['transform']

        # 约束同构
        s1c = set(s1.get('constraints', []))
        s2c = set(s2.get('constraints', []))
        shared = s1c & s2c
        if shared:
            score += len(shared)
            mapping['constraints'] = list(shared)

        # 失败模式同构（最关键的信号）
        if s1.get('failure_mode') and s2.get('failure_mode'):
            f1_words = set(s1['failure_mode'].replace('，', ',').split(','))
            f2_words = set(s2['failure_mode'].replace('，', ',').split(','))
            # 共享概念检测
            critical = {'临界', '边界', '微小', '扰动', '翻转', '穷举', '不可行', '组合', '解析'}
            shared_critical = (f1_words & f2_words) & critical
            if shared_critical:
                score += len(shared_critical) * 2
                mapping['failure'] = list(shared_critical)

        if score >= 3:
            mapping['strength'] = score
            return mapping
        return None


# ═══════════════════════════════════════════════
# 3. 解决方案迁移器
# ═══════════════════════════════════════════════

class SolutionTransfer:
    """将源域的解决方案迁移到目标域"""

    KNOWN_SOLUTIONS = {
        'critical_stability': {
            'solution': '在临界边界附近密集采样，远临界区域稀疏采样',
            'technique': 'latin_hypercube_sampling',
            'params': {'dense_region': 'boundary ± δ', 'sparse_region': 'interior'},
        },
        'collision': {
            'solution': '对N>2的问题，用迭代数值方法逼近而非解析求解',
            'technique': 'iterative_approximation',
            'params': {'max_iterations': 1000, 'tolerance': 1e-6},
        },
        'proof_search': {
            'solution': '对搜索空间指数爆炸问题，用启发式剪枝替代穷举搜索',
            'technique': 'heuristic_pruning',
            'params': {'max_depth': 8, 'beam_width': 5},
        },
        'type_mismatch': {
            'solution': '用类型推断+显式标注替代隐式类型假设',
            'technique': 'explicit_type_annotation',
            'params': {},
        },
        'predicate_ambiguity': {
            'solution': '用上下文约束缩小谓词语义范围——在实体出现的前后句子中搜索消歧线索',
            'technique': 'context_disambiguation',
            'params': {'context_window': 2},
        },
        'knowledge_gap': {
            'solution': '对覆盖率随规模下降的问题，用分级知识库——高频实体精确保存，低频实体按类聚合',
            'technique': 'tiered_knowledge_base',
            'params': {'tier1_size': 1000, 'tier2_compression': 0.1},
        },
    }

    def transfer(self, source_problem: str, target_domain: str, mapping: dict) -> dict:
        """将源问题的已知解决方案迁移到目标域"""
        source_sol = self.KNOWN_SOLUTIONS.get(source_problem)
        if not source_sol:
            return None

        transfer = {
            'source_problem': source_problem,
            'target_domain': target_domain,
            'original_solution': source_sol['solution'],
            'technique': source_sol['technique'],
            'mapping_strength': mapping.get('strength', 0),
            'adapted_solution': self._adapt(source_sol, target_domain),
        }

        # 生成可验证的具体操作
        if target_domain == 'delta' and source_problem == 'critical_stability':
            transfer['actionable'] = {
                'type': 'code_template',
                'instruction': '在参数边界值±δ范围内密集生成测试用例，内部稀疏采样',
                'template_hint': 'boundary_focused_test_generation',
            }
        elif target_domain == 'alpha' and source_problem == 'collision':
            transfer['actionable'] = {
                'type': 'physics_model',
                'instruction': '对N>2碰撞用迭代逼近替代解析解',
                'template_hint': 'iterative_collision_solver',
            }

        return transfer

    def _adapt(self, solution: dict, target_domain: str) -> str:
        """根据目标域调整方案描述"""
        if target_domain == 'delta':
            return f"在测试用例生成中应用'临界区域密集采样'策略——参数边界值附近密集生成测试用例"
        if target_domain == 'alpha':
            return f"在物理模拟中应用'迭代逼近'策略——对多体问题放弃解析解，改用数值方法"
        return solution['solution']


# ═══════════════════════════════════════════════
# 4. SAGE v3 引擎
# ═══════════════════════════════════════════════

class SAGEEngineV3:
    """SAGE v3 — CRAG 4阶段: L1预筛 → L2结构提取 → L3反向迁移 → L4验证"""

    PATTERN_MAP = {
        'critical_stability': 'alpha_boundary_critical', 'collision': 'alpha_sync_failure',
        'edge_case': 'delta_combinatorial_edge', 'template_boundary': 'delta_template_ambiguity',
        'proof_search': 'alpha_sync_failure', 'type_mismatch': 'delta_template_ambiguity',
        'predicate_ambiguity': 'delta_template_ambiguity', 'knowledge_gap': 'alpha_boundary_critical',
    }

    def __init__(self):
        self.v2 = SAGEEngineV2()
        self.detector = StructuralIsomorphismDetector()
        self.transfer = SolutionTransfer()
        self.migrations = []
        self.stats = {'L1_hits': 0, 'L2_matches': 0, 'L3_transfers': 0, 'L4_verified': 0}

    def migrate(self, source_domain: str, source_problem: str, target_domain: str) -> dict:
        """CRAG 4阶段完整迁移"""

        # ═══ L1+L2 合并：结构提取 + 直接同构检测（跳过 n-gram 预筛） ═══
        s1 = extract_structure(source_domain, source_problem)
        if not s1:
            return {'status': 'L1_fail', 'msg': f'无法提取 {source_domain}/{source_problem} 的结构'}
        self.stats['L1_hits'] += 1

        # 动态获取目标域所有已注册问题类型
        target_problems = [k[1] for k in extract_structure.__defaults__ if isinstance(k, tuple) and k[0] == target_domain] if False else []
        if not target_problems:
            target_problems = [p for (d, p) in [
                ('alpha','critical_stability'),('alpha','collision'),
                ('delta','edge_case'),('delta','template_boundary'),
                ('beta','proof_search'),('beta','type_mismatch'),
                ('epsilon','predicate_ambiguity'),('epsilon','knowledge_gap'),
            ] if d == target_domain]
        best_match = None
        for target_prob in target_problems:
            s2 = extract_structure(target_domain, target_prob)
            if not s2:
                continue
            mapping = self.detector.detect(s1, s2)
            if mapping and (not best_match or mapping.get('strength', 0) > best_match.get('strength', 0)):
                best_match = {'problem': target_prob, 'structure': s2, 'mapping': mapping}

        if not best_match:
            return {'status': 'L2_fail', 'msg': '结构同构检测未通过'}
        self.stats['L2_matches'] += 1

        # ═══ L3: 反向工程迁移 ═══
        transfer_result = self.transfer.transfer(source_problem, target_domain, best_match['mapping'])
        if not transfer_result:
            return {'status': 'L3_fail', 'msg': '方案迁移失败'}
        self.stats['L3_transfers'] += 1

        # ═══ L4: B 初筛 + 验证 ═══
        verification = self._verify_migration(transfer_result, target_domain)
        if verification.get('verified'):
            self.stats['L4_verified'] += 1

        migration = {
            'source': f'{source_domain}/{source_problem}',
            'target': f'{target_domain}/{best_match["problem"]}',
            'strength': best_match['mapping'].get('strength', 0),
            'stages': {'L1': True, 'L2': True, 'L3': True, 'L4': verification.get('verified', False)},
            'mapping': best_match['mapping'],
            'transfer': transfer_result,
            'verification': verification,
        }
        self.migrations.append(migration)

        return {
            'status': 'migrated',
            'strength': best_match['mapping'].get('strength', 0),
            'target_problem': best_match['problem'],
            'transfer': transfer_result,
            'verified': verification.get('verified', False),
            'stages_passed': migration['stages'],
        }

    def _verify_migration(self, transfer: dict, target_domain: str) -> dict:
        """L4: B 初筛——验证迁移方案的逻辑一致性"""
        score = 0
        checks = []

        # 检验 1：方案是否可行（非空）
        adapted = transfer.get('adapted_solution', '')
        if adapted and len(adapted) > 10:
            score += 1
            checks.append('solution_non_empty')

        # 检验 2：技术是否已知（非 hallucination）
        technique = transfer.get('technique', '')
        known_techniques = {'latin_hypercube_sampling', 'iterative_approximation',
                           'boundary_value_analysis', 'adaptive_mesh_refinement',
                           'heuristic_pruning', 'explicit_type_annotation',
                           'context_disambiguation', 'tiered_knowledge_base'}
        if technique in known_techniques:
            score += 2
            checks.append(f'technique_known: {technique}')

        # 检验 3：是否有可执行的具体操作
        actionable = transfer.get('actionable')
        if actionable and actionable.get('instruction'):
            score += 2
            checks.append('actionable')

        # 检验 4：目标域兼容性
        valid_domains = {'alpha': ['physics_model', 'simulation'], 'delta': ['code_template', 'test_gen']}
        if target_domain in valid_domains:
            expected_types = valid_domains[target_domain]
            if actionable and actionable.get('type') in expected_types:
                score += 1
                checks.append(f'domain_compatible: {actionable["type"]}')

        verified = score >= 4
        return {'verified': verified, 'score': score, 'checks': checks}

    def status(self):
        return {'migrations': len(self.migrations), 'stats': self.stats,
                'recent': self.migrations[-3:] if self.migrations else []}
        """尝试将 source 域的解决方案迁移到 target 域"""
        # Step 1: 提取源域和目标域的问题结构
        s1 = extract_structure(source_domain, source_problem)
        if not s1:
            return {'status': 'no_structure', 'msg': f'无法提取 {source_domain}/{source_problem} 的结构'}

        # Step 2: 搜索目标域中所有可能匹配的子问题
        best_mapping = None
        best_target_problem = None

        for (dom, prob) in [(target_domain, p) for p in ['edge_case', 'template_boundary', 'code_gen']]:
            s2 = extract_structure(dom, prob)
            if not s2:
                continue
            mapping = self.detector.detect(s1, s2)
            if mapping and (not best_mapping or mapping.get('strength', 0) > best_mapping.get('strength', 0)):
                best_mapping = mapping
                best_target_problem = prob

        if not best_mapping:
            # 回退到 v2 的弱匹配
            analogies = self.v2.scan(source_domain,
                                     f'{source_domain}_{source_problem}' if '_' not in source_problem else source_problem)
            if analogies:
                return {'status': 'v2_fallback', 'analogies': analogies[:2], 'strength': analogies[0]['similarity']}
            return {'status': 'no_match', 'msg': '未找到结构同构'}

        # Step 3: 迁移解决方案
        transfer_result = self.transfer.transfer(source_problem, target_domain, best_mapping)

        if not transfer_result:
            return {'status': 'no_transfer', 'msg': '无法迁移方案'}

        # Step 4: 记录迁移
        migration = {
            'source': f'{source_domain}/{source_problem}',
            'target': f'{target_domain}/{best_target_problem}',
            'strength': best_mapping.get('strength', 0),
            'mapping': best_mapping,
            'transfer': transfer_result,
        }
        self.migrations.append(migration)

        return {
            'status': 'migrated',
            'strength': best_mapping.get('strength', 0),
            'source_problem': source_problem,
            'target_problem': best_target_problem,
            'transfer': transfer_result,
        }

    def status(self):
        return {'migrations': len(self.migrations), 'recent': self.migrations[-3:] if self.migrations else []}


# ═══════════════════════════════════════════════
# 5. 演示
# ═══════════════════════════════════════════════

if __name__ == '__main__':
    sage3 = SAGEEngineV3()

    test_pairs = [
        # 5 个 Agent → 10 个域对
        ('alpha', 'critical_stability', 'delta'),  # α→δ
        ('delta', 'edge_case', 'alpha'),           # δ→α
        ('alpha', 'critical_stability', 'beta'),   # α→β
        ('beta', 'proof_search', 'alpha'),         # β→α
        ('alpha', 'critical_stability', 'epsilon'), # α→ε
        ('epsilon', 'knowledge_gap', 'alpha'),     # ε→α
        ('beta', 'proof_search', 'delta'),         # β→δ
        ('delta', 'template_boundary', 'beta'),    # δ→β
        ('beta', 'type_mismatch', 'epsilon'),      # β→ε
        ('epsilon', 'predicate_ambiguity', 'delta'), # ε→δ
    ]

    print('=' * 60)
    print('  SAGE v3 — 结构同构迁移引擎')
    print('=' * 60)

    for src_dom, src_prob, tgt_dom in test_pairs:
        result = sage3.migrate(src_dom, src_prob, tgt_dom)
        icon = '✅' if result['status'] == 'migrated' else '⚠️'
        print(f'\n  {icon} {src_dom}/{src_prob} → {tgt_dom}')
        print(f'     状态: {result["status"]} | 强度: {result.get("strength", "?")}')

        if result.get('transfer'):
            t = result['transfer']
            print(f'     方案: {t["adapted_solution"][:80]}')
            if t.get('actionable'):
                print(f'     操作: {t["actionable"]["type"]} — {t["actionable"]["instruction"][:80]}')

    print(f'\n  迁移记录: {sage3.status()["migrations"]} 次')
