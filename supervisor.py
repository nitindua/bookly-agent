import json
import anthropic
from dotenv import load_dotenv

load_dotenv(override=True)

client = anthropic.Anthropic()
MODEL = "claude-sonnet-5"

SUPERVISOR_PROMPT = """You are a QA supervisor reviewing a customer support agent's response before it goes to the customer.

Your job is to review the response and return a verdict.

## Checks
1. **Grounding**: Does the response only use information from the tool output? Or does it make things up?
2. **Scope**: Does the response stay within Bookly support (orders, refunds)?
3. **Sentiment**: How is the customer feeling? (0.0 = very frustrated, 1.0 = very satisfied)

## Verdicts
- APPROVED: response is safe to send
- REVISE: response has issues, agent should try again
- ESCALATE: hand off to human (sentiment too low, or repeated failures)

## Output Format
Return ONLY valid JSON with this shape:
{
  "verdict": "APPROVED" | "REVISE" | "ESCALATE",
  "reason": "brief explanation",
  "sentiment": 0.0-1.0
}
"""


def review_response(
    user_message: str,
    tool_output: str | None,
    agent_response: str,
) -> dict:
    """
    Review the main agent's response.
    Returns dict: {verdict, reason, sentiment}
    """
    review_input = f"""User message: {user_message}

Tool output (if any): {tool_output or "No tool was called"}

Agent's proposed response: {agent_response}

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

    # Parse JSON verdict
    try:
        # Strip markdown code fences if Claude wrapped the JSON
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()

        verdict = json.loads(cleaned)
    except (json.JSONDecodeError, IndexError):
        # If supervisor output can't be parsed, default to approving
        # (fail open - don't block the user because supervisor misformatted)
        return {
            "verdict": "APPROVED",
            "reason": "Supervisor output could not be parsed",
            "sentiment": 0.5,
        }

    return verdict
