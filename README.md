# 💰 Multi-Agent Financial AI Planner

A **production-grade multi-agent financial planning system** built entirely on free-tier and open-source tools. Every AWS service from the original architecture has been replaced with a free, working equivalent that is fully wired into the codebase.

---

## 🏗️ Architecture Overview

```
User Request
     │
     ▼
[FastAPI Backend]
     │
     ├─ Input Guardrails (prompt injection, PII, rate limit)
     │
     ▼
[LangGraph StateGraph] ─── Coordinator/Router Agent
     │                           │
     │              ┌────────────┼────────────┐
     │              ▼            ▼            ▼            ▼
     │         Budget         Investment    Risk         Goal
     │         Agent          Agent         Agent        Agent
     │              └────────────┴────────────┴────────────┘
     │                           │
     │              Coordinator Synthesizer Agent
     │                           │
     │                     Judge Agent (LLM-as-a-Judge)
     │
     ├─ Output Guardrails (false guarantees, system prompt leak)
     │
     ▼
[Streamlit Frontend]          [Postgres]       [Langfuse]
                           (state, history,  (traces, scores,
                            goals, scores)    token usage)
```

---

## 🔄 AWS → Free-Tier Substitution Map

| AWS Service | Free Equivalent | Why It's Better |
|-------------|----------------|-----------------|
| **Amazon Bedrock AgentCore** | **LangGraph** (open-source) | Full graph-based agent orchestration with explicit state, no vendor lock-in |
| **AWS Lambda / Step Functions** | **LangGraph StateGraph nodes** | Each agent is a typed async Python node; state passed explicitly |
| **Amazon Aurora Serverless** | **Supabase Postgres** (free 500MB) | Same Postgres SQL, full relational schema, asyncpg driver |
| **AWS SQS** | **Upstash Redis** (free 10K cmds/day) | HTTP-based Redis list used as FIFO queue; works from any environment |
| **Amazon CloudWatch** | **Langfuse** (free cloud or self-hosted) | Agent-native tracing: traces, generations, scores, token counts, latency |
| **AWS Cognito** | **Supabase Auth** (built-in, free) | Email/OAuth via Supabase's built-in auth system |
| **Amazon Bedrock Claude** | **Groq Llama 3.3 70B** (primary) + **Gemini Flash** (fallback) | Groq's free tier is faster than Bedrock; Gemini adds redundancy |

---

## 🤖 Agent Roster

### 1. Coordinator/Router Agent (`backend/agents/coordinator.py`)
- **Role**: Entry point for all requests. Decides which specialist agents to invoke based on the user question, then synthesizes their outputs into one coherent response.
- **LangGraph nodes**: `coordinator_router_node` → routing; `coordinator_synthesizer_node` → merging
- **State written**: `active_agents`, `coordinator_response`

### 2. Budget Analysis Agent (`backend/agents/budget_agent.py`)
- **Role**: Analyzes income vs expenses, applies 50/30/20 rule, identifies savings opportunities, calculates emergency fund targets.
- **State written**: `budget_analysis` (structured JSON with breakdown, net cash flow, recommendations)

### 3. Investment Planning Agent (`backend/agents/investment_agent.py`)
- **Role**: Designs portfolio allocations (index funds/ETFs), factors in risk profile and horizon, recommends tax-advantaged accounts.
- **State written**: `investment_plan` (allocations, recommended funds, return range)

### 4. Risk Assessment Agent (`backend/agents/risk_agent.py`)
- **Role**: Scores overall financial risk (1-10), flags debt-to-income ratio, emergency fund gaps, insurance gaps, and concentration risks.
- **State written**: `risk_assessment` (risk score, factors, immediate actions)

### 5. Goal Tracking Agent (`backend/agents/goal_agent.py`)
- **Role**: Loads user goals from **Postgres**, calculates monthly savings required, flags at-risk goals, suggests milestones.
- **State written**: `goal_tracking` (goals summary, progress, recommendations)
- **Postgres integration**: live read from `financial_goals` table

### 6. Judge Agent (`backend/evaluation/judge_agent.py`)
- **Role**: After each pipeline run, scores the final response on **accuracy**, **relevance**, and **safety** (1-5 scale).
- **Persists to**: Postgres `evaluation_scores` table + Langfuse scores
- **LangGraph node**: `judge_node` — runs after synthesizer, before END

