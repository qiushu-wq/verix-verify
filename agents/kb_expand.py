"""Agent ε 知识库自动扩充 — Wikipedia API → 1000+ 事实"""
import urllib.request, urllib.parse, json, os, time, re

FACT_FILE = '/opt/verix/data/fact_db.json'
LOG_FILE = '/opt/verix/logs/kb_expand.log'

def log(msg):
    t = time.strftime('%H:%M:%S')
    line = f'[{t}] {msg}'
    print(line)
    with open(LOG_FILE, 'a') as f: f.write(line + '\n')

def wiki_query(title, lang='zh'):
    """获取 Wikipedia 页面摘要"""
    params = urllib.parse.urlencode({
        'action': 'query', 'titles': title, 'prop': 'extracts|pageprops|info',
        'exintro': '1', 'explaintext': '1', 'format': 'json',
    })
    url = f'https://{lang}.wikipedia.org/w/api.php?{params}'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Verix-KB/1.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            pages = data.get('query', {}).get('pages', {})
            for pid, page in pages.items():
                if pid == '-1': continue
                return page.get('extract', '')
    except Exception as e:
        pass
    return ''

def extract_facts(title, text):
    """从 Wikipedia 摘要中提取结构化事实"""
    facts = []

    # 首都
    m = re.search(r'首都[是为]?\s*([^\s，。；]{2,8})', text)
    if m: facts.append((title, 'P36', m.group(1).strip()))

    # 人口
    m = re.search(r'人口[约为有]?\s*(\d[\d,]*)\s*万', text)
    if m:
        pop = int(m.group(1).replace(',', '')) * 10000
        facts.append((title, 'P1082', str(pop)))
    else:
        m = re.search(r'人口[约为有]?\s*(\d[\d,亿]*)', text)
        if m and '亿' in m.group(1):
            pop = int(float(m.group(1).replace('亿','')) * 1e8)
            facts.append((title, 'P1082', str(pop)))

    # 面积
    m = re.search(r'面积[约为有]?\s*(\d[\d,.]*)\s*万?\s*平方公里', text)
    if m:
        area = int(float(m.group(1).replace(',','')) * (10000 if '万' in m.group(0) else 1))
        facts.append((title, 'P2046', str(area)))

    # 所在大洲
    for continent in ['亚洲', '欧洲', '非洲', '北美洲', '南美洲', '大洋洲', '南极洲']:
        if continent in text[:200]:
            facts.append((title, 'P30', continent))
            break

    # 成立/发现年份
    m = re.search(r'(\d{4})年[建立成国发]', text)
    if m: facts.append((title, 'P571', m.group(1)))

    # 原子序数（化学元素）
    m = re.search(r'原子序数[为是]?\s*(\d+)', text)
    if m: facts.append((title, 'P1086', m.group(1)))

    # 化学式
    m = re.search(r'化学式[为是]?\s*([A-Z][A-Za-z0-9]*)', text)
    if m: facts.append((title, 'P274', m.group(1)))

    # 高度
    m = re.search(r'海拔[约为有]?\s*(\d[\d,]*)\s*米', text)
    if m: facts.append((title, 'P2048', m.group(1).replace(',','')))

    # 类型
    if '国家' in text[:100]: facts.append((title, 'P31', '国家'))
    elif '城市' in text[:100]: facts.append((title, 'P31', '城市'))
    elif '河流' in text[:100]: facts.append((title, 'P31', '河流'))
    elif '山脉' in text[:100] or '山峰' in text[:100]: facts.append((title, 'P31', '山峰'))
    elif '化学元素' in text[:100] or '金属' in text[:100]: facts.append((title, 'P31', '化学元素'))
    elif '国家' in text[:200] or '政权' in text[:200]: facts.append((title, 'P31', '历史政权'))

    return facts

def load_kb():
    if os.path.exists(FACT_FILE):
        with open(FACT_FILE) as f:
            raw = json.load(f)
        kb = {}
        for k, v in raw.items():
            s, p = k.split('|', 1)
            kb[(s, p)] = v
        return kb
    return {}

