import os
from datetime import datetime

LOG_DIR = "logs"


def _log_path(session_id: str) -> str:
    return os.path.join(LOG_DIR, f"session-{session_id}.log")


def new_session_id() -> str:
    """Create a session ID based on current timestamp."""
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def log_event(session_id: str, event_type: str, details: str = "") -> None:
    """Append a single event line to the session log file."""
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {event_type}"
    if details:
        line += f": {details}"
    with open(_log_path(session_id), "a") as f:
        f.write(line + "\n")


def log_session_start(session_id: str) -> None:
    log_event(session_id, "SESSION_START")


def log_session_end(session_id: str) -> None:
    log_event(session_id, "SESSION_END")


def log_user_message(session_id: str, message: str) -> None:
    log_event(session_id, "USER_MESSAGE", f'"{message}"')


def log_agent_response(session_id: str, response: str, helped: bool) -> None:
    truncated = response[:120] + "..." if len(response) > 120 else response
    log_event(session_id, "AGENT_RESPONSE", f'"{truncated}" (helped={helped})')


def log_tool_call(session_id: str, tool_name: str, tool_input: dict) -> None:
    log_event(session_id, "TOOL_CALL", f"{tool_name}({tool_input})")


def log_tool_result(session_id: str, tool_name: str, result: str) -> None:
    log_event(session_id, "TOOL_RESULT", f"{tool_name} -> {result}")


def log_supervisor(session_id: str, verdict: str, sentiment: float, reason: str) -> None:
    log_event(
        session_id,
        "SUPERVISOR",
        f"{verdict} (sentiment={sentiment:.2f}, reason={reason})",
    )


def log_escalation(session_id: str, reason: str) -> None:
    log_event(session_id, "ESCALATION", reason)


def log_summary(session_id: str, summary: dict) -> None:
    line = (
        f"customer={summary.get('customer', 'unknown')} | "
        f"status={summary.get('status', 'unknown')} | "
        f"next={summary.get('next', 'unknown')}"
    )
    log_event(session_id, "HANDOFF_SUMMARY", line)