---

## 📊 LangGraph State

All agents share a typed `FinancialPlannerState` (TypedDict):

```python
class FinancialPlannerState(TypedDict):
    messages: list[BaseMessage]          # conversation history
    user_input: str                       # current user question
    session_id: str                       # Postgres session UUID
    user_id: str                          # Postgres user UUID
    active_agents: list[str]             # router decision
    user_profile: dict                    # from Postgres users table
    budget_analysis: Optional[dict]      # Budget Agent output
    investment_plan: Optional[dict]      # Investment Agent output
    risk_assessment: Optional[dict]      # Risk Agent output
    goal_tracking: Optional[dict]        # Goal Agent output (from Postgres)
    coordinator_response: Optional[str]  # Final synthesized response
    judge_scores: Optional[dict]         # Accuracy / Relevance / Safety
    trace_id: Optional[str]              # Langfuse trace ID
```

State flows **explicitly** node-to-node — no hidden prompt chaining.

---

## 🗄️ Postgres Schema (Supabase)

| Table | Purpose |
|-------|---------|
| `users` | User profiles: email, name, risk_profile, monthly_income |
| `sessions` | Conversation sessions with request count |
| `messages` | Full conversation history (role, content, agent_name) |
| `financial_goals` | User goals with progress, category, target_date, status |
| `agent_runs` | Every agent execution with latency, tokens, Langfuse trace ID |
| `evaluation_scores` | Judge Agent scores per run (accuracy, relevance, safety) |
| `rate_limits` | Per-user sliding window rate limit tracking |

---

## 🔭 Langfuse Tracing

Every LLM call goes through `invoke_llm_with_tracing()` which records:
- **Trace**: name, session_id, user_id, tags (agent name)
- **Generation**: model, input messages, output content
- **Usage**: input tokens, output tokens, total tokens
- **Latency**: milliseconds per call
- **Scores**: accuracy/relevance/safety from Judge Agent

