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

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "display_messages" not in st.session_state:
    st.session_state.display_messages = []
if "sentiment" not in st.session_state:
    st.session_state.sentiment = None
if "escalated" not in st.session_state:
    st.session_state.escalated = False
if "summary" not in st.session_state:
    st.session_state.summary = None
if "system_prompt" not in st.session_state:
    st.session_state.system_prompt = build_system_prompt(CONFIG)

chat_col, monitor_col = st.columns([2, 1], gap="large")

with chat_col:
    st.subheader("Bookly Support")

    # Initial greeting
    if not st.session_state.display_messages:
        st.session_state.display_messages.append({
            "role": "assistant",
            "content": "Hi! How can I help you today?",
        })

    # Render conversation
    for msg in st.session_state.display_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Input (disabled after escalation)
    if st.session_state.escalated:
        st.info("Conversation ended — handed off to support team.")
    else:
        user_input = st.chat_input("Type your message...")
        if user_input:
            st.session_state.display_messages.append({
                "role": "user",
                "content": user_input,
            })

            # Fast-path keyword escalation
            if check_escalation_keywords(user_input):
                handoff = CONFIG["escalation"]["handoff_message"]
                st.session_state.display_messages.append({
                    "role": "assistant",
                    "content": handoff,
                })
                st.session_state.messages.append({"role": "user", "content": user_input})
                st.session_state.summary = generate_escalation_summary(
                    st.session_state.messages,
                    "user requested a human agent",
                )
                st.session_state.escalated = True
                st.rerun()

            with st.spinner("Thinking..."):
                response_text, verdict, sentiment, agent_helped = handle_turn(
                    user_input,
                    st.session_state.messages,
                    st.session_state.system_prompt,
                )

            st.session_state.sentiment = sentiment
            st.session_state.display_messages.append({
                "role": "assistant",
                "content": response_text,
            })

            if verdict == "ESCALATE":
                st.session_state.summary = generate_escalation_summary(
                    st.session_state.messages,
                    "supervisor or tool signaled escalation",
                )
                st.session_state.escalated = True

            st.rerun()

with monitor_col:
    st.subheader("Support View")
    st.caption("Internal - not shown to customer")

    # Sentiment gauge
    if st.session_state.sentiment is not None:
        s = st.session_state.sentiment
        if s >= 0.7:
            label, color = "Positive", "green"
        elif s >= 0.5:
            label, color = "Neutral", "gray"
        elif s >= 0.3:
            label, color = "Frustrated", "orange"
        else:
            label, color = "Very frustrated", "red"

        st.metric("Customer sentiment", f"{s:.2f}", label)
        st.progress(s)
    else:
        st.metric("Customer sentiment", "—", "waiting for first message")

    st.divider()

    # Escalation summary
    if st.session_state.escalated and st.session_state.summary:
        st.markdown("**Handoff summary**")
        s = st.session_state.summary
        st.markdown(f"**Customer:** {s.get('customer', 'unknown')}")
        st.markdown(f"**Status:** {s.get('status', 'unknown')}")
        st.markdown(f"**Next:** {s.get('next', 'review manually')}")
    else:
        st.markdown("**Handoff summary**")
        st.caption("Will appear if conversation is escalated.")
