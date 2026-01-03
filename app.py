import os
from datetime import datetime
from typing import Dict, List

from dotenv import load_dotenv
import streamlit as st

from perplexity_client import PerplexityClient
from prompts import SYSTEM_PROMPT, build_user_prompt
from utils import (
    brief_markdown,
    items_to_dataframe,
    parse_research_response,
    to_csv_bytes,
    to_json_bytes,
)


load_dotenv()  # load .env if present
load_dotenv("secrets.env", override=False)  # optional secrets file; won't override env vars

st.set_page_config(page_title="Pythia", layout="wide")


def init_session_state() -> None:
    defaults: Dict[str, List[Dict[str, str]]] = {
        "messages": [],
        "latest_df": None,
        "latest_json": None,
        "run_history": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def sidebar_controls():
    st.sidebar.header("Controls")
    api_key_input = st.sidebar.text_input("Perplexity API Key", type="password")
    env_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key_input and env_key:
        st.sidebar.caption("Using PERPLEXITY_API_KEY from environment.")

    model = st.sidebar.radio("Model", options=["sonar-pro", "sonar-deep-research"], index=0)
    max_items = st.sidebar.slider("Max items", min_value=5, max_value=40, value=15, step=1)
    time_window = st.sidebar.selectbox("Time window (optional)", ["None", "Last week", "Last month", "Last year"])
    output_style = st.sidebar.selectbox(
        "Output style",
        ["Creator Research Brief", "Source Table Only", "Contrarian / Debate angles"],
        index=0,
    )
    search_mode_label = st.sidebar.radio("Search mode", ["Default (Web)", "Reddit-only"], index=0)
    search_mode = "reddit" if "Reddit" in search_mode_label else "default"
    st.session_state["search_mode"] = search_mode

    if st.sidebar.button("Clear chat / reset"):
        st.session_state.messages = []
        st.session_state.latest_df = None
        st.session_state.latest_json = None
        st.session_state.run_history = []
        st.rerun()

    return api_key_input or env_key, model, max_items, time_window, output_style, search_mode


def render_chat():
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])


def build_api_messages(user_prompt: str) -> List[Dict[str, str]]:
    raw_history = [{"role": m.get("role"), "content": m.get("content")} for m in st.session_state.messages[:-1]]

    # Enforce user/assistant alternation after the system prompt to satisfy API requirements.
    cleaned: List[Dict[str, str]] = []
    last_role: Optional[str] = None
    for m in raw_history:
        if not m.get("role") or not m.get("content"):
            continue
        if last_role == m["role"]:
            continue
        cleaned.append(m)
        last_role = m["role"]

    # Drop leading assistant messages if present (API expects user first after system).
    while cleaned and cleaned[0]["role"] != "user":
        cleaned.pop(0)

    api_messages: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    api_messages.extend(cleaned)
    api_messages.append({"role": "user", "content": user_prompt})
    return api_messages


def main():
    init_session_state()
    api_key, model, max_items, time_window, output_style, search_mode = sidebar_controls()

    st.title("Research Desk")
    st.caption("Perplexity Sonar-powered research with structured outputs.")
    mode_label = "Reddit-only" if search_mode == "reddit" else "Default / Web"
    st.caption(f"Active search mode: {mode_label}")

    render_chat()

    topic_input = st.chat_input("Enter a topic to research")
    if topic_input:
        st.session_state.messages.append({"role": "user", "content": topic_input})
        with st.chat_message("assistant"):
            if not api_key:
                st.warning("Please provide a Perplexity API key in the sidebar.")
                return

            client = PerplexityClient(api_key=api_key)
            user_prompt = build_user_prompt(
                topic=topic_input,
                model=model,
                max_items=max_items,
                time_window=time_window if time_window != "None" else "",
                output_style=output_style,
                search_mode=search_mode,
            )
            api_messages = build_api_messages(user_prompt=user_prompt)

            with st.spinner("Researching with Perplexity..."):
                try:
                    raw_text = client.run_chat_completion(
                        messages=api_messages,
                        model=model,
                    )
                except Exception as exc:  # broad to surface nicely
                    st.error(f"Research failed: {exc}")
                    return
                try:
                    parsed, raw_json = parse_research_response(raw_text)
                except Exception as exc:
                    st.error(f"Could not parse structured output: {exc}")
                    with st.expander("Raw response"):
                        st.code(raw_text or "", language="json")
                    retry_key = f"retry_strict_{len(st.session_state.run_history)}"
                    if st.button("Retry with stricter formatting", key=retry_key):
                        strict_prompt = user_prompt + "\n\nReturn ONLY valid JSON adhering to the schema, no prose."
                        strict_messages = build_api_messages(user_prompt=strict_prompt)
                        with st.spinner("Retrying with strict JSON..."):
                            try:
                                raw_text = client.run_chat_completion(
                                    messages=strict_messages,
                                    model=model,
                                )
                                parsed, raw_json = parse_research_response(raw_text)
                            except Exception as exc2:
                                st.error(f"Retry failed: {exc2}")
                                with st.expander("Raw retry response"):
                                    st.code(raw_text or "", language="json")
                                return
                    else:
                        return

            df = items_to_dataframe(parsed.items)
            st.session_state.latest_df = df
            st.session_state.latest_json = raw_json
            st.session_state.run_history.append(
                {
                    "topic": topic_input,
                    "model": model,
                    "timestamp": datetime.utcnow().isoformat(),
                    "items": len(df),
                }
            )

            st.subheader("Research Summary")
            st.markdown(parsed.summary)

            st.subheader("Table: Sources & Video Angles")
            st.dataframe(df, use_container_width=True, hide_index=True)

            st.subheader("Downloads")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.download_button(
                    "Download CSV",
                    data=to_csv_bytes(df),
                    file_name="research_table.csv",
                    mime="text/csv",
                )
            with col2:
                st.download_button(
                    "Download JSON",
                    data=to_json_bytes(raw_json),
                    file_name="research_raw.json",
                    mime="application/json",
                )
            with col3:
                st.download_button(
                    "Download Brief (Markdown)",
                    data=brief_markdown(topic_input, parsed.summary, df, model),
                    file_name="research_brief.md",
                    mime="text/markdown",
                )

            st.session_state.messages.append({"role": "assistant", "content": parsed.summary})

    if st.session_state.latest_df is None:
        st.info("Enter a topic to run research. Choose model and options from the sidebar.")
    else:
        st.markdown("### Last run")
        st.dataframe(st.session_state.latest_df, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()

