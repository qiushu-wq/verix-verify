# Verix 测试数据

## gamma_human_judgments.json

67 个场景，1,475 条真人判断。

### 数据格式

```json
[
  {
    "scenario_id": "p1",
    "text": "台球碰撞——母球撞色球。色球会怎样？",
    "options": ["选项A", "选项B", "选项C", "选项D"],
    "human_answers": [0, 0, 2, 1, 0, ...],  // 每个数字=一个人选的选项索引
    "category": "physical|commonsense|social"
  }
]
```

### 场景分布

| 类别 | 数量 | 判断数 |
|------|------|--------|
| physical | 23 | 506 |
| commonsense | 25 | 550 |
| social | 19 | 419 |
| **总计** | **67** | **1,475** |

### 使用

```python
import json
with open('data/gamma_human_judgments.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
# data[i]['human_answers'] = 该场景的人工判断列表
# consensus = max(set(answers), key=answers.count)
```

### 许可

CC BY 4.0 — 可自由用于研究、商业用途，需注明出处。

## benchmark 数据

详见 `docs/BENCHMARKS.md`
