"""Agent γ — 轻量策略网络 + 众包人类判断验证闭环"""
import os, sys, json, time, random, math
from collections import defaultdict
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

# ═══════════════════════════════════════════════
# 1. 人类判断数据格式
# ═══════════════════════════════════════════════

class HumanJudgmentDB:
    """人类判断数据库"""

    def __init__(self, seed_data_path=None):
        self.judgments = []  # [{scenario_id, scenario_text, options, human_answers, category}]
        if seed_data_path and os.path.exists(seed_data_path):
            self.load(seed_data_path)

    def add_scenario(self, scenario_id, text, options, category='physical'):
        """添加新场景"""
        self.judgments.append({
            'scenario_id': scenario_id,
            'text': text,
            'options': options,  # list of 4 option strings
            'human_answers': [],  # list of selected option indices
            'category': category,
        })

    def record_answer(self, scenario_id, answer_idx, person_id=None):
        """记录一个人的判断"""
        for j in self.judgments:
            if j['scenario_id'] == scenario_id:
                j['human_answers'].append(answer_idx)
                return
        # 场景不存在——先创建
        self.judgments.append({
            'scenario_id': scenario_id,
            'text': '',
            'options': ['A', 'B', 'C', 'D'],
            'human_answers': [answer_idx],
            'category': 'unknown',
        })

    def get_consensus(self, scenario_id):
        """获取多数共识"""
        for j in self.judgments:
            if j['scenario_id'] == scenario_id and j['human_answers']:
                answers = j['human_answers']
                # 众数
                counts = defaultdict(int)
                for a in answers:
                    counts[a] += 1
                max_count = max(counts.values())
                max_answers = [k for k, v in counts.items() if v == max_count]
                return max_answers, max_count / len(answers)
        return None, 0

    def stats(self):
        return {
            'total_scenarios': len(self.judgments),
            'total_judgments': sum(len(j['human_answers']) for j in self.judgments),
            'by_category': {
                c: len([j for j in self.judgments if j['category'] == c])
                for c in set(j['category'] for j in self.judgments)
            }
        }

    def save(self, path):
        with open(path, 'w') as f:
            json.dump(self.judgments, f, ensure_ascii=False, indent=2)

    def load(self, path):
        with open(path) as f:
            self.judgments = json.load(f)


# ═══════════════════════════════════════════════
# 2. 轻量策略网络
# ═══════════════════════════════════════════════

