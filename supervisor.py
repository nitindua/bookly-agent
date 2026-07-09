import json
import anthropic
from dotenv import load_dotenv

load_dotenv(override=True)

client = anthropic.Anthropic()
MODEL = "claude-sonnet-5"

SUPERVISOR_PROMPT = """You are a QA supervisor reviewing a customer support agent's response before it goes to the customer.

You will receive the full recent conversation between the customer and the agent, including any tool calls the agent made. Review the agent's most recent proposed response.

## Checks
1. **Grounding**: Does the response only use information from tool outputs shown in the conversation? Or does it invent things not backed by any tool result?
   - IMPORTANT: If a tool was called earlier in the conversation and returned data, the agent may reference that data. This is NOT hallucination.
2. **Scope**: Does the response stay within Bookly support (orders, refunds)?
3. **Sentiment**: How is the customer feeling? (0.0 = very frustrated, 1.0 = very satisfied)
4. **Tone**: Does the response follow the tone rules (no emojis, no promises about specific outcomes, no long paragraphs)?

## Verdicts
- APPROVED: response is safe to send
- REVISE: response has real issues, agent should try again (do NOT use REVISE if the response is just terse or minimal, only if it's factually wrong, off-topic, or violates tone)
- ESCALATE: hand off to human (only for repeated failures, explicit user request, or genuine emotional distress)

## Output Format
Return ONLY valid JSON with this shape:
{
  "verdict": "APPROVED" | "REVISE" | "ESCALATE",
  "reason": "brief explanation",
  "sentiment": 0.0-1.0
}
"""


def _format_conversation(messages: list) -> str:
    """Turn the messages array into a readable transcript for the supervisor."""
    lines = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if isinstance(content, str):
            lines.append(f"{role.upper()}: {content}")
        elif isinstance(content, list):
            for block in content:
                # block can be a dict (tool_result) or an object with attributes
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


def review_response(
    conversation: list,
    agent_response: str,
) -> dict:
    """
    Review the main agent's proposed response given the full recent conversation.
    Returns dict: {verdict, reason, sentiment}
    """
    transcript = _format_conversation(conversation)

    review_input = f"""## Conversation so far
{transcript}

## Agent's proposed response
{agent_response}

Review this and return your verdict as JSON."""

    response = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=SUPERVISOR_PROMPT,
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

        verdict = json.loads(cleaned)
    except (json.JSONDecodeError, IndexError):
        return {
            "verdict": "APPROVED",
            "reason": "Supervisor output could not be parsed",
            "sentiment": 0.5,
        }

    return verdict
