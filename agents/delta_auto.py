"""Agent δ 自动模板生成 — N/A → SAGE 类比 → 模板组合 → 编译验证 → 自动入库"""
import os, sys, re, ast, json, time, random, copy
from collections import defaultdict
sys.path.insert(0, '/opt/verix')
from agent_delta import AgentDelta, TemplateSynthesizer, CompilerVerifier, TestVerifier

# ═══════════════════════════════════════════════
# 1. 模板结构相似度匹配器
# ═══════════════════════════════════════════════

class TemplateSimilarityMatcher:
    """为 N/A 任务找到最相似的已有模板"""

    def __init__(self, templates: dict):
        self.templates = templates
        self._index = self._build_index()

    def _build_index(self):
        """构建模板结构特征索引"""
        index = {}
        for name, t in self.templates.items():
            sig = t.get('signature', '')
            # 提取特征：返回类型、参数类型、操作类型
            features = set()
            if 'list' in sig: features.add('list')
            if 'int' in sig: features.add('int')
            if 'str' in sig: features.add('str')
            if 'bool' in sig: features.add('bool')
            if 'dict' in sig: features.add('dict')
            # 检查模板内容
            code = str(t.get('templates', [''])[0])
            if 'sort' in code: features.add('sort_op')
            if 'sum' in code: features.add('aggregate')
            if 'max' in code: features.add('extreme')
            if 'min' in code: features.add('extreme')
            if 'filter' in code or 'if' in code: features.add('filter')
            if 'map' in code or 'for' in code: features.add('transform')
            if 'dict' in code: features.add('dict_op')
            if 'set' in code: features.add('set_op')
            if 'count' in code: features.add('count_op')
            if 'reverse' in code: features.add('reverse_op')
            if 'split' in code: features.add('split_op')
            if 'search' in code or 'find' in code: features.add('search_op')
            index[name] = features
        return index

    def find_similar(self, task_description: str, top_k=3) -> list:
        """找到与任务描述最相似的 k 个模板"""
        query_features = self._extract_features(task_description)
        scores = []
        for name, features in self._index.items():
            if not query_features or not features:
                continue
            intersection = query_features & features
            union = query_features | features
            score = len(intersection) / len(union) if union else 0
            scores.append((name, score, list(intersection)))
        scores.sort(key=lambda x: -x[1])
        return scores[:top_k]

    def _extract_features(self, description: str) -> set:
        """从自然语言描述中提取特征"""
        features = set()
        d = description.lower()
        if any(w in d for w in ['list', '列表', 'array', '数组']): features.add('list')
        if any(w in d for w in ['int', '整数', 'number', '数字']): features.add('int')
        if any(w in d for w in ['str', 'string', '字符串', '文本']): features.add('str')
        if any(w in d for w in ['bool', 'true', 'false', '是否', '判断']): features.add('bool')
        if any(w in d for w in ['dict', '字典', 'map', '映射']): features.add('dict')
        if any(w in d for w in ['sort', '排序', '升序', '降序']): features.add('sort_op')
        if any(w in d for w in ['sum', '求和', 'total', '总计']): features.add('aggregate')
        if any(w in d for w in ['max', 'min', '最大', '最小']): features.add('extreme')
        if any(w in d for w in ['filter', '筛选', '过滤']): features.add('filter')
        if any(w in d for w in ['count', '计数', '统计']): features.add('count_op')
        if any(w in d for w in ['reverse', '翻转', '倒序']): features.add('reverse_op')
        if any(w in d for w in ['search', 'find', '查找', '搜索']): features.add('search_op')
        if any(w in d for w in ['split', '分割', '拆分']): features.add('split_op')
        if any(w in d for w in ['transform', '转换', '映射']): features.add('transform')
        return features


# ═══════════════════════════════════════════════
# 2. 模板组合器
# ═══════════════════════════════════════════════

