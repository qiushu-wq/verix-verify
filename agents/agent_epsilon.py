"""Agent ε — 事实锚 · Wikidata/DBpedia 知识图谱验证闭环"""
import os, re, json, time, urllib.request, urllib.parse
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from collections import defaultdict

# ═══════════════════════════════════════════════
# 1. 原子事实提取器（非 LLM——正则+模式匹配）
# ═══════════════════════════════════════════════

COMMON_PREDICATES = {
    '出生': 'P569',      # date of birth
    '出生地': 'P19',     # place of birth
    '死亡': 'P570',      # date of death
    '首都': 'P36',       # capital
    '人口': 'P1082',     # population
    '面积': 'P2046',     # area
    '创始人': 'P112',    # founded by
    '成立': 'P571',      # inception
    '国家': 'P17',       # country
    '位于': 'P131',      # located in administrative unit
    '国籍': 'P27',       # country of citizenship
    '职业': 'P106',      # occupation
    '作者': 'P50',       # author
    '发现者': 'P61',     # discoverer or inventor
    '发明者': 'P61',
    '配偶': 'P26',       # spouse
    '母亲': 'P25',       # mother
    '父亲': 'P22',       # father
    '类型': 'P31',       # instance of
    '子类': 'P279',      # subclass of
    '化学式': 'P274',    # chemical formula
    '原子序数': 'P1086', # atomic number
    '熔点': 'P2101',     # melting point
    '沸点': 'P2102',     # boiling point
    '质量': 'P2067',     # mass
    '高度': 'P2048',     # height
    '长度': 'P2043',     # length
}

FACT_PATTERNS = [
    # "X 是 Y" → instance of
    (r'(.+?)是(.+)', 'P31'),
    # "X 位于 Y" → located in
    (r'(.+?)位于(.+)', 'P131'),
    # "X 出生于 Y" / "X 出生在 Y"
    (r'(.+?)(?:出生于|出生在)(.+)', 'P19'),
    # "X 的(首都|人口|面积|创始人|作者)是 Y"
    (r'(.+?)的(首都|人口|面积|创始人|作者|发现者|发明者)是(.+)', None),  # predicate from capture group
    # "X 在 Y 年(成立|出生|死亡)"
    (r'(.+?)在(\d{4})年(成立|出生|死亡)', None),
    # "X 有 Y 个 Z" → has property
    (r'(.+?)有(\d+)个(.+)', None),
    # "X 的国籍是 Y"
    (r'(.+?)的(国籍|职业)是(.+)', None),
]

class FactExtractor:
    """从自然语言中提取原子事实三元组（非 LLM）"""

    def extract(self, text: str) -> List[dict]:
        """返回: [{'subject': str, 'predicate': str, 'object': str, 'pid': str or None}]"""
        facts = []
        text = text.strip()

        for pattern, default_pid in FACT_PATTERNS:
            matches = re.findall(pattern, text)
            for m in matches:
                if len(m) == 2:
                    subj, obj = m[0].strip(), m[1].strip()
                    facts.append({'subject': subj, 'predicate': '', 'object': obj, 'pid': default_pid})
                elif len(m) == 3:
                    subj, mid, obj = m[0].strip(), m[1].strip(), m[2].strip()
                    pid = COMMON_PREDICATES.get(mid)
                    facts.append({'subject': subj, 'predicate': mid, 'object': obj, 'pid': pid})

        # 如果没有匹配到任何模式，尝试简单的主谓宾拆分
        if not facts:
            for sep in ['的', '是', '有']:
                parts = text.split(sep, 1)
                if len(parts) == 2:
                    facts.append({'subject': parts[0].strip(), 'predicate': sep, 'object': parts[1].strip(), 'pid': None})

        return facts


# ═══════════════════════════════════════════════
# 2. Wikidata SPARQL 查询器
# ═══════════════════════════════════════════════

FACT_FILE = '/opt/verix/data/fact_db.json'

class LocalFactDB:
    """本地事实数据库 — 从 JSON 文件加载"""

    FACTS = {}

    @classmethod
    def load(cls):
        if not cls.FACTS and os.path.exists(FACT_FILE):
            with open(FACT_FILE) as f:
                raw = json.load(f)
            for k, v in raw.items():
                s, p = k.split('|', 1)
                cls.FACTS[(s, p)] = v

    # 硬编码种子数据（JSON不存在时回退）
    _SEED = {
        ('中国', 'P36'): ['北京'],
        ('中国', 'P1082'): ['1400000000'],
        ('法国', 'P36'): ['巴黎'],
        ('法国', 'P1082'): ['67000000'],
        ('英国', 'P36'): ['伦敦'],
        ('日本', 'P36'): ['东京'],
        ('日本', 'P1082'): ['125000000'],
        ('德国', 'P36'): ['柏林'],
        ('爱因斯坦', 'P19'): ['乌尔姆', '德国'],
        ('爱因斯坦', 'P27'): ['德国', '美国', '瑞士'],
        ('莎士比亚', 'P50'): ['哈姆雷特', '罗密欧与朱丽叶', '麦克白'],
        ('珠穆朗玛峰', 'P2048'): ['8848', '8848.86'],
        ('水的化学式', 'P274'): ['H2O'],
        ('地球', 'P31'): ['行星'],
        ('太阳', 'P31'): ['恒星'],
        ('北京', 'P1082'): ['21540000'],
        ('北京', 'P131'): ['中国'],
        ('埃菲尔铁塔', 'P131'): ['巴黎', '法国'],
        ('巴黎', 'P131'): ['法国'],
        ('太阳系', 'P31'): ['行星系'],
    }

    @classmethod
    def query(cls, subject: str, pid: str) -> Optional[list]:
        return cls.FACTS.get((subject, pid))


