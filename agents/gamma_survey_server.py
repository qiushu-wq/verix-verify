"""
Gamma Survey Server — 真人判断问卷 + 数据收集
快速重建，替代已删除的智评助手问卷前端
"""
import json, os, sys, time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

DATA_FILE = os.path.join(os.path.dirname(__file__), 'data', 'gamma_human_judgments.json')
PORT = 3002

def load_data():
    with open(DATA_FILE) as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

SURVEY_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>Verix Gamma · 真人判断问卷</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0b1120;color:#e2e8f0;min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:16px}
.card{background:#1e293b;border-radius:16px;padding:24px;max-width:500px;width:100%;box-shadow:0 4px 24px rgba(0,0,0,.4);border:1px solid #334155}
h1{font-size:20px;margin-bottom:4px;color:#f8fafc}
.sub{font-size:13px;color:#94a3b8;margin-bottom:20px}
.category{display:inline-block;padding:3px 10px;border-radius:12px;font-size:12px;margin-bottom:16px;background:rgba(99,102,241,.2);color:#a5b4fc}
.question{font-size:18px;font-weight:600;margin-bottom:20px;line-height:1.5;color:#f1f5f9}
.options{display:flex;flex-direction:column;gap:10px}
.opt{border:2px solid #334155;border-radius:12px;padding:14px 16px;cursor:pointer;transition:all .2s;background:#0f172a;font-size:15px;display:flex;align-items:center;gap:10px}
.opt:hover{border-color:#6366f1;background:#1e1b4b}
.opt.selected{border-color:#818cf8;background:#312e81;color:#e0e7ff}
.opt .dot{width:22px;height:22px;border-radius:50%;border:2px solid #475569;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:12px}
.opt.selected .dot{border-color:#818cf8;background:#6366f1;color:#fff}
.btn{width:100%;padding:14px;border-radius:12px;border:none;font-size:16px;font-weight:600;cursor:pointer;margin-top:20px;transition:all .2s}
.btn-primary{background:#6366f1;color:#fff}
.btn-primary:hover{background:#4f46e5}
.btn-primary:disabled{background:#334155;color:#64748b;cursor:not-allowed}
.btn-secondary{background:transparent;color:#94a3b8;border:1px solid #334155;margin-top:8px}
.done{text-align:center;padding:40px 20px}
.done .check{font-size:48px;margin-bottom:12px}
.done h2{font-size:22px;margin-bottom:8px;color:#f8fafc}
.done p{color:#94a3b8;margin-bottom:20px}
.stats{font-size:11px;color:#64748b;text-align:center;margin-top:16px}
.progress{height:4px;background:#334155;border-radius:2px;margin-bottom:20px;overflow:hidden}
.progress-bar{height:100%;background:#6366f1;border-radius:2px;transition:width .3s}
.toast{position:fixed;top:16px;left:50%;transform:translateX(-50%);background:#059669;color:#fff;padding:10px 20px;border-radius:20px;font-size:14px;z-index:999;opacity:0;transition:opacity .3s;pointer-events:none}
.toast.show{opacity:1}
</style>
</head>
<body>
<div class="toast" id="toast">✓ 已提交</div>
<div class="card" id="card">
<div class="progress"><div class="progress-bar" id="progress"></div></div>
<h1>🧠 Verix Gamma</h1>
<div class="sub">AI 需要你的直觉判断</div>
<div class="category" id="category"></div>
<div class="question" id="question"></div>
<div class="options" id="options"></div>
<button class="btn btn-primary" id="submitBtn" disabled onclick="submit()">提交答案</button>
<button class="btn btn-secondary" id="skipBtn" onclick="nextQuestion()" style="display:none">跳过</button>
<div class="stats" id="stats"></div>
</div>
<script>
let data = [];
let currentIdx = 0;
let answered = {};
let selectedOpt = null;

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2000);
}

function isAnswered(sid) { return answered[sid] !== undefined; }

async function load() {
  const res = await fetch('/api/scenarios');
  data = await res.json();
  const done = JSON.parse(localStorage.getItem('gamma_answered')||'{}');
  answered = done;
  // 找第一个没答过的（不能用 !，因为答案0也是合法值）
  currentIdx = data.findIndex(s => !isAnswered(s.scenario_id));
  if (currentIdx < 0) currentIdx = data.length; // 全部答完 → 展示完成页
  render();
}

function render() {
  if (!data.length || currentIdx >= data.length) {
    document.getElementById('card').innerHTML = `<div class="done">
      <div class="check">✅</div>
      <h2>全部完成！</h2>
      <p>感谢参与，你的判断将帮助 Verix 更好地理解世界。</p>
      <button class="btn btn-secondary" onclick="location.reload()">重新开始</button>
    </div>`;
    return;
  }
  const s = data[currentIdx];
  document.getElementById('category').textContent = {'physical':'🔬 物理推理','commonsense':'💡 常识判断','social':'🤝 社交场景'}[s.category] || s.category;
  document.getElementById('question').textContent = s.text;
  document.getElementById('progress').style.width = ((currentIdx / data.length) * 100) + '%';
  document.getElementById('stats').textContent = `第 ${currentIdx+1}/${data.length} 个场景 · 已收集 ${data.reduce((a,s)=>a+s.human_answers.length,0)} 条判断`;

  const optsEl = document.getElementById('options');
  optsEl.innerHTML = '';
  selectedOpt = isAnswered(s.scenario_id) ? answered[s.scenario_id] : null;
  s.options.forEach((opt, i) => {
    const div = document.createElement('div');
    div.className = 'opt' + (selectedOpt === i ? ' selected' : '');
    div.innerHTML = `<span class="dot">${selectedOpt===i?'✓':''}</span>${opt}`;
    div.onclick = () => {
      document.querySelectorAll('.opt').forEach(o => o.classList.remove('selected'));
      div.classList.add('selected');
      selectedOpt = i;
      document.getElementById('submitBtn').disabled = false;
    };
    optsEl.appendChild(div);
  });
  document.getElementById('submitBtn').disabled = (selectedOpt === null);
  document.getElementById('skipBtn').style.display = isAnswered(s.scenario_id) ? 'block' : 'none';
}

async function submit() {
  if (selectedOpt === null) return;
  const s = data[currentIdx];
  const res = await fetch('/api/record', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({scenario_id: s.scenario_id, answer: selectedOpt})
  });
  if (res.ok) {
    answered[s.scenario_id] = selectedOpt;
    localStorage.setItem('gamma_answered', JSON.stringify(answered));
    const r = await res.json();
    showToast('✓ 已提交 (' + r.human_answers + ' 人参与本题)');
    nextQuestion();
  } else {
    showToast('提交失败，请重试');
  }
}

function nextQuestion() {
  let next = currentIdx + 1;
  if (next >= data.length) next = 0;
  let attempts = 0;
  while (isAnswered(data[next]?.scenario_id) && attempts < data.length) {
    next = (next + 1) % data.length;
    attempts++;
  }
  if (attempts >= data.length) {
    currentIdx = data.length; // 全部完成
  } else {
    currentIdx = next;
  }
  selectedOpt = null;
  render();
}

load();
</script>
</body>
</html>"""

class SurveyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/gamma_survey.html' or path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(SURVEY_HTML.encode('utf-8'))
        elif path == '/api/scenarios':
            data = load_data()
            # 只返回场景信息，不返回已有答案数量（前端不需要显示偏见）
            scenarios = [{k: s[k] for k in ['scenario_id','text','options','category']} for s in data]
            scenarios_with_counts = []
            for s, raw in zip(scenarios, data):
                s['human_answers'] = len(raw.get('human_answers', []))
                scenarios_with_counts.append(s)
            self._json(scenarios_with_counts)
        elif path == '/sw.js':
            self.send_response(200)
            self.send_header('Content-Type', 'application/javascript')
            self.end_headers()
            self.wfile.write(b'// sw placeholder')
        elif path == '/favicon.ico':
            self.send_response(204)
            self.end_headers()
        else:
            self.send_response(302)
            self.send_header('Location', '/gamma_survey.html')
            self.end_headers()

    def do_POST(self):
        if self.path == '/api/record':
            content_length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(content_length))
            scenario_id = body.get('scenario_id')
            answer = body.get('answer')

            data = load_data()
            for s in data:
                if s['scenario_id'] == scenario_id:
                    s['human_answers'].append(answer)
                    save_data(data)
                    self._json({
                        'ok': True,
                        'human_answers': len(s['human_answers']),
                        'scenario_id': scenario_id,
                        'consensus': max(set(s['human_answers']), key=lambda x: s['human_answers'].count(x))
                    })
                    return
            self._json({'ok': False, 'error': 'scenario not found'}, 404)
            return

        self.send_response(405)
        self.end_headers()

    def _json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, format, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {args[0]}")

if __name__ == '__main__':
    os.chdir('/opt/verix')
    print(f"Gamma Survey Server starting on port {PORT}")
    print(f"Data file: {DATA_FILE}")
    server = HTTPServer(('0.0.0.0', PORT), SurveyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
