# Verix · Multi-Anchor Verification

> 0.5M params > 70B LLM — Not optimization, paradigm shift.

**Verix** is a multi-anchor external verification system that does not depend on large language models (LLMs). It uses tiny specialized agents, each equipped with an independent external verifier, achieving higher and more verifiable accuracy than LLMs in their respective domains.

---

## Core Philosophy

> **The quality of intelligence depends not on model parameter scale, but on the number and diversity of external verification anchors.**

- Not training bigger models — providing more diverse external reality checks
- Not "trusting AI" — verifying every output
- Not waiting for instructions — self-exploration, self-verification, self-correction

---

## Architecture

```
                   GWT Attention Scheduler
       ┌────────┬────────┬────────┬────────┬────────┐
       │        │        │        │        │        │
    Agent α  Agent β  Agent δ  Agent γ  Agent ε   SAGE
    Physics   Logic    Code     Human    Semantic  Cross-Domain
    GNN 0.5M  Lean 4   Compiler Crowd     Pattern   Transfer
    99.93%    28/28    211 tmpl  67 scenes Online    150 pairs
       │        │        │        │        │        │
       └────────┴────────┴────────┴────────┴────────┘
                           │
                  External Verifiers
          MuJoCo · Lean 4 · Compiler · Human Consensus
```

---

## Benchmarks

| Metric | LLM (70B) | Verix (0.5M) |
|------|-----------|-------------|
| Physics Accuracy | 72% | **99.93%** |
| Formal Verification | N/A | **28/28 (100%)** |
| Code Generation | ~100% | **211/211 (100%)** |
| Human Alignment | N/A | **67 scenarios, 92.9%** |
| Inference Latency | ~500ms | **3.3ms** |
| External Verification | None | **Quadruple cross-check** |
| Cost / 1K inferences | ~$10 | **$0** |

---

## Test Data

67 scenarios, 1,475 real human judgments — open source under CC BY 4.0.
See `data/gamma_human_judgments.json` · `docs/BENCHMARKS.md`

---

## License

AGPL v3 — Commercial use allowed. Cloud deployments must disclose modifications.
Test data: CC BY 4.0

---

*The Verix project includes additional proprietary modules (thalamic gating, dopamine RPE, hippocampal memory, three-role debate, recursive self-architecture, meta-verifier generation, self-model, IIT consciousness metrics) available under commercial license.*
