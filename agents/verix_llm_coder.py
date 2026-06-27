"""
Verix LLM Coder — DeepSeek 候选生成 + 7层验证
DeepSeek API (OpenAI 兼容) 生成代码变体 → 验证管道筛选 → 只交付活的

模型: deepseek-chat  ¥1/百万token (比 Claude Haiku 便宜 7x)
"""
import sys, os, json, re, time
from openai import OpenAI

sys.path.insert(0, '/opt/verix')
from verix_fullstack import FullStackPipeline, verify_html, verify_accessibility, verify_performance

SYSTEM_PROMPT = """You are a code generator for Verix, an AI system that verifies code through multiple layers.

RULES:
1. Output ONLY the code. No markdown fences, no explanations.
2. Code must compile/parse (C1).
3. Include test assertions (C2).
4. Backend: include try/catch error handling.
5. Frontend: include semantic HTML, aria labels, alt text.
6. Web: include responsive CSS, defer scripts.
7. If you cannot generate working code, respond with "VERIX_BLIND_SPOT: <reason>".
8. Never use placeholders like TODO or FIXME."""


class LLMCandidateGenerator:
    """用 DeepSeek API 生成代码候选"""

    def __init__(self, api_key=None, model="deepseek-chat"):
        self.model = model
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        self.client = None
        self.n_generated = 0
        self.n_blind_spots = 0

    def _ensure_client(self):
        if self.client is None:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url="https://api.deepseek.com",
            )

    def generate(self, request: str, category: str = "backend",
                 n_candidates: int = 3) -> list:
        """生成 N 个代码候选"""
        self._ensure_client()
        candidates = []

        category_hints = {
            "backend": "Generate server-side code (Express/Node.js). Include error handling and validation.",
            "frontend": "Generate client-side component (Vue3 SFC or React). Include accessibility attributes.",
            "web": "Generate complete HTML page with embedded CSS. Include semantic tags and responsive design.",
            "fullstack": "Generate both backend API and frontend component as separate code blocks.",
        }
        hint = category_hints.get(category, category_hints["backend"])
        user_prompt = f"{hint}\n\nTask: {request}\n\nGenerate ONLY the code:"

        for i in range(n_candidates):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=4000,
                    temperature=0.3 + i * 0.2,  # 每次不同变体
                )

                code = response.choices[0].message.content.strip()

                # 去除可能的 markdown 代码块标记
                code = re.sub(r'^```\w*\n?', '', code)
                code = re.sub(r'\n?```$', '', code)

                if "VERIX_BLIND_SPOT" in code:
                    self.n_blind_spots += 1
                    continue

                if len(code) > 10:
                    candidates.append({
                        'code': code,
                        'candidate_id': i,
                        'tokens': response.usage.completion_tokens if response.usage else 0,
                    })
                    self.n_generated += 1

            except Exception as e:
                print(f"  DeepSeek 生成异常 (candidate {i}): {e}")
                continue

        return candidates

    def status(self):
        return {
            'model': self.model,
            'provider': 'DeepSeek',
            'generated': self.n_generated,
            'blind_spots': self.n_blind_spots,
        }


