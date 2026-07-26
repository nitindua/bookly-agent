import re
import streamlit as st
import tools
from agent import (
    CONFIG,
    check_escalation_keywords,
    handle_turn,
)
from summarizer import generate_escalation_summary
from logger import (
    new_session_id,
    log_session_start,
    log_user_message,
    log_escalation,
    log_summary,
)


def extract_refund_threshold(prose: str) -> int:
    """Pull the refund threshold value out of the AOP prose."""
    match = re.search(r"refund exceeds \$(\d+)", prose, re.IGNORECASE)
    return int(match.group(1)) if match else 100


EVENT_CLASS = {
    "USER_MESSAGE": "user",
    "TOOL_CALL": "tool",
    "TOOL_RESULT": "tool",
    "AGENT_RESPONSE": "agent",
    "SUPERVISOR": "supervisor",
    "ESCALATION": "escalate",
    "HANDOFF_SUMMARY": "summary",
}


def load_session_log(session_id: str) -> list:
    """Parse the session log file into event dicts."""
    events = []
    try:
        with open(f"logs/session-{session_id}.log", "r") as f:
            for line in f:
                match = re.match(r"\[([\d\- :]+)\] ([A-Z_]+)(?::\s*(.*))?", line.strip())
                if match:
                    ts, event_type, details = match.groups()
                    if event_type in EVENT_CLASS:
                        events.append({"time": ts, "type": event_type, "details": details or ""})
    except FileNotFoundError:
        pass
    return events


def _truncate(text: str, max_len: int = 60) -> str:
    """Trim text with an ellipsis if it exceeds max_len."""
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "…"


def render_timeline(events: list) -> str:
    """Render session events as an HTML timeline with colored rail and dots."""
    lines = ['<ul class="timeline">']
    for e in events:
        cls = EVENT_CLASS.get(e["type"], "summary")
        time_str = e["time"].split(" ")[1] if " " in e["time"] else e["time"]
        details = _truncate(e["details"]).replace("<", "&lt;").replace(">", "&gt;")
        lines.append(
            f'<li class="ev-{cls}">'
            f'<span class="ev-time">{time_str}</span>'
            f'<span class="ev-type {cls}">{e["type"]}</span>'
            f'<div class="ev-body">{details}</div>'
            f'</li>'
        )
    lines.append('</ul>')
    return "\n".join(lines)

st.set_page_config(
    page_title="Bookly Support",
    layout="wide",
)

TYPING_HTML = """
<div style="display: inline-flex; gap: 5px; padding: 4px 0; align-items: center;">
  <div class="typing-dot"></div>
  <div class="typing-dot"></div>
  <div class="typing-dot"></div>
</div>
<style>
.typing-dot { width: 7px; height: 7px; background: #808495; border-radius: 50%;
              animation: typing-bounce 1.4s infinite; }
.typing-dot:nth-child(2) { animation-delay: 0.2s; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes typing-bounce {
  0%, 60%, 100% { opacity: 0.3; transform: translateY(0); }
  30%           { opacity: 1;   transform: translateY(-4px); }
}
</style>
"""

# UI polish: subtle vertical divider between chat and support view
st.markdown("""
<style>
[data-testid="stHorizontalBlock"] > div:nth-child(2) {
    border-left: 1px solid rgba(120, 120, 120, 0.2);
    padding-left: 1.5rem;
}
[data-testid="stTextArea"] textarea {
    background-color: white !important;
}
[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary * {
    font-weight: 600 !important;
    font-size: 1rem !important;
}
/* Session log timeline */
ul.timeline {
    position: relative;
    padding-left: 22px;
    margin: 0;
    list-style: none;
}
ul.timeline::before {
    content: "";
    position: absolute;
    left: 5px; top: 6px; bottom: 6px;
    width: 1.5px;
    background: #e6e9ef;
}
ul.timeline li {
    position: relative;
    padding: 2px 0 6px;
}
ul.timeline li::before {
    content: "";
    position: absolute;
    left: -20px; top: 8px;
    width: 8px; height: 8px;
    border-radius: 50%;
    background: #ffffff;
    border: 2px solid #808495;
}
ul.timeline li.ev-user::before       { border-color: #ff4b4b; }
ul.timeline li.ev-tool::before       { border-color: #7c3aed; }
ul.timeline li.ev-agent::before      { border-color: #0068c9; }
ul.timeline li.ev-supervisor::before { border-color: #26a561; }
ul.timeline li.ev-escalate::before   { border-color: #a02020; background: #a02020; }
ul.timeline li.ev-summary::before    { border-color: #808495; }
ul.timeline .ev-time {
    font-family: "SF Mono", Menlo, monospace;
    font-size: 11px;
    color: #808495;
    margin-right: 8px;
}
ul.timeline .ev-type {
    font-family: "SF Mono", Menlo, monospace;
    font-size: 10.5px;
    font-weight: 700;
    letter-spacing: 0.4px;
    text-transform: uppercase;
}
ul.timeline .ev-type.user       { color: #ff4b4b; }
ul.timeline .ev-type.tool       { color: #7c3aed; }
ul.timeline .ev-type.agent      { color: #0068c9; }
ul.timeline .ev-type.supervisor { color: #26a561; }
ul.timeline .ev-type.escalate   { color: #a02020; }
ul.timeline .ev-type.summary    { color: #808495; }
ul.timeline .ev-body {
    font-family: "SF Mono", Menlo, monospace;
    font-size: 11.5px;
    color: #545a67;
    margin-top: 2px;
}
</style>
""", unsafe_allow_html=True)

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "display_messages" not in st.session_state:
    st.session_state.display_messages = [
        {"role": "assistant", "content": "Hi! How can I help you today?"}
    ]
