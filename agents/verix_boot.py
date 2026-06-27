"""Verix 终端启动动画 + 自动跳转 TUI"""
import sys, time

C = {'cyan': '\033[36m', 'green': '\033[32m', 'purple': '\033[35m', 'amber': '\033[33m', 'dim': '\033[90m', 'bold': '\033[1m', 'reset': '\033[0m'}
def wait(ms): time.sleep(ms/1000)

ASCII = [
    [r"──"], [r" ▐▌"], [r"▐▐▌"], [r"▐▐▐▌"], [r"▐▐▐▐▐▐▐▐▌"],
    [r"▐▐▐▐▐▐▐▐▐▐▐▐▐▌"], [r"▐▐▐▐▐▐▐▐▐▐▐▐▐▐▐▐▌"], [r"▐▐▐▐▐▐▐▐▐▐▐▐▐▐▐▐▐▌"],
    [r"▐▐▐▐▐▌  ▐▐▐▐▐▐▌"], [r"▐▐▐▌  ▐▐▐▌  ▐▐▐▌"], [r"▐▐▐▌  ▐▐▐▌  ▐▐▐▌"],
]

def boot():
    sys.stdout.write('\033[2J\033[H'); sys.stdout.flush()
    print(f"\n{C['dim']}Verix · 多维验证 — 终端控制台 {C['reset']}\n")
    print(f"  {C['bold']}初始化...{C['reset']}\n")

    for i, lines in enumerate(ASCII):
        sys.stdout.write('\033[6A')
        if i > 0:
            for _ in range(4): sys.stdout.write('\033[K\n')
        for line in lines:
            sys.stdout.write(f'\033[K  {C["cyan"]}{line}{C["reset"]}\n')
        sys.stdout.flush(); wait(120 if i < 8 else 200)

    sys.stdout.write(f'\033[K  {C["cyan"]}VERIX · 多维验证{C["reset"]}\n')
    sys.stdout.write(f'\033[K  {C["dim"]}GWT 调度器  ·  多锚验证  ·  自我进化{C["reset"]}\n')
    sys.stdout.flush(); wait(500)

    print()
    agents = [
        ('α', '物理推理', 'GNN 0.5M + MuJoCo', 'cyan', 800),
        ('β', '逻辑推理', 'Lean 4 类型检查', 'green', 600),
        ('δ', '编程推理', '编译器 + 测试', 'purple', 500),
    ]
    for name, role, tech, color, delay in agents:
        for _ in range(3):
            for dot in ['.  ', '.. ', '...']:
                sys.stdout.write(f'\033[K  {C[color]}[{name}] {role} · {tech} {C["dim"]}{dot}{C["reset"]}\r')
                sys.stdout.flush(); wait(100)
        sys.stdout.write(f'\033[K  {C["green"]}✓ {C[color]}[{name}] {role} · {C["dim"]}{tech}{C["reset"]}\n')
        sys.stdout.flush(); wait(delay)

    b, re = C['bold'], C['reset']
    print(f"\n  {b}全锚在线 · 系统就绪{re}")
    wait(300)
    sys.stdout.write('\033[2J\033[H'); sys.stdout.flush()

def launch_tui():
    boot()
    from verix_tui import VerixTUI
    VerixTUI().run()

if __name__ == '__main__':
    launch_tui()
