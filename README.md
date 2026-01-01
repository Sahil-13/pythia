# Pythia – Research Desk

Pythia is a Streamlit “Research Desk” that uses Perplexity Sonar (Pro or Deep Research) via the OpenAI-compatible API to produce structured research briefs with citations. It returns a summary plus a table of sources and video angles, with CSV/JSON/Markdown downloads and in-session chat history.

## Features

- Perplexity Sonar models: `sonar-pro` and `sonar-deep-research`.
- Structured outputs enforced by JSON schema (summary + items).
- Streamlit UI with sidebar controls (API key, model, max items, time window, output style).
- Downloads: CSV, JSON, and Markdown brief.
- In-memory session state for chat history and last run (no DB in MVP).

## Requirements

- Python 3.9+ (works with `pip` or `conda` environments).
- Perplexity API key (`PERPLEXITY_API_KEY`).

## Setup

1. Clone and enter the project:

```bash
git clone https://github.com/yourusername/pythia.git
cd pythia
```

1. Install dependencies (pip):

```bash
pip install -r requirements.txt
```

Or with conda:

```bash
conda create -n pythia python=3.11
conda activate pythia
pip install -r requirements.txt
```

1. Provide your Perplexity API key (environment or Streamlit sidebar):

```env
PERPLEXITY_API_KEY=ppx-...
```

## Run

```bash
streamlit run app.py
```

Then open the provided local URL. Enter a topic, pick a model, and run research to see the summary, table, and download options.

## Notes

- If structured output parsing fails, the app surfaces the raw response and offers a “retry with strict JSON.”
- Future-ready for containerization or persistence (e.g., SQLite), but current MVP is in-memory only.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
