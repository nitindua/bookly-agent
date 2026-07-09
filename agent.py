import yaml
import anthropic
from tools import TOOLS, run_tool

# Load config
with open("config.yaml", "r") as f:
    CONFIG = yaml.safe_load(f)

client = anthropic.Anthropic()
MODEL = "claude-sonnet-4-20250514"


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


def chat_with_claude(messages: list, system_prompt: str) -> str:
    """
    Send messages to Claude, handle any tool use loop,
    return the final text response.
    """
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=system_prompt,
        tools=TOOLS,
        messages=messages,
    )

    # Tool use loop
    while response.stop_reason == "tool_use":
        tool_use_block = next(b for b in response.content if b.type == "tool_use")

        tool_result = run_tool(tool_use_block.name, tool_use_block.input)

        # Add Claude's tool request to history
        messages.append({"role": "assistant", "content": response.content})

        # Add tool result to history
        messages.append({
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": tool_use_block.id,
                "content": tool_result,
            }]
        })

        # Send back to Claude for final response
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=system_prompt,
            tools=TOOLS,
            messages=messages,
        )

    # Extract text response
    text_response = next(
        (b.text for b in response.content if hasattr(b, "text")),
        "I'm sorry, I couldn't generate a response."
    )
    messages.append({"role": "assistant", "content": response.content})
    return text_response


def main():
    system_prompt = build_system_prompt(CONFIG)
    messages = []

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

        messages.append({"role": "user", "content": user_input})

        try:
            response = chat_with_claude(messages, system_prompt)
            print(f"\n{CONFIG['agent']['name']}: {response}\n")
        except Exception as e:
            print(f"\nError: {e}\n")
            break


if __name__ == "__main__":
    main()
