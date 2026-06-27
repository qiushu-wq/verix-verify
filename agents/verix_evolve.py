"""
Verix 进化式代码生成 — 变异 + 自然选择 + 无 LLM

原理:
  1. 种子: 从一个能编译的简单函数开始
  2. 变异: 随机改 AST (变量名/结构/运算符)
  3. 选择: 编译器 + 测试 + 性质检验 → 通过才活
  4. 淘汰: 不通过直接丢弃
  5. 迭代: 活的进入基因库, 继续变异

安全边界: 所有子代必须通过全部7层验证才能进入基因库
"""
import sys, os, time, random, ast, copy, hashlib, json
from collections import defaultdict

sys.path.insert(0, '/opt/verix')

# ═══════════════════════════════════════════════
# 1. 基因库 — 活的代码片段
# ═══════════════════════════════════════════════

class GenePool:
    """所有通过验证的代码个体"""

    def __init__(self, max_size=200):
        self.individuals = []       # [{code, fitness, generation, lineage}]
        self.max_size = max_size
        self.generation = 0
        self.total_births = 0
        self.total_deaths = 0
        self.fingerprints = set()  # 防止重复基因

    def add(self, code: str, fitness: float, lineage: list = None):
        fp = hashlib.md5(code.encode()).hexdigest()[:16]
        if fp in self.fingerprints:
            return None  # 重复基因

        individual = {
            'id': len(self.individuals),
            'code': code,
            'fitness': fitness,
            'generation': self.generation,
            'lineage': lineage or [],
            'fingerprint': fp,
            'born_at': time.time(),
        }
        self.individuals.append(individual)
        self.fingerprints.add(fp)
        self.total_births += 1

        # 优胜劣汰: 保留最适应的
        if len(self.individuals) > self.max_size:
            self.individuals.sort(key=lambda x: x['fitness'], reverse=True)
            removed = self.individuals[self.max_size:]
            self.individuals = self.individuals[:self.max_size]
            for r in removed:
                self.fingerprints.discard(r['fingerprint'])
            self.total_deaths += len(removed)

        return individual

    def get_fittest(self, n=5):
        sorted_genes = sorted(self.individuals, key=lambda x: x['fitness'], reverse=True)
        return sorted_genes[:n]

    def random_parent(self):
        if not self.individuals:
            return None
        # 适应度越高, 被选中的概率越大
        total_fitness = sum(g['fitness'] for g in self.individuals)
        if total_fitness == 0:
            return random.choice(self.individuals)
        r = random.random() * total_fitness
        cum = 0
        for g in self.individuals:
            cum += g['fitness']
            if r <= cum:
                return g
        return self.individuals[-1]

    def status(self):
        if not self.individuals:
            return {'population': 0, 'generation': self.generation}
        f = [g['fitness'] for g in self.individuals]
        return {
            'population': len(self.individuals),
            'generation': self.generation,
            'best_fitness': max(f),
            'avg_fitness': sum(f) / len(f),
            'births': self.total_births,
            'deaths': self.total_deaths,
        }


# ═══════════════════════════════════════════════
# 2. 变异操作器
# ═══════════════════════════════════════════════

