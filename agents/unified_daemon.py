"""Verix 全自动闭环 — 统一启动主动探索 + SAGE v3 + 增量学习"""
import os, sys, time, json, random
from datetime import datetime

sys.path.insert(0, '/opt/verix')
from active_explore import ActiveExplorer
from sage_v3 import SAGEEngineV3
from agent_alpha import AgentAlpha
from agent_delta import AgentDelta
from delta_auto import AutoExtensionEngine

STATUS_FILE = '/opt/verix/logs/unified_status.json'
LOG_FILE = '/opt/verix/logs/unified.log'

class UnifiedDaemon:
    def __init__(self):
        self.explorer = ActiveExplorer()
        self.sage = SAGEEngineV3()
        self.start_time = time.time()
        self.cycles = 0
        self.milestones = []
        os.makedirs('/opt/verix/logs', exist_ok=True)

    def log(self, msg):
        t = datetime.now().strftime('%H:%M:%S')
        line = f'[{t}] {msg}'
        print(line)
        with open(LOG_FILE, 'a') as f: f.write(line + '\n')

    def cycle(self):
        self.cycles += 1
        result = {'cycle': self.cycles, 'explore': None, 'sage': None}

        # 主动探索
        explore_result = self.explorer.run_cycle()
        result['explore'] = {
            'probes': len(explore_result.get('probes', [])),
            'discoveries': len(explore_result.get('discoveries', [])),
            'new_caps': len(explore_result.get('new_capabilities', [])),
        }

        # SAGE v3 跨域迁移 — 每 5 周期跑一次
        if self.cycles % 5 == 0:
            pairs = [
                ('alpha', 'critical_stability', 'delta'),
                ('alpha', 'critical_stability', 'beta'),
                ('beta', 'type_mismatch', 'epsilon'),
                ('epsilon', 'predicate_ambiguity', 'delta'),
            ]
            for src_d, src_p, tgt_d in pairs:
                r = self.sage.migrate(src_d, src_p, tgt_d)
                if r['status'] == 'migrated':
                    self.log(f'SAGE: {src_d}/{src_p}→{tgt_d} strength={r["strength"]}')

        return result

    def save(self):
        s = {
            'uptime_h': round((time.time() - self.start_time) / 3600, 1),
            'cycles': self.cycles,
            'explorer': self.explorer.status(),
            'sage': self.sage.status(),
            'milestones': len(self.milestones),
            'last_update': datetime.now().isoformat(),
        }
        with open(STATUS_FILE, 'w') as f: json.dump(s, f, ensure_ascii=False, indent=2)

    def run(self, interval=45):
        self.log(f'全自动闭环启动 · {interval}s 周期')
        try:
            while True:
                result = self.cycle()
                if self.cycles % 5 == 0:
                    self.log(f'周期 {self.cycles}: {result["explore"]["probes"]}探测 '
                             f'{result["explore"]["discoveries"]}发现 {result["explore"]["new_caps"]}新能力')
                self.save()
                time.sleep(interval)
        except KeyboardInterrupt:
            self.log('闭环已停止')

    def status(self):
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE) as f:
                s = json.load(f)
            print(f'  运行: {s["uptime_h"]}h | 周期: {s["cycles"]}')
            print(f'  探测: {s["explorer"]["probes"]} | 发现: {s["explorer"]["discoveries"]}')
            print(f'  能力地图: {s["explorer"]["capability_map"]["total_regions"]} 区域')
            print(f'  SAGE 迁移: {s["sage"]["migrations"]}')
            print(f'  里程碑: {s["milestones"]}')
        else:
            print('  未运行')

if __name__ == '__main__':
    d = UnifiedDaemon()
    if '--status' in sys.argv:
        d.status()
    elif '--once' in sys.argv:
        for _ in range(3):
            d.cycle()
            time.sleep(5)
        d.status()
    else:
        d.run(interval=45)
