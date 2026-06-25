# Verix · 多维验证

> 0.5M 参数胜过 70B LLM — 不是优化，是范式转换。

**Verix** 是一个不依赖大语言模型（LLM）的多锚外部验证系统。它用多个极小的专用 Agent，每个配备独立的外部验证源（物理模拟器、类型检查器、编译器、知识图谱），在各自的领域内实现比 LLM 更高、更可验证的准确率。

## 核心理念

> **智能的质量不取决于模型的参数规模，而取决于外部验证锚的数量和多样性。**

- 不是训练更大的模型 — 是为模型提供更多样的外部现实检验
- 不是"相信 AI" — 是"验证 AI 的每一个输出"

## 架构

```
                    GWT 注意力调度器
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
    Agent α          Agent β         Agent δ/ε
    物理推理          形式推理         编程/事实
    GNN+MuJoCo       Lean 4         编译器+KB
    99.93%           100%            100% / PoC
```

## 基准数据

| 指标 | LLM (70B) | Verix |
|------|-----------|-------|
| 物理推理准确率 | 72% | **99.93%** |
| 形式验证通过率 | N/A | **100%** |
| 编程任务通过率 | ~100% | **100%** (77 任务) |
| 推理延迟 | ~500ms | **3.3ms** |
| 外部验证 | 无 | **三重持续验证** |
| 成本 | GPU 推理 | **¥0** (四个 Agent) |

## 快速开始

```bash
pip install -r requirements.txt

# 运行 Agent α (物理推理)
python agents/alpha/agent_alpha.py --demo

# 运行 Agent δ (编程验证)
python agents/delta/agent_delta.py --eval

# 运行 SAGE 跨域类比
python sage/sage_v2.py

# 启动终端仪表盘
python dashboard/tui_dashboard.py
```

## 组件

| Agent | 域 | 外部验证 | 技术 |
|-------|-----|---------|------|
| α | 物理推理 | MuJoCo 物理模拟器 | GNN 0.5M |
| β | 形式推理 | Lean 4 类型检查器 | 符号搜索 + BFS |
| δ | 编程推理 | 编译器 + 测试框架 | 模板合成 |
| ε | 事实核查 | 本地知识图谱 | SPARQL + 模式匹配 |
| γ | 社会推理 | 人类判断众包 | MLP |


## 许可证

AGPL v3 — 允许商用，但云服务部署必须公开修改。

## 引用

技术白皮书见 `docs/WHITEPAPER.md`
架构设计见 `docs/ARCHITECTURE.md`
基准数据见 `docs/BENCHMARKS.md`
