"""Agent ε 知识库加载器 — DBpedia + Wikipedia API"""
import os, json, gzip, io, time, urllib.request, urllib.parse, re
from collections import defaultdict

FACT_FILE = '/opt/verix/data/fact_db.json'
DBPEDIA_INSTANCE = 'https://downloads.dbpedia.org/repo/dbpedia/generic/instance-types/2024.08.01/instance-types_lang=en.ttl.bz2'

# ── 方案 A：DBpedia 批量下载 ──
def load_dbpedia_instances():
    """下载 DBpedia instance types（实体→类型映射）"""
    facts = defaultdict(list)
    try:
        print('  下载 DBpedia instance types...')
        req = urllib.request.Request(DBPEDIA_INSTANCE, headers={'User-Agent': 'Verix/1.0'})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        # 简单解析 Turtle 格式的 instance type 三元组
        text = data.decode('utf-8', errors='ignore')
        # 模式: <http://dbpedia.org/resource/XXX> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://dbpedia.org/ontology/YYY>
        triples = 0
        for line in text.split('\n')[:20000]:  # 先取 20000 行
            if 'rdf-syntax-ns#type' in line or 'rdf:type' in line:
                match = re.search(r'resource/([^>]+)', line)
                if match:
                    entity = match.group(1).replace('_', ' ')
                    type_match = re.search(r'ontology/([^>]+)', line)
                    if type_match:
                        etype = type_match.group(1)
                        facts[entity].append(etype)
                        triples += 1
        print(f'  DBpedia: {triples} 个三元组, {len(facts)} 个实体')
        return facts
    except Exception as e:
        print(f'  DBpedia 下载失败: {e}')
        return facts

# ── 方案 B：Wikipedia API 补充 ──
def fetch_wikipedia_facts(entity_name, lang='zh'):
    """从 Wikipedia API 提取结构化事实"""
    facts = {}
    # 获取页面摘要
    params = urllib.parse.urlencode({
        'action': 'query', 'titles': entity_name, 'prop': 'extracts|pageprops',
        'exintro': '1', 'explaintext': '1', 'format': 'json',
    })
    url = f'https://{lang}.wikipedia.org/w/api.php?{params}'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Verix/1.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            pages = data.get('query', {}).get('pages', {})
            for page_id, page in pages.items():
                if page_id == '-1':
                    continue
                extract = page.get('extract', '')
                # 从摘要中提取常见模式
                if '首都' in extract:
                    m = re.search(r'首都是?([^，。；\n]+)', extract)
                    if m: facts['capital'] = m.group(1).strip()
                if '人口' in extract:
                    m = re.search(r'人口[约超]?(\d[\d,]*)', extract)
                    if m: facts['population'] = m.group(1).replace(',', '')
                if '面积' in extract:
                    m = re.search(r'面积[约为]?(\d[\d,]*)', extract)
                    if m: facts['area'] = m.group(1).replace(',', '')
    except Exception as e:
        pass
    return facts

# ── 种子数据注入 ──
SEED_FACTS = [
    # 地理
    ('中国', 'P36', '北京'), ('中国', 'P1082', '1400000000'), ('中国', 'P17', '亚洲'),
    ('法国', 'P36', '巴黎'), ('英国', 'P36', '伦敦'), ('日本', 'P36', '东京'),
    ('德国', 'P36', '柏林'), ('俄罗斯', 'P36', '莫斯科'), ('印度', 'P36', '新德里'),
    ('巴西', 'P36', '巴西利亚'), ('埃及', 'P36', '开罗'), ('韩国', 'P36', '首尔'),
    ('北京', 'P131', '中国'), ('上海', 'P131', '中国'), ('东京', 'P131', '日本'),
    ('巴黎', 'P131', '法国'), ('伦敦', 'P131', '英国'), ('纽约', 'P131', '美国'),
    ('珠穆朗玛峰', 'P2048', '8848'), ('珠穆朗玛峰', 'P131', '尼泊尔'),
    ('尼罗河', 'P2043', '6650'), ('亚马孙河', 'P2043', '6400'),
    ('太平洋', 'P2046', '165200000'), ('大西洋', 'P2046', '106400000'),
    ('撒哈拉沙漠', 'P2046', '9200000'),
    # 人物
    ('爱因斯坦', 'P19', '乌尔姆'), ('爱因斯坦', 'P27', '德国'),
    ('牛顿', 'P19', '英格兰'), ('牛顿', 'P27', '英国'),
    ('达尔文', 'P19', '英格兰'), ('达尔文', 'P27', '英国'),
    ('莎士比亚', 'P19', '英格兰'), ('莎士比亚', 'P50', '哈姆雷特'),
    ('贝多芬', 'P19', '波恩'), ('贝多芬', 'P27', '德国'),
    ('莫扎特', 'P19', '萨尔茨堡'), ('莫扎特', 'P27', '奥地利'),
    ('达芬奇', 'P19', '芬奇镇'), ('达芬奇', 'P27', '意大利'),
    ('居里夫人', 'P19', '华沙'), ('居里夫人', 'P27', '波兰'),
    ('图灵', 'P19', '伦敦'), ('图灵', 'P27', '英国'),
    # 科学
    ('水的化学式', 'P274', 'H2O'), ('二氧化碳', 'P274', 'CO2'),
    ('氧', 'P1086', '8'), ('氢', 'P1086', '1'), ('碳', 'P1086', '6'),
    ('铁', 'P1086', '26'), ('金', 'P1086', '79'), ('铀', 'P1086', '92'),
    ('地球', 'P31', '行星'), ('太阳', 'P31', '恒星'),
    ('月球', 'P31', '卫星'), ('火星', 'P31', '行星'),
    ('光速', 'P2067', '299792458'),
    # 建筑/地标
    ('埃菲尔铁塔', 'P131', '巴黎'), ('埃菲尔铁塔', 'P2048', '330'),
    ('自由女神像', 'P131', '纽约'), ('自由女神像', 'P2048', '93'),
    ('长城', 'P2043', '21196'), ('长城', 'P131', '中国'),
    ('大本钟', 'P131', '伦敦'), ('大本钟', 'P2048', '96'),
    ('金字塔', 'P131', '埃及'), ('泰姬陵', 'P131', '印度'),
    # 历史
    ('法国大革命', 'P585', '1789'), ('美国独立宣言', 'P585', '1776'),
    ('辛亥革命', 'P585', '1911'), ('中华人民共和国成立', 'P585', '1949'),
    ('二战结束', 'P585', '1945'), ('人类登月', 'P585', '1969'),
    # 百科事实
    ('太阳系', 'P36', '太阳'), ('银河系', 'P31', '星系'),
    ('人体正常体温', 'P2067', '37'), ('光年', 'P2043', '9460730472580800'),
]

def build_kb():
    """构建完整知识库"""
    facts = defaultdict(list)

    # 种子数据
    for s, p, o in SEED_FACTS:
        facts[(s, p)].append(o)

    # DBpedia
    dbpedia_facts = load_dbpedia_instances()
    for entity, types in dbpedia_facts.items():
        for t in types:
            facts[(entity, 'P31')].append(t)

    # 保存
    kb = {f'{s}|{p}': v for (s, p), v in facts.items()}
    os.makedirs('/opt/verix/data', exist_ok=True)
    with open(FACT_FILE, 'w') as f:
        json.dump(kb, f, ensure_ascii=False)
    print(f'  知识库: {len(kb)} 条事实 → {FACT_FILE}')
    return kb

if __name__ == '__main__':
    build_kb()