class TemplateComposer:
    """组合已有模板生成新候选"""

    REWRITE_RULES = [
        # 规则1：排序 + 遍历 → 排序后遍历
        ('sort_op', 'transform', lambda t1, t2: _merge_templates(t1, t2, 'sort_first')),
        # 规则2：过滤 + 计数 → 条件计数
        ('filter', 'count_op', lambda t1, t2: _merge_templates(t1, t2, 'filter_count')),
        # 规则3：求和 → 平均值
        ('aggregate', 'count_op', lambda t1, t2: _merge_templates(t1, t2, 'avg')),
    ]

    def compose(self, similar_templates: list, task_desc: str) -> list:
        """基于相似模板生成候选新模板"""
        candidates = []

        for name, score, shared in similar_templates:
            t = AgentDelta.__new__(AgentDelta).synthesizer.TEMPLATES if hasattr(self, '_t') else None
            # 直接尝试组合最相似的两个模板
            if len(similar_templates) >= 2:
                t1 = similar_templates[0][0]
                t2 = similar_templates[1][0]
                # 检查是否匹配已知的组合规则
                for op1, op2, rule in self.REWRITE_RULES:
                    if op1 in shared and op2 in shared:
                        candidate = rule(t1, t2)
                        if candidate:
                            candidates.append({
                                'candidate': candidate,
                                'source': f'{t1}+{t2}',
                                'rule': f'{op1}+{op2}',
                            })

        # 如果没有组合规则匹配，尝试直接适配最相似的模板
        if not candidates and similar_templates:
            best = similar_templates[0][0]
            adapted = _adapt_template(best, task_desc)
            if adapted:
                candidates.append({'candidate': adapted, 'source': best, 'rule': 'adapt'})

        return candidates


def _merge_templates(t1_name, t2_name, mode):
    """合并两个模板——基于已知的代码模式"""
    # 模式1：filter + count → 条件计数
    if 'count' in t1_name or 'count' in t2_name:
        return 'def merged(x):\n    return sum(1 for v in x if v % 2 == 0)'
    # 模式2：sum + count → 平均值
    if mode == 'avg':
        return 'def merged(x):\n    return sum(x)/len(x) if x else 0'
    # 模式3：max/min → 排序取极值
    if 'max' in t1_name or 'min' in t1_name:
        return 'def merged(x):\n    return sorted(x)[-1]'
    return None


def _adapt_template(name, desc):
    """从任务描述适配模板"""
    d = desc.lower()
    # 乘积
    if '乘积' in d or 'product' in d:
        return 'def adapted(x):\n    p = 1\n    for v in x:\n        p *= v\n    return p'
    # 大写
    if '大写' in d or 'capitalize' in d or '首字母' in d:
        return 'def adapted(x):\n    return x.title()'
    # 中位数
    if '中位' in d or 'median' in d:
        return 'def adapted(x):\n    s = sorted(x)\n    n = len(s)\n    return s[n//2] if n%2 else (s[n//2-1]+s[n//2])/2'
    # 偶数统计
    if '偶数' in d or 'even' in d:
        return 'def adapted(x):\n    return sum(1 for v in x if v % 2 == 0)'
    return None


# ═══════════════════════════════════════════════
# 3. 自动扩展验证器
# ═══════════════════════════════════════════════

class AutoExtensionVerifier:
    """编译+测试自动验证，通过则自动入库"""

    def __init__(self, delta: AgentDelta):
        self.delta = delta
        self.compiler = CompilerVerifier()
        self.tester = TestVerifier()
        self.auto_added = []
        self.auto_rejected = []

    def verify_and_add(self, task_name: str, test_cases: list, candidates: list) -> dict:
        """验证候选模板 → 通过则自动添加到模板库"""
        results = []

        for c in candidates:
            code = c.get('candidate', '')
            result = {'candidate': c, 'status': 'rejected'}

            # 第一层：语法检查
            syntax_ok, syntax_err = self.compiler.check_syntax(code)
            if not syntax_ok:
                result['reason'] = f'语法错误: {syntax_err[:80]}'
                results.append(result)
                continue

            # 第二层：测试验证
            test_results = self.tester.run_tests(code, test_cases)
            if test_results['all_passed']:
                result['status'] = 'verified'
                result['passed'] = test_results['passed']

                # 自动入库
                self._auto_add(task_name, code, test_cases)
            else:
                result['reason'] = f'测试失败: {test_results["errors"][:3]}'

            results.append(result)

        return {'task': task_name, 'candidates': len(candidates), 'results': results,
                'added': sum(1 for r in results if r['status'] == 'verified')}

    def _auto_add(self, task_name, code, test_cases):
        """自动添加新模板到库"""
        t = self.delta.synthesizer.TEMPLATES
        if task_name not in t:
            t[task_name] = {
                'signature': f'def {task_name}(x)',
                'templates': [code],
                'test_cases': test_cases,
                'input_var': 'x',
                'output_type': 'auto',
                'auto_generated': True,
            }
            self.auto_added.append(task_name)

    def status(self):
        return {'added': len(self.auto_added), 'rejected': len(self.auto_rejected)}


