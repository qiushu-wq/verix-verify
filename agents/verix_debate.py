"""
Verix 三角色对抗推演 — 基于 Irving et al. 2018 "AI safety via debate"
GWT Phase 4: A构建者/B批判者/C实验者

协议:
  1. 全局工作空间广播议题
  2. A 提出假说 (基于 Alpha/因果图)
  3. B 批判假说 (基于 MuJoCo/Gamma矛盾/证据)
  4. C 设计验证实验 (参数空间, 证伪标准)
  5. GWT 裁决: 假说确认/证伪/需更多数据
  6. 最多 3 轮，B 的批判 A 必须在下一轮回应
"""
import os, sys, time, json, math, random
from collections import defaultdict
from dataclasses import dataclass, field
import numpy as np

# ═══════════════════════════════════════════════
# 1. 议题与发言
# ═══════════════════════════════════════════════

@dataclass
class DebateTopic:
    """辩论议题 — 从 GWT 广播中提取"""
    source_agent: str       # 哪个 Agent 的信号触发了辩论
    source_signal: str      # 信号类型
    claim: str              # 核心主张
    evidence_for: dict      # 支持证据
    evidence_against: dict  # 反对证据
    salience: float = 0.5   # 显著性
    timestamp: float = field(default_factory=time.time)

@dataclass
class Statement:
    """一轮发言"""
    role: str               # 'A' | 'B' | 'C'
    round_num: int
    content: str            # 发言内容
    evidence: dict          # 引用的证据
    confidence: float       # 0-1
    references: list        # 引用的验证器结果

@dataclass
class DebateResult:
    """辩论结果"""
    topic: DebateTopic
    rounds: list            # List[List[Statement]] — 每轮 3 个发言
    verdict: str            # 'confirmed' | 'falsified' | 'undecided'
    confidence: float
    key_finding: str        # 核心发现
    action_required: str    # 需要的后续行动
    timestamp: float = field(default_factory=time.time)


# ═══════════════════════════════════════════════
# 2. 角色 A — 乐观构建者
# ═══════════════════════════════════════════════

class RoleA_Builder:
    """
    A — 乐观构建者
    提出假说 + 提供证据 + 做出可证伪的预测
    必须回应 B 的批判
    """

    def __init__(self, alpha=None, causal=None):
        self.alpha = alpha
        self.causal = causal

    def build(self, topic: DebateTopic, round_num: int,
              previous_criticisms: list = None) -> Statement:
        """构建正面论证"""

        evidence = dict(topic.evidence_for)
        confidence = 0.7

        # 有因果图 → 因果推理
        if self.causal:
            causal_structure = self.causal.graph.get_structure()
            if causal_structure['n_edges'] > 0:
                evidence['causal_structure'] = f"{causal_structure['n_edges']} causal edges"
                confidence += 0.05 * min(causal_structure['n_edges'], 5)

        # 有 Alpha → 物理直觉
        if self.alpha:
            evidence['physics_model'] = f'GNN step {self.alpha.global_step}'
            confidence += 0.05

        # 构建主张
        claim = f"[A] 基于{len(evidence)}项证据: {topic.claim}"
        if previous_criticisms:
            # 回应 B 的批判
            responses = []
            for crit in previous_criticisms[-2:]:
                if isinstance(crit, Statement):
                    responses.append(f"回应'{crit.content[:50]}...': 证据仍成立，需更多数据验证")
            if responses:
                claim += " | " + " | ".join(responses)

        return Statement(
            role='A', round_num=round_num,
            content=claim, evidence=evidence,
            confidence=min(1.0, confidence),
            references=list(evidence.keys()),
        )


# ═══════════════════════════════════════════════
# 3. 角色 B — 严苛批判者
# ═══════════════════════════════════════════════

class RoleB_Critic:
    """
    B — 严苛批判者
    找逻辑漏洞、验证矛盾、反例
    禁止笼统质疑 → 必须具体到数据
    """

    def __init__(self, gamma_bridge=None, hippocampus=None):
        self.gamma = gamma_bridge
        self.hippocampus = hippocampus

    def critique(self, topic: DebateTopic, statement_a: Statement,
                 round_num: int) -> Statement:
        """批判 A 的论证"""

        criticisms = []
        evidence = dict(topic.evidence_against)
        confidence = 0.5

        # 1. Gamma 矛盾检查
        if self.gamma:
            contradictions = self.gamma.contradictions[-5:]
            for c in contradictions:
                if c.get('scenario', '')[:20] in topic.claim[:40]:
                    criticisms.append(
                        f"人类共识矛盾: {c['scenario'][:40]} "
                        f"(人类选{c['humans_said']} vs Alpha选{c['alpha_said']}, "
                        f"人类一致性{c.get('human_agreement',0):.0%})")
                    evidence['gamma_contradiction'] = c
                    confidence += 0.15

        # 2. 海马体反例检索
        if self.hippocampus:
            similar = self.hippocampus.retrieve_by_type('contradiction', limit=5)
            for m in similar:
                if hasattr(m, 'content'):
                    criticisms.append(f"历史反例: {str(m.content)[:60]}")
                    confidence += 0.05
                    break

        # 3. 如果找不到具体漏洞 → 提出需要验证的点
        if not criticisms:
            criticisms.append(
                "缺乏反面证据，但这不意味着假说成立——需要独立验证")
            confidence = 0.3

        # 4. 数量级检查
        criticisms.append(
            "要求A给出数量级估计: 效应的预期大小? 置信度?")

        return Statement(
            role='B', round_num=round_num,
            content=" | ".join(criticisms),
            evidence=evidence,
            confidence=min(1.0, confidence),
            references=list(evidence.keys()),
        )


