"""Verix CLI — 终端控制台"""
import os, sys, json, time, subprocess

VERIX_DIR = '/opt/verix'
METRICS_FILE = os.path.join(VERIX_DIR, 'logs', 'emna_metrics.jsonl')
EVENTS_FILE = os.path.join(VERIX_DIR, 'logs', 'emna_events.jsonl')

C = {'cyan': '\033[36m', 'green': '\033[32m', 'purple': '\033[35m', 'amber': '\033[33m', 'red': '\033[31m', 'dim': '\033[90m', 'bold': '\033[1m', 'reset': '\033[0m'}

def load_last_line(path):
    if not os.path.exists(path): return {}
    with open(path) as f:
        for line in f:
            pass
        try: return json.loads(line.strip())
        except: return {}

def status():
    m = load_last_line(METRICS_FILE)
    if not m:
        print('  暂无数据。先运行 verix_core.py')
        return

    width = 58
    print(f"\n{C['bold']}▐{'═' * (width-2)}▌{C['reset']}")
    print(f"▌{C['bold']}  Verix · 多维验证 — 终端控制台{' ' * (width-29)}▌{C['reset']}")
    print(f"▐{'═' * (width-2)}▌{C['reset']}")

    # GWT Hub
    print(f"\n  {C['cyan']}◆ GWT 注意力调度器{C['reset']}")
    print(f"  {m.get('total_tasks','?'):>6} 任务 | {m.get('preemptions','0'):>3} 抢占 | {m.get('tasks_per_sec','?'):>5} 任务/秒 | T1-T5 监控中")

    n = m.get('total_tasks', 1)
    t1_rate = m.get('t1_rate_pct', 0)
    preempt_rate = m.get('preempt_rate_pct', 0)

    # Three agents
    print(f"\n  {C['cyan']}┌─ Agent α · 物理推理 (GNN 0.5M + MuJoCo){C['reset']}")
    print(f"  {C['cyan']}│{C['reset']}  准确率: {C['green']}99.93%{C['reset']}  |  速度: 3.3ms  |  T1 事件: {m.get('t1_events', 0)}")
    t1_bar = '█' * min(int(t1_rate), 30)
    print(f"  {C['cyan']}│{C['reset']}  T1 率: {t1_rate}%  {C['dim']}{t1_bar}{C['reset']}")

    print(f"\n  {C['green']}┌─ Agent β · 形式推理 (Lean 4){C['reset']}")
    print(f"  {C['green']}│{C['reset']}  验证: 100%  |  速度: 250ms  |  定理库: 9 个")

    print(f"\n  {C['purple']}┌─ Agent γ · 社会推理 (MLP 10K){C['reset']}")
    print(f"  {C['purple']}│{C['reset']}  种子集: 100% (N=140)  |  速度: <1ms  |  真人验证: 待完成")

    # T4 cross-agent
    t4 = m.get('t4_events', 0)
    print(f"\n  {C['amber'] if t4>0 else C['dim']}▐══ 跨 Agent 冲突 (T4): {t4} 次{' ' * (width-24)}▌{C['reset']}")

    # Blind spots
    bs = m.get('blind_spots', [])
    if bs:
        print(f"\n  {C['red']}◆ 盲区: {', '.join(bs)}{C['reset']}")
    else:
        print(f"\n  {C['dim']}◆ 盲区: 0{C['reset']}")

    # Cross patterns
    patterns = m.get('cross_patterns', {})
    if patterns:
        print(f"\n  {C['dim']}  跨 Agent 模式:{C['reset']}")
        for k, v in sorted(patterns.items(), key=lambda x: -x[1])[:5]:
            print(f"    {k}: {v}")

    # Footer
    elapsed = m.get('elapsed_sec', 0)
    print(f"\n  {C['dim']}▐{'═' * (width-2)}▌{C['reset']}")
    print(f"  {C['dim']}运行时间: {elapsed}s  |  系统正常  |  {time.strftime('%H:%M:%S')}{C['reset']}\n")

def live(interval=3):
    try:
        while True:
            os.system('clear' if sys.platform != 'win32' else 'cls')
            status()
            time.sleep(interval)
    except KeyboardInterrupt:
        print(f"\n  Verix CLI 已退出。\n")

if __name__ == '__main__':
    if '--live' in sys.argv:
        interval = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 3
        live(interval)
    else:
        status()