if "sentiment" not in st.session_state:
    st.session_state.sentiment = None
if "escalated" not in st.session_state:
    st.session_state.escalated = False
if "summary" not in st.session_state:
    st.session_state.summary = None
if "aop_prose" not in st.session_state:
    with open("aop.md", "r") as f:
        st.session_state.aop_prose = f.read()
    tools.RUNTIME_CONFIG["refund_threshold"] = extract_refund_threshold(st.session_state.aop_prose)
if "aop_editor" not in st.session_state:
    st.session_state.aop_editor = st.session_state.aop_prose
if "pending_input" not in st.session_state:
    st.session_state.pending_input = None
if "session_id" not in st.session_state:
    st.session_state.session_id = new_session_id()
    log_session_start(st.session_state.session_id)

chat_col, monitor_col = st.columns([2, 1], gap="large")

with chat_col:
    st.subheader("Bookly Support")

    for msg in st.session_state.display_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"].replace("$", "\\$"))

    if st.session_state.pending_input:
        user_input = st.session_state.pending_input
        st.session_state.pending_input = None
        log_user_message(st.session_state.session_id, user_input)

        with st.chat_message("assistant"):
            placeholder = st.empty()
            placeholder.markdown(TYPING_HTML, unsafe_allow_html=True)

            if check_escalation_keywords(user_input):
                handoff = CONFIG["escalation"]["handoff_message"]
                st.session_state.messages.append({"role": "user", "content": user_input})
                st.session_state.display_messages.append({"role": "assistant", "content": handoff})
                log_escalation(st.session_state.session_id, "user requested a human agent (keyword)")
                st.session_state.summary = generate_escalation_summary(
                    st.session_state.messages,
                    "user requested a human agent",
                    st.session_state.aop_prose,
                )
                log_summary(st.session_state.session_id, st.session_state.summary)
                st.session_state.escalated = True
                st.rerun()

            response_text, verdict, sentiment, _ = handle_turn(
                user_input,
                st.session_state.messages,
                st.session_state.aop_prose,
                st.session_state.session_id,
            )

            placeholder.markdown(response_text.replace("$", "\\$"))

        st.session_state.sentiment = sentiment
        st.session_state.display_messages.append({"role": "assistant", "content": response_text})

        if verdict == "ESCALATE":
            log_escalation(st.session_state.session_id, "supervisor or tool signaled escalation")
            st.session_state.summary = generate_escalation_summary(
                st.session_state.messages,
                "supervisor or tool signaled escalation",
                st.session_state.aop_prose,
            )
            log_summary(st.session_state.session_id, st.session_state.summary)
            st.session_state.escalated = True
        st.rerun()

    if st.session_state.escalated:
        st.info("Conversation ended — handed off to support team.")
    else:
        user_input = st.chat_input("Type your message...")
        if user_input:
            st.session_state.display_messages.append({"role": "user", "content": user_input})
            st.session_state.pending_input = user_input
            st.rerun()

with monitor_col:
    st.subheader("Support View")
    st.caption("Internal — not shown to customer")

    # Sentiment card
    with st.container(border=True):
        st.markdown("**Customer sentiment**")
        if st.session_state.sentiment is not None:
            s = st.session_state.sentiment
            if s >= 0.7:
                label = "Positive"
            elif s >= 0.5:
                label = "Neutral"
            elif s >= 0.3:
                label = "Frustrated"
            else:
                label = "Very frustrated"

            st.metric("Customer sentiment", f"{s:.2f}", label, label_visibility="collapsed")
            st.progress(s)
        else:
            st.metric("Customer sentiment", "—", "waiting for first message", label_visibility="collapsed")

    # Handoff summary card
    with st.container(border=True):
        st.markdown("**Handoff summary**")
        if st.session_state.escalated and st.session_state.summary:
            s = st.session_state.summary
            def _safe(text):
                # Escape $ so Streamlit doesn't interpret it as LaTeX
                return str(text).replace("$", "\\$")
            st.markdown(f"**Customer:** {_safe(s.get('customer', 'unknown'))}")
            st.markdown(f"**Status:** {_safe(s.get('status', 'unknown'))}")
            st.markdown(f"**Next:** {_safe(s.get('next', 'review manually'))}")
        else:
            st.caption("Appears if conversation is escalated.")

    # AOP editor card
    with st.expander("Agent Operating Procedures", expanded=False):
        tab_preview, tab_edit = st.tabs(["Preview", "Edit"])
        with tab_preview:
            st.markdown(st.session_state.aop_prose)
        with tab_edit:
            st.text_area(
                "AOP",
                key="aop_editor",
                height=500,
                label_visibility="collapsed",
            )
            if st.button("Apply", use_container_width=True):
                st.session_state.aop_prose = st.session_state.aop_editor
                tools.RUNTIME_CONFIG["refund_threshold"] = extract_refund_threshold(st.session_state.aop_prose)
                st.toast("AOP updated — applies on next turn")

    # Session log card
    with st.expander("Session log", expanded=False):
        events = load_session_log(st.session_state.session_id)
        if not events:
            st.caption("Log starts populating after your first message.")
        else:
            st.markdown(render_timeline(events), unsafe_allow_html=True)
