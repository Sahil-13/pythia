import os
from datetime import datetime
from typing import Dict, List, Optional

from dotenv import load_dotenv
import streamlit as st
from streamlit.runtime.secrets import Secrets, StreamlitSecretNotFoundError
import pandas as pd

from db import (
    delete_run,
    fetch_latest_run,
    fetch_run_with_messages,
    fetch_runs,
    init_db,
    save_run,
)
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


def get_shared_password() -> str:
    try:
        secrets: Optional[Secrets] = st.secrets
        secret_pw = secrets.get("APP_PASSWORD", "") if secrets else ""
    except StreamlitSecretNotFoundError:
        secret_pw = ""
    return secret_pw or os.getenv("APP_PASSWORD", "")


def init_session_state() -> None:
    defaults: Dict[str, List[Dict[str, str]]] = {
        "messages": [],
        "latest_df": None,
        "latest_json": None,
        "latest_summary": None,
        "latest_topic": None,
        "run_history": [],
        "auth_ok": False,
        "db_ready": False,
        "db_checked": False,
        "db_error": "",
        "selected_run_id": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def sidebar_controls():
    st.sidebar.header("Controls")
    api_key_input = st.sidebar.text_input("Perplexity API Key", type="password")
    try:
        secrets: Optional[Secrets] = st.secrets
        secret_key = secrets.get("PERPLEXITY_API_KEY") if secrets else None
    except StreamlitSecretNotFoundError:
        secret_key = None
    env_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key_input and secret_key:
        st.sidebar.caption("Using PERPLEXITY_API_KEY from Streamlit secrets.")
    elif not api_key_input and env_key:
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

    if st.session_state.get("db_ready"):
        runs = fetch_runs(limit=20)
        options = ["(latest)"] + [f"Run {r['id']} • {r['topic'] or '(no topic)'}" for r in runs]
        selection = st.sidebar.selectbox("Saved runs", options, index=0, key="runs_selectbox")
        if selection != "(latest)":
            try:
                run_idx = options.index(selection) - 1
                run_id = runs[run_idx]["id"]
                run, msgs, items = fetch_run_with_messages(run_id)
                if run and msgs:
                    st.session_state.messages = [{"role": m["role"], "content": m["content"]} for m in msgs]
                    st.session_state.latest_summary = run.get("summary")
                    st.session_state.latest_json = run.get("raw_json")
                    st.session_state.latest_topic = run.get("topic")
                    st.session_state.latest_df = pd.DataFrame(items) if items else None
                    st.session_state.selected_run_id = run_id
                else:
                    st.sidebar.caption("No messages in this run.")
            except Exception as exc:
                st.sidebar.caption(f"Could not load run: {exc}")
        else:
            st.session_state.selected_run_id = None

    if st.sidebar.button("Clear chat / reset"):
        st.session_state.messages = []
        st.session_state.latest_df = None
        st.session_state.latest_json = None
        st.session_state.latest_summary = None
        st.session_state.latest_topic = None
        st.session_state.run_history = []
        st.session_state.auth_ok = False
        st.session_state.db_checked = False
        st.rerun()

    if st.session_state.get("db_ready") and st.session_state.get("selected_run_id"):
        if st.sidebar.button("Delete selected run", type="primary"):
            try:
                delete_run(st.session_state.selected_run_id)
                st.session_state.selected_run_id = None
                st.session_state.messages = []
                st.session_state.latest_df = None
                st.session_state.latest_json = None
                st.session_state.latest_summary = None
                st.session_state.latest_topic = None
                st.session_state.run_history = []
                st.rerun()
            except Exception as exc:
                st.sidebar.caption(f"Could not delete run: {exc}")

    resolved_key = api_key_input or secret_key or env_key
    return resolved_key, model, max_items, time_window, output_style, search_mode


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

    # Ensure last history message is assistant (or none) before appending current user.
    while cleaned and cleaned[-1]["role"] == "user":
        cleaned.pop()

    api_messages: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    api_messages.extend(cleaned)
    api_messages.append({"role": "user", "content": user_prompt})
    return api_messages


def ensure_db_ready() -> None:
    if st.session_state.get("db_checked"):
        return
    try:
        init_db()
        st.session_state.db_ready = True
        st.session_state.db_error = ""
    except Exception as exc:  # pragma: no cover - surface to UI
        st.session_state.db_ready = False
        st.session_state.db_error = str(exc)
    finally:
        st.session_state.db_checked = True


def load_latest_run_into_session() -> None:
    if st.session_state.messages:
        return
    if not st.session_state.get("db_ready"):
        return
    try:
        run, msgs, items = fetch_latest_run()
    except Exception:
        return
    if run and msgs:
        st.session_state.messages = [{"role": m["role"], "content": m["content"]} for m in msgs]
        st.session_state.latest_summary = run.get("summary")
        st.session_state.latest_json = run.get("raw_json")
        st.session_state.latest_topic = run.get("topic")
        st.session_state.latest_df = pd.DataFrame(items) if items else None


def main():
    init_session_state()
    shared_pw = get_shared_password()

    if not st.session_state.get("auth_ok", False):
        st.title("Research Desk")
        st.caption("Enter password to continue.")
        pw_input = st.text_input("App password", type="password")
        if st.button("Unlock"):
            if shared_pw and pw_input == shared_pw:
                st.session_state.auth_ok = True
                st.rerun()
            else:
                st.error("Invalid password.")
        if not shared_pw:
            st.info("No APP_PASSWORD configured in secrets; set one to enable access control.")
        return

    ensure_db_ready()
    load_latest_run_into_session()

    api_key, model, max_items, time_window, output_style, search_mode = sidebar_controls()

    st.title("Research Desk")
    st.caption("Perplexity Sonar-powered research with structured outputs.")
    mode_label = "Reddit-only" if search_mode == "reddit" else "Default / Web"
    st.caption(f"Active search mode: {mode_label}")
    if st.session_state.get("db_ready"):
        st.caption("Database: connected")
    elif st.session_state.get("db_error"):
        st.caption(f"Database disabled: {st.session_state.db_error}")

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
            st.session_state.latest_summary = parsed.summary
            st.session_state.latest_topic = topic_input
            st.session_state.run_history.append(
                {
                    "topic": topic_input,
                    "model": model,
                    "timestamp": datetime.utcnow().isoformat(),
                    "items": len(df),
                }
            )

            if st.session_state.get("db_ready"):
                try:
                    save_run(
                        topic=topic_input,
                        model=model,
                        search_mode=search_mode,
                        time_window=time_window if time_window != "None" else "",
                        output_style=output_style,
                        messages=st.session_state.messages,
                        summary=parsed.summary,
                        raw_json=raw_json,
                        items=[item.model_dump() for item in parsed.items],
                    )
                except Exception as exc:
                    st.warning(f"Could not save chat to database: {exc}")

            st.session_state.messages.append({"role": "assistant", "content": parsed.summary})

    if st.session_state.latest_df is None:
        st.info("Enter a topic to run research. Choose model and options from the sidebar.")
    elif st.session_state.latest_summary:
        st.subheader("Research Summary")
        st.markdown(st.session_state.latest_summary)

        st.subheader("Table: Sources & Video Angles")
        st.dataframe(st.session_state.latest_df, use_container_width=True, hide_index=True)

        st.subheader("Downloads")
        col1, col2, col3 = st.columns(3)
        topic_for_download = st.session_state.latest_topic or "research"
        with col1:
            st.download_button(
                "Download CSV",
                data=to_csv_bytes(st.session_state.latest_df),
                file_name="research_table.csv",
                mime="text/csv",
            )
        with col2:
            st.download_button(
                "Download JSON",
                data=to_json_bytes(st.session_state.latest_json or {}),
                file_name="research_raw.json",
                mime="application/json",
            )
        with col3:
            st.download_button(
                "Download Brief (Markdown)",
                data=brief_markdown(
                    topic_for_download,
                    st.session_state.latest_summary,
                    st.session_state.latest_df,
                    model,
                ),
                file_name="research_brief.md",
                mime="text/markdown",
            )


if __name__ == "__main__":
    main()

