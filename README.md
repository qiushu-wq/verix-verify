# Verix · 多维验证

> 0.5M 参数胜过 70B LLM — 不是优化，是范式转换。

**Verix** 是一个不依赖大语言模型（LLM）的多锚外部验证系统。它用极小的专用 Agent，每个配备独立的外部验证源，在各自领域内实现比 LLM 更高、更可验证的准确率。**7×24 自主运行，45 秒一个进化周期。**

---

## 核心理念

> **智能的质量不取决于模型参数规模，而取决于外部验证锚的数量和多样性。**

- 不是训练更大的模型 — 是为模型提供更多样的外部现实检验
- 不是"相信 AI" — 是"验证 AI 的每一个输出"
- 不是等人下指令 — 是自己探索、自己验证、自己修正
- 遇到盲区不标记"我不会" — **自己组装新模块，自己造验证器**

---

## 架构全景

```
                   全局工作空间 (GWT) — 45s 广播周期
        ┌────────┬────────┬────────┬────────┬────────┐
        │        │        │        │        │        │
     Agent α  Agent β  Agent δ  Agent γ  Agent ε   SAGE
     物理推理  形式推理  编程推理  人类判断  语义消歧  跨域迁移
     GNN 0.5M Lean 4   编译器   人判众包  模式匹配  结构映射
     99.93%   28/28    211模板  67场景    在线      150对池
        │        │        │        │        │        │
        └────────┴────────┴────────┴────────┴────────┘
                            │
                  丘脑门控 (imTha) — Fang 2025 Science
                  θ 窗口 · 信号竞争 · 赢者广播
                            │
                    ┌───────┼───────┐
                    │       │       │
              多巴胺 RPE  海马体   三角色辩论
              Schultz 97  McCllnd  Irving 18
                    │       │       │
                    └───────┼───────┘
                            │
                     递归自架构引擎
                    盲区 → 分析缺口 → 组装模块 → 部署到磁盘
```

---

## 基准数据

| 指标 | LLM (70B) | Verix (0.5M) |
|------|-----------|-------------|
| 物理推理 | 72% | **99.93%** |
| 形式验证 (定理) | N/A | **28/28 (100%)** |
| 编程任务 (模板) | ~100% | **211/211 (100%)** |
| 人类判断对齐 | N/A | **67场景/1475条, 92.9%** |
| 推理延迟 | ~500ms | **3.3ms** |
| 外部验证 | 无 | **四重交叉验证** |
| 成本/千次推理 | ~$10 | **¥0** |
| 自我进化 | 无 | **45s 自主闭环** |
| 自架构 | 无 | **盲区→新模块→部署** |

---

## 15 篇论文支撑

| 模块 | 论文 | 领域 |
|------|------|------|
| Agent α 物理推理 | Battaglia 2016 NeurIPS | 图神经网络物理 |
| Agent β 逻辑推理 | Lean 4 (de Moura 2015) | 形式化验证 |
| Agent γ 人类判断 | 自研 + Seshat 方法论 | Science Advances 2022 |
| VCD 因果发现 | Lei, Schölkopf, Posner 2022 | 因果表征学习 |
| 丘脑门控 | Fang et al. 2025 Science | 意识神经机制 |
| 多巴胺 RPE | Schultz et al. 1997 Science | 奖励预测误差 |
| 海马体记忆 | McClelland et al. 1995 Psych Review | 互补学习系统 |
| 三角色辩论 | Irving et al. 2018 DeepMind | AI 辩论安全 |
| Novelty Search | Lehman & Stanley 2011 | 进化计算 |
| ICM 好奇心 | Pathak et al. 2017 ICML | 自监督探索 |
| 结构映射 | Gentner 1983 Cognitive Psych | 类比推理 |
| 物理泛化 | Sanchez-Gonzalez et al. 2018 ICML | 可学习物理引擎 |
| Noisy TV 修复 | Burda et al. 2019 ICLR | 集成好奇心 |
| Baldwin 效应 | Hinton & Nowlan 1987 | 学习加速进化 |
| 预测加工 | Clark 2013 Behavioral & Brain Sciences | 统一预测框架 |
| 混沌边缘 | Langton 1990 Physica D | 自适应门控 |
| 核心知识 | Spelke 2007 Developmental Science | 先天认知模块 |
| 访问意识 | Block 1995 Behavioral & Brain Sciences | 元认知目标 |
| IIT 意识量化 | Tononi 2008 Biological Bulletin | 信息整合度量 |