def save_kb(kb):
    out = {}
    for (s, p), v in kb.items():
        out[f'{s}|{p}'] = v
    with open(FACT_FILE, 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

# ═══════════════════════════════════════════════
# 查询列表
# ═══════════════════════════════════════════════

ENTITIES = [
    # 国家 (50)
    '美国', '俄罗斯', '加拿大', '澳大利亚', '阿根廷', '土耳其', '沙特阿拉伯', '伊朗',
    '泰国', '越南', '马来西亚', '新加坡', '印度尼西亚', '菲律宾', '缅甸', '柬埔寨',
    '巴基斯坦', '孟加拉国', '斯里兰卡', '尼泊尔', '蒙古国', '朝鲜', '阿富汗', '伊拉克',
    '叙利亚', '以色列', '约旦', '阿联酋', '卡塔尔', '科威特', '阿曼', '也门',
    '南非', '尼日利亚', '肯尼亚', '埃塞俄比亚', '坦桑尼亚', '加纳', '摩洛哥', '阿尔及利亚',
    '意大利', '西班牙', '荷兰', '比利时', '瑞士', '瑞典', '挪威', '波兰', '乌克兰', '希腊',
    # 城市 (20)
    '上海市', '广州市', '深圳市', '重庆市', '武汉市', '西安市', '南京市', '杭州市', '成都市', '天津市',
    '香港', '澳门', '台北市', '曼谷', '河内', '吉隆坡', '马尼拉', '雅加达', '迪拜', '伊斯坦布尔',
    # 人物 (20)
    '亚里士多德', '伽利略', '哥白尼', '开普勒', '麦克斯韦', '法拉第', '拉瓦锡', '门捷列夫',
    '巴斯德', '弗洛伊德', '亚当·斯密', '凯恩斯', '柏拉图', '笛卡尔', '康德', '尼采',
    '拿破仑', '成吉思汗', '哥伦布', '马可·波罗',
    # 河流/山脉 (15)
    '长江', '黄河', '密西西比河', '伏尔加河', '多瑙河', '恒河', '湄公河',
    '阿尔卑斯山', '喜马拉雅山', '安第斯山脉', '落基山脉', '富士山', '乞力马扎罗山', '泰山', '华山',
    # 化学元素 (20)
    '钠', '钾', '钙', '镁', '铝', '锌', '银', '铜', '铅', '锡',
    '铂', '汞', '碘', '氦', '氖', '氩', '锂', '铍', '硼', '硅',
    # 历史事件 / 地标 (15)
    '工业革命', '文艺复兴', '启蒙时代', '冷战', '丝绸之路', '大航海时代',
    '巨石阵', '马丘比丘', '吴哥窟', '帕特农神庙', '罗马斗兽场', '比萨斜塔',
    '悉尼歌剧院', '金门大桥', '巴拿马运河',
]

def run():
    kb = load_kb()
    before = len(kb)
    log(f'开始扩充 · 当前 {before} 条')

    new_count = 0
    total = len(ENTITIES)

    for i, entity in enumerate(ENTITIES):
        # 跳过已有足够数据的实体
        existing = sum(1 for (s, p) in kb if s == entity)
        if existing >= 3:
            continue

        text = wiki_query(entity)
        if not text:
            text = wiki_query(entity, 'en')
        if not text:
            continue

        facts = extract_facts(entity, text)
        for s, p, o in facts:
            if o and (s, p) not in kb:
                kb[(s, p)] = [o]
                new_count += 1
            elif o and o not in kb.get((s, p), []):
                kb[(s, p)].append(o)
                new_count += 1

        if (i + 1) % 20 == 0:
            log(f'进度 {i+1}/{total} · +{new_count} 条')
            save_kb(kb)

        time.sleep(0.5)  # 尊重 API 限频

    save_kb(kb)
    after = len(kb)
    log(f'扩充完成 · {before} → {after} (+{new_count} 条)')
    return after

if __name__ == '__main__':
    os.makedirs('/opt/verix/logs', exist_ok=True)
    run()
