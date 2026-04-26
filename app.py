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

st.set_page_config(page_title="LifeQuant", page_icon="⚡", layout="centered", initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background: #080B12; color: #F1F5F9; }
section[data-testid="stSidebar"] { display: none; }
.block-container { max-width: 780px !important; padding: 0 1rem !important; }
a[href*="github.com"] { display: none !important; }
[data-testid="stToolbar"] { display: none !important; }
#MainMenu { display: none !important; }
header { display: none !important; }

/* Top bar */
.topbar { display: flex; align-items: center; justify-content: space-between;
          padding: 14px 0 10px; border-bottom: 1px solid #1E293B; margin-bottom: 16px; }
.lq-logo { font-size: 1.3rem; font-weight: 700; letter-spacing: -0.5px;
           background: linear-gradient(90deg, #2563EB, #8B5CF6, #14B8A6);
           -webkit-background-clip: text; -webkit-text-fill-color: transparent; }

/* Score cards */
.score-row { display: flex; gap: 8px; margin: 12px 0; }
.score-card { flex: 1; background: #0F1623; border-radius: 10px; padding: 10px 8px;
              text-align: center; border: 1px solid #1E293B; }
.score-label { font-size: 0.58rem; color: #475569; text-transform: uppercase; letter-spacing: 0.08em; }
.score-num { font-size: 1.3rem; font-weight: 700; margin-top: 2px; }
.sf { color: #3B82F6; } .sft { color: #10B981; } .sc { color: #8B5CF6; } .so { color: #F59E0B; }

/* Welcome */
.welcome-wrap { text-align: center; padding: 40px 20px 20px; }
.welcome-icon { font-size: 3rem; margin-bottom: 12px; }
.welcome-title { font-size: 1.5rem; font-weight: 700; color: #E2E8F0; margin-bottom: 8px; }
.welcome-sub { font-size: 0.88rem; color: #475569; line-height: 1.7; margin-bottom: 24px; }

/* Onboarding questions */
.question-card { background: #0F1623; border: 1px solid #1E293B; border-radius: 12px;
                 padding: 20px; margin: 8px 0; }
.question-num { font-size: 0.68rem; color: #475569; text-transform: uppercase;
                letter-spacing: 0.08em; margin-bottom: 6px; }
.question-text { font-size: 0.95rem; font-weight: 500; color: #E2E8F0; margin-bottom: 12px; }

/* Pills */
.pill-row { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
.pill { background: #111827; border: 1px solid #1E293B; border-radius: 999px;
        padding: 4px 12px; font-size: 0.75rem; color: #94A3B8; cursor: pointer; }

/* Brutal pill */
.brutal-pill { background: #450a0a; color: #fca5a5; border: 1px solid #7f1d1d;
               font-size: 0.6rem; font-weight: 700; padding: 2px 7px;
               border-radius: 999px; text-transform: uppercase; }

/* Chat */
.stChatMessage { scroll-margin-top: 0; }
div[data-testid="stChatMessageContent"] p { font-size: 0.88rem; line-height: 1.75; }
div[data-testid="stChatMessageContent"] h3 { font-size: 0.9rem !important; font-weight: 600; margin: 6px 0 3px; }
div[data-testid="stChatMessageContent"] h2 { font-size: 0.95rem !important; font-weight: 700; margin: 8px 0 3px; }
div[data-testid="stChatMessageContent"] table { font-size: 0.82rem; width: 100%; }
div[data-testid="stChatMessageContent"] th { background: #0F1623; color: #94A3B8; font-size: 0.75rem; }
div[data-testid="stChatMessageContent"] td { padding: 5px 8px; border-bottom: 1px solid #1E293B; }

/* Buttons */
.stButton > button { background: #0F1623 !important; border: 1px solid #1E293B !important;
                     color: #94A3B8 !important; border-radius: 8px !important;
                     font-size: 0.78rem !important; }
.stButton > button:hover { background: #1E293B !important; color: #E2E8F0 !important; }

/* Progress */
.prog-bar { background: #1E293B; border-radius: 999px; height: 6px; margin: 4px 0 8px; }
.prog-fill-green { background: #10B981; height: 6px; border-radius: 999px; }
.prog-fill-amber { background: #F59E0B; height: 6px; border-radius: 999px; }
.prog-fill-red { background: #EF4444; height: 6px; border-radius: 999px; }

/* File chip */
.file-chip { display: inline-flex; align-items: center; gap: 6px; background: #0F1623;
             border: 1px solid #1E293B; border-radius: 8px; padding: 4px 10px;
             font-size: 0.75rem; color: #94A3B8; margin: 2px; }
</style>
""", unsafe_allow_html=True)

# ── DB ────────────────────────────────────────────────────────────────────────
DB_PATH = "lifequant.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS sessions (
        sid TEXT PRIMARY KEY, doc_context TEXT, user_context TEXT,
        profile_json TEXT, scores_json TEXT, messages_json TEXT,
        brutal INTEGER DEFAULT 0, onboarded INTEGER DEFAULT 0,
        suggestions_json TEXT, updated_at TEXT)""")
    for col in ["user_context","onboarded","suggestions_json"]:
        try: conn.execute(f"ALTER TABLE sessions ADD COLUMN {col} TEXT")
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
        "user_context": row[2] or "",
        "profile":      json.loads(row[3]) if row[3] else {},
        "scores":       json.loads(row[4]) if row[4] else {},
        "messages":     json.loads(row[5]) if row[5] else [],
        "brutal":       bool(row[6]),
        "onboarded":    bool(row[7]) if len(row) > 7 else False,
        "suggestions":  json.loads(row[8]) if len(row) > 8 and row[8] else [],
        "personalized_questions": [],
    }

def save_session(sid, data):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""INSERT OR REPLACE INTO sessions
        (sid,doc_context,user_context,profile_json,scores_json,messages_json,brutal,onboarded,suggestions_json,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)""", (
        sid,
        data.get("doc_context",""),
        data.get("user_context",""),
        json.dumps(data.get("profile",{})),
        json.dumps(data.get("scores",{})),
        json.dumps(data.get("messages",[])),
        int(data.get("brutal",False)),
        int(data.get("onboarded",False)),
        json.dumps(data.get("suggestions",[])),
        datetime.now().isoformat()
    ))
    conn.commit(); conn.close()

init_db()

# ── Session ───────────────────────────────────────────────────────────────────
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
        st.session_state.user_context = ""
        st.session_state.profile      = {}
        st.session_state.scores       = {}
        st.session_state.messages     = []
        st.session_state.brutal       = False
        st.session_state.onboarded    = False
        st.session_state.suggestions  = []
        st.session_state.personalized_questions = []
    st.session_state.loaded        = True
    st.session_state.onboard_step  = 0
    st.session_state.onboard_answers = {}

# ── API key ───────────────────────────────────────────────────────────────────
api_key = os.environ.get("ANTHROPIC_API_KEY","")
if not api_key:
    st.markdown('<div class="topbar"><div class="lq-logo">⚡ LifeQuant</div></div>', unsafe_allow_html=True)
    api_key = st.text_input("API Key", type="password", placeholder="Enter your Anthropic API key (sk-ant-...)")
    st.caption("Get yours at [console.anthropic.com](https://console.anthropic.com)")
    st.stop()

client = anthropic.Anthropic(api_key=api_key)

# ── Helpers ───────────────────────────────────────────────────────────────────
def clean_output(text: str) -> str:
    import re
    # Fix X/month X/mo X/year patterns
    text = re.sub(r'\$([\d,]+)/month', r'$\1 per month', text)
    text = re.sub(r'\$([\d,]+)/mo\b', r'$\1 per month', text)
    text = re.sub(r'\$([\d,]+)/year', r'$\1 per year', text)
    text = re.sub(r'\$([\d,]+)/yr\b', r'$\1 per year', text)
    # Fix number/month without dollar sign
    text = re.sub(r'([\d,]+)/month', r'\1 per month', text)
    text = re.sub(r'([\d,]+)/mo\b', r'\1 per month', text)
    # Fix asterisk * used as multiply or bullet outside of markdown
    text = re.sub(r'(?<!\*)\*(?!\*)(\w)', r' \1', text)
    text = re.sub(r'(\w)\*(?!\*)(?!\s*\*)', r'\1 ', text)
    return text

def extract_text(f) -> str:
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
{"finance":{"income_monthly":null,"expenses_monthly":null,"savings_rate_pct":null,"debt_monthly":null,"subscriptions":[],"top_expenses":[],"currency":"USD"},
"fitness":{"weight":null,"weight_unit":"kg","bench_1rm":null,"squat_1rm":null,"deadlift_1rm":null,"training_days_per_week":null,"goal":null},
"career":{"current_role":null,"experience_years":null,"company":null,"current_ctc":null,"target_role":null,"target_ctc":null,"key_gap":null},
"scores":{"finance":null,"fitness":null,"career":null,"overall":null},
"name":null,"summary":"one sentence max 20 words"}
Scores 1-10 how optimized each area is. overall=average."""

def run_extraction(text: str) -> dict:
    try:
        r = client.messages.create(
            model="claude-haiku-4-5", max_tokens=1000, system=EXTRACT_SYS,
            messages=[{"role":"user","content":f"Extract:\n\n{text[:8000]}"}])
        raw = r.content[0].text.strip().replace("```json","").replace("```","").strip()
        return json.loads(raw)
    except: return {}

def generate_personalized_questions(doc_context: str, profile: dict) -> list:
    """Use Claude to generate 10 personalized questions based on uploaded documents."""
    try:
        fin = profile.get("finance", {})
        fit = profile.get("fitness", {})
        car = profile.get("career", {})
        
        prompt = f"""You are analyzing someone's personal documents. Based on the data below, generate exactly 10 highly personalized questions to better understand this person.

DOCUMENT CONTEXT:
{doc_context[:6000]}

EXTRACTED PROFILE:
{json.dumps(profile, indent=2)}

Generate 10 questions that:
1. Are SPECIFIC to their actual data (mention their real numbers, companies, situations)
2. Fill gaps in what we know about them
3. Help LifeQuant give better advice
4. Mix single-select and multi-select questions
5. Cover finance, fitness, career, and habits/lifestyle

Return ONLY a valid JSON array — no markdown, no explanation:
[
  {{
    "emoji": "💰",
    "key": "unique_key",
    "question": "Specific personalized question mentioning their real data",
    "options": ["Option 1", "Option 2", "Option 3", "Option 4", "Option 5"],
    "multi": true
  }}
]

Rules:
- options array: 4-6 specific relevant options (not generic)
- multi: true if multiple can apply, false if only one answer
- key: short snake_case unique identifier
- Always include at least 2 finance, 2 fitness, 2 career questions
- Make questions feel like a smart advisor who READ their documents
- First question should ALWAYS be about age (pure text, empty options array, multi: false)"""

        r = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=6000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = r.content[0].text.strip().replace("```json","").replace("```","").strip()
        questions = json.loads(raw)
        
        # Convert to our tuple format: (emoji, key, question, options, multi)
        result = []
        for q in questions[:10]:
            result.append((
                q.get("emoji", "❓"),
                q.get("key", f"q_{len(result)}"),
                q.get("question", ""),
                q.get("options", []),
                q.get("multi", True)
            ))
        return result
    except Exception as e:
        # Fallback to basic questions if generation fails
        return [
            ("👤", "age", "How old are you?", [], False),
            ("💰", "income", "What is your monthly income?", ["Under $3k", "$3k-$6k", "$6k-$10k", "$10k-$15k", "$15k+"], False),
            ("😈", "bad_habits", "What are your worst daily habits?", ["Phone 3+ hrs", "Poor sleep", "Junk food", "Skipping workouts", "Overspending"], True),
        ]

def get_adaptive_suggestions(messages, scores, profile) -> list:
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
            messages=[{"role":"user","content":"Suggest 4 specific follow-ups to: " + (messages[-1]["content"][:400] if messages else "") + "\nReturn ONLY JSON array of 4 strings max 6 words each."}])
        raw = r.content[0].text.strip().replace("```json","").replace("```","").strip()
        sugs = json.loads(raw)
        return sugs[:4] if isinstance(sugs,list) else []
    except:
        return ["💰 Fix finances","💪 Training plan","🎯 Career roadmap","📈 5-year simulation"]

def status(s):
    try:
        n = int(str(s))
        return "🔴 Critical" if n<=4 else "🟡 Needs work" if n<=6 else "🟢 Good"
    except: return "⚪ Unknown"

def render_scores(scores: dict):
    if not any(v for v in scores.values() if v): return
    f=scores.get("finance","—"); ft=scores.get("fitness","—")
    c=scores.get("career","—"); o=scores.get("overall","—")
    st.markdown(f"""<div class="score-row">
<div class="score-card"><div class="score-label">Finance</div><div class="score-num sf">{f}/10</div></div>
<div class="score-card"><div class="score-label">Fitness</div><div class="score-num sft">{ft}/10</div></div>
<div class="score-card"><div class="score-label">Career</div><div class="score-num sc">{c}/10</div></div>
<div class="score-card"><div class="score-label">Overall</div><div class="score-num so">{o}/10</div></div>
</div>""", unsafe_allow_html=True)

# ── System prompt ─────────────────────────────────────────────────────────────
def build_system(profile: dict, user_context: str, brutal: bool) -> str:
    tone = "BRUTAL MODE ON — Zero softening. Every number exposed. Make them feel exact cost of inaction." if brutal else ""
    profile_str = f"\n\nUSER PROFILE:\n{json.dumps(profile,indent=2)}" if profile else ""
    ctx_str = f"\n\nUSER CONTEXT (habits, goals, lifestyle from onboarding):\n{user_context}" if user_context else ""
    scores = profile.get("scores",{})
    score_str = f"\nScores: Finance:{scores.get('finance','?')}/10 Fitness:{scores.get('fitness','?')}/10 Career:{scores.get('career','?')}/10" if any(v for v in scores.values() if v) else ""

    return f"""You are LifeQuant — the most powerful personal optimization engine ever built. You are part quant analyst, part elite performance coach, part brutally honest best friend who happens to have access to all your financial, fitness and career data.

CORE IDENTITY:
You don't give advice. You reveal truth. You show people the EXACT cost of their habits in dollars, days and years. You name the villains. You make the gap between where they are and where they could be impossible to ignore.

EMOTIONAL LANGUAGE RULES:
- Never say "you should consider" — say "this is costing you" or "this must change"
- Always translate money into time: "You spent $4,614 on DoorDash — that is 184 hours of work for food you could make in 20 minutes"
- Always show consequence of inaction: "At this rate in 5 years you will have exactly this much saved: nothing"
- Name the villain: "DoorDash, Adobe, Netflix — these companies are systematically extracting wealth from you"
- Use the mirror test: "The number on your scale will be identical in 12 months if nothing changes today"
- Show the gap in days: "You are 1,247 days from financial independence. Every $100 wasted adds 11 days to that number"
- Make it personal: use their real name, their real numbers, their real company from the profile

FORMATTING RULES — CRITICAL:
- NEVER write X/month or X/mo or X/year — always write X per month
- NEVER use asterisk * around words — only use ** for bold headers
- NEVER write math fractions inline in text
- Write all currency as $X,XXX not $X/anything

Never say simply or obviously. Always use specific numbers, timelines, probabilities.

BEHAVIOR:
- Casual (hi/hello) → warm 2-line reply, score summary, ask what to tackle. NO full analysis.
- Specific question → answer only that with real profile numbers.
- "full analysis" → complete 3-module breakdown.
- "5 year simulation" or "what if" or "trajectory" or "5 year" → generate full What-If simulator:

### 📊 5-Year What-If Simulator

**Based on your real data vs LifeQuant optimized plan**

| Metric | Today | Current Path (5yr) | LifeQuant Path (5yr) | Δ Difference |
|--------|-------|-------------------|---------------------|-------------|
| 💰 Monthly savings | ₹X | ₹X | ₹X | +₹X |
| 💰 Net worth | ₹X | ₹X | ₹X | +₹X |
| 💰 Total debt | ₹X | ₹X | ₹0 | Debt free |
| 💰 Investments | ₹X | ₹X | ₹X | +₹X |
| 💪 Weight | Xkg | Xkg | Xkg | -Xkg |
| 💪 Bench press | Xkg | Xkg | Xkg | +Xkg |
| 💪 Training days/wk | X | X | X | +X |
| 🎯 Role | X | X | X | Promoted |
| 🎯 Salary | ₹X LPA | ₹X LPA | ₹X LPA | +₹X LPA |
| 🎯 Net worth impact | - | - | +₹X | Career uplift |

### 🔴 If You Change Nothing
2 paragraphs. Where they end up in 5 years doing exactly what they're doing now. Real numbers. Make it uncomfortable but true.

### 🟢 The LifeQuant Path
2 paragraphs. Where they end up following all recommendations. Inspiring with specific numbers and milestones.

### ⚙️ Key Assumptions
- Bullet points of exact changes made in optimized path with numbers
- e.g. "Cancelled ₹6,830/mo dead subscriptions → SIP at 12% CAGR"
- e.g. "4x/week training → 8kg fat loss in 9 months"
- e.g. "LinkedIn active + system design prep → EM role in 14 months"

OUTPUT FORMAT always:
- Lead every insight with NUMBER: "₹9,924/mo → food delivery (11.7% of income)"
- Use ### for headers ONLY — never # or ##. Keep headers small.
- In GAP line write plain text only no markdown bold
- Tables for comparisons
- Bullets for lists
- Emoji progress bars: Weight: 🟧🟧🟧🟧🟧🟧🟧⬜⬜⬜ 89.5kg → 82kg (🟩=good 🟧=progress 🟥=critical ⬜=remaining)
- End EVERY response with:
### ⚡ 3 Actions This Week
| Action | Timeline | Impact |
|--------|----------|--------|
| [specific action] | [X days] | [outcome with number] |
| [specific action] | [X days] | [outcome with number] |
| [specific action] | [X days] | [outcome with number] |
- Then: ⚠️ GAP: [most urgent thing + exact consequence]

Never repeat full profile after first message.
{tone}{profile_str}{ctx_str}{score_str}"""

# ── Smart adaptive questions ──────────────────────────────────────────────────

CORE_QUESTIONS = [
    ("👤", "age", "How old are you?", [], False),
    ("📍", "location", "Which city are you based in?",
     ["New York", "Los Angeles", "Chicago", "Houston", "London", "Toronto", "Sydney", "Remote"], False),
]

FINANCE_QUESTIONS = [
    ("💰", "income", "What is your monthly income?",
     ["Under ₹30k", "₹30k-₹60k", "₹60k-₹1L", "₹1L-₹2L", "₹2L+"], False),
    ("💸", "expenses", "Where does most of your money go?",
     ["Rent/EMI", "Food & dining", "Subscriptions", "Shopping", "Debt payments"], True),
    ("🏦", "debt", "What debts do you currently have?",
     ["Home loan", "Car loan", "Personal loan", "Credit card", "No debt"], True),
    ("📈", "investment", "What is your current investment situation?",
     ["No investments", "Just started SIP", "Stocks/MF", "FD only", "Real estate"], True),
]

FITNESS_QUESTIONS = [
    ("💪", "fitness_goal", "What are your fitness goals?",
     ["Lose weight", "Build muscle", "Get consistent", "Run 5km", "Better sleep", "Reduce stress"], True),
    ("🏋", "fitness_block", "What is blocking your fitness progress?",
     ["No time", "No motivation", "Work stress", "Injury", "Poor diet", "Inconsistency"], True),
]

CAREER_QUESTIONS = [
    ("🎯", "career_goal", "What is your career target in 2 years?",
     ["Get promoted", "Switch companies", "Start business", "Increase salary 50%+", "Change field", "MBA"], True),
    ("😤", "career_block", "What is holding your career back?",
     ["No visibility", "Skill gaps", "Wrong company", "No network", "Low confidence", "Underpaid"], True),
]

CLOSING_QUESTIONS = [
    ("😈", "bad_habits", "What are your worst daily habits?",
     ["Phone 3+ hrs/day", "Poor sleep <6hrs", "Junk food", "Skipping workouts", "Procrastination", "Overspending"], True),
    ("🏆", "success", "What does success look like in 12 months?",
     ["Financial freedom", "Dream body", "Dream job", "All of the above", "Debt free", "Business launched"], True),
]

def build_adaptive_questions(profile: dict) -> list:
    questions = list(CORE_QUESTIONS)
    fin = profile.get("finance", {})
    fit = profile.get("fitness", {})
    car = profile.get("career", {})
    has_finance = bool(fin.get("income_monthly") or fin.get("expenses_monthly"))
    if not has_finance:
        questions.extend(FINANCE_QUESTIONS)
    else:
        questions.append(("🏦", "debt_focus", "Which debt do you want to clear first?",
                          ["Home loan", "Car loan", "Personal loan", "Credit card", "No debt"], True))
    has_fitness = bool(fit.get("weight") or fit.get("bench_1rm") or fit.get("training_days_per_week"))
    if not has_fitness:
        questions.extend(FITNESS_QUESTIONS)
    else:
        questions.append(("🏋", "fitness_block", "What is blocking your fitness progress?",
                          ["No time", "No motivation", "Work stress", "Injury", "Poor diet", "Inconsistency"], True))
    has_career = bool(car.get("current_role") or car.get("target_role"))
    if not has_career:
        questions.extend(CAREER_QUESTIONS)
    else:
        questions.append(("😤", "career_block", "What is holding your career back?",
                          ["No visibility", "Skill gaps", "Wrong company", "No network", "Underpaid"], True))
    questions.extend(CLOSING_QUESTIONS)
    return questions[:10]



# ── TOP BAR ───────────────────────────────────────────────────────────────────
brutal_pill = '<span class="brutal-pill">🧠 Deep</span>' if st.session_state.brutal else ""
st.markdown(f'<div style="display:flex;align-items:center;gap:8px;padding:10px 0;border-bottom:1px solid #1E293B;margin-bottom:8px"><div class="lq-logo">⚡ LifeQuant</div>{brutal_pill}</div>', unsafe_allow_html=True)
st.markdown('<div style="border-top:1px solid #1E293B;margin-bottom:16px"></div>', unsafe_allow_html=True)

# ── SCORES ────────────────────────────────────────────────────────────────────
if st.session_state.scores:
    render_scores(st.session_state.scores)

# ══════════════════════════════════════════════════════════════════════════════
# ONBOARDING FLOW
# ══════════════════════════════════════════════════════════════════════════════
if not st.session_state.onboarded:
    step = st.session_state.get("onboard_step", 0)

    # Step 0 — Welcome + file upload
    if step == 0:
        st.markdown("""<div class="welcome-wrap">
<div class="welcome-icon">⚡</div>
<div class="welcome-title">Meet LifeQuant</div>
<div class="welcome-sub">Your quantitative life coach — finance, fitness, career.<br>
Upload your documents and answer a few questions.<br>I'll build your complete optimization plan.</div>
</div>""", unsafe_allow_html=True)

        uploaded = st.file_uploader(
            "Upload your documents (optional)",
            type=["pdf","csv","txt"],
            accept_multiple_files=True,
            help="Bank statements, workout logs, career notes — any combination"
        )

        context_text = st.text_area(
            "Or describe your situation in your own words",
            placeholder="e.g. I earn ₹85k/month but always run out of money. I go to gym 2x a week but not consistent. I've been a senior engineer for 2 years and want to move into management...",
            height=100
        )

        c1, c2 = st.columns(2)
        with c1:
            skip = st.button("Skip → Just chat", use_container_width=True)
        with c2:
            proceed = st.button("Continue →", use_container_width=True, type="primary")

        if proceed or skip:
            if uploaded:
                with st.spinner("Reading your documents..."):
                    combined = ""; raw_all = ""
                    for f in uploaded:
                        txt = extract_text(f)
                        combined += f"\n\n[FILE: {f.name}]\n{chunk_text(txt,4000)}"
                        raw_all += txt
                    extracted = run_extraction(raw_all[:10000])
                    st.session_state.doc_context = combined.strip()
                    st.session_state.profile     = extracted
                    st.session_state.scores      = extracted.get("scores",{})

            if context_text.strip():
                st.session_state.user_context = context_text.strip()

            if skip:
                st.session_state.onboarded = True
                st.session_state.onboard_step = 0
                save_session(SID, st.session_state)
                st.rerun()
            else:
                st.session_state.onboard_step = 1
                st.rerun()

    # Steps 1-10 — Adaptive questions with multi-select
    elif 1 <= step <= 10:
        # Generate personalized questions if not already generated
        if "personalized_questions" not in st.session_state or not st.session_state.personalized_questions:
            with st.spinner("Generating your personalized questions..."):
                st.session_state.personalized_questions = generate_personalized_questions(
                    st.session_state.doc_context,
                    st.session_state.profile
                )
        QUESTIONS = st.session_state.personalized_questions
        if step > len(QUESTIONS):
            st.session_state.onboard_step = 11
            st.rerun()

        q_idx = step - 1
        emoji, q_key, question, options, multi = QUESTIONS[q_idx]

        st.markdown(f'<div style="font-size:0.72rem;color:#475569;margin-bottom:16px">Question {step} of {len(QUESTIONS)}</div>', unsafe_allow_html=True)
        pct = int((step / len(QUESTIONS)) * 100)
        st.markdown(f'<div class="prog-bar"><div class="prog-fill-green" style="width:{pct}%"></div></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="question-card"><div class="question-num">Question {step} of {len(QUESTIONS)}</div><div class="question-text">{emoji} {question}</div></div>', unsafe_allow_html=True)

        # Initialize selected tags in session state
        tag_key = f"tags_{step}"
        if tag_key not in st.session_state:
            st.session_state[tag_key] = []

        if len(options) == 0:
            # Pure text input (age)
            answer = st.text_input("Type your answer", placeholder="e.g. 28", key=f"q_{step}", label_visibility="collapsed")
            selected = []
        else:
            # Pill tag selection
            if multi:
                st.markdown('<div style="font-size:0.75rem;color:#94A3B8;margin:10px 0 8px">Select all that apply — click to toggle:</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div style="font-size:0.75rem;color:#94A3B8;margin:10px 0 8px">Select one or more:</div>', unsafe_allow_html=True)

            # Render pill buttons in rows of 3
            options_per_row = 3
            for row_start in range(0, len(options), options_per_row):
                row_opts = options[row_start:row_start+options_per_row]
                cols = st.columns(len(row_opts))
                for i, opt in enumerate(row_opts):
                    with cols[i]:
                        is_selected = opt in st.session_state[tag_key]
                        btn_style = "primary" if is_selected else "secondary"
                        if st.button(
                            f"✓ {opt}" if is_selected else opt,
                            key=f"tag_{step}_{row_start+i}",
                            use_container_width=True,
                            type=btn_style
                        ):
                            if is_selected:
                                st.session_state[tag_key].remove(opt)
                            else:
                                st.session_state[tag_key].append(opt)
                            st.rerun()

            selected = st.session_state[tag_key]
            answer = st.text_input("Or add your own", placeholder="Type here...", key=f"q_{step}", label_visibility="collapsed")

        c1, c2 = st.columns(2)
        with c1:
            if step > 1:
                if st.button("← Back", use_container_width=True):
                    st.session_state.onboard_step = step - 1
                    st.rerun()
        with c2:
            if st.button("Next →", use_container_width=True):
                val = answer.strip() if answer.strip() else (", ".join(selected) if selected else "")
                if val:
                    st.session_state.onboard_answers[q_key] = val
                # Clear tag state for this step
                if f"tags_{step}" in st.session_state:
                    del st.session_state[f"tags_{step}"]
                st.session_state.onboard_step = step + 1
                st.rerun()

    # Step 11+ — Done
    elif step > 10:
        # Build user context from answers
        answers = st.session_state.get("onboard_answers", {})
        context_lines = [f"- {q}: {a}" for q, a in answers.items()]
        existing = st.session_state.user_context or ""
        st.session_state.user_context = existing + "\n\nOnboarding answers:\n" + "\n".join(context_lines)

        # Generate welcome analysis
        profile = st.session_state.profile
        scores = st.session_state.scores
        name = profile.get("name","") or ""
        gname = f" {name}," if name else ","
        fin_s = scores.get("finance","?"); fit_s = scores.get("fitness","?")
        car_s = scores.get("career","?"); over_s = scores.get("overall","?")

        answers_summary = "\n".join([f"• {q}: {a}" for q, a in answers.items()])

        auto = f"""Hey{gname} I've got everything I need. Here's your snapshot:

**Overall Score: {over_s}/10**

| Area | Score | Status |
|------|-------|--------|
| 💰 Finance | {fin_s}/10 | {status(fin_s)} |
| 💪 Fitness | {fit_s}/10 | {status(fit_s)} |
| 🎯 Career  | {car_s}/10 | {status(car_s)} |

{profile.get("summary","") or ""}

**What you told me:**
{answers_summary}

I now have a complete picture of your situation — documents + your real context. What do you want to tackle first?"""

        st.session_state.messages = [{"role":"assistant","content":auto}]
        st.session_state.suggestions = ["💰 Fix my finances","💪 Build training plan","🎯 Career roadmap","📊 5-year simulation"]
        st.session_state.onboarded = True
        st.session_state.onboard_step = 0
        save_session(SID, st.session_state)
        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# MAIN CHAT
# ══════════════════════════════════════════════════════════════════════════════
else:
    # Chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Adaptive suggestions
    if st.session_state.messages and st.session_state.suggestions:
        cols = st.columns(len(st.session_state.suggestions))
        for i, s in enumerate(st.session_state.suggestions):
            with cols[i]:
                if st.button(s, use_container_width=True, key=f"sug{i}{s[:5]}"):
                    st.session_state._quick = s

    # Controls row — Full Profile Analysis | Deep Thinking | Restart
    col_h1, col_h2, col_h3 = st.columns([2,2,1])
    with col_h1:
        if st.button("🧠 Full Profile Analysis", use_container_width=True, key="deep_profile"):
            st.session_state._quick = "Run a complete deep profile analysis across all 3 modules — finance, fitness and career. Use every data point from my documents and answers. Be extremely specific with numbers, timelines and action plans."
    with col_h2:
        brutal = st.toggle("🧠 Deep Thinking", value=st.session_state.brutal, key="brutal_bottom", help="Deep Thinking — maximum detail, raw numbers")
        if brutal != st.session_state.brutal:
            st.session_state.brutal = brutal
            save_session(SID, st.session_state)
    with col_h3:
        if st.button("↺ Restart", key="home_bottom", help="Clear everything and start over", use_container_width=True):
            for k in ["doc_context","user_context","profile","scores","messages","brutal","onboarded","suggestions"]:
                st.session_state[k] = {} if k in ["profile","scores"] else [] if k in ["messages","suggestions"] else False if k in ["brutal","onboarded"] else ""
            st.session_state.onboard_step = 0
            st.session_state.onboard_answers = {}
            st.session_state.personalized_questions = []
            save_session(SID, {"doc_context":"","user_context":"","profile":{},"scores":{},"messages":[],"brutal":False,"onboarded":False,"suggestions":[]})
            st.rerun()

    # File upload + chat input area
    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)

    # File uploader (compact, above chat)
    with st.expander("📎 Add more documents", expanded=False):
        new_files = st.file_uploader("Upload", type=["pdf","csv","txt"],
                                      accept_multiple_files=True, label_visibility="collapsed")
        extra_context = st.text_area("Add more context", placeholder="Any additional info about your situation...",
                                      height=80, label_visibility="collapsed")
        if st.button("⚡ Add to my profile", use_container_width=True):
            if new_files:
                with st.spinner("Processing..."):
                    for f in new_files:
                        txt = extract_text(f)
                        st.session_state.doc_context += f"\n\n[FILE: {f.name}]\n{chunk_text(txt,3000)}"
                    new_extracted = run_extraction(st.session_state.doc_context[:10000])
                    if new_extracted.get("scores"):
                        st.session_state.profile = new_extracted
                        st.session_state.scores = new_extracted.get("scores",{})
            if extra_context.strip():
                st.session_state.user_context += f"\n\nAdditional context: {extra_context.strip()}"
            save_session(SID, st.session_state)
            st.success("✓ Profile updated!")
            st.rerun()

    # Chat input
    quick = getattr(st.session_state, "_quick", None)
    if quick:
        del st.session_state._quick
        user_input = quick
    else:
        hint = "Ask anything... (🔬 Deep Analysis on)" if st.session_state.brutal else "Ask LifeQuant anything..."
        user_input = st.chat_input(hint)

    if user_input:
        content = user_input
        if st.session_state.doc_context:
            content = f"USER DOCUMENTS:\n{st.session_state.doc_context}\n\nUSER CONTEXT:\n{st.session_state.user_context}\n\nUSER MESSAGE: {user_input}"
        elif st.session_state.user_context:
            content = f"USER CONTEXT:\n{st.session_state.user_context}\n\nUSER MESSAGE: {user_input}"

        st.session_state.messages.append({"role":"user","content":user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        api_msgs = []
        for i, m in enumerate(st.session_state.messages):
            if i == len(st.session_state.messages)-1 and m["role"]=="user":
                api_msgs.append({"role":"user","content":content})
            else:
                api_msgs.append({"role":m["role"],"content":m["content"]})

        with st.chat_message("assistant"):
            ph = st.empty(); full = ""
            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=6000,
                system=build_system(st.session_state.profile, st.session_state.user_context, st.session_state.brutal),
                messages=api_msgs,
            ) as stream:
                for text in stream.text_stream:
                    full += text
                    ph.markdown(clean_output(full) + "▌")
            ph.markdown(clean_output(full))

        st.session_state.messages.append({"role":"assistant","content":full})
        new_sugs = get_adaptive_suggestions(st.session_state.messages, st.session_state.scores, st.session_state.profile)
        st.session_state.suggestions = new_sugs if new_sugs else st.session_state.suggestions
        save_session(SID, st.session_state)
        st.rerun()
