import streamlit as st
import anthropic
import pdfplumber
import csv
import io
import os
import json
import sqlite3
import uuid
from datetime import datetime

st.set_page_config(page_title="LifeQuant", page_icon="⚡", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background: #080B12; color: #F1F5F9; }
[data-testid="stSidebar"] { background: #080B12 !important; border-right: 1px solid #1E293B; }
.lq-logo { font-size: 1.4rem; font-weight: 700; letter-spacing: -0.5px;
           background: linear-gradient(90deg, #2563EB, #8B5CF6, #14B8A6);
           -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.score-row { display: flex; gap: 6px; margin: 8px 0; }
.score-card { flex: 1; background: #0F1623; border-radius: 8px; padding: 8px 6px;
              text-align: center; border: 1px solid #1E293B; }
.score-label { font-size: 0.58rem; color: #475569; text-transform: uppercase; letter-spacing: 0.08em; }
.score-num { font-size: 1.2rem; font-weight: 700; margin-top: 1px; }
.sf { color: #3B82F6; } .sft { color: #10B981; } .sc { color: #8B5CF6; } .so { color: #F59E0B; }
.profile-compact { background: #0F1623; border-radius: 8px; padding: 8px 10px;
                   border: 1px solid #1E293B; margin: 6px 0; }
.pc-row { display: flex; justify-content: space-between; padding: 2px 0;
          font-size: 0.72rem; border-bottom: 1px solid #0d1420; }
.pc-row:last-child { border-bottom: none; }
.pc-k { color: #475569; } .pc-v { color: #CBD5E1; font-weight: 500; }
.brutal-pill { background: #450a0a; color: #fca5a5; border: 1px solid #7f1d1d;
               font-size: 0.6rem; font-weight: 700; padding: 2px 7px;
               border-radius: 999px; text-transform: uppercase; }
.welcome-card { background: #0F1623; border: 1px solid #1E293B; border-radius: 14px;
                padding: 28px; text-align: center; margin: 16px 0; }
.stButton > button { background: #0F1623 !important; border: 1px solid #1E293B !important;
                     color: #94A3B8 !important; border-radius: 8px !important;
                     font-size: 0.78rem !important; padding: 4px 8px !important; }
.stButton > button:hover { background: #1E293B !important; color: #E2E8F0 !important; }
.stChatMessage { scroll-margin-top: 0; }
div[data-testid="stChatMessageContent"] p { font-size: 0.88rem; line-height: 1.7; }
div[data-testid="stChatMessageContent"] h3 { font-size: 0.9rem !important; font-weight: 600; margin: 4px 0 2px; }
div[data-testid="stChatMessageContent"] h2 { font-size: 0.95rem !important; font-weight: 700; margin: 6px 0 2px; }
div[data-testid="stChatMessageContent"] h1 { font-size: 1rem !important; font-weight: 700; margin: 6px 0 2px; }
div[data-testid="stChatMessageContent"] table { font-size: 0.82rem; width: 100%; }
div[data-testid="stChatMessageContent"] th { background: #0F1623; color: #94A3B8; font-size: 0.75rem; }
div[data-testid="stChatMessageContent"] td { padding: 4px 8px; border-bottom: 1px solid #1E293B; }
</style>
""", unsafe_allow_html=True)

DB_PATH = "lifequant.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS sessions (
        sid TEXT PRIMARY KEY, doc_context TEXT,
        profile_json TEXT, scores_json TEXT,
        messages_json TEXT, brutal INTEGER DEFAULT 0,
        suggestions_json TEXT, updated_at TEXT)""")
    try:
        conn.execute("ALTER TABLE sessions ADD COLUMN suggestions_json TEXT")
    except: pass
    conn.commit(); conn.close()

def load_session(sid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM sessions WHERE sid=?", (sid,))
    row = c.fetchone(); conn.close()
    if not row: return None
    return {
        "doc_context":  row[1] or "",
        "profile":      json.loads(row[2]) if row[2] else {},
        "scores":       json.loads(row[3]) if row[3] else {},
        "messages":     json.loads(row[4]) if row[4] else [],
        "brutal":       bool(row[5]),
        "suggestions":  json.loads(row[6]) if row[6] else [],
    }

def save_session(sid, data):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""INSERT OR REPLACE INTO sessions
        (sid,doc_context,profile_json,scores_json,messages_json,brutal,suggestions_json,updated_at)
        VALUES (?,?,?,?,?,?,?,?)""", (
        sid,
        data.get("doc_context",""),
        json.dumps(data.get("profile",{})),
        json.dumps(data.get("scores",{})),
        json.dumps(data.get("messages",[])),
        int(data.get("brutal",False)),
        json.dumps(data.get("suggestions",[])),
        datetime.now().isoformat()
    ))
    conn.commit(); conn.close()

init_db()

if "session_id" not in st.session_state:
    params = st.query_params
    sid = params.get("sid", str(uuid.uuid4())[:8])
    st.session_state.session_id = sid
    st.query_params["sid"] = sid

SID = st.session_state.session_id

if "loaded" not in st.session_state:
    saved = load_session(SID)
    if saved:
        st.session_state.update(saved)
    else:
        st.session_state.doc_context  = ""
        st.session_state.profile      = {}
        st.session_state.scores       = {}
        st.session_state.messages     = []
        st.session_state.brutal       = False
        st.session_state.suggestions  = []
    st.session_state.loaded        = True
    st.session_state.profile_shown = False

api_key = os.environ.get("ANTHROPIC_API_KEY","")
if not api_key:
    with st.sidebar:
        st.markdown("### API Key")
        api_key = st.text_input("Key", type="password", placeholder="sk-ant-...", label_visibility="collapsed")
if not api_key:
    st.markdown('<div class="welcome-card"><div style="font-size:2.5rem">⚡</div><div style="font-size:1.2rem;font-weight:700;color:#E2E8F0;margin:10px 0 6px">Welcome to LifeQuant</div><div style="font-size:0.85rem;color:#475569">Add your API key in the sidebar to begin</div></div>', unsafe_allow_html=True)
    st.stop()

client = anthropic.Anthropic(api_key=api_key)

def extract_text(f):
    name = f.name.lower()
    if name.endswith(".pdf"):
        with pdfplumber.open(f) as pdf:
            return "\n\n".join(p.extract_text() or "" for p in pdf.pages)
    elif name.endswith(".csv"):
        content = f.read().decode("utf-8")
        return "\n".join(", ".join(r) for r in csv.reader(io.StringIO(content)))
    else:
        return f.read().decode("utf-8", errors="ignore")

def chunk_text(text, max_chars=12000):
    if len(text) <= max_chars: return text
    half = max_chars // 2
    return text[:half] + "\n\n[truncated]\n\n" + text[-half:]

EXTRACT_SYS = """Extract all data. Return ONLY valid JSON no markdown:
{"finance":{"income_monthly":null,"expenses_monthly":null,"savings_rate_pct":null,"debt_monthly":null,"subscriptions":[],"top_expenses":[],"currency":"INR"},
"fitness":{"weight":null,"weight_unit":"kg","bench_1rm":null,"squat_1rm":null,"deadlift_1rm":null,"training_days_per_week":null,"goal":null},
"career":{"current_role":null,"experience_years":null,"company":null,"current_ctc":null,"target_role":null,"target_ctc":null,"key_gap":null},
"scores":{"finance":null,"fitness":null,"career":null,"overall":null},
"name":null,"summary":"one sentence max 20 words"}
Scores 1-10: how optimized each area is. overall=average of non-null scores."""

def run_extraction(text):
    try:
        r = client.messages.create(
            model="claude-haiku-4-5", max_tokens=1000, system=EXTRACT_SYS,
            messages=[{"role":"user","content":f"Extract:\n\n{text[:8000]}"}])
        raw = r.content[0].text.strip().replace("```json","").replace("```","").strip()
        return json.loads(raw)
    except: return {}

def get_adaptive_suggestions(messages, scores, profile):
    if not messages: return []
    try:
        last = messages[-4:] if len(messages) >= 4 else messages
        conv = "\n".join([f"{m['role']}: {m['content'][:200]}" for m in last])
        weakest = "finance"
        if scores:
            valid = {k:v for k,v in scores.items() if v and k != "overall"}
            if valid: weakest = min(valid.items(), key=lambda x: x[1])[0]
        r = client.messages.create(
            model="claude-haiku-4-5", max_tokens=150,
            messages=[{"role":"user","content":f"Suggest 4 short follow-up button labels based on:\nConversation: {conv}\nWeakest: {weakest} ({scores.get(weakest,'?')}/10)\nReturn ONLY JSON array of 4 strings max 5 words each."}])
        raw = r.content[0].text.strip().replace("```json","").replace("```","").strip()
        sugs = json.loads(raw)
        return sugs[:4] if isinstance(sugs,list) else []
    except:
        return ["💰 Fix finances","💪 Training plan","🎯 Career roadmap","📈 5-year view"]

def build_system(profile, brutal):
    tone = "BRUTAL MODE ON — Zero softening. Every number exposed. Make them feel exact cost of inaction." if brutal else ""
    profile_str = f"\n\nUSER PROFILE (always use these real numbers):\n{json.dumps(profile,indent=2)}" if profile else ""
    scores = profile.get("scores",{})
    score_str = f"\nScores: Finance:{scores.get('finance','?')}/10 Fitness:{scores.get('fitness','?')}/10 Career:{scores.get('career','?')}/10" if any(v for v in scores.values() if v) else ""
    return f"""You are LifeQuant — sharp quantitative life coach: finance, fitness, career.
Personality: Direct, data-driven. Brilliant friend = quant analyst + personal trainer + career coach.
Never say simply or obviously. Always use specific numbers, timelines, probabilities.
BEHAVIOR:
- Casual (hi/hello) → warm 2-line reply, score summary, ask what to tackle. NO full analysis.
- Specific question → answer only that with real numbers.
- "full analysis" → complete 3-module breakdown.
OUTPUT FORMAT:
- Lead every insight with NUMBER: "₹9,924/mo → food delivery (11.7% of income)"
- Use ### for headers (small)
- Use markdown tables for comparisons
- Use bullet points for action lists
- Progress bars using emojis:
  Weight: 🟧🟧🟧🟧🟧🟧🟧⬜⬜⬜ 89.5kg → 82kg
  Use 🟩=good 🟧=progress 🟥=critical ⬜=remaining. Show current → target.
- End EVERY response with:
### ⚡ 3 Actions This Week
| Action | Timeline | Impact |
|--------|----------|--------|
| [action] | [X days] | [outcome with number] |
| [action] | [X days] | [outcome with number] |
| [action] | [X days] | [outcome with number] |
- Then: ⚠️ GAP: [urgent thing + exact consequence]
Never repeat full profile after first message.
{tone}{profile_str}{score_str}"""

def render_profile_compact(p):
    fin=p.get("finance",{}); fit=p.get("fitness",{}); car=p.get("career",{})
    cur=fin.get("currency","₹")
    rows=[]
    if p.get("name"):               rows.append(("Name",p["name"]))
    if fin.get("income_monthly"):   rows.append(("Income",f"{cur}{int(fin['income_monthly']):,}/mo"))
    if fin.get("expenses_monthly"): rows.append(("Expenses",f"{cur}{int(fin['expenses_monthly']):,}/mo"))
    if fin.get("savings_rate_pct"): rows.append(("Savings",f"{fin['savings_rate_pct']}%"))
    if fin.get("debt_monthly"):     rows.append(("Debt/mo",f"{cur}{int(fin['debt_monthly']):,}"))
    if fit.get("weight"):           rows.append(("Weight",f"{fit['weight']}{fit.get('weight_unit','kg')}"))
    if fit.get("bench_1rm"):        rows.append(("Bench",f"{fit['bench_1rm']}kg"))
    if car.get("current_role"):     rows.append(("Role",str(car["current_role"])[:22]))
    if car.get("target_role"):      rows.append(("Target",str(car["target_role"])[:22]))
    if not rows: return
    html='<div class="profile-compact">'
    for k,v in rows:
        html+=f'<div class="pc-row"><span class="pc-k">{k}</span><span class="pc-v">{v}</span></div>'
    html+="</div>"
    st.markdown(html,unsafe_allow_html=True)

def render_scores(scores):
    if not any(v for v in scores.values() if v): return
    f=scores.get("finance","—"); ft=scores.get("fitness","—"); c=scores.get("career","—"); o=scores.get("overall","—")
    st.markdown(f'''<div class="score-row">
<div class="score-card"><div class="score-label">Finance</div><div class="score-num sf">{f}/10</div></div>
<div class="score-card"><div class="score-label">Fitness</div><div class="score-num sft">{ft}/10</div></div>
<div class="score-card"><div class="score-label">Career</div><div class="score-num sc">{c}/10</div></div>
<div class="score-card"><div class="score-label">Overall</div><div class="score-num so">{o}/10</div></div>
</div>''', unsafe_allow_html=True)

def status(s):
    try:
        n=int(str(s))
        return "🔴 Critical" if n<=4 else "🟡 Needs work" if n<=6 else "🟢 Good"
    except: return "⚪ Unknown"

with st.sidebar:
    st.markdown('<div class="lq-logo">⚡ LifeQuant</div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size:0.68rem;color:#334155;margin-bottom:12px">Quantitative life optimization</div>', unsafe_allow_html=True)
    color="#10B981" if st.session_state.messages else "#334155"
    badge="● Session saved" if st.session_state.messages else "● New session"
    st.markdown(f'<div style="font-size:0.68rem;color:{color};margin-bottom:10px">{badge}</div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size:0.78rem;font-weight:600;color:#94A3B8;margin-bottom:4px">📎 Upload Documents</div>', unsafe_allow_html=True)
    st.caption("Bank statements, workout logs, career notes — all at once")
    uploaded = st.file_uploader("Upload files", type=["pdf","csv","txt"], accept_multiple_files=True, label_visibility="collapsed")
    st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)
    brutal = st.toggle("💀 Brutal honesty mode", value=st.session_state.brutal)
    if brutal != st.session_state.brutal:
        st.session_state.brutal = brutal
        save_session(SID, st.session_state)
    if uploaded:
        if st.button("⚡ Analyze All Files", use_container_width=True):
            with st.spinner("Reading files + extracting profile..."):
                combined=""; raw_all=""
                for f in uploaded:
                    txt=extract_text(f)
                    combined+=f"\n\n[FILE: {f.name}]\n{chunk_text(txt,4000)}"
                    raw_all+=txt
                extracted=run_extraction(raw_all[:10000])
                st.session_state.doc_context=combined.strip()
                st.session_state.profile=extracted
                st.session_state.scores=extracted.get("scores",{})
                st.session_state.profile_shown=False
                scores=extracted.get("scores",{})
                name=extracted.get("name","") or ""
                gname=f" {name}," if name else ","
                fin_s=scores.get("finance","?"); fit_s=scores.get("fitness","?")
                car_s=scores.get("career","?"); over_s=scores.get("overall","?")
                auto=f"""Hey{gname} I've read all your files. Here's where you stand:

**Overall Score: {over_s}/10**

| Area | Score | Status |
|------|-------|--------|
| 💰 Finance | {fin_s}/10 | {status(fin_s)} |
| 💪 Fitness | {fit_s}/10 | {status(fit_s)} |
| 🎯 Career  | {car_s}/10 | {status(car_s)} |

{extracted.get("summary","I have a clear picture of your situation.")}

What do you want to tackle first?"""
                st.session_state.messages=[{"role":"assistant","content":auto}]
                st.session_state.suggestions=["💰 Fix my finances","💪 Build training plan","🎯 Career roadmap","🔍 Full analysis"]
                save_session(SID,st.session_state)
            st.success(f"✓ {len(uploaded)} file(s) analyzed!")
            st.rerun()
    if st.session_state.profile:
        st.markdown('<div style="height:4px"></div>', unsafe_allow_html=True)
        render_profile_compact(st.session_state.profile)
    st.markdown("---")
    if st.button("🗑️ Clear Everything", use_container_width=True):
        st.session_state.doc_context=""; st.session_state.profile={}
        st.session_state.scores={}; st.session_state.messages=[]
        st.session_state.brutal=False; st.session_state.suggestions=[]
        st.session_state.profile_shown=False
        save_session(SID,{"doc_context":"","profile":{},"scores":{},"messages":[],"brutal":False,"suggestions":[]})
        st.rerun()

brutal_pill='<span class="brutal-pill">💀 Brutal</span>' if st.session_state.brutal else ""
has_docs=bool(st.session_state.doc_context)
doc_label=f'<span style="font-size:0.68rem;color:#334155;margin-left:auto">📎 {len(st.session_state.doc_context)//1000}k chars</span>' if has_docs else ""
st.markdown(f'''<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;padding-bottom:8px;border-bottom:1px solid #1E293B">
<span style="font-size:1.05rem;font-weight:700;color:#E2E8F0">LifeQuant</span>{brutal_pill}{doc_label}</div>''',unsafe_allow_html=True)

if st.session_state.scores:
    render_scores(st.session_state.scores)

if not st.session_state.messages:
    st.markdown('''<div class="welcome-card">
<div style="font-size:2.2rem;margin-bottom:10px">⚡</div>
<div style="font-size:1.1rem;font-weight:700;color:#E2E8F0;margin-bottom:6px">Your Quantitative Life Coach</div>
<div style="font-size:0.82rem;color:#475569;line-height:1.7;margin-bottom:16px">Upload your documents on the left — or just start chatting</div>
<div style="display:flex;gap:8px;justify-content:center;flex-wrap:wrap">
<span style="background:#0a1223;border:1px solid #1E293B;border-radius:20px;padding:5px 12px;font-size:0.75rem;color:#3B82F6">💰 Finance</span>
<span style="background:#071a10;border:1px solid #1E293B;border-radius:20px;padding:5px 12px;font-size:0.75rem;color:#10B981">💪 Fitness</span>
<span style="background:#100a1f;border:1px solid #1E293B;border-radius:20px;padding:5px 12px;font-size:0.75rem;color:#8B5CF6">🎯 Career</span>
</div></div>''',unsafe_allow_html=True)

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if st.session_state.messages and st.session_state.suggestions:
    cols=st.columns(len(st.session_state.suggestions))
    for i,s in enumerate(st.session_state.suggestions):
        with cols[i]:
            if st.button(s,use_container_width=True,key=f"s{i}{s[:6]}"):
                st.session_state._quick=s

quick=getattr(st.session_state,"_quick",None)
if quick:
    del st.session_state._quick
    user_input=quick
else:
    hint="Ask anything... (💀 brutal)" if st.session_state.brutal else "Ask LifeQuant anything..."
    user_input=st.chat_input(hint)

if user_input:
    content=user_input
    if st.session_state.doc_context:
        content=f"USER DOCUMENTS:\n{st.session_state.doc_context}\n\nUSER MESSAGE: {user_input}"
    st.session_state.messages.append({"role":"user","content":user_input})
    with st.chat_message("user"):
        st.markdown(user_input)
    api_msgs=[]
    for i,m in enumerate(st.session_state.messages):
        if i==len(st.session_state.messages)-1 and m["role"]=="user":
            api_msgs.append({"role":"user","content":content})
        else:
            api_msgs.append({"role":m["role"],"content":m["content"]})
    with st.chat_message("assistant"):
        ph=st.empty(); full=""
        with client.messages.stream(
            model="claude-sonnet-4-6", max_tokens=4000,
            system=build_system(st.session_state.profile,st.session_state.brutal),
            messages=api_msgs,
        ) as stream:
            for text in stream.text_stream:
                full+=text
                ph.markdown(full+"▌")
        ph.markdown(full)
    st.session_state.messages.append({"role":"assistant","content":full})
    new_sugs=get_adaptive_suggestions(st.session_state.messages,st.session_state.scores,st.session_state.profile)
    st.session_state.suggestions=new_sugs if new_sugs else st.session_state.suggestions
    save_session(SID,st.session_state)
    st.rerun()