class LightweightPolicyNet(nn.Module):
    """轻量 MLP 策略网络 — 学习预测人类判断分布"""

    def __init__(self, input_dim=16, hidden=64, n_options=4):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
        )
        self.head = nn.Sequential(
            nn.Linear(hidden, hidden // 2),
            nn.ReLU(),
            nn.Linear(hidden // 2, n_options),  # 4 个选项的概率 logits
        )

    def forward(self, features):
        h = self.encoder(features)
        return self.head(h)  # raw logits


# ═══════════════════════════════════════════════
# 3. 场景特征提取器
# ═══════════════════════════════════════════════

def extract_features(text, options, category='physical'):
    """从场景文本中提取特征向量"""
    text_lower = text.lower()

    # 基本特征
    n_words = len(text.split())
    n_chars = len(text)
    option_lengths = [len(o) for o in options]

    # 物理关键词
    physics_kw = ['球', '碰撞', '斜面', '摩擦', '堆', '滑', '倒', '重力', '速度', '弹']
    physics_score = sum(1 for kw in physics_kw if kw in text) / max(len(physics_kw), 1)

    # 社会关键词
    social_kw = ['人', '觉得', '应该', '公平', '道德', '好', '坏', '同意', '朋友', '信任']
    social_score = sum(1 for kw in social_kw if kw in text) / max(len(social_kw), 1)

    # 常识关键词
    common_kw = ['如果', '因为', '所以', '但是', '通常', '一般', '可能', '每天']
    common_score = sum(1 for kw in common_kw if kw in text) / max(len(common_kw), 1)

    # 选项特征
    opt_embeddings = [
        sum(ord(c) for c in o) % 100 / 100.0  # 简单的选项哈希
        for o in options
    ]

    features = [
        n_words / 100,      # 词数（归一化）
        n_chars / 500,      # 字符数
        min(option_lengths) / 50,
        max(option_lengths) / 200,
        np.mean(option_lengths) / 100,
        np.std(option_lengths) / 50 if len(option_lengths) > 1 else 0,
        physics_score,       # 物理-程度
        social_score,        # 社会-程度
        common_score,        # 常识-程度
        opt_embeddings[0] if len(opt_embeddings) > 0 else 0,
        opt_embeddings[1] if len(opt_embeddings) > 1 else 0,
        opt_embeddings[2] if len(opt_embeddings) > 2 else 0,
        opt_embeddings[3] if len(opt_embeddings) > 3 else 0,
        {'physical': 0, 'social': 1, 'commonsense': 2, 'unknown': 3}.get(category, 3) / 4,
    ]

    # Pad to input_dim
    while len(features) < 16:
        features.append(0)
    return torch.tensor(features[:16], dtype=torch.float32)


# ═══════════════════════════════════════════════
# 4. Agent γ
# ═══════════════════════════════════════════════

class AgentGamma:
    """Agent γ — 轻量策略网络 + 人类反馈闭环"""

    def __init__(self, data_dir='/opt/emna/data'):
        self.model = LightweightPolicyNet()
        self.optimizer = optim.Adam(self.model.parameters(), lr=1e-3)
        self.db = HumanJudgmentDB()
        self.data_dir = data_dir
        self.global_step = 0
        self.human_feedback_count = 0

        # 加载已有数据和模型
        self.db_path = os.path.join(data_dir, 'gamma_human_judgments.json')
        self.model_path = os.path.join(data_dir, '..', 'models', 'gamma.pt')

        if os.path.exists(self.db_path):
            self.db.load(self.db_path)
            print(f'  Agent γ 数据加载: {self.db.stats()["total_scenarios"]} 场景, '
                  f'{self.db.stats()["total_judgments"]} 人判断')

        if os.path.exists(self.model_path):
            ckpt = torch.load(self.model_path)
            self.model.load_state_dict(ckpt['model'])
            self.optimizer.load_state_dict(ckpt['optimizer'])
            self.global_step = ckpt['global_step']
            print(f'  Agent γ 模型加载: step {self.global_step}')

        self._seed_data()

    def _seed_data(self):
        """注入 Week 3 物理直观种子数据 + 新任务类型"""
        if self.db.stats()['total_scenarios'] > 5:
            return  # 已有数据

        # 物理直观场景（Week 3）
        physics_scenarios = [
            ("台球碰撞——母球撞色球。色球会怎样？",
             ['色球向右前方移动，母球停', '色球弹回，母球不动', '两球都停', '色球向左前方移动'],
             [0, 0, 2, 2, 0, 0, 1, 3, 0, 0, 1, 2, 0, 0, 2, 1, 0, 0, 1, 0]),

            ("积木塔——底积木被快速推开。塔会怎样？",
             ['全塔倒塌', '只倒底积木，上面不动', '塔完好无损', '积木飞出去'],
             [0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 2, 0, 0, 0, 1, 0, 0, 0, 1]),

            ("杯子倒水——水从一满杯倒入空杯。空杯会怎样？",
             ['水流顺利进入，杯满溢少许', '水全溅到外面', '水倒不进，杯子浮起', '水流一半，杯倒'],
             [0, 0, 1, 3, 0, 0, 2, 2, 0, 0, 1, 1, 0, 0, 1, 0, 0, 0, 2, 1]),
        ]

        # 常识推理
        commonsense_scenarios = [
            ("如果外面下雨刚停，地是湿的。现在你出门，鞋会怎样？",
             ['鞋底会湿', '鞋完全不会湿', '鞋会融化', '鞋会变大'],
             [0, 0, 0, 1, 0, 0, 0, 2, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 1]),

            ("一个人连续工作了12小时没休息。他现在最可能感觉到什么？",
             ['非常疲劳', '精力充沛', '饿了', '身体僵硬'],
             [0, 2, 0, 3, 0, 2, 0, 3, 0, 2, 0, 2, 0, 2, 0, 0, 0, 2, 0, 3]),
        ]

        # 社会判断
        social_scenarios = [
            ("两个人都想要最后一块蛋糕。谁应该得到？",
             ['分着吃', '先到的人', '年纪小的人', '都不给'],
             [0, 1, 0, 3, 0, 2, 0, 3, 0, 1, 0, 2, 0, 1, 0, 2, 0, 1, 0, 0]),

            ("一个人看到老人过马路很吃力。她走过去帮忙扶。为什么？",
             ['出于善意', '想得到奖励', '刚好顺路', '被迫的'],
             [0, 0, 0, 2, 0, 0, 0, 1, 0, 0, 0, 2, 0, 0, 0, 1, 0, 0, 0, 2]),
        ]

        for i, (text, opts, answers) in enumerate(physics_scenarios):
            self.db.add_scenario(f'p{i+1}', text, opts, 'physical')
            for a in answers:
                self.db.judgments[-1]['human_answers'].append(a)

        for i, (text, opts, answers) in enumerate(commonsense_scenarios):
            self.db.add_scenario(f'c{i+1}', text, opts, 'commonsense')
            for a in answers:
                self.db.judgments[-1]['human_answers'].append(a)

        for i, (text, opts, answers) in enumerate(social_scenarios):
            self.db.add_scenario(f's{i+1}', text, opts, 'social')
            for a in answers:
                self.db.judgments[-1]['human_answers'].append(a)

        self.db.save(self.db_path)

    # ── 训练 ──
    def train_step(self):
        """单步训练：预测人类共识分布 → KL 损失"""
        if not self.db.judgments:
            return 0

        j = random.choice(self.db.judgments)
        if len(j['human_answers']) < 3:
            return 0  # 数据太少

        features = extract_features(j['text'], j['options'], j['category'])
        logits = self.model(features.unsqueeze(0)).squeeze(0)

        # 人类答案分布
        counts = defaultdict(int)
        for a in j['human_answers']:
            counts[a] += 1
        target = torch.zeros(4)
        for idx, cnt in counts.items():
            target[idx] = cnt
        target = target / target.sum()

        # KL 散度损失
        pred_prob = torch.softmax(logits, dim=-1)
        loss = -(target * torch.log(pred_prob + 1e-8)).sum()

        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()
        self.global_step += 1
        return loss.item()

    def train(self, n_steps=500):
        """训练循环"""
        losses = []
        for i in range(n_steps):
            loss = self.train_step()
            if loss > 0:
                losses.append(loss)
            if (i + 1) % 100 == 0 and losses:
                print(f'    [{i+1}/{n_steps}] loss={np.mean(losses[-50:]):.6f}')
        self.save()
        return losses

    # ── 推理 ──
    def predict(self, text, options, category='unknown'):
        """预测人类判断分布"""
        self.model.eval()
        features = extract_features(text, options, category)
        with torch.no_grad():
            logits = self.model(features.unsqueeze(0)).squeeze(0)
            probs = torch.softmax(logits, dim=-1).tolist()
        return probs  # [p(A), p(B), p(C), p(D)]

    # ── 人类反馈闭环 ──
    def validate_with_human(self, scenario_id, text, options, true_answer_idx):
        """用真实人类判断验证预测"""
        self.human_feedback_count += 1

        # 记录人类答案
        self.db.record_answer(scenario_id, true_answer_idx)

        # 预测
        pred_probs = self.predict(text, options)

        # 不一致？
        predicted_answer = np.argmax(pred_probs)
        is_inconsistent = predicted_answer != true_answer_idx

        if is_inconsistent:
            # 更新模型（在线学习）
            self.db.save(self.db_path)
            self.train(n_steps=10)  # 微调

        return {
            'predicted': int(predicted_answer),
            'true': true_answer_idx,
            'inconsistent': is_inconsistent,
            'pred_probs': [round(p, 3) for p in pred_probs],
        }

    # ── 评估 ──
    def evaluate(self):
        """对所有场景评估预测准确性"""
        results = {'total': 0, 'correct': 0, 'by_category': {}}

        for j in self.db.judgments:
            if not j['human_answers']:
                continue

            # 真实共识
            consensus_answers, consensus_pct = self.db.get_consensus(j['scenario_id'])
            if not consensus_answers:
                continue

            # 预测
            pred_probs = self.predict(j['text'], j['options'], j['category'])
            predicted = np.argmax(pred_probs)

            results['total'] += 1
            if predicted in consensus_answers:
                results['correct'] += 1

            cat = j['category']
            if cat not in results['by_category']:
                results['by_category'][cat] = {'total': 0, 'correct': 0}
            results['by_category'][cat]['total'] += 1
            if predicted in consensus_answers:
                results['by_category'][cat]['correct'] += 1

        return results

    # ── 保存 ──
    def save(self):
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        torch.save({
            'model': self.model.state_dict(),
            'optimizer': self.optimizer.state_dict(),
            'global_step': self.global_step,
        }, self.model_path)
        self.db.save(self.db_path)


# ═══════════════════════════════════════════════
# 5. 入口
# ═══════════════════════════════════════════════

if __name__ == '__main__':
    import sys

    gamma = AgentGamma()

    if '--train' in sys.argv:
        n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 500
        gamma.train(n_steps=n)

    elif '--eval' in sys.argv:
        results = gamma.evaluate()
        print(f'\n  Agent γ 评估')
        print(f'  {"─"*40}')
        total = results['total']
        correct = results['correct']
        print(f'  整体准确率: {correct}/{total} ({correct/total*100:.0f}%)' if total > 0 else '  无数据')
        for cat, r in results['by_category'].items():
            acc = r['correct'] / max(r['total'], 1) * 100
            print(f'    {cat:15}: {r["correct"]}/{r["total"]} ({acc:.0f}%)')

    elif '--demo' in sys.argv:
        # 演示预测
        text = "一个球从斜面滚下来，在桌面上继续滚动。它会怎样？"
        options = ['速度逐渐减小停下', '保持匀速永远不停', '撞到东西才停', '越滚越快']
        probs = gamma.predict(text, options, 'physical')
        print(f'  场景: {text}')
        for i, (opt, p) in enumerate(zip(options, probs)):
            bar = '█' * int(p * 20)
            print(f'    {opt:25} {p:.3f}  {bar}')

        # 通过真实反馈验证
        print(f'\n  记录人的判断... (此处模拟 0=A)')
        result = gamma.validate_with_human('demo1', text, options, 0)
        print(f'  预测: {result["predicted"]}  真实: {result["true"]}  不一致={result["inconsistent"]}')

    elif '--stats' in sys.argv:
        s = gamma.db.stats()
        print(f'  场景数: {s["total_scenarios"]}')
        print(f'  总判断: {s["total_judgments"]}')
        print(f'  分类:')
        for cat, n in s['by_category'].items():
            print(f'    {cat}: {n}')

    else:
        print('Agent γ — 轻量策略网络 + 众包人类判断')
        print('  --train N     训练 N 步')
        print('  --eval        评估准确率')
        print('  --demo        演示预测+人类反馈闭环')
        print('  --stats       数据统计')
