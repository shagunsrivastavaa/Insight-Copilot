"""Streamlit chat interface for the deterministic Insight Copilot assistant."""

from typing import Any

import streamlit as st

from agent.graph import run_query


WELCOME_MESSAGE = (
    "Welcome to Insight Copilot. Ask a question about the Olist dataset, and I'll "
    "summarize the relevant results with the metric definitions and counts."
)
EXAMPLE_QUESTIONS = [
    "What are the top five product categories by item sales?",
    "Show monthly order trends from 2017-01 to 2017-03",
    "What was the late-delivery percentage?",
]

st.set_page_config(page_title="Insight Copilot", layout="centered")
st.markdown(
    """
    <style>
        .block-container {
            max-width: 940px;
            padding-top: 2rem;
            padding-bottom: 5rem;
        }
        [data-testid="stChatMessage"] {
            border-radius: 0.75rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Insight Copilot")
st.caption(
    "Ask about product or category item sales, monthly order trends, and delivery performance in the Olist dataset."
)

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = [
        {"role": "assistant", "content": WELCOME_MESSAGE}
    ]


def _render_assistant_details(message: dict[str, Any]) -> None:
    """Render an answer, its trace, tool results, and any real errors."""
    if message.get("exception"):
        st.error(f"Could not process this question: {message['exception']}")
        state = message.get("state")
    else:
        answer = message.get("content")
        if answer:
            st.markdown(answer)
        state = message.get("state")

    if not isinstance(state, dict):
        return

    with st.expander("Plan & execution trace", expanded=False):
        plan = state.get("plan")
        st.markdown("**Plan**")
        st.write(plan if plan else "No plan was returned.")

        selected_tools = state.get("selected_tools") or []
        st.markdown("**Selected tools**")
        st.write(", ".join(selected_tools) if selected_tools else "No tools selected")

        st.markdown("**Routing explanations**")
        explanations = state.get("reasoning_trace") or []
        if explanations:
            for explanation in explanations:
                st.markdown(f"- {explanation}")
        else:
            st.write("No routing explanation was returned.")
        st.caption("This is a deterministic plan and routing trace; no LLM generates it.")

    tool_results = state.get("tool_results") or {}
    if isinstance(tool_results, dict):
        for tool_name, result in tool_results.items():
            with st.expander(f"Structured results: {tool_name}", expanded=False):
                st.json(result)

    graph_error = state.get("error")
    tool_result_errors = []
    if isinstance(tool_results, dict):
        for tool_name, result in tool_results.items():
            if isinstance(result, dict) and result.get("error"):
                tool_result_errors.append(f"{tool_name}: {result['error']}")

    if graph_error:
        selected_tools = state.get("selected_tools") or []
        label = "Execution error" if selected_tools else "Routing error"
        st.error(f"{label}: {graph_error}")
    elif tool_result_errors:
        st.error("Execution error: " + "; ".join(tool_result_errors))


def _render_message(message: dict[str, Any]) -> None:
    """Render one stored chat message and assistant diagnostics."""
    role = message.get("role", "assistant")
    with st.chat_message(role):
        if role == "user":
            st.markdown(message.get("content", ""))
        else:
            _render_assistant_details(message)


def _process_question(query: str) -> None:
    """Run one submitted question once and store both messages in session state."""
    st.session_state.chat_messages.append({"role": "user", "content": query})
    with st.spinner("Analyzing the question and preparing the results…"):
        try:
            result = run_query(query)
            if not isinstance(result, dict):
                raise TypeError("The graph returned a result that was not a dictionary.")
            answer = result.get("final_answer")
            if not isinstance(answer, str) or not answer.strip():
                assistant_message = {
                    "role": "assistant",
                    "content": "",
                    "exception": "The graph returned without a final answer.",
                    "state": result,
                }
            else:
                assistant_message = {
                    "role": "assistant",
                    "content": answer,
                    "state": result,
                }
        except Exception as exc:
            assistant_message = {
                "role": "assistant",
                "content": "",
                "exception": f"{type(exc).__name__}: {exc}",
            }
    st.session_state.chat_messages.append(assistant_message)


with st.expander("Example questions", expanded=len(st.session_state.chat_messages) == 1):
    st.caption("Select an example to send it, or type your own question below.")
    columns = st.columns(3)
    selected_example = None
    for index, (column, question) in enumerate(zip(columns, EXAMPLE_QUESTIONS)):
        with column:
            if st.button(question, key=f"example_question_{index}", use_container_width=True):
                selected_example = question

for stored_message in st.session_state.chat_messages:
    _render_message(stored_message)

submitted_question = st.chat_input(
    "Ask about product/category sales, monthly orders, or delivery performance"
)
question_to_process = selected_example or submitted_question
if question_to_process:
    _process_question(question_to_process)
    st.rerun()
