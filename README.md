# Bookly Support Agent

An AI customer support agent prototype for a fictional online bookstore.

## What It Does

Handles customer inquiries about:
- Order status
- Refund requests

Built with config-driven behavior rules (Decagon-style AOPs), forced tool grounding, and escalation logic.

## Architecture

| File | Responsibility |
| --- | --- |
| `agent.py` | Main chat loop, Claude API orchestration |
| `tools.py` | Tool definitions and handlers |
| `config.yaml` | Agent behavior rules (editable by non-engineers) |
| `data.py` | Mock database (orders, refunds) |

## Setup

1. Install dependencies:
```
pip install -r requirements.txt
```

2. Set your Anthropic API key:
```
cp .env.example .env
```
Then edit `.env` with your key.

3. Export the key (or use a tool like `python-dotenv`):
```
export ANTHROPIC_API_KEY=your_key_here
```

## Run

```
python agent.py
```

## Try These

- "Where's my order?" → agent asks for order ID
- "ORD-123" → agent looks up and responds
- "I need a refund for ORD-456" → agent asks for reason
- "It arrived damaged" → agent processes refund
- "Refund ORD-789" → escalation (high value order)
- "Let me talk to a human" → immediate escalation
