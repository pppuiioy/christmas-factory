import os,re,secrets,base64
from functools import wraps
from flask import Flask,request,session,redirect,render_template_string,abort,flash
import psycopg
from psycopg.rows import dict_row
from werkzeug.security import generate_password_hash,check_password_hash
app=Flask(__name__)
app.secret_key=os.environ['SECRET_KEY']
app.config.update(MAX_CONTENT_LENGTH=50*1024*1024,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',SESSION_COOKIE_SECURE=True)
def db(): return psycopg.connect(os.environ['DATABASE_URL'],row_factory=dict_row)
with db() as c:
 c.execute('''CREATE TABLE IF NOT EXISTS gift_users(id text PRIMARY KEY,pw text NOT NULL); CREATE TABLE IF NOT EXISTS gift_stations(id int PRIMARY KEY,name text NOT NULL,url text NOT NULL); CREATE TABLE IF NOT EXISTS gift_votes(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,uid text REFERENCES gift_users(id),station int REFERENCES gift_stations(id),qty int CHECK(qty>0),proof text NOT NULL,status text DEFAULT '待审核',created timestamptz DEFAULT now()); CREATE TABLE IF NOT EXISTS gift_rewards(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,name text,cost int CHECK(cost>0),stock int CHECK(stock>=0),active boolean DEFAULT true); CREATE TABLE IF NOT EXISTS gift_orders(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,uid text REFERENCES gift_users(id),reward bigint REFERENCES gift_rewards(id),name text,cost int,status text DEFAULT '待发货');''')
 c.execute("ALTER TABLE gift_votes ADD COLUMN IF NOT EXISTS reason text DEFAULT ''; ALTER TABLE gift_votes ADD COLUMN IF NOT EXISTS submitted_qty int;")
 for i,n in enumerate(['粉丝团聚力场','星拍站姐光影场','粉丝IP元力场','超话大赏'],1): c.execute('INSERT INTO gift_stations VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',(i,n,'http://t.cn/AXcF9tyj' if i<4 else 'http://t.cn/AXTMhDZ8'))
 for i,old,new in [(1,'星光生产线 · 粉丝团聚力场','粉丝团聚力场'),(2,'丝带生产线 · 星拍站姐光影场','星拍站姐光影场'),(3,'雪花生产线 · 粉丝IP元力场','粉丝IP元力场'),(4,'铃铛生产线 · 超话大赏','超话大赏')]: c.execute('UPDATE gift_stations SET name=%s WHERE id=%s AND name=%s',(new,i,old))
def rows(c,q,p=()): return c.execute(q,p).fetchall()
def balance(c,u): return c.execute("SELECT COALESCE((SELECT sum(qty) FROM gift_votes WHERE uid=%s AND status='已通过'),0)-COALESCE((SELECT sum(cost) FROM gift_orders WHERE uid=%s AND status!='已取消'),0) AS n",(u,u)).fetchone()['n']
@app.before_request
def csrf():
 if 'csrf' not in session: session['csrf']=secrets.token_hex(24)
 if request.method=='POST' and not secrets.compare_digest(request.form.get('csrf',''),session['csrf']): abort(400)
def admin():
 if not session.get('admin'): abort(403)
def user():
 if not session.get('uid'): abort(403)
 return session['uid']
@app.route('/',methods=['GET','POST'])
def home():
 if request.method=='POST':
  action=request.form.get('action'); u=request.form.get('uid','').strip(); p=request.form.get('password','')
  with db() as c:
   if action=='admin':
    role=next((r for r,k in [('高级审核员','ADMIN_PASSWORD'),('普通审核员','AUDIT_PASSWORD')] if os.environ.get(k) and secrets.compare_digest(p.encode(),os.environ[k].encode())),None)
    if role: session.clear();session['admin']=role;return redirect('/admin')
    flash('管理员密码错误')
   elif action=='register':
    if not u or len(u)>100 or not re.fullmatch('[A-Za-z0-9]+',p) or p!=request.form.get('confirm'): flash('请检查账号、密码及确认密码')
    elif c.execute('INSERT INTO gift_users VALUES(%s,%s) ON CONFLICT DO NOTHING RETURNING id',(u,generate_password_hash(p))).fetchone(): flash('注册成功，请登录')
    else: flash('账号已存在')
   elif action=='login':
    r=c.execute('SELECT pw FROM gift_users WHERE id=%s',(u,)).fetchone()
    if r and check_password_hash(r['pw'],p): session.clear();session['uid']=u;return redirect('/')
    flash('账号或密码错误')
  return redirect('/')
 with db() as c:
  u=session.get('uid'); stations=rows(c,'SELECT * FROM gift_stations ORDER BY id'); rewards=rows(c,'SELECT * FROM gift_rewards WHERE active ORDER BY cost'); board=rows(c,"SELECT u.id,COALESCE(sum(v.qty),0) AS total FROM gift_users u LEFT JOIN gift_votes v ON u.id=v.uid AND v.status='已通过' GROUP BY u.id ORDER BY total DESC,u.id")
  votes=rows(c,'SELECT id,station,qty,status,reason FROM gift_votes WHERE uid=%s ORDER BY id DESC',(u,)) if u else []; orders=rows(c,'SELECT * FROM gift_orders WHERE uid=%s ORDER BY id DESC',(u,)) if u else []; counts=[sum(v['qty'] for v in votes if v['station']==s['id'] and v['status']=='已通过') for s in stations]; available=balance(c,u) if u else 0
 return page('home',**locals())
@app.post('/vote')
def vote():
 u=user(); files=request.files.getlist('proof'); qty=request.form.get('qty',type=int); station=request.form.get('station',type=int)
 if not files or len(files)>10 or not qty or qty<1 or qty>100000 or station not in range(1,5): abort(400)
 import json
 proofs=[]
 for f in files:
  raw=f.read()
  mime='image/png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if raw.startswith(b'\xff\xd8\xff') else 'video/mp4' if raw[4:8]==b'ftyp' else None
  if not mime: flash('请上传 JPG、PNG 或 MP4/MOV 录屏');return redirect('/')
  proofs.append('data:'+mime+';base64,'+base64.b64encode(raw).decode())
 proof=json.dumps(proofs)
 with db() as c:
  c.execute('SELECT id FROM gift_users WHERE id=%s FOR UPDATE',(u,))
  old=rows(c,"SELECT proof FROM gift_votes WHERE uid=%s AND station=%s AND status!='已拒绝'",(u,station))
  if any(set(proofs)&set(json.loads(r['proof']) if r['proof'].startswith('[') else [r['proof']]) for r in old): flash('凭证已提交')
  else: c.execute('INSERT INTO gift_votes(uid,station,qty,proof,submitted_qty) VALUES(%s,%s,%s,%s,%s)',(u,station,qty,proof,qty));flash('已提交，等待审核')
 return redirect('/')
@app.post('/redeem')
def redeem():
 u=user(); rid=request.form.get('id',type=int)
 with db() as c:
  c.execute('SELECT id FROM gift_users WHERE id=%s FOR UPDATE',(u,)); r=c.execute('SELECT * FROM gift_rewards WHERE id=%s AND active FOR UPDATE',(rid,)).fetchone()
  if not r or r['stock']<1 or balance(c,u)<r['cost']: flash('库存或原料不足')
  else:
   c.execute('UPDATE gift_rewards SET stock=stock-1 WHERE id=%s',(rid,));c.execute('INSERT INTO gift_orders(uid,reward,name,cost) VALUES(%s,%s,%s,%s)',(u,rid,r['name'],r['cost']));flash('兑换成功')
 return redirect('/')
@app.route('/admin',methods=['GET','POST'])
def manage():
 admin()
 with db() as c:
  if request.method=='POST':
   a=request.form['action']; i=request.form.get('id',type=int)
   if a in ('station','reward','hide') and session['admin']!='高级审核员': abort(403)
   if a=='station':
    url=request.form['url'].strip()
    if url and not url.startswith(('https://','http://')): abort(400)
    c.execute('UPDATE gift_stations SET name=%s,url=%s WHERE id=%s',(request.form['name'],url,i))
   elif a=='review':
    status=request.form['status']; qty=request.form.get('qty',type=int); reason=request.form.get('reason','').strip()
    if status=='已拒绝' and not reason: flash('请填写驳回原因');return redirect('/admin')
    if status not in ['已通过','已拒绝'] or not qty or qty<1 or qty>100000: abort(400)
    v=c.execute('SELECT uid FROM gift_votes WHERE id=%s',(i,)).fetchone()
    if v:
     c.execute('SELECT id FROM gift_users WHERE id=%s FOR UPDATE',(v['uid'],));c.execute("UPDATE gift_votes SET status=%s,qty=%s,reason=%s WHERE id=%s AND status='待审核'",(status,qty,reason,i))
   elif a=='reward':
    p=(request.form['name'],request.form.get('cost',type=int),request.form.get('stock',type=int))
    if not p[0] or not p[1] or p[1]<1 or p[2] is None or p[2]<0: abort(400)
    if i: c.execute('UPDATE gift_rewards SET name=%s,cost=%s,stock=%s WHERE id=%s',(*p,i))
    else: c.execute('INSERT INTO gift_rewards(name,cost,stock) VALUES(%s,%s,%s)',p)
   elif a=='hide': c.execute('UPDATE gift_rewards SET active=NOT active WHERE id=%s',(i,))
   elif a=='ship': c.execute("UPDATE gift_orders SET status='已发货' WHERE id=%s AND status='待发货'",(i,))
   return redirect('/admin')
  stations=rows(c,'SELECT * FROM gift_stations ORDER BY id'); votes=rows(c,'SELECT id,uid,station,qty,status,reason,submitted_qty FROM gift_votes ORDER BY id DESC'); rewards=rows(c,'SELECT * FROM gift_rewards ORDER BY id'); orders=rows(c,'SELECT * FROM gift_orders ORDER BY id DESC')
 import json
 with db() as conn:
  for v in votes:
   raw=conn.execute('SELECT proof FROM gift_votes WHERE id=%s',(v['id'],)).fetchone()['proof']; v['media']=[x.split(';')[0][5:] for x in (json.loads(raw) if raw.startswith('[') else [raw])]
 tab=request.args.get('tab','audit')
 if tab!='audit' and session['admin']!='高级审核员': abort(403)
 return page('admin',**locals())
@app.get('/proof/<int:i>/<int:j>')
def proof(i,j):
 admin()
 with db() as c: r=c.execute('SELECT proof FROM gift_votes WHERE id=%s',(i,)).fetchone()
 if not r: abort(404)
 from flask import Response
 import json
 items=json.loads(r['proof']) if r['proof'].startswith('[') else [r['proof']]
 if j>=len(items): abort(404)
 header,data=items[j].split(',',1);return Response(base64.b64decode(data),mimetype=header.split(':')[1].split(';')[0],headers={'X-Content-Type-Options':'nosniff'})
@app.post('/logout')
def logout(): session.clear();return redirect('/')
def page(mode,**ctx): return render_template_string(TEMPLATE,mode=mode,**ctx)
TEMPLATE='''{% macro token() %}<input type="hidden" name="csrf" value="{{session.csrf}}">{% endmacro %}
<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>冬日心愿 · 圣诞礼物工厂</title>
<style>
:root{--ink:#49346d;--muted:#9483ad;--purple:#8055b9;--purple2:#a985d0;--line:#e8daf6;--gold:#fff2c9;--paper:#fff;--green:#43866b;--bg:#f8f3ff}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;min-height:100vh;color:var(--ink);font:16px/1.55 "PingFang SC","Microsoft YaHei",system-ui,sans-serif;background:radial-gradient(ellipse at 10% 8%,#fff 0,transparent 34%),radial-gradient(ellipse at 92% 32%,#eee3ff 0,transparent 38%),linear-gradient(145deg,#faf6ff,#eee4fb 58%,#fffaff)}
body:before{content:"❄　✦　❄　　 ✧　　 ❄　✦　❄";position:fixed;inset:0 0 auto;z-index:-1;text-align:center;color:#b99bdc;opacity:.28;letter-spacing:16px;font-size:22px;padding:16px;pointer-events:none}
main{width:min(900px,calc(100% - 28px));margin:18px auto 44px}.shell{background:#ffffff72;border:1px solid #eee4fa;border-radius:28px;padding:18px;box-shadow:0 16px 45px #64458b10}.brandbar{display:flex;justify-content:space-between;align-items:center;gap:12px;margin:0 2px 18px;color:#78618f;font-weight:800;letter-spacing:.7px}.brand{display:flex;align-items:center;gap:8px}.admin-link{border:0;border-radius:14px;padding:10px 15px;background:#eadcf7;color:#69498e;box-shadow:none;font-size:14px;text-decoration:none;white-space:nowrap}
.hero{text-align:center;padding:28px 16px 24px;border-radius:24px;background:linear-gradient(135deg,#f4edff,#fff 48%,#eadcfb);margin-bottom:18px}.hero-icons{font-size:54px;line-height:1.3;letter-spacing:10px}.hero h1{font-size:clamp(28px,5vw,38px);margin:8px 0 0;color:#241b2c;font-weight:850}.hero h2{font-size:23px;margin:0;color:#33243f}.hero p{margin:9px 0 0;color:#8a70a8;font-weight:650}.hero .tagline{font-size:14px;letter-spacing:.5px}.panel{background:#fff;border:1px solid var(--line);border-radius:22px;padding:22px;margin:16px 0;box-shadow:0 9px 28px #64458b09}.panel h2{font-size:22px;margin:0 0 14px;color:#2e2538}.panel h3{margin:0 0 8px}.muted,small{color:var(--muted)}.eyebrow{font-size:12px;letter-spacing:2px;color:#a18bbd;font-weight:700}.input{width:100%;border:1px solid #ddcdef;border-radius:13px;padding:14px 15px;font:inherit;color:var(--ink);background:#fff;margin:7px 0}.input:focus{outline:3px solid #e5d7f5;border-color:#9b79ca}button,.btn{border:0;border-radius:13px;padding:12px 17px;font:inherit;font-weight:750;background:linear-gradient(120deg,#8055b9,#9871c7);color:#fff;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;justify-content:center;gap:7px;box-shadow:0 5px 13px #7852b522}button:hover,.btn:hover{filter:brightness(1.04)}button:disabled{opacity:.4;cursor:not-allowed}.full{width:100%;margin-top:8px}.btn-light{background:#eee2f8;color:#725292;box-shadow:none}.btn-green{background:#44866c}.notice{background:#fff4d2;border:1px solid #f4e6b8;color:#8b7041;border-radius:13px;padding:12px 14px;margin:14px 0;font-weight:650}.flash{background:#fff4d2;color:#7c6336;padding:10px 14px;border-radius:12px;margin:12px 0}.auth-panel{padding:22px}.auth-panel h2{margin-bottom:14px}.register-row{display:flex;justify-content:center;align-items:center;gap:10px;margin-top:12px;color:#8b74a5}.register-row button{padding:9px 16px}.auth-note{font-size:13px;margin-top:14px}.top-meta{display:flex;justify-content:space-between;align-items:center;gap:10px;margin:0 3px 12px;color:#8d7aa5;font-size:13px}.logout{padding:7px 12px;background:#eee2f8;color:#745493;box-shadow:none;font-size:13px}.tabs{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:14px 0}.tabs a{display:flex;justify-content:center;align-items:center;text-decoration:none;color:#765696;background:#ecdef8;border-radius:13px;padding:12px 5px;font-weight:750}.tabs a.active{background:linear-gradient(120deg,#8055b9,#9871c7);color:#fff;box-shadow:0 5px 14px #8055b933}.stat-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:14px 0}.stat{border:1px solid var(--line);border-radius:15px;padding:14px;background:#fdfbff}.stat .label{font-size:13px;color:#8e7ba6}.stat strong{display:block;font-size:27px;color:#714a9d;margin-top:4px}.production-list{display:grid;gap:0}.production-row{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center;padding:16px 0;border-bottom:1px solid #eee5f6}.production-row:last-child{border-bottom:0}.production-title{font-size:18px;font-weight:800}.production-title span{font-size:22px;margin-right:7px}.production-sub{font-size:12px;color:#9a89ae;margin-top:3px}.venue-link{background:#eee1f8;color:#765493;box-shadow:none;white-space:nowrap}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.form-grid label,.admin-item label{display:block;font-weight:650;color:#6e5789;font-size:14px}.form-grid .wide{grid-column:1/-1}.filebox{display:block;border:1px dashed #cbb4e2;border-radius:14px;padding:14px;background:#fcf9ff;color:#80649d}.filebox input{display:block;width:100%;margin-top:8px}.hint{font-size:13px;color:#9988ad}.rewards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.reward{border:1px solid var(--line);border-radius:17px;padding:16px;background:#fff}.reward .gift{font-size:30px}.reward .cost{font-weight:850;color:#8055b9}.board{width:100%;border-collapse:collapse}.board th,.board td{text-align:left;padding:12px 9px;border-bottom:1px solid #eee5f6}.board th{color:#806a9b;font-size:14px}.history-row{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:12px 0;border-bottom:1px solid #eee5f6}.pill{display:inline-block;padding:4px 10px;border-radius:30px;background:#eee4f7;color:#785b98;font-size:12px;white-space:nowrap}.pill.ok{background:#e5f4eb;color:#3e7b5b}.pill.bad{background:#ffeded;color:#a55353}.footer{text-align:center;color:#9a83b5;padding:20px 8px 4px;font-size:13px}.footer .snowline{letter-spacing:8px;color:#a88acb}.admin-nav{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}.admin-item{border:1px solid var(--line);border-radius:16px;padding:16px;margin:12px 0;background:#fff}.media{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}.media img,.media video{width:min(180px,45%);max-height:220px;object-fit:contain;border-radius:10px;background:#f4eff8}.form-row{display:flex;gap:8px}.form-row>*{flex:1}.inline{display:inline}.section-head{display:flex;justify-content:space-between;align-items:center;gap:12px}.hide{display:none!important}
@media(max-width:600px){main{width:calc(100% - 14px);margin:7px auto 25px}.shell{padding:10px;border-radius:22px}.hero{padding:23px 10px 20px}.hero-icons{font-size:46px}.hero h1{font-size:29px}.hero h2{font-size:20px}.panel{padding:17px;margin:12px 0;border-radius:18px}.tabs{gap:5px}.tabs a{font-size:13px;padding:10px 2px}.stat-grid{gap:6px}.stat{padding:10px}.stat strong{font-size:22px}.production-title{font-size:16px}.venue-link{padding:10px 12px;font-size:13px}.form-grid{grid-template-columns:1fr}.form-grid .wide{grid-column:auto}.rewards{grid-template-columns:1fr}.history-row{align-items:flex-start;font-size:13px}.brandbar{font-size:13px}.admin-link{padding:8px 10px}}
</style></head><body><main><div class="shell">
<div class="brandbar"><div class="brand">❄️ CHRISTMAS FACTORY</div>{% if mode=='home' %}<a class="admin-link" href="#admin-entry">管理员入口</a>{% else %}<a class="admin-link" href="/">返回工厂</a>{% endif %}</div>
<header class="hero"><div class="hero-icons">🎄 🎁</div><h1>冬日心愿</h1><h2>圣诞礼物工厂</h2><p class="tagline">积极参与投票任务，拿下年度最佳</p><p class="hint">以热爱为原料 · 以心意制礼</p></header>
{% for m in get_flashed_messages() %}<p class="flash">{{m}}</p>{% endfor %}
{% if mode=='home' %}
{% if not u %}
<section class="panel auth-panel"><h2>欢迎来到圣诞工厂</h2><form method="post">{{token()}}<input type="hidden" name="action" value="login"><input class="input" name="uid" placeholder="微博ID" autocomplete="username" required><input class="input" name="password" type="password" placeholder="密码（英文字母或数字）" autocomplete="current-password" required><button class="full">进入工厂</button></form><div class="register-row"><span>首次参与？</span><button class="btn-light" type="button" onclick="document.getElementById('register-box').classList.toggle('hide')">立即注册</button></div><div id="register-box" class="hide"><form method="post">{{token()}}<input type="hidden" name="action" value="register"><input class="input" name="uid" placeholder="微博ID" required><input class="input" name="password" type="password" pattern="[A-Za-z0-9]+" placeholder="设置密码（英文字母或数字）" required><input class="input" name="confirm" type="password" placeholder="再次输入密码" required><button class="full">注册账号</button></form></div><div class="notice auth-note">预览测试：可直接注册任意测试账号，初始原料为 0。</div></section>
{% else %}
<div class="top-meta"><span>🎄 欢迎回来，<b>{{u}}</b></span><form action="/logout" method="post" class="inline">{{token()}}<button class="logout">退出登录</button></form></div>
<div class="stat-grid"><div class="stat"><div class="label">⭐ 累计有效票数</div><strong>{{counts|sum}}</strong></div><div class="stat"><div class="label">🎁 当前原料</div><strong>{{available}}</strong></div><div class="stat"><div class="label">📋 待审核凭证</div><strong>{{votes|selectattr('status','equalto','待审核')|list|length}}</strong></div></div>
<nav class="tabs"><a href="/?view=warehouse" class="{% if request.args.get('view','warehouse')=='warehouse' %}active{% endif %}">仓库</a><a href="/?view=vote" class="{% if request.args.get('view')=='vote' %}active{% endif %}">投票</a><a href="/?view=redeem" class="{% if request.args.get('view')=='redeem' %}active{% endif %}">兑换</a><a href="/?view=board" class="{% if request.args.get('view')=='board' %}active{% endif %}">榜单</a><a href="/?view=records" class="{% if request.args.get('view')=='records' %}active{% endif %}">记录</a></nav>
{% set view=request.args.get('view','warehouse') %}
{% if view=='warehouse' %}<section class="panel"><h2>📦 原料仓库</h2><p class="muted">每投 1 票获得 1 份原料，审核通过后到账。</p><div class="production-list">{% for s in stations %}<div class="production-row"><div><div class="production-title"><span>{{['⭐','🎀','❄️','🔔'][loop.index0]}}</span>{{s.name}}</div><div class="production-sub">{{['粉丝团聚力场','星拍站姐光影场','粉丝IP元力场','超话大赏'][loop.index0]}} · 已累计 {{counts[loop.index0]}} 票</div></div><a class="btn venue-link" href="/?view=vote&station={{s.id}}">前往投票</a></div>{% endfor %}</div></section>
{% elif view=='vote' %}<section class="panel"><h2>🗳️ 投票登记</h2><p class="muted">前往对应活动会场完成投票，填写本次新增票数并上传凭证，审核通过后按实际有效票数增加原料。</p><div class="production-list">{% for s in stations %}<div class="production-row"><div><div class="production-title"><span>{{['⭐','🎀','❄️','🔔'][loop.index0]}}</span>{{s.name}}</div><div class="production-sub">{{['粉丝团聚力场','星拍站姐光影场','粉丝IP元力场','超话大赏'][loop.index0]}}</div></div><a class="btn venue-link" href="{{s.url}}" target="_blank" rel="noopener">前往投票 ↗</a></div>{% endfor %}</div><form action="/vote" method="post" enctype="multipart/form-data" class="form-grid">{{token()}}<div class="wide"><label>选择提交的会场</label><select class="input" name="station" required>{% for s in stations %}<option value="{{s.id}}" {% if request.args.get('station',type=int)==s.id %}selected{% endif %}>{{s.name}}</option>{% endfor %}</select></div><div class="wide"><label>本次新增有效票数</label><input class="input" name="qty" type="number" min="1" max="100000" placeholder="填写本次新增有效票数" required></div><div class="wide"><label class="filebox">上传投票凭证（可多张截图或录屏）<input type="file" name="proof" accept="image/png,image/jpeg,video/mp4,video/quicktime" multiple required></label></div><div class="wide"><button class="full">提交审核</button></div></form></section>
{% elif view=='redeem' %}<section class="panel"><div class="section-head"><h2>🎁 圣诞礼物兑换屋</h2><span class="pill">当前原料：{{available}}</span></div><p class="muted">选择心仪礼物，使用已到账原料兑换。</p><div class="rewards">{% for r in rewards %}<article class="reward"><div class="gift">🎁</div><h3>{{r.name}}</h3><p class="cost">{{r.cost}} 原料</p><p class="muted">剩余库存：{{r.stock}}</p><form action="/redeem" method="post" onsubmit="return confirm('确认兑换这份礼物吗？')">{{token()}}<input type="hidden" name="id" value="{{r.id}}"><button class="full" {% if available<r.cost or not r.stock %}disabled{% endif %}>立即兑换</button></form></article>{% else %}<p class="muted">礼物正在准备中，敬请期待。</p>{% endfor %}</div></section>
{% elif view=='board' %}<section class="panel"><h2>🏆 心愿制造师荣誉榜</h2><p class="muted">全站共享榜单，按累计审核通过票数排名。</p><table class="board"><tr><th>排名</th><th>微博ID</th><th>累计票数</th></tr>{% for b in board %}<tr><td>{% if loop.index==1 %}🥇{% elif loop.index==2 %}🥈{% elif loop.index==3 %}🥉{% else %}{{loop.index}}{% endif %}</td><td>{{b.id}}</td><td>{{b.total}}</td></tr>{% else %}<tr><td colspan="3" class="muted">暂无数据</td></tr>{% endfor %}</table></section>
{% else %}<section class="panel"><h2>📋 我的记录</h2><h3>投票提交记录</h3>{% for v in votes %}<div class="history-row"><span>{{stations[v.station-1].name}} · {{v.qty}} 票</span><span class="pill {% if v.status=='已通过' %}ok{% elif v.status=='已拒绝' %}bad{% endif %}">{{v.status}}{% if v.reason %}：{{v.reason}}{% endif %}</span></div>{% else %}<p class="muted">还没有投票提交记录。</p>{% endfor %}<h3 style="margin-top:22px">礼物兑换记录</h3>{% for o in orders %}<div class="history-row"><span>{{o.name}} · {{o.cost}} 原料</span><span class="pill">{{o.status}}</span></div>{% else %}<p class="muted">还没有兑换记录。</p>{% endfor %}</section>{% endif %}
{% endif %}
<details class="panel" id="admin-entry"><summary><b>🔐 管理员入口</b></summary>{% if session.admin %}<p>当前身份：{{session.admin}}</p><a class="btn" href="/admin">进入管理后台</a>{% else %}<form method="post">{{token()}}<input type="hidden" name="action" value="admin"><input class="input" type="password" name="password" placeholder="管理员密码" required><button>管理员登录</button></form>{% endif %}</details>
{% else %}
<section class="panel"><div class="eyebrow">ADMIN WORKSPACE</div><h2>🛠 圣诞工厂管理后台 · {{session.admin}}</h2><div class="admin-nav"><a class="btn {% if tab=='audit' %}{% else %}btn-light{% endif %}" href="/admin?tab=audit">投票审核</a>{% if session.admin=='高级审核员' %}<a class="btn btn-light" href="/admin?tab=gift">奖品管理</a><a class="btn btn-light" href="/admin?tab=settings">会场设置</a>{% endif %}<a class="btn btn-light" href="/">返回工厂</a></div><p class="muted">普通审核员负责投票凭证审核；高级审核员拥有奖品管理及会场设置权限。</p></section>
{% if tab=='settings' %}<section class="panel"><h2>会场名称与投票链接</h2>{% for s in stations %}<form class="admin-item" method="post">{{token()}}<input type="hidden" name="action" value="station"><input type="hidden" name="id" value="{{s.id}}"><label>会场名称</label><input class="input" name="name" value="{{s.name}}" required><label>投票链接</label><input class="input" name="url" type="url" value="{{s.url}}" required><button>保存会场 {{s.id}}</button></form>{% endfor %}</section>
{% elif tab=='gift' %}<section class="panel"><h2>🎁 奖品管理</h2>{% for r in rewards+[{'id':'','name':'','cost':'','stock':'','active':true}] %}<form class="admin-item" method="post">{{token()}}<input type="hidden" name="action" value="reward"><input type="hidden" name="id" value="{{r.id}}"><label>奖品名称</label><input class="input" name="name" value="{{r.name}}" placeholder="奖品名称" required><div class="form-row"><input class="input" type="number" name="cost" min="1" value="{{r.cost}}" placeholder="兑换原料数" required><input class="input" type="number" name="stock" min="0" value="{{r.stock}}" placeholder="库存" required></div><button>{{'保存修改' if r.id else '新增奖品'}}</button></form>{% if r.id %}<form method="post">{{token()}}<input type="hidden" name="action" value="hide"><input type="hidden" name="id" value="{{r.id}}"><button class="btn-light">{{'下架奖品' if r.active else '重新上架'}}</button></form>{% endif %}{% endfor %}</section>
{% else %}<section class="panel"><h2>🧾 投票凭证审核</h2>{% for v in votes %}<article class="admin-item"><div class="section-head"><div><b>#{{v.id}} · {{v.uid}}</b><p class="muted">{{stations[v.station-1].name}} · {{v.status}}</p></div><span class="pill {% if v.status=='已通过' %}ok{% elif v.status=='已拒绝' %}bad{% endif %}">{{v.status}}</span></div><div class="media">{% for m in v.media %}{% if m.startswith('video/') %}<video controls preload="none" src="/proof/{{v.id}}/{{loop.index0}}"></video>{% else %}<a href="/proof/{{v.id}}/{{loop.index0}}" target="_blank"><img loading="lazy" src="/proof/{{v.id}}/{{loop.index0}}"></a>{% endif %}{% endfor %}</div><p>用户申报票数：<b>{{v.submitted_qty or v.qty}}</b>{% if v.reason %} · 备注：{{v.reason}}{% endif %}</p>{% if v.status=='待审核' %}<form method="post">{{token()}}<input type="hidden" name="action" value="review"><input type="hidden" name="id" value="{{v.id}}"><label>审核确认有效票数</label><input class="input" name="qty" type="number" min="1" max="100000" value="{{v.qty}}" required><input class="input" name="reason" placeholder="驳回原因（驳回时必填）"><div class="form-row"><button name="status" value="已通过" class="btn-green">审核通过</button><button name="status" value="已拒绝">驳回凭证</button></div></form>{% else %}<p class="muted">最终计入票数：{{v.qty}}</p>{% endif %}</article>{% else %}<p class="muted">暂无提交凭证。</p>{% endfor %}</section><section class="panel"><h2>📦 兑换订单与发货</h2>{% for o in orders %}<div class="history-row"><span>#{{o.id}} · {{o.uid}} · {{o.name}} · {{o.cost}} 原料 · {{o.status}}</span>{% if o.status=='待发货' %}<form method="post">{{token()}}<input type="hidden" name="action" value="ship"><input type="hidden" name="id" value="{{o.id}}"><button>标记已发货</button></form>{% endif %}</div>{% else %}<p class="muted">暂无兑换订单。</p>{% endfor %}</section>{% endif %}
{% endif %}
<div class="footer"><div class="snowline">❄️ ✦ ❄️ ✦ ❄️</div><p>每一票都算数，年度最佳一起拿下</p><div>CHRISTMAS FACTORY · WINTER WISH</div></div>
</div></main></body></html>'''

