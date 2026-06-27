"""Verix 守护进程 — 7×24 自主闭环运行"""
import os, sys, json, time, signal, random
from datetime import datetime

sys.path.insert(0, '/opt/verix')
from verix_loop import VerixLoop, real_events
from agent_alpha import AgentAlpha
from agent_delta import AgentDelta

STATUS_FILE = '/opt/verix/logs/daemon_status.json'
LOG_FILE = '/opt/verix/logs/daemon.log'

class VerixDaemon:
    def __init__(self):
        self.alpha = AgentAlpha()
        self.delta = AgentDelta()
        self.loop = VerixLoop(alpha=self.alpha, delta=self.delta)
        self.running = True
        self.start_time = time.time()
        self.discoveries = []
        self._init_log()

    def _init_log(self):
        os.makedirs('/opt/verix/logs', exist_ok=True)
        with open(LOG_FILE, 'a') as f:
            f.write(f'\n{"="*50}\nVerix Daemon started {datetime.now().isoformat()}\n{"="*50}\n')

    def log(self, msg):
        t = datetime.now().strftime('%H:%M:%S')
        line = f'[{t}] {msg}'
        print(line)
        with open(LOG_FILE, 'a') as f:
            f.write(line + '\n')

    def save_status(self):
        status = self.loop.status()
        status['uptime'] = round(time.time() - self.start_time)
        status['discoveries'] = len(self.discoveries)
        status['last_update'] = datetime.now().isoformat()
        with open(STATUS_FILE, 'w') as f:
            json.dump(status, f, ensure_ascii=False, indent=2)

    def run(self, interval=10):
        """主循环 — 每 interval 秒执行一个闭环周期"""
        self.log(f'Verix 守护进程启动 · 周期 {interval}s')

        while self.running:
            # 从真实 Agent 运行中采集事件
            events = real_events(self.alpha, self.delta, n_per_agent=random.randint(2, 4))

            # 执行闭环周期
            result = self.loop.step(events)

            # 记录发现
            if result['sage_analogies']:
                for a in result['sage_analogies']:
                    self.discoveries.append({
                        'time': datetime.now().isoformat(),
                        'source': a['source_agent'],
                        'target': a['target_agent'],
                        'similarity': a.get('similarity', 0),
                        'solution_domain': a.get('solution_domain', ''),
                    })
                    self.log(f'SAGE: {a["source_agent"]}→{a["target_agent"]} '
                             f'sim={a.get("similarity",0):.2f} src={a.get("solution_domain","")}')

            if result['alerts']:
                for a in result['alerts']:
                    if a['signal'] == 'blind_spot_density':
                        self.log(f'GWT: {a["agent"]} 盲区密度 {a["count"]}次/30s')

            # 保存状态
            self.save_status()
            time.sleep(interval)

    def stop(self):
        self.running = False
        self.save_status()
        self.log('Verix 守护进程已停止')


def status():
    """查看守护进程状态"""
    if not os.path.exists(STATUS_FILE):
        print('守护进程未运行。启动: python3 verix_daemon.py')
        return

    with open(STATUS_FILE) as f:
        s = json.load(f)

    uptime = s.get('uptime', 0)
    h, m = divmod(uptime, 3600)
    m, s_sec = divmod(m, 60)

    print(f'\n  {"="*45}')
    print(f'  Verix 守护进程 — 运行中')
    print(f'  {"="*45}')
    print(f'  运行时间: {h}h {m}m {s_sec}s')
    print(f'  闭环周期: {s.get("cycles", 0)}')
    print(f'  闭环数:   {s.get("closed_loops", 0)}')
    print(f'  发现数:   {s.get("discoveries", 0)}')
    print(f'  最近告警: {s.get("recent_alerts", 0)}')
    print(f'  盲区分布: {s.get("blind_spots", {})}')
    print(f'  最后更新: {s.get("last_update", "?")}')
    print(f'  日志: /opt/verix/logs/daemon.log')
    print()


if __name__ == '__main__':
    if '--status' in sys.argv:
        status()
    elif '--once' in sys.argv:
        # 单次运行
        d = VerixDaemon()
        events = real_events(d.alpha, d.delta, n_per_agent=4)
        result = d.loop.step(events)
        d.save_status()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif '--stop' in sys.argv:
        # 发送停止信号
        if os.path.exists('/tmp/verix_daemon.pid'):
            with open('/tmp/verix_daemon.pid') as f:
                pid = int(f.read())
            os.kill(pid, signal.SIGTERM)
            print('已发送停止信号')
        else:
            print('守护进程未运行')
    else:
        # 启动守护进程
        with open('/tmp/verix_daemon.pid', 'w') as f:
            f.write(str(os.getpid()))
        daemon = VerixDaemon()
        signal.signal(signal.SIGTERM, lambda s, f: daemon.stop())
        signal.signal(signal.SIGINT, lambda s, f: daemon.stop())
        daemon.run(interval=8)
