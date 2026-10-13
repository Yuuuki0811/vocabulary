"""Business English gateway for Aliyun FC Web functions (Python standard library)."""
import json,os,secrets,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
ALLOWED='https://yuuuki0811.github.io'
LOCK=threading.Lock()
RECENT=[]
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def send(self,status,obj):
  b=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status)
  self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
  if self.headers.get('Origin')==ALLOWED:self.send_header('Access-Control-Allow-Origin',ALLOWED);self.send_header('Vary','Origin')
  self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def allowed(self):
  if self.headers.get('Origin') not in (None,ALLOWED):self.send(403,{'error':'来源不允许'});return False
  code=os.environ.get('LEARNING_ACCESS_CODE','');auth=self.headers.get('Authorization','');token=auth[7:] if auth.startswith('Bearer ') else ''
  if len(code)<24:self.send(503,{'error':'请配置至少24位的学习助手访问码'});return False
  if not secrets.compare_digest(token,code):self.send(401,{'error':'请先连接学习助手，或检查访问码'});return False
  return True
 def do_OPTIONS(self):
  if self.headers.get('Origin')!=ALLOWED:return self.send(403,{'error':'来源不允许'})
  self.send_response(204);self.send_header('Access-Control-Allow-Origin',ALLOWED);self.send_header('Vary','Origin');self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS');self.send_header('Access-Control-Allow-Headers','Content-Type, Authorization');self.send_header('Access-Control-Max-Age','600');self.send_header('Content-Length','0');self.end_headers()
 def do_GET(self):
  if self.path=='/':return self.send(200,{'service':'商语 AI 学习助手','message':'后台正在运行，请通过学习网页连接。'})
  if self.path!='/api/status':return self.send(404,{'error':'未找到'})
  if self.allowed():self.send(200,{'available':bool(os.environ.get('DASHSCOPE_API_KEY')),'provider':'阿里云百炼','mode':'qwen_api'})
 def do_POST(self):
  if self.path not in ('/api/test','/api/generate'):return self.send(404,{'error':'未找到'})
  if not self.allowed():return
  key=os.environ.get('DASHSCOPE_API_KEY','')
  if not key:return self.send(503,{'error':'后台尚未配置百炼密钥'})
  try:
   n=int(self.headers.get('Content-Length','0'))
   if not 0<n<=40000:return self.send(413,{'error':'内容过长或为空'})
   if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.send(415,{'error':'需要 JSON'})
   x=json.loads(self.rfile.read(n));prompt=x.get('prompt')
   if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>20000:return self.send(400,{'error':'内容无效'})
  except (ValueError,TypeError):return self.send(400,{'error':'内容格式无效'})
  if not LOCK.acquire(blocking=False):return self.send(429,{'error':'正在生成，请稍后重试'})
  try:
   now=time.monotonic();RECENT[:]=[t for t in RECENT if now-t<60]
   if len(RECENT)>=6:return self.send(429,{'error':'生成频繁，请一分钟后重试'})
   RECENT.append(now)
   workspace=os.environ.get('DASHSCOPE_WORKSPACE_ID','')
   import re
   if workspace and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{1,100}',workspace):return self.send(503,{'error':'业务空间配置无效'})
   endpoint=f'https://{workspace}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions' if workspace else 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions'
   payload={'model':os.environ.get('DASHSCOPE_MODEL','qwen-plus'),'enable_thinking':False,'response_format':{'type':'json_object'},'max_tokens':5000,'messages':[{'role':'system','content':'You are a careful business English tutor. Return JSON only. Never invent etymology or claim sources were checked.'},{'role':'user','content':'Return exactly {"ok":true}' if self.path=='/api/test' else prompt}]}
   req=Request(endpoint,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+key},method='POST')
   with urlopen(req,timeout=55) as r:result=json.load(r)
   content=result['choices'][0]['message']['content'].strip();content=re.sub(r'^```(?:json)?\s*|\s*```$','',content);data=json.loads(content)
   if not isinstance(data,dict):raise ValueError()
   self.send(200,data)
  except HTTPError as e:self.send(502,{'error':f'百炼返回 {e.code}，请检查额度与配置'})
  except (URLError,TimeoutError):self.send(504,{'error':'连接百炼超时，请重试'})
  except Exception:self.send(502,{'error':'生成结果格式不完整，请重试'})
  finally:LOCK.release()
if __name__=='__main__':ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','9000'))),Handler).serve_forever()
