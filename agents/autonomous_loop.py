"""Verix 自主推演引擎 — 主动盲区探测 + 自主实验设计 + 自我改进"""
import os, sys, time, random, json
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, '/opt/verix')
from verix_loop import VerixLoop, MetacognitiveMonitor, real_events
from agent_alpha import AgentAlpha, SceneGenerator
from agent_delta import AgentDelta
from delta_auto import AutoExtensionEngine
from alpha_learn import BlindSpotResolver
from sage_engine import SAGEEngineV2

STATUS_FILE = '/opt/verix/logs/autonomous_status.json'
LOG_FILE = '/opt/verix/logs/autonomous.log'

class AutonomousEngine:
    """自主推演引擎 — 主动探测 + 自我改进"""

    def __init__(self):
        self.alpha = AgentAlpha()
        self.delta = AgentDelta()
        self.loop = VerixLoop(alpha=self.alpha, delta=self.delta)
        self.sage = SAGEEngineV2()
        self.resolver = BlindSpotResolver(self.alpha)
        self.extender = AutoExtensionEngine(self.delta)
        self.monitor = MetacognitiveMonitor()

        self.probes_launched = 0
        self.discoveries = []
        self.capability_growth = []
        self.start_time = time.time()

        os.makedirs('/opt/verix/logs', exist_ok=True)

    def log(self, msg):
        t = datetime.now().strftime('%H:%M:%S')
        line = f'[{t}] [AUTO] {msg}'
        print(line)
        with open(LOG_FILE, 'a') as f:
            f.write(line + '\n')

    def cycle(self) -> dict:
        """执行一个自主推演周期"""
        result = {'cycle': time.time(), 'probes': [], 'learning': [], 'discoveries': []}

        # Step 1: 采集真实事件
        events = real_events(self.alpha, self.delta, n_per_agent=2)
        for e in events:
            self.monitor.feed(e)

        # Step 2: GWT 元认知检查
        alerts = self.monitor.check()

        # Step 3: 主动盲区探测
        for alert in alerts:
            if alert['signal'] == 'blind_spot_density' and alert['agent'] == 'alpha':
                # 设计探测任务——在盲区边界生成测试场景
                probe = self._probe_alpha_boundary(alert)
                if probe:
                    result['probes'].append(probe)
                    self.probes_launched += 1

            if alert['signal'] == 'learning_stagnation' and alert['agent'] == 'delta':
                # 尝试自动扩展——为最不稳定的模板区域生成新变体
                probe = self._probe_delta_boundary()
                if probe:
                    result['probes'].append(probe)

        # Step 4: SAGE 跨域发现
        if self.probes_launched > 0 and self.probes_launched % 5 == 0:
            analogies = self.sage.scan('alpha', 'alpha_boundary_critical')
            for a in analogies[:2]:
                result['discoveries'].append({
                    'type': 'sage_cross_domain',
                    'source': a['source_agent'],
                    'target': a['target_agent'],
                    'similarity': a['similarity'],
                    'solution': a['solution'][:80],
                })

        # Step 5: 自我改进——如果足够多的探测完成，汇总学习
        if len(result['probes']) >= 3:
            summary = self._summarize_probes(result['probes'])
            if summary:
                result['learning'].append(summary)
                self.capability_growth.append(summary)

        self._save_status()
        return result

    def _probe_alpha_boundary(self, alert: dict) -> dict:
        """在物理盲区边界设计探测任务"""
        gen = SceneGenerator()
        # 在盲区边界附近生成极端场景
        scene = gen.random_scene('collision')
        for obj in scene.objects:
            obj['mass'] *= random.uniform(5, 20)
            obj['vel'] = [v * random.uniform(3, 8) for v in obj['vel']]

        # 执行增量学习
        learn_result = self.resolver.resolve(scene, 'auto_probe')
        self.log(f'alpha probe: RMSE {learn_result.get("baseline_rmse",0):.4f} → {learn_result.get("new_rmse",0):.4f} ({learn_result.get("status","?")})')
        return {'type': 'alpha_probe', 'agent': 'alpha', 'result': learn_result}

    def _probe_delta_boundary(self) -> dict:
        """在模板覆盖边界设计探测任务"""
        # 找一个不在模板库中的任务类型
        probe_tasks = [
            ('list_median', '计算整数列表的中位数', [('[1,2,3]', '2'), ('[1,2,3,4]', '2.5')]),
            ('str_trim', '去除字符串首尾空格', [('" hello "', '"hello"')]),
        ]
        task_name, task_desc, test_cases = random.choice(probe_tasks)

        if task_name not in self.delta.synthesizer.TEMPLATES:
            result = self.extender.extend(task_name, task_desc, test_cases)
            self.log(f'delta probe: {task_name} → {result.get("status","?")}')
            return {'type': 'delta_probe', 'agent': 'delta', 'task': task_name, 'result': result}
        return None

    def _summarize_probes(self, probes: list) -> dict:
        """汇总探测结果，生成学习摘要"""
        alpha_probes = [p for p in probes if p['type'] == 'alpha_probe']
        delta_probes = [p for p in probes if p['type'] == 'delta_probe']

        summary = {
            'alpha_improvements': sum(1 for p in alpha_probes if p['result'].get('status') == 'resolved'),
            'delta_extensions': sum(1 for p in delta_probes if p['result'].get('status') == 'extended'),
            'total_probes': len(probes),
            'time': datetime.now().isoformat(),
        }

        if summary['alpha_improvements'] > 0:
            self.log(f'learning: {summary["alpha_improvements"]} alpha blind spots resolved')
        if summary['delta_extensions'] > 0:
            self.log(f'learning: {summary["delta_extensions"]} delta templates auto-extended')

        return summary

    def _save_status(self):
        status = {
            'uptime_hours': round((time.time() - self.start_time) / 3600, 1),
            'probes_launched': self.probes_launched,
            'discoveries': len(self.discoveries),
            'capability_growth': len(self.capability_growth),
            'gwt_status': self.loop.status(),
            'resolver_status': self.resolver.status(),
            'extender_status': self.extender.status(),
            'last_update': datetime.now().isoformat(),
        }
        with open(STATUS_FILE, 'w') as f:
            json.dump(status, f, ensure_ascii=False, indent=2)

    def status(self):
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE) as f:
                s = json.load(f)
            print(f'  运行时间: {s["uptime_hours"]}h')
            print(f'  主动探测: {s["probes_launched"]} 次')
            print(f'  发现: {s["discoveries"]}')
            print(f'  能力增长: {s["capability_growth"]} 次')
            print(f'  已解决盲区: {s.get("resolver_status",{}).get("resolved",0)}')
            print(f'  已扩展模板: {s.get("extender_status",{}).get("verifier_status",{}).get("added",0)}')
        else:
            print('  引擎未运行')

    def run(self, cycles=10, interval=15):
        """运行 N 个自主推演周期"""
        self.log(f'自主推演引擎启动 · {cycles} 周期 · {interval}s/周期')
        for i in range(cycles):
            result = self.cycle()
            probes = len(result['probes'])
            learning = len(result['learning'])
            discoveries = len(result['discoveries'])
            if probes or learning or discoveries:
                self.log(f'周期 {i+1}/{cycles}: {probes}探测 {learning}学习 {discoveries}发现')
            time.sleep(interval)
        self.log(f'完成 · {self.probes_launched} 探测 · {len(self.discoveries)} 发现 · {len(self.capability_growth)} 学习')

    def run_daemon(self, interval=30):
        """守护进程模式——无限循环"""
        self.log(f'自主推演守护进程启动 · 周期 {interval}s')
        try:
            while True:
                self.cycle()
                time.sleep(interval)
        except KeyboardInterrupt:
            self.log('引擎已停止')


if __name__ == '__main__':
    import sys
    engine = AutonomousEngine()

    if '--status' in sys.argv:
        engine.status()
    elif '--daemon' in sys.argv:
        interval = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 30
        engine.run_daemon(interval)
    elif '--once' in sys.argv:
        cycles = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 5
        engine.run(cycles=cycles, interval=5)
    else:
        engine.run(cycles=3, interval=3)
        engine.status()