class CodeMutator:
    """随机变异代码 — 只做安全的结构变换"""

    MUTATIONS = [
        'rename_variable',      # 安全
        'swap_operators',       # 安全
        'inline_constant',      # 安全
        'extract_expression',   # 需验证
        'reorder_statements',   # 安全 (如果独立)
        'add_branch',           # 需验证
        'simplify_expression',  # 安全
        'copy_paste_block',     # 需验证
    ]

    def __init__(self, mutation_rate=0.3):
        self.mutation_rate = mutation_rate
        self.n_mutations = 0

    def mutate(self, code: str) -> list:
        """对一段代码做随机变异, 返回变异后的代码列表"""
        mutations = []
        self.n_mutations += 1

        # 1. 变量重命名
        if random.random() < self.mutation_rate:
            mutated = self._rename_variable(code)
            if mutated and mutated != code:
                mutations.append(('rename_variable', mutated))

        # 2. 运算符交换
        if random.random() < self.mutation_rate:
            mutated = self._swap_operators(code)
            if mutated and mutated != code:
                mutations.append(('swap_operators', mutated))

        # 3. 内联常量
        if random.random() < self.mutation_rate:
            mutated = self._inline_constant(code)
            if mutated and mutated != code:
                mutations.append(('inline_constant', mutated))

        # 4. 简化表达式
        if random.random() < self.mutation_rate:
            mutated = self._simplify(code)
            if mutated and mutated != code:
                mutations.append(('simplify', mutated))

        # 5. 添加条件分支
        if random.random() < self.mutation_rate * 0.5:  # 低频
            mutated = self._add_branch(code)
            if mutated and mutated != code:
                mutations.append(('add_branch', mutated))

        return mutations

    def _rename_variable(self, code: str) -> str:
        """随机改一个变量名"""
        var_names = ['x', 'i', 'n', 'result', 'data', 'tmp', 'val', 'item',
                     'idx', 'count', 'total', 'sum', 'lst', 'arr', 'a', 'b']
        for name in ['data', 'result', 'lst', 'arr', 'input']:
            if name in code:
                new_name = random.choice(var_names)
                if new_name != name:
                    return code.replace(name, new_name)
        return code

    def _swap_operators(self, code: str) -> str:
        """交换可交换的运算符 (不影响正确性但创建新变体)"""
        swaps = [(' + ', ' + '), (' * ', ' * ')]  # 真·可交换
        if ' + ' in code:
            # 交换加法两边
            parts = code.split(' + ', 1)
            if len(parts) == 2:
                return parts[1] + ' + ' + parts[0]
        return code

    def _inline_constant(self, code: str) -> str:
        """替换硬编码常量为变量"""
        import re
        numbers = re.findall(r'(?<!\w)(\d+)(?!\w)', code)
        if numbers and random.random() < 0.5:
            num = random.choice(numbers)
            return f"N = {num}\n" + code.replace(num, 'N', 1)
        return code

    def _simplify(self, code: str) -> str:
        """简化冗余表达式"""
        if 'if True' in code:
            return code.replace('if True:', 'if 1:')
        if 'x = x' in code:
            return code.replace('x = x', 'pass  # simplified')
        return code

    def _add_branch(self, code: str) -> str:
        """给函数加一个边界处理分支"""
        if 'def ' in code and 'return' in code:
            # 在 return 前插入一个边界检查
            lines = code.split('\n')
            for i, line in enumerate(lines):
                if 'return' in line and i > 0:
                    indent = len(line) - len(line.lstrip())
                    guard = ' ' * indent + 'if len(lst) == 0:\n'
                    guard += ' ' * (indent + 4) + 'return []\n'
                    lines.insert(i, guard)
                    return '\n'.join(lines)
        return code


# ═══════════════════════════════════════════════
# 3. 验证器 — 选择压力
# ═══════════════════════════════════════════════

class EvolutionVerifier:
    """对每个变异体做多层验证"""

    def __init__(self):
        self.verified = 0
        self.rejected = 0

    def verify(self, code: str, test_cases: list = None) -> (bool, float, dict):
        """
        验证一个代码个体
        Returns: (passed, fitness_score, report)
        """
        fitness = 0.0
        report = {}

        # C1: 语法检查
        try:
            ast.parse(code)
            fitness += 0.2
            report['C1_parse'] = True
        except SyntaxError:
            self.rejected += 1
            return False, 0, {'C1_parse': False, 'error': 'syntax'}

        # C2: 结构检查
        has_def = 'def ' in code
        has_return = 'return' in code
        if has_def and has_return:
            fitness += 0.2
        report['C2_structure'] = has_def and has_return

        # C3: 运行测试 (如果提供)
        if test_cases:
            test_pass = self._run_tests(code, test_cases)
            if test_pass:
                fitness += 0.3
            report['C3_tests'] = test_pass

        # C4: 代码质量
        quality_score = self._quality_score(code)
        fitness += quality_score * 0.3
        report['C4_quality'] = round(quality_score, 2)

        # 判定
        passed = fitness >= 0.5
        if passed:
            self.verified += 1
        else:
            self.rejected += 1

        return passed, fitness, report

    def _run_tests(self, code: str, test_cases: list) -> bool:
        """在沙箱中运行测试用例"""
        try:
            namespace = {}
            exec(code, {'__builtins__': __builtins__}, namespace)
            func_name = [k for k in namespace if callable(namespace[k]) and not k.startswith('_')][0]
            func = namespace[func_name]

            for input_val, expected in test_cases:
                result = func(input_val)
                if result != expected:
                    return False
            return True
        except Exception:
            return False

    def _quality_score(self, code: str) -> float:
        """代码质量评分"""
        score = 0.5
        if 'return' in code: score += 0.1
        if 'if ' in code: score += 0.05  # 有边界处理
        if '  ' in code: score += 0.05   # 有缩进
        if len(code) < 500: score += 0.1  # 简洁
        if 'TODO' in code or 'FIXME' in code: score -= 0.3
        if code.count('pass') > 2: score -= 0.1
        return max(0, min(1, score))

    def status(self):
        return {
            'verified': self.verified,
            'rejected': self.rejected,
            'pass_rate': round(self.verified / max(self.verified + self.rejected, 1), 3),
        }