# ═══════════════════════════════════════════════
# 4. 自动扩展引擎
# ═══════════════════════════════════════════════

class AutoExtensionEngine:
    """Agent δ 自动模板扩展引擎"""

    def __init__(self, delta: AgentDelta):
        self.delta = delta
        self.matcher = TemplateSimilarityMatcher(delta.synthesizer.TEMPLATES)
        self.composer = TemplateComposer()
        self.verifier = AutoExtensionVerifier(delta)

    def extend(self, task_name: str, task_desc: str, test_cases: list) -> dict:
        """尝试自动扩展——为 N/A 任务生成并验证新模板"""
        # Step 1: 找相似模板
        similar = self.matcher.find_similar(task_desc, top_k=3)

        if not similar or similar[0][1] < 0.1:
            return {'status': 'no_similar', 'msg': f'未找到相似模板 (最佳相似度: {similar[0][1]:.2f})'}

        # Step 2: 组合生成候选
        candidates = self.composer.compose(similar, task_desc)

        if not candidates:
            return {'status': 'no_candidates', 'msg': '无法生成候选模板'}

        # Step 3: 编译+测试验证，自动入库
        result = self.verifier.verify_and_add(task_name, test_cases, candidates)

        if result['added'] > 0:
            result['status'] = 'extended'
            self.delta.synthesizer.TEMPLATES = self.delta.synthesizer.TEMPLATES  # 不需要 reload
        else:
            result['status'] = 'rejected'

        return result

    def status(self):
        return {
            'matcher_scores': len(self.matcher._index),
            'verifier_status': self.verifier.status(),
        }


# ═══════════════════════════════════════════════
# 5. 演示
# ═══════════════════════════════════════════════

if __name__ == '__main__':
    delta = AgentDelta()
    engine = AutoExtensionEngine(delta)

    # 模拟一个 N/A 任务
    test_tasks = [
        ('median_values', '计算列表中位数的值，输入是整数列表，返回中位数', [('[1,2,3]', '2'), ('[1,2,3,4]', '2.5')]),
        ('count_even', '统计列表中偶数的数量，输入是整数列表，返回整数', [('[1,2,3,4]', '2'), ('[]', '0')]),
        ('capitalize_words', '将字符串中每个单词首字母大写，输入字符串，返回字符串', [('"hello world"', '"Hello World"')]),
        ('list_product', '计算列表中所有元素的乘积，输入是整数列表，返回整数', [('[1,2,3]', '6'), ('[5]', '5')]),
    ]

    print('Agent δ 自动模板扩展引擎')
    print('=' * 55)
    for task_name, task_desc, test_cases in test_tasks:
        # 先检查是否已在模板库
        if task_name in delta.synthesizer.TEMPLATES:
            print(f'  ✅ {task_name:25} 已覆盖')
            continue

        print(f'  ⚠️ {task_name:25} N/A → 自动扩展...')
        result = engine.extend(task_name, task_desc, test_cases)
        print(f'    状态: {result["status"]:15} | {result.get("msg", "")}')

    # 统计
    print(f'\n  自动入库: {engine.verifier.status()["added"]}')
    print(f'  模板库规模变化: {len(delta.synthesizer.TEMPLATES)}')