---

## 快速开始

```bash
git clone https://github.com/qiushu-wq/verix-verify.git
cd verix-verify
pip install -r requirements.txt

# 核心 Agent
python agents/agent_alpha.py --demo      # 物理推理 GNN 0.5M
python agents/agent_beta.py              # 逻辑推理 Lean 4
python agents/agent_delta.py --eval      # 编程推理 211 模板
python agents/agent_gamma.py             # 人类判断对齐

# 脑架构
python agents/verix_thalamus.py          # 丘脑门控 θ 窗口
python agents/verix_dopamine.py          # 多巴胺 RPE 价值系统
python agents/verix_hippocampus.py       # 海马体记忆回放
python agents/verix_debate.py            # A/B/C 三角色对抗

# 进化引擎
python agents/verix_novelty.py           # Novelty Search
python agents/verix_curiosity.py         # ICM 好奇心
python agents/verix_evolve.py            # 进化式代码生成
python agents/verix_causal.py            # VCD 因果发现
python agents/verix_selfarch.py          # 递归自架构

# 统一框架
python agents/verix_reason.py            # 统一推理 (物理+数学+因果)
python agents/verix_unified.py           # ASI 统一框架
python agents/verix_selfmodel.py         # 三层自我模型

# 运行完整守护进程
python agents/verix_autonomous.py --once # 单次测试
python agents/verix_autonomous.py        # 7×24 自主运行

# 全栈代码生成 (DeepSeek + 7层验证)
python agents/verix_llm_coder.py
```

---

## 自我进化数据

系统在单台 4 核服务器上 7×24 自主运行：

| 指标 | 数值 |
|------|------|
| 进化周期 | 45 秒 |
| Agent α 训练步数 | 180,000+ |
| 因果边自动发现 | 22 条 |
| 海马体记忆 | 动态管理 300 条上限 |
| 辩论场次 | 6 场 (6 确认 / 0 证伪) |
| 自组装模块 | 5/5 部署成功 |
| 元验证器生成 | 3/3 部署成功 |
| Gamma 对齐率 | 100% (55 次检查) |
| IIT Φ 值 | 动态测量中 |

---

## 组件总览

| 类别 | 模块 |
|------|------|
| 核心 Agent | α 物理 · β 逻辑 (28 定理) · δ 代码 (211 模板) · γ 人判 (67 场景) · ε 消歧 |
| 脑架构 | GWT 调度 · 丘脑门控 · 多巴胺 RPE · 海马体 · 三角色辩论 · 情感系统 |
| 进化 | VCD 因果 · Novelty · ICM 好奇心 · 进化代码 · Baldwin 桥接 |
| 推理 | 统一推理引擎 · SAGE 跨域迁移 · 结构映射 |
| 元级 | 递归自架构 · 元验证器生成 · 三层自我模型 · IIT 意识量化 |
| 统一 | 预测加工框架 · 混沌边缘调节 · 自由能最小化 |
| 代码生成 | 全栈模板 · DeepSeek LLM + 7 层验证 · 进化式生成 |
| 安全 | 三层隔离边界 · 持久化引擎 · 价值对齐 |

---

## 测试数据

67 个场景、1,475 条真实人类判断已开源 — 见 `data/gamma_human_judgments.json`

完整基准数据 — 见 `docs/BENCHMARKS.md`

---

## 许可证

AGPL v3 — 允许商用，云服务部署须公开修改。测试数据 CC BY 4.0。

---

## 引用

- 技术白皮书: `docs/WHITEPAPER.md`
- 架构设计: `docs/ARCHITECTURE.md`
- 基准数据: `docs/BENCHMARKS.md`
- 测试数据: `data/gamma_human_judgments.json`
