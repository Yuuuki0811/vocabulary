"""Local-only internal AI gateway. Never expose this development server publicly."""
import json, os, secrets, time, threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
ROOT = Path(__file__).resolve().parent
SESSION = secrets.token_urlsafe(32)
KEY = os.environ.get('BUSINESS_OPENAI_KEY', '')
MODEL = os.environ.get('BUSINESS_OPENAI_MODEL', '')
LOCK = threading.Lock()
LAST = 0

def generate(prompt):
    payload = {'model': MODEL, 'messages': [{'role':'system','content':'You are a careful business English tutor. Return JSON only. Never invent etymology or claim sources were checked.'},{'role':'user','content':prompt}]}
    request = Request('https://api.openai.com/v1/chat/completions', data=json.dumps(payload).encode(), headers={'Content-Type':'application/json','Authorization':'Bearer '+KEY}, method='POST')
    with urlopen(request, timeout=55) as response:
        result = json.load(response)
    content = result['choices'][0]['message']['content'].strip()
    if content.startswith('```'):
        content = content.split('\n',1)[1].rsplit('```',1)[0]
    return json.loads(content)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass # Avoid logging prompts, cookies, or credentials.
    def valid_host(self):
        return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'
    def send(self, status, value, mime='application/json', cookie=False):
        data = json.dumps(value, ensure_ascii=False).encode() if mime=='application/json' else value
        self.send_response(status)
        self.send_header('Content-Type', mime+'; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        if cookie:
            self.send_header('Set-Cookie', f'business_session={SESSION}; HttpOnly; SameSite=Strict; Path=/')
        self.end_headers()
        self.wfile.write(data)
    def authorized(self):
        from http.cookies import SimpleCookie
        c = SimpleCookie(self.headers.get('Cookie',''))
        v = c.get('business_session')
        return v and secrets.compare_digest(v.value, SESSION)
    def do_GET(self):
        if not self.valid_host(): return self.send(403, {'error':'禁止外部访问'})
        if self.path == '/api/status':
            if not self.authorized(): return self.send(401, {'error':'请重新打开内部首页'})
            return self.send(200, {'available':bool(KEY and MODEL),'verified':False,'mode':'server_api','chatgptLoginAvailable':False})
        if self.path in ('/','/index.html','/business-english.html'):
            return self.send(200, (ROOT/'business-english.html').read_bytes(),'text/html',True)
        return self.send(404, {'error':'未找到'})
    def do_POST(self):
        global LAST
        origin = f'http://127.0.0.1:{self.server.server_port}'
        if not self.valid_host() or self.headers.get('Origin') != origin or not self.authorized():
            return self.send(403, {'error':'连接会话无效，请重新打开内部首页'})
        if self.path not in ('/api/generate','/api/test'): return self.send(404, {'error':'未找到'})
        if not KEY or not MODEL: return self.send(503, {'error':'后台已启动，尚未开通 AI 服务；ChatGPT 官方托管授权资格尚未配置'})
        try:
            size = int(self.headers.get('Content-Length','0'))
            if not 0 < size <= 40000: return self.send(413, {'error':'请求过大或为空'})
            if self.headers.get('Content-Type','').split(';')[0] != 'application/json': return self.send(415, {'error':'需要 JSON'})
            obj = json.loads(self.rfile.read(size))
            prompt = obj.get('prompt')
            if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>20000: return self.send(400, {'error':'内容无效'})
            if not LOCK.acquire(blocking=False): return self.send(429, {'error':'正在生成，请稍后再试'})
            try:
                if time.monotonic()-LAST < 1: return self.send(429, {'error':'请求太频繁'})
                LAST = time.monotonic()
                result = generate('Return exactly {"ok":true}' if self.path=='/api/test' else prompt)
                if self.path=='/api/test' and result.get('ok') is not True: raise ValueError()
                return self.send(200, result)
            finally: LOCK.release()
        except HTTPError as e: return self.send(502, {'error':f'AI 服务返回 {e.code}，请检查后台凭证与额度'})
        except (URLError, TimeoutError): return self.send(504, {'error':'AI 服务连接超时，请稍后重试'})
        except Exception: return self.send(502, {'error':'生成结果格式不完整，请重试'})

if __name__ == '__main__':
    server = ThreadingHTTPServer(('127.0.0.1',8770), Handler)
    print('内部版：http://127.0.0.1:8770/ （仅本机可访问）', flush=True)
    server.serve_forever()