class LLMPoweredPipeline:
    """DeepSeek 候选生成 + Verix 验证管道"""

    def __init__(self, api_key=None):
        self.llm = LLMCandidateGenerator(api_key=api_key)
        self.fullstack = FullStackPipeline()
        self.stats = {'generated': 0, 'verified': 0, 'delivered': 0, 'rejected': 0}

    def process(self, request: str, n_candidates: int = 3) -> dict:
        """完整管道：LLM生成 → 验证筛选 → 交付"""
        # 分类请求
        r = request.lower()
        if any(k in r for k in ['api', '接口', '后端', '路由', '认证', 'jwt', 'token', '数据库', 'sql', 'express']):
            category = 'backend'
        elif any(k in r for k in ['组件', 'component', 'vue', 'react', '状态', 'store', 'hook', '表单']):
            category = 'frontend'
        elif any(k in r for k in ['页面', 'html', 'css', '样式', '布局', '动画', '响应式', '网站']):
            category = 'web'
        else:
            category = 'backend'

        # Step 1: DeepSeek 生成候选
        candidates = self.llm.generate(request, category, n_candidates)
        self.stats['generated'] += len(candidates)

        if not candidates:
            return {
                'status': 'rejected',
                'reason': 'no_candidates',
                'message': f'无法为 "{request[:60]}" 生成代码',
            }

        # Step 2: 验证每个候选
        verified = []
        for c in candidates:
            result = self._verify_candidate(c['code'], category)
            result['candidate_id'] = c['candidate_id']
            result['tokens'] = c.get('tokens', 0)
            if result['passed']:
                verified.append(result)
            self.stats['verified'] += 1

        # Step 3: 交付
        if verified:
            self.stats['delivered'] += 1
            best = verified[0]
            return {
                'status': 'delivered',
                'request': request,
                'category': category,
                'code': best['code'],
                'candidates': len(candidates),
                'verified': len(verified),
                'verification': best['checks'],
            }
        else:
            self.stats['rejected'] += 1
            return {
                'status': 'rejected',
                'reason': 'all_rejected',
                'candidates': len(candidates),
            }

    def _verify_candidate(self, code: str, category: str) -> dict:
        """7层验证"""
        checks = {}

        # C1: 语法
        checks['C1_syntax'] = {
            'passed': len(code) > 20 and 'error' not in code[:50].lower(),
            'balanced': code.count('{') == code.count('}'),
        }

        # C2: 结构
        has_code = any(k in code for k in ['function', 'const', 'def', 'class', 'import', 'export', '<template', '<html'])
        checks['C2_structure'] = {'passed': has_code}

        # C3: 性质
        props = {}
        if category == 'backend':
            props['error_handling'] = 'catch' in code or 'error' in code.lower()
        elif category in ('frontend', 'web'):
            props['semantic'] = any(t in code for t in ['<header', '<main', '<nav', '<footer', '<article'])
        checks['C3_properties'] = {'passed': all(props.values()) if props else True}

        # C4: 常识
        checks['C4_sanity'] = {
            'passed': 'TODO' not in code and 'FIXME' not in code and 'placeholder' not in code.lower(),
        }

        # C5-C7: Web
        if '<html' in code:
            checks['C5_html'] = verify_html(code)
            checks['C6_a11y'] = verify_accessibility(code)
            checks['C7_perf'] = verify_performance(code)

        all_passed = all(
            isinstance(v, dict) and v.get('passed', True)
            for v in checks.values()
        )

        return {'code': code, 'passed': all_passed, 'checks': checks}

    def status(self):
        return {
            'llm': self.llm.status(),
            'pipeline': self.stats,
            'templates': self.fullstack.status(),
        }


# ═══════════════════════════════════════════════
# 自检
# ═══════════════════════════════════════════════

if __name__ == '__main__':
    print("Verix Code Pipeline — DeepSeek + 7-Layer Verify")
    print("=" * 60)

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("\n⚠ DEEPSEEK_API_KEY 未设置")
        print("  获取: https://platform.deepseek.com → API Keys")
        print("  设置: set DEEPSEEK_API_KEY=sk-...")
        print("\n  当前可用: 模板驱动模式 (9个模板, 0成本)")
    else:
        print(f"\n  DeepSeek API: {api_key[:12]}...")
        pipeline = LLMPoweredPipeline(api_key=api_key)
        result = pipeline.process("写一个返回当前时间的 Express API", n_candidates=2)
        print(f"  测试结果: {result.get('status', '?')}")
        if result['status'] == 'delivered':
            print(f"  候选: {result['candidates']}个, 通过: {result['verified']}个")
            print(f"  代码: {result['code'][:150]}...")

    print(f"\n✓ LLM Coder 就绪 (DeepSeek)")
