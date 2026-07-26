import yaml
import anthropic
from dotenv import load_dotenv
from tools import TOOLS, run_tool
from supervisor import review_response
from summarizer import generate_escalation_summary, print_summary
from logger import (
    new_session_id,
    log_session_start,
    log_session_end,
    log_user_message,
    log_agent_response,
    log_tool_call,
    log_tool_result,
    log_supervisor,
    log_escalation,
    log_summary,
)

load_dotenv(override=True)

# Load config
with open("config.yaml", "r") as f:
    CONFIG = yaml.safe_load(f)

client = anthropic.Anthropic()
MODEL = "claude-sonnet-5"
MAX_RETRIES = 2


def build_system_prompt(config: dict) -> str:
    """Convert YAML config into a prose system prompt for Claude."""
    agent = config["agent"]
    actions = config["actions"]
    guardrails = config["guardrails"]
    tone = config["tone"]
    escalation = config["escalation"]

    scope = "\n".join(f"- {s}" for s in agent["scope"])
    must_use = "\n".join(f"- {m}" for m in guardrails["must_use_action_before_answering"])
    never = "\n".join(f"- {n}" for n in guardrails["never_do"])
    do = "\n".join(f"- {d}" for d in tone["do"])
    avoid = "\n".join(f"- {a}" for a in tone["avoid"])

    action_rules = []
    for name, details in actions.items():
        rule = f"- {name}: {details['description']}"
        if "escalation_condition" in details:
            rule += f" Escalate if {details['escalation_condition']}."
        action_rules.append(rule)
    action_rules_str = "\n".join(action_rules)

    return f"""You are {agent['name']}, a customer service agent for Bookly, an online bookstore.

## Scope
You can help with:
{scope}

If a request is outside this scope, respond with:
"{agent['default_response']}"

## Available Actions
{action_rules_str}

## Policy Rules (These Are Real - Not Made Up)
- Refunds for orders over $100 MUST be escalated to a human. This is company policy.
- When a tool returns `escalate: true`, the refund was NOT processed. Do not claim otherwise.
- When a tool returns `success: false`, the action failed. Do not claim it succeeded.

## Grounding Rules
You MUST call an action before answering questions about:
{must_use}

Never guess or make up information. Always call the appropriate action first.
Only claim an action succeeded if the tool response says `success: true`.

## Hard Rules - You Must NEVER:
{never}

## Escalation
If the user requests a human, agent, or manager, or you detect frustration,
respond with:
"{escalation['handoff_message']}"

## Tone: {tone['style']}
Do:
{do}

Avoid:
{avoid}
"""


def check_escalation_keywords(user_message: str) -> bool:
    """Check if user message contains any escalation trigger keywords."""
    keywords = CONFIG["escalation"]["triggers"]["keywords"]
    message_lower = user_message.lower()
    return any(kw.lower() in message_lower for kw in keywords)


def get_agent_response(
    messages: list,
    system_prompt: str,
    session_id: str | None = None,
) -> tuple[str, str | None, list]:
    """
    Send messages to Claude, handle tool use loop.
    Returns: (final_text_response, tool_output_json, final_content_blocks)

    Note: appends tool-use turns to `messages` but NOT the final assistant response,
    so the caller can decide whether to keep it after supervisor review.
    """
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=system_prompt,
        tools=TOOLS,
        messages=messages,
    )

    tool_output = None

    # Tool use loop - handle parallel tool calls (Claude may return multiple tool_use blocks)
    while response.stop_reason == "tool_use":
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for tool_use_block in tool_use_blocks:
            if session_id:
                log_tool_call(session_id, tool_use_block.name, dict(tool_use_block.input))
            tool_output = run_tool(tool_use_block.name, tool_use_block.input)
            if session_id:
                log_tool_result(session_id, tool_use_block.name, tool_output)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use_block.id,
                "content": tool_output,
            })

        messages.append({"role": "user", "content": tool_results})

        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=system_prompt,
            tools=TOOLS,
            messages=messages,
        )

    text_response = next(
        (b.text for b in response.content if hasattr(b, "text")),
        "I'm sorry, I couldn't generate a response."
    )
    return text_response, tool_output, response.content


def _tool_signaled_escalation(tool_output: str | None) -> bool:
    """Check if the tool result marked this as needing escalation."""
    if not tool_output:
        return False
    try:
        import json as _json
        data = _json.loads(tool_output)
        return bool(data.get("escalate"))
    except (ValueError, TypeError):
        return False


def _tool_call_succeeded(tool_output: str | None) -> bool:
    """Check if a tool call in this turn returned success (agent helped the user)."""
    if not tool_output:
        return False
    try:
        import json as _json
        data = _json.loads(tool_output)
        return bool(data.get("success"))
    except (ValueError, TypeError):
        return False


