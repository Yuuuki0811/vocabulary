"""Two local learning accounts. Password hashes only; progress sharing requires login."""
import sqlite3, hashlib, secrets, json, os, time, threading
from pathlib import Path
PATH=Path(__file__).resolve().parent/'.private-accounts.sqlite3'
LOCK=threading.Lock()
SESSIONS={}
def connect():
 c=sqlite3.connect(PATH,timeout=10)
 os.chmod(PATH,0o600)
 c.execute('CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL, salt TEXT NOT NULL, hash TEXT NOT NULL, progress TEXT)')
 return c

def register(name,password):
 if not isinstance(name,str) or not 1<=len(name.strip())<=20:raise ValueError('账户名称需1–20个字符')
 if not isinstance(password,str) or not 8<=len(password)<=128:raise ValueError('密码需8–128个字符')
 name=name.strip();salt=secrets.token_hex(16);hashed=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),200000).hex()
 with LOCK,connect() as c:
  if c.execute('SELECT COUNT(*) FROM users').fetchone()[0]>=2:raise ValueError('两个账户已创建，请直接登录')
  try:c.execute('INSERT INTO users VALUES (?,?,?,?,?)',(secrets.token_hex(16),name,salt,hashed,None))
  except sqlite3.IntegrityError:raise ValueError('账户名称已存在')
 return login(name,password)

def login(name,password):
 if not isinstance(name,str) or not isinstance(password,str):raise ValueError('账户或密码不正确')
 with connect() as c:row=c.execute('SELECT id,name,salt,hash FROM users WHERE name=?',(name.strip(),)).fetchone()
 if not row:raise ValueError('账户或密码不正确')
 hashed=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(row[2]),200000).hex()
 if not secrets.compare_digest(hashed,row[3]):raise ValueError('账户或密码不正确')
 token=secrets.token_urlsafe(32)
 SESSIONS[token]=(row[0],time.time()+86400*7)
 return {'id':row[0],'name':row[1]},token

def user(token):
 session=SESSIONS.get(token)
 if not session or session[1]<time.time():return None
 with connect() as c:row=c.execute('SELECT id,name FROM users WHERE id=?',(session[0],)).fetchone()
 return {'id':row[0],'name':row[1]} if row else None

def update_progress(user_id,data):
 if not isinstance(data,dict):raise ValueError('进度格式无效')
 clean={}
 for k in ['newToday','reviewToday','streak','mastered','totalLearned','fedDays','feedCount','achievements','weekScore','weekDays','newGoal','reviewGoal']:
  v=data.get(k,0)
  if not isinstance(v,(int,float)) or isinstance(v,bool) or not 0<=v<=100000:raise ValueError('进度数值无效')
  clean[k]=int(v)
 import re
 day=data.get('day','')
 if day and (not isinstance(day,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day)):raise ValueError('日期无效')
 week=data.get('week','')
 if week and (not isinstance(week,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',week)):raise ValueError('周日期无效')
 clean['week']=week
 clean['day']=day
 clean['updatedAt']=time.time()
 with connect() as c:c.execute('UPDATE users SET progress=? WHERE id=?',(json.dumps(clean),user_id))

def pair_progress():
 with connect() as c:rows=c.execute('SELECT id,name,progress FROM users ORDER BY name').fetchall()
 return [{'id':r[0],'name':r[1],'progress':json.loads(r[2]) if r[2] else None} for r in rows]