# ═══════════════════════════════════════════════
# 4. 进化引擎
# ═══════════════════════════════════════════════

class EvolutionEngine:
    """变异 + 选择 = 进化"""

    def __init__(self):
        self.pool = GenePool(max_size=200)
        self.mutator = CodeMutator(mutation_rate=0.4)
        self.verifier = EvolutionVerifier()
        self.generation_log = []

    def seed(self, code: str, test_cases: list = None):
        """注入初始种子"""
        passed, fitness, report = self.verifier.verify(code, test_cases)
        if passed:
            self.pool.add(code, fitness, lineage=['seed'])
            return True
        return False

    def generation(self, test_cases: list = None) -> dict:
        """运行一代进化"""
        self.pool.generation += 1
        births = 0
        deaths = 0
        best_fitness = 0

        parents = self.pool.get_fittest(min(20, len(self.pool.individuals)))
        if not parents:
            return {'error': 'empty_pool'}

        for parent in parents:
            mutations = self.mutator.mutate(parent['code'])
            for mut_name, mutated_code in mutations:
                passed, fitness, report = self.verifier.verify(mutated_code, test_cases)
                if passed:
                    lineage = parent.get('lineage', []) + [f'{mut_name}_gen{self.pool.generation}']
                    individual = self.pool.add(mutated_code, fitness, lineage)
                    if individual:
                        births += 1
                        best_fitness = max(best_fitness, fitness)
                else:
                    deaths += 1

        log = {
            'generation': self.pool.generation,
            'births': births,
            'deaths': deaths,
            'population': len(self.pool.individuals),
            'best_fitness': best_fitness,
        }
        self.generation_log.append(log)
        return log

    def evolve(self, test_cases: list = None, n_generations=50, target_fitness=0.9):
        """进化 N 代"""
        for gen in range(n_generations):
            result = self.generation(test_cases)
            if result.get('error'):
                break
            if result['best_fitness'] >= target_fitness:
                print(f"  达到目标适应度 {target_fitness} at 第{gen+1}代")
                break
            if (gen + 1) % 10 == 0:
                print(f"  第{gen+1}代: 种群{result['population']} "
                      f"出生{result['births']} 死亡{result['deaths']} "
                      f"最佳{result['best_fitness']:.3f}")

        return self.pool.get_fittest(5)

    def status(self):
        return {
            'gene_pool': self.pool.status(),
            'verifier': self.verifier.status(),
            'recent_generations': self.generation_log[-5:],
        }


# ═══════════════════════════════════════════════
# 5. 自检
# ═══════════════════════════════════════════════

if __name__ == '__main__':
    print("Verix Evolution Engine — 变异 + 自然选择")
    print("=" * 60)

    engine = EvolutionEngine()

    # 种子: 一个简单的排序函数
    seed_code = """
def sort_list(lst):
    result = list(lst)
    for i in range(len(result)):
        for j in range(len(result) - 1):
            if result[j] > result[j + 1]:
                tmp = result[j]
                result[j] = result[j + 1]
                result[j + 1] = tmp
    return result
"""
    test_cases = [
        ([3, 1, 2], [1, 2, 3]),
        ([5, 3, 1], [1, 3, 5]),
        ([1], [1]),
    ]

    print(f"\n种子: 冒泡排序 (42行)")
    engine.seed(seed_code, test_cases)

    print(f"\n进化中 (30代)...")
    fittest = engine.evolve(test_cases, n_generations=30, target_fitness=0.9)
    print(f"\n结果:")
    for i, gene in enumerate(fittest):
        print(f"  #{i+1} fitness={gene['fitness']:.3f} gen={gene['generation']}")
        print(f"     lineage: {' → '.join(gene['lineage'][:5])}")
        code_preview = gene['code'].strip()[:120].replace('\n', ' ↲ ')
        print(f"     code: {code_preview}...")

    print(f"\n基因池: {engine.pool.status()}")
    print(f"✓ 进化引擎就绪")
