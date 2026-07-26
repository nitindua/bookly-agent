import json
import anthropic
from dotenv import load_dotenv

load_dotenv(override=True)

client = anthropic.Anthropic()
MODEL = "claude-sonnet-5"

SUMMARY_PROMPT = """You are generating a handoff summary for a human support agent taking over a conversation from an AI agent.

Produce a concise, factual summary the human can read in 10 seconds to understand what happened and continue from where the AI agent left off.

Refer to the automated agent as "the AI agent" (never just "AI" or "the AI").

## Output Format
Return ONLY valid JSON with this shape:
{
  "customer": "one short line - what the customer wanted",
  "status": "one short line - what the AI agent did, current state, and why this is escalated",
  "next": "one short line - what the human should do next"
}

Keep each field to a single line. Be factual, not speculative. Base everything on the actual conversation and tool calls.
"""


def _format_conversation(messages: list) -> str:
    """Turn the messages array into a readable transcript."""
    lines = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if isinstance(content, str):
            lines.append(f"{role.upper()}: {content}")
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    block_type = block.get("type")
                    if block_type == "tool_result":
                        lines.append(f"TOOL_RESULT: {block.get('content', '')}")
                    elif block_type == "text":
                        lines.append(f"{role.upper()}: {block.get('text', '')}")
                    elif block_type == "tool_use":
                        lines.append(f"AGENT_TOOL_CALL: {block.get('name')}({block.get('input')})")
                else:
                    block_type = getattr(block, "type", None)
                    if block_type == "text":
                        lines.append(f"{role.upper()}: {getattr(block, 'text', '')}")
                    elif block_type == "tool_use":
                        lines.append(f"AGENT_TOOL_CALL: {block.name}({block.input})")
    return "\n".join(lines)


def generate_escalation_summary(
    messages: list,
    escalation_reason: str,
    aop_prose: str = "",
) -> dict:
    """Generate a handoff summary for a human agent taking over."""
    if not messages:
        return {
            "customer": "no interaction",
            "status": f"escalated: {escalation_reason}",
            "next": "greet customer and ask how you can help",
        }

    transcript = _format_conversation(messages)

    aop_section = f"""## Current agent operating procedures
The agent was running under the following procedures. Any policy the agent references (thresholds, escalation rules, restrictions) is REAL and comes from here — do not describe it as invented or fabricated.

{aop_prose}

""" if aop_prose else ""

    review_input = f"""{aop_section}## Conversation transcript
{transcript}

## Escalation reason
{escalation_reason}

Generate the handoff summary as JSON."""

    response = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=SUMMARY_PROMPT,
        messages=[{"role": "user", "content": review_input}],
    )

    raw_text = next(
        (b.text for b in response.content if hasattr(b, "text")),
        ""
    )

    try:
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()

        return json.loads(cleaned)
    except (json.JSONDecodeError, IndexError) as e:
        print(f"\n[debug] Summary parse failed: {e}")
        print(f"[debug] Raw response: {raw_text[:500]}")
        return {
            "customer": "unable to parse summary",
            "status": f"escalated: {escalation_reason}. See transcript.",
            "next": "review conversation manually",
        }


def print_summary(summary: dict) -> None:
    """Print a compact, clearly-system-output summary for the human agent."""
    print("\n[SYSTEM: AGENT HANDED OFF — SUMMARY FOR SUPPORT TEAM]\n")
    print(f"  customer  {summary.get('customer', 'unknown')}")
    print(f"  status    {summary.get('status', 'unknown')}")
    print(f"  next      {summary.get('next', 'review manually')}")
    print()