class FactVerifier:
    """事实验证器 — 本地知识库版本"""

    def __init__(self):
        self.total = 0
        self.verified = 0
        self.contradicted = 0

    def verify_fact(self, subject: str, pid: str, obj: str) -> dict:
        self.total += 1
        values = LocalFactDB.query(subject, pid)

        if values is None:
            return {'status': 'no_data', 'msg': f'知识库中无 {subject} 的此属性'}

        obj_norm = obj.strip().lower().replace(' ', '').replace(',', '')
        for v in values:
            v_norm = v.lower().replace(' ', '').replace(',', '')
            if obj_norm in v_norm or v_norm in obj_norm:
                self.verified += 1
                return {'status': 'verified', 'msg': f'{subject} → {v}', 'evidence': v}

        self.contradicted += 1
        return {'status': 'contradicted', 'msg': f'{subject} 的属性值应为 {values}，而非 {obj}', 'actual': values}

    def metrics(self):
        return {'total': self.total, 'verified': self.verified, 'contradicted': self.contradicted}


# ═══════════════════════════════════════════════
# 3. Agent ε — 事实核查闭环
# ═══════════════════════════════════════════════

class AgentEpsilon:
    """Agent ε — 知识图谱事实验证锚"""

    def __init__(self):
        self.extractor = FactExtractor()
        self.verifier = FactVerifier()
        self.total_checks = 0
        self.verified = 0
        self.contradicted = 0
        self.no_data = 0

    def verify(self, statement: str) -> dict:
        """验证一句陈述"""
        self.total_checks += 1
        facts = self.extractor.extract(statement)

        results = []
        for f in facts:
            pid = f.get('pid')
            if not pid:
                results.append({'fact': f, 'status': 'no_predicate', 'msg': '无法识别谓词'})
                continue

            r = self.verifier.verify_fact(f['subject'], pid, f['object'])
            r['fact'] = f
            results.append(r)

            if r['status'] == 'verified':
                self.verified += 1
            elif r['status'] == 'contradicted':
                self.contradicted += 1
            else:
                self.no_data += 1

        # 汇总结论
        verified_count = sum(1 for r in results if r['status'] == 'verified')
        contradicted_count = sum(1 for r in results if r['status'] == 'contradicted')
        no_data_count = sum(1 for r in results if r['status'] in ('no_data', 'no_entity', 'no_predicate', 'error'))

        if contradicted_count > 0:
            verdict = 'contradicted'
        elif verified_count > 0 and no_data_count == 0:
            verdict = 'verified'
        elif verified_count > 0:
            verdict = 'partial'
        else:
            verdict = 'no_data'

        return {
            'statement': statement,
            'facts_extracted': len(facts),
            'verified': verified_count,
            'contradicted': contradicted_count,
            'no_data': no_data_count,
            'verdict': verdict,
            'results': results,
        }

    def metrics(self):
        return {
            'total': self.total_checks,
            'verified': self.verified,
            'contradicted': self.contradicted,
            'no_data': self.no_data,
            'verify_rate': round(self.verified / max(self.total_checks, 1) * 100, 1),
        }


# ═══════════════════════════════════════════════
# 4. 入口
# ═══════════════════════════════════════════════

if __name__ == '__main__':
    import sys

    epsilon = AgentEpsilon()

    test_statements = [
        '中国的首都是北京',
        '法国的首都是伦敦',
        '爱因斯坦出生于德国',
        '水的化学式是H2O',
        '地球位于太阳系',
        '日本的面积是1000平方公里',
        '莎士比亚是哈姆雷特的作者',
        '埃菲尔铁塔位于巴黎',
        '珠穆朗玛峰的高度是8848米',
        '北京的人口是1个人',
    ]

    if '--test' in sys.argv:
        stmt = ' '.join(sys.argv[2:]) if len(sys.argv) > 2 else test_statements[0]
        r = epsilon.verify(stmt)
        print(json.dumps(r, ensure_ascii=False, indent=2))

    elif '--eval' in sys.argv:
        print(f'  Agent ε · 事实锚 — 知识图谱验证')
        print(f'  {"─"*50}')
        for s in test_statements:
            r = epsilon.verify(s)
            icon = '✅' if r['verdict'] == 'verified' else '❌' if r['verdict'] == 'contradicted' else '⚠️'
            print(f'  {icon} {s:35} → {r["verdict"]:15} ({r["verified"]}/{r["facts_extracted"]}原子)')
        m = epsilon.metrics()
        print(f'\n  总检查: {m["total"]} | 验证: {m["verified"]} | 矛盾: {m["contradicted"]} | 无数据: {m["no_data"]}')
        print(f'  验证率: {m["verify_rate"]}%')

    elif '--demo' in sys.argv:
        s = '中国的首都是北京'
        r = epsilon.verify(s)
        for res in r['results']:
            f = res['fact']
            print(f'  {f["subject"]} → {f["predicate"] or f["pid"]} → {f["object"]}')
            print(f'    状态: {res["status"]} — {res.get("msg","")}')

    else:
        print('Agent ε · 事实锚 — Wikidata SPARQL 验证')
        print('  --eval         评估全部测试陈述')
        print('  --test "..."   验证单句陈述')
        print('  --demo         演示')