# ═══════════════════════════════════════════════
# 4. 角色 C — 实验主义者
# ═══════════════════════════════════════════════

class RoleC_Experimenter:
    """
    C — 实验主义者
    设计验证实验 + 证伪标准 + 条件参数
    预算上限: 虚拟 (CPU周期)
    """

    def __init__(self, alpha=None, delta=None):
        self.alpha = alpha
        self.delta = delta

    def design(self, topic: DebateTopic,
               statement_a: Statement, statement_b: Statement,
               round_num: int) -> Statement:
        """设计验证实验"""

        # 从 A 的假说和 B 的批判中提取可测试点
        test_design = {
            'hypothesis': topic.claim[:100],
            'test_type': 'comparative',
            'groups': [],
            'metrics': [],
            'falsification_criteria': '',
        }

        # 物理类 → MuJoCo 对照实验
        if topic.source_agent in ['alpha', 'gamma']:
            test_design['test_type'] = 'mu_jo_co_comparison'
            test_design['groups'] = [
                {'name': 'control', 'params': 'default physics'},
                {'name': 'test', 'params': 'varied mass/velocity'},
                {'name': 'human_baseline', 'params': 'gamma_consensus'},
            ]
            test_design['metrics'] = ['rmse', 'alignment_rate', 'causal_consistency']
            test_design['falsification_criteria'] = (
                '如果对照组与测试组 RMSE 差异 < 0.05, 且对齐率 < 0.8, 则假说证伪')

        # 逻辑/代码类 → 编译器+测试
        elif topic.source_agent in ['delta', 'beta']:
            test_design['test_type'] = 'compiler_verification'
            test_design['groups'] = [
                {'name': 'reference', 'params': 'known_correct'},
                {'name': 'generated', 'params': 'agent_output'},
            ]
            test_design['metrics'] = ['compilation_pass', 'test_pass_rate', 'coverage']
            test_design['falsification_criteria'] = (
                '如果编译失败 或 测试通过率 < 90%, 则假说证伪')

        # 因果发现类
        elif topic.source_agent in ['causal', 'sage']:
            test_design['test_type'] = 'causal_intervention'
            test_design['groups'] = [
                {'name': 'observational', 'params': 'natural_distribution'},
                {'name': 'interventional', 'params': 'do(X=value)'},
            ]
            test_design['metrics'] = ['mechanism_shift', 'invariance_score']
            test_design['falsification_criteria'] = (
                '如果干预后因果边强度变化 < 0.1, 则不是因果边而是相关性')

        return Statement(
            role='C', round_num=round_num,
            content=json.dumps(test_design, ensure_ascii=False),
            evidence={'test_design': test_design},
            confidence=0.6,
            references=['mu_jo_co', 'lean4', 'compiler', 'gamma_db'],
        )


# ═══════════════════════════════════════════════
# 5. 对抗推演引擎
# ═══════════════════════════════════════════════

