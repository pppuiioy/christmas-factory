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
 for i,n in enumerate(['星光生产线 · 粉丝团聚力场','丝带生产线 · 星拍站姐光影场','雪花生产线 · 粉丝IP元力场','铃铛生产线 · 超话大赏'],1): c.execute('INSERT INTO gift_stations VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',(i,n,'http://t.cn/AXcF9tyj' if i<4 else 'http://t.cn/AXTMhDZ8'))
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
TEMPLATE='''<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>冬日心愿·圣诞礼物工厂</title><style>*{box-sizing:border-box}body{margin:0;background:linear-gradient(145deg,#eee5ff,#faf7ff,#e6dcfa);color:#49366b;font:16px system-ui,sans-serif;min-height:100vh}main{max-width:900px;margin:auto;padding:18px}header{text-align:center;padding:38px 12px;background:linear-gradient(130deg,#50317e,#9774ce);color:white;border-radius:24px;box-shadow:0 8px 30px #7151a333}h1{font-size:clamp(24px,5vw,40px);margin:12px 0}h2{font-size:21px}section,article{background:#fff;border:1px solid #e6daf5;border-radius:18px;padding:18px;margin:16px 0;box-shadow:0 4px 18px #62428b0b}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}.grid article{margin:0}input,select,button{font:inherit;border:1px solid #d9c9ee;border-radius:10px;padding:10px;margin:5px 0;max-width:100%}input:not([type=hidden]),select{width:100%}button,.link{background:#7952b4;color:white;border:0;padding:10px 16px;border-radius:10px;cursor:pointer;display:inline-block;text-decoration:none}small{color:#76668c}.count{font-size:32px;font-weight:bold;color:#8057b9}summary{cursor:pointer}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:9px;border-bottom:1px solid #eee5f8;overflow-wrap:anywhere}.notice{background:#fff2d8;padding:12px;border-radius:12px}.snow{letter-spacing:12px;color:#f5dba1}a{color:#7952b4}form{margin:8px 0}</style><main><header><div class="snow">✦ ❄ ✦ ❄ ✦</div><h1>冬日心愿 · 圣诞礼物工厂</h1><p>积极参与投票任务，拿下年度最佳</p></header>{% macro token() %}<input type="hidden" name="csrf" value="{{session.csrf}}">{% endmacro %}{% for m in get_flashed_messages() %}<p class="notice">{{m}}</p>{% endfor %}{% if session.uid or session.admin %}<form action="/logout" method="post">{{token()}}<button>退出登录</button></form>{% endif %}
{% if mode=='home' %}{% if not u %}<section><h2>欢迎来到圣诞工厂</h2><form method="post">{{token()}}<input type="hidden" name="action" value="login"><input name="uid" placeholder="微博ID" required><input name="password" type="password" placeholder="密码" required><button>进入工厂</button></form><details><summary>首次参与？注册账号</summary><form method="post">{{token()}}<input type="hidden" name="action" value="register"><input name="uid" placeholder="微博ID" required><input name="password" type="password" pattern="[A-Za-z0-9]+" placeholder="英文大小写或数字，建议8位以上" required><input name="confirm" type="password" placeholder="确认密码" required><button>注册</button></form></details></section>{% else %}<section><h2>🎁 {{u}} 的原料仓库</h2><div class="grid"><div>累计有效票数<div class="count">{{counts|sum}}</div></div><div>可兑换原料<div class="count">{{available}}</div></div></div></section><section><h2>🏭 圣诞礼物总工厂</h2><div class="grid">{% for s in stations %}{% if loop.index==4 %}</div><h2>🏠 圣诞特别工厂</h2><div class="grid">{% endif %}<article><h3>{{['⭐','🎀','❄️','🔔'][loop.index0]}} {{s.name}}</h3><div class="count">{{counts[loop.index0]}}</div>{% if s.url %}<a class="link" href="{{s.url}}" target="_blank" rel="noopener">前往投票</a>{% else %}<small>投票链接待配置</small>{% endif %}<form action="/vote" method="post" enctype="multipart/form-data">{{token()}}<input type="hidden" name="station" value="{{s.id}}"><input name="qty" type="number" min="1" max="100000" placeholder="本次新增票数" required><p>上传投票录屏/截图（必填），必须清晰展示具体票数</p><input type="file" name="proof" accept="image/png,image/jpeg,video/mp4,video/quicktime" multiple required><button>提交原料入库</button></form></article>{% endfor %}</div></section><section><h2>🎄 圣诞礼物兑换屋</h2><div class="grid">{% for r in rewards %}<article><h3>🎁 {{r.name}}</h3><p>{{r.cost}} 原料 · 库存 {{r.stock}}</p><form action="/redeem" method="post" onsubmit="return confirm('确认兑换？')">{{token()}}<input type="hidden" name="id" value="{{r.id}}"><button {% if available<r.cost or not r.stock %}disabled style="opacity:.45"{% endif %}>兑换礼物</button></form></article>{% else %}<p>礼物正在准备中</p>{% endfor %}</div></section><section><h2>入库记录</h2>{% for v in votes %}<p>#{{v.id}} · {{stations[v.station-1].name}} · {{v.qty}}票 · {{v.status}} {{v.reason or ""}}</p>{% else %}暂无记录{% endfor %}<h2>兑换记录</h2>{% for o in orders %}<p>#{{o.id}} · {{o.name}} · {{o.cost}}原料 · {{o.status}}</p>{% else %}暂无记录{% endfor %}</section>{% endif %}<section><h2>🏆 心愿制造师荣誉榜</h2><table><tr><th>排名</th><th>微博ID</th><th>累计票数</th></tr>{% for b in board %}<tr><td>{{loop.index}}</td><td>{{b.id}}</td><td>{{b.total}}</td></tr>{% endfor %}</table></section><details><summary>管理员入口</summary>{% if session.admin %}<a href="/admin">进入后台</a>{% else %}<form method="post">{{token()}}<input type="hidden" name="action" value="admin"><input type="password" name="password" placeholder="管理员密码" required><button>进入后台</button></form>{% endif %}</details>
{% else %}<section><h2>工厂管理后台 · {{session.admin}}</h2><a class="link" href="/admin?tab=audit">审核中心</a> {% if session.admin=="高级审核员" %}<a class="link" href="/admin?tab=gift">奖品管理</a> <a class="link" href="/admin?tab=settings">活动设置</a>{% endif %}</section>{% if tab=="settings" %}<section><h3>投票入口配置</h3>{% for s in stations %}<form method="post">{{token()}}<input type="hidden" name="action" value="station"><input type="hidden" name="id" value="{{s.id}}"><input name="name" value="{{s.name}}" required><input name="url" type="url" value="{{s.url}}" placeholder="投票链接"><button>保存入口 {{s.id}}</button></form>{% endfor %}</section>{% elif tab=="audit" %}<section><h2>投票审核</h2>{% for v in votes %}<article><p>#{{v.id}} · {{v.uid}} · {{stations[v.station-1].name}} · {{v.status}}</p>{% for m in v.media %}{% if m.startswith("video/") %}<video controls preload="none" style="width:100%;max-height:320px" src="/proof/{{v.id}}/{{loop.index0}}"></video>{% else %}<a href="/proof/{{v.id}}/{{loop.index0}}" target="_blank"><img loading="lazy" style="max-width:100%;max-height:220px" src="/proof/{{v.id}}/{{loop.index0}}"></a>{% endif %}{% endfor %}<p>申报票数：{{v.submitted_qty or v.qty}} · {{v.reason or ""}}</p>{% if v.status=='待审核' %}<form method="post">{{token()}}<input type="hidden" name="action" value="review"><input type="hidden" name="id" value="{{v.id}}"><input name="qty" type="number" min="1" value="{{v.qty}}" required><input name="reason" placeholder="驳回原因（驳回必填）"><button name="status" value="已通过">通过</button> <button name="status" value="已拒绝">拒绝</button></form>{% else %} · {{v.qty}}票{% endif %}</article>{% endfor %}</section>{% elif tab=="gift" %}<section><h2>奖品管理</h2>{% for r in rewards+[{'id':'','name':'','cost':'','stock':''}] %}<form method="post">{{token()}}<input type="hidden" name="action" value="reward"><input type="hidden" name="id" value="{{r.id}}"><input name="name" value="{{r.name}}" placeholder="奖品名称" required><input type="number" name="cost" min="1" value="{{r.cost}}" placeholder="兑换原料数" required><input type="number" name="stock" min="0" value="{{r.stock}}" placeholder="库存" required><button>{{'保存' if r.id else '新增奖品'}}</button></form>{% if r.id %}<form method="post">{{token()}}<input type="hidden" name="action" value="hide"><input type="hidden" name="id" value="{{r.id}}"><button>{{'下架' if r.active else '上架'}}</button></form>{% endif %}{% endfor %}</section>{% endif %}{% if tab=="audit" %}<section><h2>兑换及发货</h2>{% for o in orders %}<p>#{{o.id}} · {{o.uid}} · {{o.name}} · {{o.status}}</p>{% if o.status=='待发货' %}<form method="post">{{token()}}<input type="hidden" name="action" value="ship"><input type="hidden" name="id" value="{{o.id}}"><button>标记已发货</button></form>{% endif %}{% endfor %}</section>{% endif %}{% endif %}<p style="text-align:center;color:#8873a6">❄ 每一票都算数，年度最佳一起拿下 ❄</p></main></html>'''
