# Bookly Support Agent

An AI customer support agent prototype for a fictional online bookstore.

## What It Does

Handles two support scenarios end-to-end:
- **Order status** lookups
- **Refund requests**, with escalation to a human agent for high-value orders or when the customer needs one

## Architecture

| File | Responsibility |
| --- | --- |
| `agent.py` | Main orchestration and Claude API calls |
| `app.py` | Streamlit web UI |
| `supervisor.py` | Reviews every agent response before it's sent |
| `config.yaml` | Agent behavior rules (scope, tools, escalation, tone) |

## Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Set your Anthropic API key:
   ```
   cp .env.example .env
   ```
   Then edit `.env` and add your key.

## Run

**Streamlit (recommended):**
```
streamlit run app.py
```

**CLI:**
```
python agent.py
```

## Try These

- "Where's my order?" → order lookup flow
- "Refund ORD-789" → high-value escalation
- "Let me talk to a human" → keyword escalation
