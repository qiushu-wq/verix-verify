"""SAGE 真结构推理引擎 — CRAG 四阶段模板提取"""
import json, time
from collections import defaultdict

# ═══════════════════════════════════════════════
# 1. 结构模板库 — 每个域的结构失败模式
# ═══════════════════════════════════════════════

STRUCTURE_TEMPLATES = {
    'alpha': {
        'name': '物理推理',
        'patterns': [
            {
                'id': 'alpha_sync_failure',
                'name': '双过程同步失败',
                'structure': '{过程A}和{过程B}被假设为{同步关系}协同，但{过程A}的本征时间尺度{τ_A}和{过程B}的本征时间尺度{τ_B}相差{N}个数量级。同步假设要求{同步条件}，但{物理约束}使同步不可能。',
                'abstract': '两个独立过程的时间尺度错配导致协同假设不成立',
                'detection': ['碰撞', '堆叠', '多体'],
                'source_solutions': [
                    {'domain': '经济学', 'solution': '货币政策不试图和市场价格同步——通过前瞻性指引间接引导预期'},
                    {'domain': '生态学', 'solution': '物种不加速进化——通过迁移改变栖息地环境'},
                    {'domain': '软件架构', 'solution': '异步消息队列——不假设两个服务同时响应'},
                ],
            },
            {
                'id': 'alpha_boundary_critical',
                'name': '边界临界稳定性',
                'structure': '{系统}在{边界条件}下从{有序状态}向{无序状态}的转变取决于{N}个参数的{组合关系}。当任一参数接近{临界值}时，微小扰动导致{系统}行为产生{质变}。',
                'abstract': '多参数边界条件的临界稳定性——在边界附近系统行为不可预测',
                'detection': ['堆叠', '斜面', '混合'],
                'source_solutions': [
                    {'domain': '软件测试', 'solution': '边界值分析——在参数取值范围的边界上密集测试，内部稀疏测试'},
                    {'domain': '气候科学', 'solution': '临界点监测——在临界阈值附近部署密集传感器，远临界值区域稀疏采样'},
                ],
            },
            {
                'id': 'alpha_friction_irreversible',
                'name': '摩擦不可逆转换',
                'structure': '{系统}的{状态转换}涉及{摩擦力}从{静摩擦}到{动摩擦}的{不可逆转换}。转换点由{压力}和{接触面积}的{非线性关系}决定。',
                'abstract': '不可逆临界转换点的非线性动力学',
                'detection': ['斜面', '滑动'],
                'source_solutions': [
                    {'domain': '材料科学', 'solution': '屈服强度——材料在临界应力处发生不可逆塑性变形，设计时避免接近此点'},
                ],
            },
        ],
    },
    'delta': {
        'name': '编程推理',
        'patterns': [
            {
                'id': 'delta_combinatorial_edge',
                'name': '参数组合爆炸',
                'structure': '代码{模板}的{输入参数}在{边界值}处产生{组合爆炸}。{N}个参数各有{M}个取值范围，组合数={M}^{N}。测试覆盖所有组合{不可行}，边缘case{未被覆盖}。',
                'abstract': '多参数组合爆炸导致边界条件未被充分测试',
                'detection': ['模板填充', '边界值', '多参数'],
                'source_solutions': [
                    {'domain': '物理模拟', 'solution': '临界稳定性分析——识别关键参数组合，在临界区域密集采样，非临界区域稀疏采样'},
                    {'domain': '统计实验设计', 'solution': '拉丁超立方采样——在参数空间中均匀分布采样点，确保覆盖各维度边界'},
                ],
            },
            {
                'id': 'delta_template_ambiguity',
                'name': '模板边界模糊',
                'structure': '模板{模板名}适用于{适用条件}，但输入{实际输入}处于{适用条件}的{边界}。模板的{输出格式}与{测试预期}的{差异}源于{输出类型}的{隐式假设}。',
                'abstract': '模板适用边界不明确导致的输出格式失配',
                'detection': ['输出格式', '列表', 'dict'],
                'source_solutions': [
                    {'domain': '法律解释', 'solution': '明确法条适用范围——在法律的模棱两可处，以判例法补充明确边界'},
                ],
            },
        ],
    },
    'epsilon': {
        'name': '事实推理',
        'patterns': [
            {
                'id': 'epsilon_predicate_ambiguity',
                'name': '谓词映射歧义',
                'structure': '陈述"{陈述}"中的{主语}和{宾语}通过{谓词}连接，但{谓词}映射到的{知识库属性}在{主语}的{实际属性集}中{不匹配}。{谓词}的{语义范围}比{知识库属性}{更宽/更窄}。',
                'abstract': '自然语言谓词到知识库属性的映射歧义',
                'detection': ['P19', 'P27', '出生'],
                'source_solutions': [
                    {'domain': '翻译学', 'solution': '一词多义消歧——用上下文约束缩小候选词义范围'},
                ],
            },
        ],
    },
}