View all traces at [cloud.langfuse.com](https://cloud.langfuse.com) or your self-hosted instance.

---

## 🛡️ Guardrails

### Input Guardrails (`backend/guardrails/input_guard.py`)
- **Prompt injection**: 16 regex patterns (ignore instructions, jailbreak, DAN mode, hex escapes, etc.)
- **PII detection**: SSN, credit card numbers, passports — auto-redacted, request still proceeds
- **Length limit**: 5,000 character max
- **Domain relevance**: optional finance-only filter

### Output Guardrails (`backend/guardrails/output_guard.py`)
- **False guarantees**: blocks "guaranteed return", "100% safe", "cannot lose", etc.
- **System prompt leakage**: blocks if response reveals system instructions
- **Unsafe advice**: blocks "invest everything", "insider trading", "launder", "pyramid scheme", etc.
- **Disclaimer**: appended to all financial responses automatically

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check + queue depth |
| `POST` | `/users` | Create/update user profile |
| `GET` | `/users/{id}` | Get user by ID |
| `POST` | `/sessions` | Start a new session |
| `POST` | `/chat` | Main chat endpoint (sync pipeline) |
| `POST` | `/analyze/async` | Enqueue task via Upstash Redis |
| `GET` | `/goals/{user_id}` | List user goals |
| `POST` | `/goals` | Create a new goal |
| `PATCH` | `/goals/{goal_id}` | Update goal progress |
| `DELETE` | `/goals/{goal_id}` | Cancel a goal |
| `GET` | `/history/{session_id}` | Conversation history |
| `GET` | `/queue/status` | Redis queue depth |

API docs auto-generated at `http://localhost:8000/docs`

---

## 🚀 Local Setup

### Step 1: Get Free API Keys

| Service | URL | Free Tier |
|---------|-----|-----------|
| **Groq** | https://console.groq.com | 30 req/min, 14,400/day |
| **Google Gemini** | https://aistudio.google.com/app/apikey | 15 req/min, 1M tokens/day |
| **Supabase** | https://supabase.com | 500MB DB, 5GB bandwidth |
| **Upstash Redis** | https://upstash.com | 10,000 cmds/day |
| **Langfuse** | https://cloud.langfuse.com | Unlimited traces, 30-day retention |

### Step 2: Configure Environment

```bash
cd financial-ai-planner
cp .env.example .env
# Edit .env and fill in all your API keys
```

### Step 3: Set Up Database

1. Create a Supabase project at https://supabase.com
2. Go to **SQL Editor** in your Supabase dashboard
3. Paste and run the contents of `backend/db/schema.sql`
4. Copy your connection string from **Settings > Database > Connection String (Transaction Pooler)**
5. Add it as `DATABASE_URL` in your `.env`

### Step 4: Install Dependencies

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### Step 5: Start the Backend

```bash
# From the project root:
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### Step 6: Start the Frontend

```bash
# In a second terminal (with venv activated):
streamlit run frontend/app.py
```

### Step 7: Open the App

- **Streamlit UI**: http://localhost:8501
- **API Docs (Swagger)**: http://localhost:8000/docs
- **Langfuse Dashboard**: https://cloud.langfuse.com

---

## 🐳 Self-Hosting Langfuse (Optional)

If you prefer self-hosted Langfuse instead of the cloud:

```bash
cd docker
docker-compose up -d
```

Then access Langfuse at `http://localhost:3000` and update your `.env`:
```
LANGFUSE_HOST=http://localhost:3000
```

---

## 📈 Viewing Traces in Langfuse

1. Open [cloud.langfuse.com](https://cloud.langfuse.com) (or your self-hosted instance)
2. Navigate to **Traces** to see every pipeline run
3. Click any trace to see:
   - Agent execution timeline (router → budget → investment → risk → goal → synthesizer → judge)
   - Token usage per agent call
   - Latency per step
   - Input/output for each LLM call
4. Navigate to **Scores** to see Judge Agent evaluations (accuracy, relevance, safety)
5. Navigate to **Sessions** to group traces by user session

---

## 🧪 Quick Test

```bash
# 1. Create a user
curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","name":"Test User","risk_profile":"moderate","monthly_income":6000}'

# 2. Create a session (use the user_id from step 1)
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"user_id":"<user_id_from_step_1>"}'

# 3. Chat (use user_id and session_id from above)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "<user_id>",
    "session_id": "<session_id>",
    "message": "I earn $6000/month and spend $4500. How should I budget and invest?"
  }'
```

---

## 📁 Project Structure

```
financial-ai-planner/
├── backend/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── state.py               # LangGraph TypedDict state
│   │   ├── graph.py               # StateGraph wiring
│   │   ├── coordinator.py         # Router + Synthesizer
│   │   ├── budget_agent.py        # Budget Analysis
│   │   ├── investment_agent.py    # Investment Planning
│   │   ├── risk_agent.py          # Risk Assessment
│   │   └── goal_agent.py          # Goal Tracking (Postgres)
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py              # pydantic-settings config
│   │   └── llm_provider.py        # Groq + Gemini with fallback
│   ├── db/
│   │   ├── __init__.py
│   │   ├── schema.sql             # Supabase Postgres schema
│   │   └── database.py            # asyncpg pool + repositories
│   ├── evaluation/
│   │   ├── __init__.py
│   │   └── judge_agent.py         # LLM-as-a-Judge pipeline
│   ├── guardrails/
│   │   ├── __init__.py
│   │   ├── input_guard.py         # Injection, PII, length checks
│   │   └── output_guard.py        # Guarantee, leak, unsafe checks
│   ├── observability/
│   │   ├── __init__.py
│   │   └── langfuse_client.py     # Langfuse client + helpers
│   └── queue/
│       ├── __init__.py
│       └── redis_queue.py         # Upstash Redis task queue
├── frontend/
│   └── app.py                     # Streamlit UI
├── docker/
│   └── docker-compose.yml         # Self-hosted Langfuse
├── .env.example                   # All required env vars
├── .gitignore
├── requirements.txt
└── README.md
```

---

## ⚠️ Important Notes

- **Not financial advice**: This system is for educational/demo purposes. Always consult a certified financial advisor.
- **Rate limits**: Groq free tier has limits. If you hit them, the system auto-falls back to Gemini.
- **Supabase connection**: Use the **Transaction Pooler** connection string (port 6543), not direct connection, for serverless compatibility.
- **Secret key**: Generate a secure `SECRET_KEY` with `python -c "import secrets; print(secrets.token_hex(32))"`
