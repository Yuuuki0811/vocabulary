"""Local-only internal AI gateway. Never expose this development server publicly."""
import json, os, secrets, time, threading, ssl
import accounts
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
ROOT = Path(__file__).resolve().parent
SESSION = secrets.token_urlsafe(32)
CONFIG_FILE = ROOT / '.private-api-config.json'
def load_config():
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {'key':os.environ.get('DASHSCOPE_API_KEY',''),'workspace':os.environ.get('DASHSCOPE_WORKSPACE_ID',''),'model':os.environ.get('DASHSCOPE_MODEL','qwen-plus')}
CONFIG = load_config()
KEY = CONFIG.get('key','')
MODEL = CONFIG.get('model','qwen-plus')
WORKSPACE = CONFIG.get('workspace','')

def endpoint(workspace):
    import re
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{1,100}', workspace):
        raise ValueError('业务空间 ID 格式不正确')
    return f'https://{workspace}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions'

SETUP = b''

LOCK = threading.Lock()
LAST = 0

def generate(prompt):
    payload = {'model': MODEL, 'enable_thinking':False, 'response_format':{'type':'json_object'}, 'max_tokens':5000, 'messages': [{'role':'system','content':'You are a careful business English tutor. Return JSON only. Never invent etymology or claim sources were checked.'},{'role':'user','content':prompt}]}
    request = Request(endpoint(WORKSPACE), data=json.dumps(payload).encode(), headers={'Content-Type':'application/json','Authorization':'Bearer '+KEY}, method='POST')
    with urlopen(request, timeout=55, context=ssl.create_default_context(cafile='/etc/ssl/cert.pem' if Path('/etc/ssl/cert.pem').is_file() else None)) as response:
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
        if getattr(self,'account_cookie',None):self.send_header('Set-Cookie',self.account_cookie)
        if cookie:
            self.send_header('Set-Cookie', f'business_session={SESSION}; HttpOnly; SameSite=Strict; Path=/')
        self.end_headers()
        self.wfile.write(data)
    def authorized(self):
        from http.cookies import SimpleCookie
        c = SimpleCookie(self.headers.get('Cookie',''))
        v = c.get('business_session')
        return v and secrets.compare_digest(v.value, SESSION)
    def learning_user(self):
        from http.cookies import SimpleCookie
        c=SimpleCookie(self.headers.get('Cookie',''));v=c.get('learning_user')
        return accounts.user(v.value) if v else None
    def account_post(self):
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=10000:return self.send(400,{'error':'内容无效'})
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.send(415,{'error':'需要 JSON'})
            x=json.loads(self.rfile.read(size))
            if self.path in ('/api/accounts/register','/api/accounts/login'):
                method=accounts.register if self.path.endswith('register') else accounts.login
                user,token=method(x.get('name'),x.get('password'))
                self.account_cookie=f'learning_user={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=604800'
                return self.send(200,{'user':user})
            user=self.learning_user()
            if not user:return self.send(401,{'error':'请先登录学习账户'})
            if self.path=='/api/accounts/logout':
                from http.cookies import SimpleCookie
                c=SimpleCookie(self.headers.get('Cookie',''));accounts.SESSIONS.pop(c['learning_user'].value,None)
                self.account_cookie='learning_user=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'
                return self.send(200,{'ok':True})
            accounts.update_progress(user['id'],x)
            return self.send(200,{'ok':True})
        except ValueError as e:return self.send(400,{'error':str(e)})
        except Exception:return self.send(500,{'error':'账户服务暂时不可用'})
    def do_GET(self):
        if not self.valid_host(): return self.send(403, {'error':'禁止外部访问'})
        if self.path in ('/api/accounts/me','/api/accounts/progress'):
            user=self.learning_user()
            if self.path.endswith('/me'):return self.send(200,{'user':user})
            if not user:return self.send(401,{'error':'请先登录学习账户'})
            return self.send(200,{'users':accounts.pair_progress()})
        if self.path == '/setup':
            return self.send(200, (ROOT/'setup.html').read_bytes(),'text/html',True)
        if self.path == '/api/status':
            if not self.authorized(): return self.send(401, {'error':'请重新打开内部首页'})
            return self.send(200, {'available':bool(KEY and MODEL and WORKSPACE),'verified':False,'mode':'qwen_api','provider':'阿里云百炼','model':MODEL,'chatgptLoginAvailable':False})
        if self.path in ('/','/index.html','/business-english.html'):
            return self.send(200, (ROOT/'business-english.html').read_bytes(),'text/html',True)
        return self.send(404, {'error':'未找到'})
    def configure(self):
        global KEY, MODEL, WORKSPACE
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=10000: return self.send(400,{'error':'配置内容无效'})
            if self.headers.get('Content-Type','').split(';')[0]!='application/json': return self.send(415,{'error':'需要 JSON'})
            x=json.loads(self.rfile.read(size))
            key=x.get('key','').strip(); workspace=x.get('workspace','').strip(); model=x.get('model','qwen-plus').strip()
            import re
            if not key.startswith('sk-') or len(key)<20 or len(key)>1000: return self.send(400,{'error':'需要百炼模型服务的 API Key，智能体密钥库名称不适用'})
            endpoint(workspace)
            if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',model): return self.send(400,{'error':'模型名称无效'})
            if CONFIG_FILE.is_symlink(): raise ValueError()
            flags=os.O_WRONLY|os.O_CREAT|os.O_TRUNC|getattr(os,'O_NOFOLLOW',0)
            fd=os.open(str(CONFIG_FILE),flags,0o600)
            with os.fdopen(fd,'w') as f: json.dump({'key':key,'workspace':workspace,'model':model},f)
            os.chmod(CONFIG_FILE,0o600)
            KEY,WORKSPACE,MODEL=key,workspace,model
            return self.send(200,{'saved':True,'message':'已保存在本机后台，尚需验证连接；没有上传 GitHub或公开部署'})
        except Exception: return self.send(400,{'error':'配置未保存，请检查业务空间 ID'})
    def do_POST(self):
        global LAST, KEY, MODEL, WORKSPACE
        origin = f'http://127.0.0.1:{self.server.server_port}'
        if not self.valid_host() or self.headers.get('Origin') != origin or not self.authorized():
            return self.send(403, {'error':'连接会话无效，请重新打开内部首页'})
        if self.path in ('/api/accounts/register','/api/accounts/login','/api/accounts/logout','/api/accounts/progress'):
            return self.account_post()
        if self.path == '/api/configure':
            return self.configure()
        if self.path not in ('/api/generate','/api/test'): return self.send(404, {'error':'未找到'})
        if not KEY or not MODEL or not WORKSPACE: return self.send(503, {'error':'请先在本机后台配置页填写百炼 API Key 和业务空间 ID'})
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