class SAGEEngineV2:
    """SAGE 真结构推理引擎 — CRAG 四阶段"""

    def __init__(self):
        self.scan_count = 0
        self.match_count = 0

    # ── 阶段 1：结构模板提取 ──
    def extract_structure(self, agent: str, t1_events: list) -> list:
        """从 Agent 的 T1 事件中提取失败的结构模板"""
        if agent not in STRUCTURE_TEMPLATES:
            return []

        domain = STRUCTURE_TEMPLATES[agent]
        matched = []

        for pattern in domain['patterns']:
            # 检测 T1 事件是否匹配该结构模板的 detection 关键词
            detection_hits = 0
            total_events = len(t1_events)
            for event in t1_events:
                detail = event.get('detail', '')
                scene_type = event.get('scene_type', '')
                for kw in pattern['detection']:
                    if kw in detail or kw in scene_type:
                        detection_hits += 1
                        break

            if detection_hits >= min(2, total_events):
                matched.append({
                    'pattern': pattern,
                    'hit_rate': detection_hits / max(total_events, 1),
                    'agent': agent,
                })

        return matched

    # ── 阶段 2：跨域同构搜索 ──
    def search_isomorphic(self, source_agent: str, source_pattern_id: str) -> list:
        """在其他域中搜索同构结构模板"""
        source_pattern = None
        for p in STRUCTURE_TEMPLATES.get(source_agent, {}).get('patterns', []):
            if p['id'] == source_pattern_id:
                source_pattern = p
                break
        if not source_pattern:
            return []

        source_abstract = source_pattern['abstract']
        analogies = []

        for agent_key, domain in STRUCTURE_TEMPLATES.items():
            if agent_key == source_agent:
                continue
            for target in domain['patterns']:
                # 结构同构检测：比较 abstract 字段
                similarity = self._abstract_similarity(source_abstract, target['abstract'])
                if similarity >= 0.3:
                    # 收集该目标域的源解决方案
                    for sol in target.get('source_solutions', []):
                        analogies.append({
                            'source_agent': source_agent,
                            'source_pattern': source_pattern['name'],
                            'source_abstract': source_abstract,
                            'target_agent': agent_key,
                            'target_pattern': target['name'],
                            'target_domain': domain['name'],
                            'similarity': similarity,
                            'solution_domain': sol['domain'],
                            'solution': sol['solution'],
                            'suggestion': (
                                f'{domain["name"]}的"{target["name"]}"\n'
                                f'  ↔ {source_pattern["name"]}\n'
                                f'  来源: {sol["domain"]}\n'
                                f'  方案: {sol["solution"]}'
                            ),
                        })
        analogies.sort(key=lambda a: a['similarity'], reverse=True)
        self.match_count += len(analogies)
        return analogies

    # ── 阶段 3：验证 → 交由调用方用 Agent δ 编译器验证 ──

    # ── 辅助：抽象概念相似度 ──
    def _abstract_similarity(self, a: str, b: str) -> float:
        """中文结构描述相似度——基于 2-gram + 核心概念词"""
        # 2-gram 集合（覆盖"边界条件"、"临界稳定"等复合词）
        def ngrams(text, n=2):
            clean = text.replace('——', '').replace('、', '').replace('，', '').replace('。', '')
            return {clean[i:i+n] for i in range(len(clean)-n+1)}

        grams_a = ngrams(a, 2) | ngrams(a, 3)
        grams_b = ngrams(b, 2) | ngrams(b, 3)

        intersection = grams_a & grams_b
        union = grams_a | grams_b
        if not union:
            return 0
        base = len(intersection) / len(union)

        # 核心概念词加分（单字+复合词均覆盖）
        advanced = {'临界', '边界', '不可逆', '组合', '爆炸', '数量级', '同步', '转换', '歧义', '阈值', '非线性', '参数', '稳定', '多参数', '模板', '失配'}
        adv_hits = sum(1 for w in advanced if w in a and w in b)
        boost = adv_hits * 0.08

        return min(1.0, base + boost)

    def scan(self, source_agent: str, source_pattern: str = None) -> list:
        """主入口：给定 Agent + 模式ID，返回跨域类比列表"""
        self.scan_count += 1
        return self.search_isomorphic(source_agent, source_pattern)

    def status(self):
        return {'scans': self.scan_count, 'matches': self.match_count}