def handle_turn(
    user_input: str,
    messages: list,
    system_prompt: str,
    session_id: str | None = None,
) -> tuple[str, str, float, bool]:
    """
    Handle one user turn: get agent response, run supervisor, retry if needed.
    Returns: (final_response_text, final_verdict, sentiment, agent_helped)
    """
    messages.append({"role": "user", "content": user_input})

    for attempt in range(MAX_RETRIES + 1):
        response_text, tool_output, content_blocks = get_agent_response(
            messages, system_prompt, session_id
        )

        # Hard rule: if a tool signaled escalation, force it regardless of what agent said
        if _tool_signaled_escalation(tool_output):
            print(f"\n[debug] Tool signaled escalation. Forcing handoff.")
            return CONFIG["escalation"]["handoff_message"], "ESCALATE", 0.5, False

        agent_helped = _tool_call_succeeded(tool_output)

        verdict_data = review_response(messages, response_text, system_prompt)
        verdict = verdict_data["verdict"]
        sentiment = verdict_data.get("sentiment", 0.5)
        if session_id:
            log_supervisor(session_id, verdict, sentiment, verdict_data.get("reason", ""))

        # If agent decided to hand off on its own (response contains the handoff message),
        # treat this as an escalation regardless of what the supervisor said.
        handoff_marker = CONFIG["escalation"]["handoff_message"][:40]
        if handoff_marker in response_text:
            return response_text, "ESCALATE", sentiment, agent_helped

        if verdict == "APPROVED":
            messages.append({"role": "assistant", "content": content_blocks})
            if session_id:
                log_agent_response(session_id, response_text, agent_helped)
            return response_text, verdict, sentiment, agent_helped

        if verdict == "ESCALATE":
            print(f"\n[debug] Agent's original response: {response_text}")
            print(f"[debug] Escalation reason: {verdict_data.get('reason', 'no reason')}")
            return CONFIG["escalation"]["handoff_message"], verdict, sentiment, agent_helped

        # REVISE: add feedback note and retry
        if attempt < MAX_RETRIES:
            feedback = verdict_data.get("reason", "please revise")
            print(f"\n[debug] Response revised. Original: {response_text}")
            print(f"[debug] Revise reason: {feedback}")
            messages.append({
                "role": "user",
                "content": f"[Reviewer note: your previous response was rejected. Reason: {feedback}. Please try again.]"
            })

    # Retries exhausted
    return CONFIG["escalation"]["handoff_message"], "ESCALATE", sentiment, False


def main():
    system_prompt = build_system_prompt(CONFIG)
    messages = []
    frustrated_turns = 0
    min_sentiment = CONFIG["escalation"]["triggers"]["min_sentiment"]
    frustrated_limit = CONFIG["escalation"]["triggers"]["frustrated_response_limit"]

    session_id = new_session_id()
    log_session_start(session_id)

    print(f"\n{CONFIG['agent']['name']}: Hi! How can I help you today?\n")
    print(f"[debug] Logging to logs/session-{session_id}.log\n")

    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue
        if user_input.lower() in ["quit", "exit", "bye"]:
            print(f"\n{CONFIG['agent']['name']}: Goodbye!\n")
            log_session_end(session_id)
            break

        log_user_message(session_id, user_input)

        # Fast path: keyword-based escalation
        if check_escalation_keywords(user_input):
            messages.append({"role": "user", "content": user_input})
            print(f"\n{CONFIG['agent']['name']}: {CONFIG['escalation']['handoff_message']}\n")
            log_escalation(session_id, "user requested a human agent (keyword)")
            summary = generate_escalation_summary(messages, "user requested a human agent")
            log_summary(session_id, summary)
            print_summary(summary)
            log_session_end(session_id)
            break

        try:
            response_text, verdict, sentiment, agent_helped = handle_turn(
                user_input, messages, system_prompt, session_id
            )
            print(f"\n{CONFIG['agent']['name']}: {response_text}\n")
            print(f"[debug] verdict={verdict} sentiment={sentiment:.2f} helped={agent_helped}\n")

            if verdict == "ESCALATE":
                log_escalation(session_id, "supervisor or tool signaled escalation")
                summary = generate_escalation_summary(messages, "supervisor or tool signaled escalation")
                log_summary(session_id, summary)
                print_summary(summary)
                log_session_end(session_id)
                break

            # Track consecutive frustrated turns - but reset if agent successfully helped
            # (give the user a chance to react to a helpful response before escalating)
            if agent_helped:
                frustrated_turns = 0
            elif sentiment < min_sentiment:
                frustrated_turns += 1
            else:
                frustrated_turns = 0

            if frustrated_turns >= frustrated_limit:
                print(f"\n{CONFIG['agent']['name']}: {CONFIG['escalation']['handoff_message']}\n")
                log_escalation(session_id, f"user showed frustration for {frustrated_turns} consecutive turns")
                summary = generate_escalation_summary(messages, f"user showed frustration for {frustrated_turns} consecutive turns")
                log_summary(session_id, summary)
                print_summary(summary)
                log_session_end(session_id)
                break

        except Exception as e:
            print(f"\nError: {e}\n")
            log_session_end(session_id)
            break


if __name__ == "__main__":
    main()
