import yaml
import anthropic
from dotenv import load_dotenv
from tools import TOOLS, run_tool
from supervisor import review_response

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

## Grounding Rules
You MUST call an action before answering questions about:
{must_use}

Never guess or make up information. Always call the appropriate action first.

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

    # Tool use loop
    while response.stop_reason == "tool_use":
        tool_use_block = next(b for b in response.content if b.type == "tool_use")
        tool_output = run_tool(tool_use_block.name, tool_use_block.input)

        messages.append({"role": "assistant", "content": response.content})
        messages.append({
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": tool_use_block.id,
                "content": tool_output,
            }]
        })

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


def handle_turn(
    user_input: str,
    messages: list,
    system_prompt: str,
) -> tuple[str, str, float]:
    """
    Handle one user turn: get agent response, run supervisor, retry if needed.
    Returns: (final_response_text, final_verdict, sentiment)
    """
    messages.append({"role": "user", "content": user_input})

    for attempt in range(MAX_RETRIES + 1):
        response_text, tool_output, content_blocks = get_agent_response(
            messages, system_prompt
        )

        verdict_data = review_response(user_input, tool_output, response_text)
        verdict = verdict_data["verdict"]
        sentiment = verdict_data.get("sentiment", 0.5)

        if verdict == "APPROVED":
            messages.append({"role": "assistant", "content": content_blocks})
            return response_text, verdict, sentiment

        if verdict == "ESCALATE":
            print(f"\n[debug] Agent's original response: {response_text}")
            print(f"[debug] Escalation reason: {verdict_data.get('reason', 'no reason')}")
            return CONFIG["escalation"]["handoff_message"], verdict, sentiment

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
    return CONFIG["escalation"]["handoff_message"], "ESCALATE", sentiment


def main():
    system_prompt = build_system_prompt(CONFIG)
    messages = []
    frustrated_turns = 0
    min_sentiment = CONFIG["escalation"]["triggers"]["min_sentiment"]
    frustrated_limit = CONFIG["escalation"]["triggers"]["frustrated_response_limit"]

    print(f"\n{CONFIG['agent']['name']}: Hi! How can I help you today?\n")

    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue
        if user_input.lower() in ["quit", "exit", "bye"]:
            print(f"\n{CONFIG['agent']['name']}: Goodbye!\n")
            break

        # Fast path: keyword-based escalation
        if check_escalation_keywords(user_input):
            print(f"\n{CONFIG['agent']['name']}: {CONFIG['escalation']['handoff_message']}\n")
            break

        try:
            response_text, verdict, sentiment = handle_turn(
                user_input, messages, system_prompt
            )
            print(f"\n{CONFIG['agent']['name']}: {response_text}\n")
            print(f"[debug] verdict={verdict} sentiment={sentiment:.2f}\n")

            # Track consecutive frustrated turns
            if sentiment < min_sentiment:
                frustrated_turns += 1
            else:
                frustrated_turns = 0

            if verdict == "ESCALATE":
                break
            if frustrated_turns >= frustrated_limit:
                print(f"\n{CONFIG['agent']['name']}: {CONFIG['escalation']['handoff_message']}\n")
                break

        except Exception as e:
            print(f"\nError: {e}\n")
            break


if __name__ == "__main__":
    main()
