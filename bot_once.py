# GitHub Actions uchun: har ishga tushganda bir marta tekshiradi va tugaydi.
# Maxfiy qiymatlar (Secrets): BOT_TOKEN, OWNER_CHAT_ID, FIREBASE_KEY (serviceAccount.json ichidagi matn)
import os, json, time, datetime, requests, firebase_admin
from firebase_admin import credentials, firestore
TOKEN = os.environ['BOT_TOKEN']; OWNER = int(os.environ.get('OWNER_CHAT_ID') or 0)
firebase_admin.initialize_app(credentials.Certificate(json.loads(os.environ['FIREBASE_KEY'])))
db = firestore.client(); API = f'https://api.telegram.org/bot{TOKEN}/'
TZ = datetime.timezone(datetime.timedelta(hours=5))
P, S = 'products', 'sales'  # faqat asosiy do'kon
MN = ['Yanvar', 'Fevral', 'Mart', 'Aprel', 'May', 'Iyun', 'Iyul', 'Avgust', 'Sentabr', 'Oktabr', 'Noyabr', 'Dekabr']
def send(text, chat=None):
    requests.post(API + 'sendMessage', json={'chat_id': chat or OWNER, 'text': text, 'parse_mode': 'HTML'}, timeout=20)
def prods(): return [x.to_dict() for x in db.collection(P).stream()]
def sales_since(ms): return [x.to_dict() for x in db.collection(S).where('t', '>=', ms).stream()]
def totals(s):
    return (sum(x['total'] for x in s), sum(i['q'] * (i['sell'] - i['buy']) for x in s for i in x['items']), sum(i['q'] for x in s for i in x['items']))
def kam(low):
    if not low: return "✅ Kam qolgan tovar yo'q"
    return "⚠️ <b>Kam qolgan tovarlar:</b>\n" + "\n".join(f"{'❌' if p['qty'] == 0 else '🔸'} {p['name']} — {p['qty']} ta (min {p['min']})" for p in sorted(low, key=lambda p: p['qty']))
def day_start(n): return n.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000
def bugun(n):
    s = sales_since(day_start(n)); rev, pr, _ = totals(s); by = {}
    for x in s: by[x.get('by', '-')] = by.get(x.get('by', '-'), 0) + x['total']
    return f"📊 <b>Bugun</b>\nSavdo: {rev:,.0f} so'm\nFoyda: {pr:,.0f} so'm\nSotuvlar: {len(s)}\n" + "\n".join(f"• {k}: {v:,.0f}" for k, v in by.items())
def oylik(n):
    s = sales_since(day_start(n.replace(day=1))); rev, pr, dona = totals(s)
    return (f"🗓 <b>{MN[n.month - 1]} oyi yakuni</b>\nSavdo: {rev:,.0f} so'm\nFoyda: {pr:,.0f} so'm\n"
            f"Sotuvlar: {len(s)}\nSotilgan dona: {dona}\nKunlik o'rtacha savdo: {rev / n.day:,.0f} so'm")
def backup(n):
    data = {'shops': [{'id': 'asosiy', 'name': "Asosiy do'kon"}],
            'data': {'asosiy': {'products': prods(), 'sales': [x.to_dict() for x in db.collection(S).stream()]}},
            'users': db.collection('meta').document('users').get().to_dict() or {}}
    requests.post(API + 'sendDocument', data={'chat_id': OWNER, 'caption': '💾 Kunlik zaxira nusxa'},
                  files={'document': (f"zaxira-{n.date()}.json", json.dumps(data, ensure_ascii=False).encode())}, timeout=120)

ref = db.collection('meta').document('botstate'); st = ref.get().to_dict() or {}
first = 'last_t' not in st
n = datetime.datetime.now(TZ); now_ms = time.time() * 1000
# 1) Buyruqlar (/kam /bugun /zaxira) — javob 10-15 daqiqagacha kechikishi mumkin
r = requests.get(API + 'getUpdates', params={'offset': st.get('offset', 0), 'timeout': 0}, timeout=30).json()
for u in r.get('result', []):
    st['offset'] = u['update_id'] + 1; m = u.get('message', {}); cid = m.get('chat', {}).get('id'); t = m.get('text', '')
    if cid != OWNER: send(f'Sizning chat ID: {cid}', cid); continue
    if t.startswith('/kam'): send(kam([p for p in prods() if p['qty'] <= p['min']]))
    elif t.startswith('/bugun'): send(bugun(n))
    elif t.startswith('/zaxira'): backup(n)
    else: send('/kam — kam qolgan tovarlar\n/bugun — bugungi savdo\n/zaxira — zaxira nusxa')
# 2) Yangi sotuvlar
last_t = st.get('last_t', now_ms); new = []
if not first:
    new = sorted([x.to_dict() for x in db.collection(S).where('t', '>', last_t).stream()], key=lambda x: x['t'])
for x in new:
    send(f"🛒 {x.get('by', '-')}: " + ", ".join(f"{i['name']} ×{i['q']}" for i in x['items']) + f" — {x['total']:,.0f} so'm"); last_t = max(last_t, x['t'])
st['last_t'] = now_ms if first else last_t
# 3) Rejali xabarlar (har biri kuniga bir marta)
done = st.get('done', []); jobs = []
def job(tag, cond, fn):
    k = f"{n.date()}-{tag}"
    if OWNER and cond and k not in done: done.append(k); jobs.append(fn)
last_day = (n + datetime.timedelta(days=1)).month != n.month
job('kam', 9 <= n.hour <= 11, 'kam'); job('bugun', n.hour in (21, 22), 'bugun')
job('oy', last_day and n.hour in (22, 23), 'oy'); job('zaxira', n.hour == 23, 'zaxira')
# 4) Kam qolgan tovar ogohlantirishi (faqat sotuv bo'lganda yoki rejali vaqtda tekshiriladi)
if new or first or 'kam' in jobs:
    low = [p for p in prods() if p['qty'] <= p['min']]; alerted = set(st.get('alerted', []))
    if not first:
        for p in low:
            if str(p['id']) not in alerted:
                send(f"{'❌ Tugadi' if p['qty'] == 0 else '⚠️ Kam qoldi'}: {p['name']} — {p['qty']} ta (min {p['min']})")
    st['alerted'] = sorted(str(p['id']) for p in low)
    if 'kam' in jobs: send(kam(low))
if 'bugun' in jobs: send(bugun(n))
if 'oy' in jobs: send(oylik(n))
if 'zaxira' in jobs: backup(n)
st['done'] = done[-20:]; ref.set(st)