class DebateEngine:
    """三角色对抗推演引擎"""

    def __init__(self, alpha=None, causal=None, gamma=None, hippocampus=None, delta=None):
        self.role_a = RoleA_Builder(alpha=alpha, causal=causal)
        self.role_b = RoleB_Critic(gamma_bridge=gamma, hippocampus=hippocampus)
        self.role_c = RoleC_Experimenter(alpha=alpha, delta=delta)

        self.max_rounds = 3
        self.debate_history = []  # List[DebateResult]
        self.n_debates = 0
        self.n_confirmed = 0
        self.n_falsified = 0
        self.n_undecided = 0

    def debate(self, topic: DebateTopic) -> DebateResult:
        """执行完整的三角色对抗推演"""
        self.n_debates += 1
        all_statements = []
        previous_criticisms = []

        for r in range(self.max_rounds):
            # A 发言
            stmt_a = self.role_a.build(topic, r + 1, previous_criticisms)

            # B 批判
            stmt_b = self.role_b.critique(topic, stmt_a, r + 1)

            # C 设计实验
            stmt_c = self.role_c.design(topic, stmt_a, stmt_b, r + 1)

            all_statements.append([stmt_a, stmt_b, stmt_c])
            previous_criticisms.append(stmt_b)

            # 检查是否达成共识
            if r >= 1:
                verdict = self._arbitrate(all_statements)
                if verdict != 'undecided':
                    break

        # 最终裁决
        verdict = self._arbitrate(all_statements)
        confidence = self._calc_confidence(all_statements)

        result = DebateResult(
            topic=topic,
            rounds=all_statements,
            verdict=verdict,
            confidence=confidence,
            key_finding=self._extract_finding(all_statements, verdict),
            action_required=self._action(topic, verdict),
        )

        self.debate_history.append(result)
        if verdict == 'confirmed':
            self.n_confirmed += 1
        elif verdict == 'falsified':
            self.n_falsified += 1
        else:
            self.n_undecided += 1

        return result

    def _arbitrate(self, all_statements: list) -> str:
        """GWT 裁决: 审视全部发言, 裁定假说状态"""
        if len(all_statements) < 2:
            return 'undecided'

        last_round = all_statements[-1]
        stmt_a, stmt_b, stmt_c = last_round

        # B 的置信度 < 0.3 → 批评无力 → 假说暂成立
        # B 的置信度 > 0.7 → 批评有力 → 假说证伪
        # A 回应了 B 的批评且 B 置信度下降 → 假说增强

        if stmt_b.confidence > 0.7 and stmt_b.references:
            return 'falsified'
        elif stmt_b.confidence < 0.35:
            return 'confirmed'
        elif len(all_statements) >= self.max_rounds:
            # 打满回合未分胜负
            if stmt_a.confidence > stmt_b.confidence:
                return 'confirmed'
            else:
                return 'falsified'
        return 'undecided'

    def _calc_confidence(self, all_statements: list) -> float:
        if not all_statements:
            return 0.5
        confs = []
        for round_stmts in all_statements:
            for s in round_stmts:
                confs.append(s.confidence)
        return round(np.mean(confs), 3) if confs else 0.5

    def _extract_finding(self, all_statements: list, verdict: str) -> str:
        if not all_statements:
            return "无足够发言"
        stmt_b = all_statements[-1][1]
        if verdict == 'falsified':
            return f"假说证伪: {stmt_b.content[:80]}"
        elif verdict == 'confirmed':
            return f"假说暂立: {stmt_b.content[:80]}"
        return "需更多数据"

    def _action(self, topic: DebateTopic, verdict: str) -> str:
        if verdict == 'confirmed':
            return f"将确认的假说写入 fact_db, 降低 {topic.source_agent} 盲区权重"
        elif verdict == 'falsified':
            return f"对 {topic.source_agent} 触发盲区学习, 生成针对性变体"
        return f"增加 Gamma 场景, 收集人类判断 (当前需>30条/场景)"

    def status(self) -> dict:
        return {
            'total_debates': self.n_debates,
            'confirmed': self.n_confirmed,
            'falsified': self.n_falsified,
            'undecided': self.n_undecided,
            'recent': [{
                'verdict': r.verdict,
                'confidence': r.confidence,
                'topic': r.topic.claim[:60],
            } for r in self.debate_history[-3:]],
        }


# ═══════════════════════════════════════════════
# 6. 自检
# ═══════════════════════════════════════════════

if __name__ == '__main__':
    print("Verix Debate Engine — Irving et al. 2018")

    engine = DebateEngine()

    # 模拟辩论
    topic1 = DebateTopic(
        source_agent='alpha', source_signal='discovery',
        claim='碰撞中物体质量主导最终速度分布',
        evidence_for={'alpha_rmse': 0.08, 'samples': 50},
        evidence_against={},
    )
    result = engine.debate(topic1)
    print(f"\n  辩论 #1: {result.verdict} (conf={result.confidence})")
    print(f"    发现: {result.key_finding}")
    print(f"    行动: {result.action_required}")

    topic2 = DebateTopic(
        source_agent='gamma', source_signal='contradiction',
        claim='积木塔底积木被推开，全塔倒塌 vs 只倒底积木',
        evidence_for={'gamma_consensus': '全塔倒塌', 'agreement': 0.71},
        evidence_against={'alpha_rmse': 0.22},
    )
    result2 = engine.debate(topic2)
    print(f"\n  辩论 #2: {result2.verdict} (conf={result2.confidence})")
    print(f"    发现: {result2.key_finding}")
    print(f"    行动: {result2.action_required}")

    print(f"\n  状态: {engine.status()}")

    print("\n✓ 三角色对抗就绪")
