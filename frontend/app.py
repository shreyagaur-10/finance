"""
Streamlit frontend for the Multi-Agent Financial AI Planner.
Provides a complete, demoable interface.
"""
import streamlit as st
import requests
import json
from datetime import datetime

# ─── Config ────────────────────────────────────────────────────────────────────
API_BASE = "http://localhost:8000"
st.set_page_config(
    page_title="Financial AI Planner",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Session State ─────────────────────────────────────────────────────────────
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "user_profile" not in st.session_state:
    st.session_state.user_profile = {}


def api_post(endpoint: str, data: dict) -> dict:
    try:
        r = requests.post(f"{API_BASE}{endpoint}", json=data, timeout=120)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.HTTPError as e:
        st.error(f"API Error: {e.response.status_code} - {e.response.text}")
        return {}
    except Exception as e:
        st.error(f"Connection error: {e}")
        return {}


def api_get(endpoint: str) -> dict:
    try:
        r = requests.get(f"{API_BASE}{endpoint}", timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Error: {e}")
        return {}


# ─── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("💰 Financial AI Planner")
    st.caption("Multi-Agent System • Powered by Llama 3.3 70B")
    st.divider()

    tab = st.radio("Navigation", ["💬 Chat", "👤 Profile", "🎯 Goals", "📊 System Status"])

# ─── Profile Setup ──────────────────────────────────────────────────────────────
if tab == "👤 Profile":
    st.header("👤 User Profile")

    col1, col2 = st.columns(2)
    with col1:
        email = st.text_input("Email", placeholder="you@example.com")
        name = st.text_input("Name", placeholder="John Doe")
    with col2:
        risk_profile = st.selectbox("Risk Profile", ["conservative", "moderate", "aggressive"])
        monthly_income = st.number_input("Monthly Income ($)", min_value=0.0, value=5000.0, step=100.0)

    if st.button("Create / Login", type="primary"):
        if email:
            result = api_post("/users", {
                "email": email, "name": name,
                "risk_profile": risk_profile, "monthly_income": monthly_income,
            })
            if result.get("user"):
                user = result["user"]
                st.session_state.user_id = user["id"]
                st.session_state.user_profile = user

                session = api_post("/sessions", {"user_id": user["id"]})
                if session.get("session"):
                    st.session_state.session_id = session["session"]["id"]
                    st.success(f"✅ Welcome, {name or email}! Session started.")
                    st.json(user)
        else:
            st.warning("Please enter an email.")

    if st.session_state.user_id:
        st.info(f"✅ Logged in | User: `{st.session_state.user_id[:8]}...` | Session: `{st.session_state.session_id[:8]}...`")

# ─── Goals ──────────────────────────────────────────────────────────────────────
elif tab == "🎯 Goals":
    st.header("🎯 Financial Goals")

    if not st.session_state.user_id:
        st.warning("Please set up your profile first.")
    else:
        # Show existing goals
        goals_data = api_get(f"/goals/{st.session_state.user_id}")
        goals = goals_data.get("goals", [])

        if goals:
            st.subheader("Your Active Goals")
            for g in goals:
                progress = (g["current_amount"] / g["target_amount"] * 100) if g["target_amount"] > 0 else 0
                with st.expander(f"{g['name']} — {progress:.1f}% complete"):
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Target", f"${g['target_amount']:,.0f}")
                    col2.metric("Current", f"${g['current_amount']:,.0f}")
                    col3.metric("Progress", f"{progress:.1f}%")
                    st.progress(min(progress / 100, 1.0))
                    st.caption(f"Category: {g['category']} | Priority: {g['priority']} | Status: {g['status']}")

                    new_amount = st.number_input(
                        "Update current amount ($)",
                        key=f"update_{g['id']}",
                        value=float(g["current_amount"]),
                    )
                    if st.button("Update Progress", key=f"btn_{g['id']}"):
                        res = requests.patch(f"{API_BASE}/goals/{g['id']}", json={"current_amount": new_amount})
                        if res.status_code == 200:
                            st.success("Updated!")
                            st.rerun()
        else:
            st.info("No active goals yet. Create one below!")

        st.divider()
        st.subheader("Add New Goal")
        col1, col2 = st.columns(2)
        with col1:
            goal_name = st.text_input("Goal Name", placeholder="Emergency Fund")
            target_amount = st.number_input("Target Amount ($)", min_value=0.0, value=10000.0)
            category = st.selectbox("Category", [
                "retirement", "emergency_fund", "home_purchase",
                "education", "vacation", "investment", "debt_payoff", "other"
            ])
        with col2:
            description = st.text_area("Description", placeholder="6 months of expenses")
            target_date = st.date_input("Target Date")
            priority = st.slider("Priority", 1, 5, 3)

        if st.button("➕ Add Goal", type="primary"):
            if goal_name and target_amount > 0:
                result = api_post("/goals", {
                    "user_id": st.session_state.user_id,
                    "name": goal_name,
                    "target_amount": target_amount,
                    "category": category,
                    "description": description,
                    "target_date": str(target_date),
                    "priority": priority,
                })
                if result.get("goal"):
                    st.success(f"✅ Goal '{goal_name}' created!")
                    st.rerun()

# ─── System Status ──────────────────────────────────────────────────────────────
elif tab == "📊 System Status":
    st.header("📊 System Status")

    health = api_get("/health")
    queue = api_get("/queue/status")

    col1, col2, col3 = st.columns(3)
    col1.metric("API Status", health.get("status", "unknown").upper())
    col2.metric("Queue Depth", queue.get("queue_depth", 0))
    col3.metric("Timestamp", health.get("timestamp", "")[:19])

    st.subheader("🏗️ Architecture")
    st.markdown("""
    | Component | Technology | Role |
    |-----------|-----------|------|
    | **Orchestration** | LangGraph StateGraph | Multi-agent coordination |
    | **Primary LLM** | Groq Llama 3.3 70B | Fast inference |
    | **Fallback LLM** | Google Gemini Flash | Redundancy |
    | **Database** | Supabase Postgres | State & history |
    | **Task Queue** | Upstash Redis | Async tasks |
    | **Observability** | Langfuse | Tracing & scoring |
    | **Guardrails** | Custom (regex + LLM) | Input/output safety |
    | **Backend** | FastAPI | REST API |
    | **Frontend** | Streamlit | This UI |
    """)

    st.subheader("🤖 Agents")
    agents = {
        "Coordinator": "Routes requests and synthesizes responses",
        "Budget Agent": "Analyzes income/expenses and cash flow",
        "Investment Agent": "Designs portfolio allocations",
        "Risk Agent": "Evaluates financial risk exposure",
        "Goal Agent": "Tracks goals persisted in Postgres",
        "Judge Agent": "Scores every response (accuracy/relevance/safety)",
    }
    for agent, desc in agents.items():
        st.markdown(f"**{agent}** — {desc}")

# ─── Chat ───────────────────────────────────────────────────────────────────────
else:  # Chat tab
    st.header("💬 Financial AI Planner Chat")

    if not st.session_state.user_id:
        st.warning("⚠️ Please go to **👤 Profile** tab first to set up your account.")
        st.stop()

    # Display conversation history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("metadata"):
                with st.expander("📊 Agent Details", expanded=False):
                    meta = msg["metadata"]
                    if meta.get("agents_invoked"):
                        st.write(f"**Agents invoked:** {', '.join(meta['agents_invoked'])}")
                    if meta.get("judge_scores"):
                        scores = meta["judge_scores"]
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("Accuracy", f"{scores.get('accuracy', 0):.1f}/5")
                        c2.metric("Relevance", f"{scores.get('relevance', 0):.1f}/5")
                        c3.metric("Safety", f"{scores.get('safety', 0):.1f}/5")
                        c4.metric("Overall", f"{scores.get('overall', 0):.1f}/5")
                    if meta.get("latency_ms"):
                        st.caption(f"⚡ Latency: {meta['latency_ms']:.0f}ms")
                    if meta.get("guard_flags"):
                        st.warning(f"Guard flags: {meta['guard_flags']}")

    # Chat input
    if prompt := st.chat_input("Ask about your budget, investments, goals, or risk..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("🤖 Multi-agent pipeline running..."):
                result = api_post("/chat", {
                    "user_id": st.session_state.user_id,
                    "session_id": st.session_state.session_id,
                    "message": prompt,
                    "user_profile": st.session_state.user_profile,
                })

            if result:
                response = result.get("response", "No response generated.")
                st.markdown(response)

                metadata = {
                    "agents_invoked": result.get("agents_invoked", []),
                    "judge_scores": result.get("judge_scores"),
                    "latency_ms": result.get("latency_ms"),
                    "guard_flags": result.get("guard_flags", []),
                }

                with st.expander("📊 Agent Details", expanded=False):
                    if metadata.get("agents_invoked"):
                        st.write(f"**Agents invoked:** {', '.join(metadata['agents_invoked'])}")
                    if metadata.get("judge_scores"):
                        scores = metadata["judge_scores"]
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("Accuracy", f"{scores.get('accuracy', 0):.1f}/5")
                        c2.metric("Relevance", f"{scores.get('relevance', 0):.1f}/5")
                        c3.metric("Safety", f"{scores.get('safety', 0):.1f}/5")
                        c4.metric("Overall", f"{scores.get('overall', 0):.1f}/5")
                    if metadata.get("latency_ms"):
                        st.caption(f"⚡ Latency: {metadata['latency_ms']:.0f}ms")

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response,
                    "metadata": metadata,
                })
            else:
                st.error("Failed to get a response. Check the API is running.")
