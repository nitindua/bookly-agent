import streamlit as st
from agent import (
    CONFIG,
    build_system_prompt,
    check_escalation_keywords,
    handle_turn,
)
from summarizer import generate_escalation_summary

st.set_page_config(
    page_title="Bookly Support",
    layout="wide",
)

# UI polish: right-align user chat bubbles, vertical divider between columns
st.markdown("""
<style>
[data-testid="stChatMessage"]:has(> div:first-child > [data-testid="stChatMessageAvatarUser"]) {
    flex-direction: row-reverse;
    text-align: right;
}
[data-testid="stChatMessage"]:has(> div:first-child > [data-testid="stChatMessageAvatarUser"]) > div:last-child {
    align-items: flex-end;
}
[data-testid="stHorizontalBlock"] > div:nth-child(2) {
    border-left: 1px solid rgba(120, 120, 120, 0.2);
    padding-left: 1.5rem;
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
if "system_prompt" not in st.session_state:
    st.session_state.system_prompt = build_system_prompt(CONFIG)
if "pending_input" not in st.session_state:
    st.session_state.pending_input = None

chat_col, monitor_col = st.columns([2, 1], gap="large")

with chat_col:
    st.subheader("Bookly Support")

    for msg in st.session_state.display_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if st.session_state.pending_input:
        user_input = st.session_state.pending_input
        st.session_state.pending_input = None

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                if check_escalation_keywords(user_input):
                    handoff = CONFIG["escalation"]["handoff_message"]
                    st.session_state.messages.append({"role": "user", "content": user_input})
                    st.session_state.display_messages.append({"role": "assistant", "content": handoff})
                    st.session_state.summary = generate_escalation_summary(
                        st.session_state.messages,
                        "user requested a human agent",
                    )
                    st.session_state.escalated = True
                    st.rerun()

                response_text, verdict, sentiment, _ = handle_turn(
                    user_input,
                    st.session_state.messages,
                    st.session_state.system_prompt,
                )

            st.markdown(response_text)

        st.session_state.sentiment = sentiment
        st.session_state.display_messages.append({"role": "assistant", "content": response_text})

        if verdict == "ESCALATE":
            st.session_state.summary = generate_escalation_summary(
                st.session_state.messages,
                "supervisor or tool signaled escalation",
            )
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

            col_num, col_label = st.columns([1, 1])
            with col_num:
                st.markdown(f"### {s:.2f}")
            with col_label:
                st.markdown(f"_{label}_")
            st.progress(s)
        else:
            st.caption("Waiting for first message...")

    # Handoff summary card
    with st.container(border=True):
        st.markdown("**Handoff summary**")
        if st.session_state.escalated and st.session_state.summary:
            s = st.session_state.summary
            st.markdown(f"**Customer:** {s.get('customer', 'unknown')}")
            st.markdown(f"**Status:** {s.get('status', 'unknown')}")
            st.markdown(f"**Next:** {s.get('next', 'review manually')}")
        else:
            st.caption("Appears if conversation is escalated.")
