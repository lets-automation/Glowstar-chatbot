"""
streamlit_app.py
----------------
A simple internal DEMO chat UI for showing the agent to the client.

This is NOT the production frontend (the client builds that in React).
It's a quick, throwaway chat screen that calls the same agent.ask().

Run from the project root with:
    & C:\\Glowstar_chatbot\\venv\\Scripts\\streamlit.exe run demo/streamlit_app.py
"""

import os
import sys

# Make the project root importable when Streamlit runs this file directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st  # noqa: E402

from app.config import settings  # noqa: E402

st.set_page_config(page_title="Aastha ERP Assistant", page_icon="💎")
st.title("💎 Aastha ERP Assistant")
st.caption("Ask questions about packets, labour, jangad, attendance, and more.")

# Warn if the AI key isn't set yet.
if not settings.GROQ_API_KEY:
    st.warning(
        "No GROQ_API_KEY in .env — answers are disabled until the key is added. "
        "The UI still works; it just can't call the LLM yet."
    )

# Keep the conversation in session state.
if "messages" not in st.session_state:
    st.session_state.messages = []

# Replay history.
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input.
if prompt := st.chat_input("e.g. How many packets are on jangad?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        if not settings.GROQ_API_KEY:
            st.markdown("⚠️ AI key not configured — add GROQ_API_KEY to .env.")
        else:
            from app.agent.agent import ask

            with st.spinner("Thinking..."):
                result = ask(prompt)
            st.markdown(result["answer"])
            if result["sql_used"]:
                with st.expander("See the SQL the assistant ran"):
                    for sql in result["sql_used"]:
                        st.code(sql, language="sql")
            st.session_state.messages.append(
                {"role": "assistant", "content": result["answer"]}
            )
