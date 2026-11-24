# Football Scouting Assistant — Version 4.4

**Course:** Intelligent Agents and Multi-Agent Systems (AISM) — Final Project
**Group members:** César Fernández Puerma, Óscar David Imbaquingo Yugsi

## What the project does

A local multi-agent system that helps a football club find transfer targets. The user writes a recruitment request in natural language (for example, *"We are looking for a striker under the age of 25 years, with at least 8 goals and a maximum value of 25 million euros."*). Three LLM agents interpret the request, search a CSV of 67 fictional players and write a ranked top-three report, while a deterministic Python validator enforces every hard requirement. Everything runs locally with Ollama: no paid API and no API key.

## Multi-agent architecture

```
User request -> Agent 1 Club Analyst -> Agent 2 Player Scout -> Python Validator -> Agent 3 Recruitment Advisor -> Report
                  (LLM, JSON profile)    (LLM + CSV pre-filter)   (plain code)         (LLM, ranked top 3)
```

1. **Agent 1 — Club Analyst (LLM):** converts the request into a structured JSON profile. Afterwards, Python removes any constraint that cannot be traced to the request text (small models invent filters) and re-reads the explicit wording of age and budget limits.
2. **Agent 2 — Player Scout (LLM + Python/CSV):** a Python pre-filter applies the hard constraints to `data/players.csv`; the LLM then selects candidates among at most 30 records. Names are checked against the source dataset.
3. **Python Validator:** independently enforces every mandatory constraint. A player with missing data for a constrained field is rejected.
4. **Agent 3 — Recruitment Advisor (LLM):** compares only validated players and returns up to three recommendations. Unknown or duplicated names are discarded and ranks are renumbered 1..3 in Python.

The three agents share the same local model but have separate roles, prompts, inputs, outputs and log entries. Agents pass structured JSON to each other.

### Strict vs. inclusive limits

| Wording | Meaning |
|---|---|
| `under 25`, `younger than 25`, `below 25`, `less than 25`, `menor de 25` | age < 25 |
| `at most 25`, `no older than 25`, `maximum age 25`, `up to 25` | age <= 25 |
| `budget below €20 million`, `under 20 million`, `less than 20 million` | value < 20 |
| `maximum value of 20 million`, `budget of 20 million` | value <= 20 |

These rules are applied deterministically after the LLM answer, in the Python pre-filter and in the validator. A model response cannot override them.

## Installation

Requirements: Windows 11 (Linux/macOS also work with the equivalent commands), **Python 3.10+**, about 16 GB RAM recommended, [Ollama](https://ollama.com/download). No GPU, account or API key is needed.

1. Install Ollama and download the model:
   ```powershell
   ollama pull qwen2.5:1.5b
   ```
2. In the project folder, create a virtual environment and install the dependencies:
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   py -m pip install -r requirements.txt
   ```
   Alternatively, run `install_windows.bat` once.

Optional environment variables: `OLLAMA_URL` (default `http://localhost:11434`) and `OLLAMA_MODEL` (default `qwen2.5:1.5b`). If you ever add secrets, keep them in a `.env` file, which is already in `.gitignore`.

## How to run

Make sure Ollama is running, then choose one option:

```powershell
# Web interface (Streamlit)
py -m streamlit run app.py        # or run_app.bat

# Command line (runs the default example request)
py main.py

# Regression tests (no Ollama needed: the LLM is mocked)
py -m unittest discover -s tests -v
```

On CPU the first response can take several minutes while the model loads.

## Expected output

**Streamlit** (opens at `http://localhost:8501`) shows, in order:
1. the extracted JSON profile (position `ST`, `max_age` 25 with `age_limit_exclusive: true`, `min_goals` 8, `max_value_m` 25);
2. the number of players in the CSV (67), the number of validated candidates and a table of them, with a button to download them as CSV;
3. the final report: a summary and up to three ranked recommendations with rationale, strengths and risks;
4. an expandable view with the JSON exchanged between agents.

**Command line** prints the extracted profile, the number of validated candidates and the report dictionary.

**No-result case:** for *"a goalkeeper aged 18 with at least 50 goals and a maximum value of 1 million euros"* the system shows a warning that no player satisfies the requirements and generates no recommendations.

**Tests:** `Ran 17 tests ... OK`.

## Repository structure

```
football_scouting_assistant/
├── app.py                 Streamlit interface
├── main.py                Command-line entry point
├── agents.py              Agents 1-3, Ollama client, JSON parsing, request-vs-profile checks, pipeline, logging
├── scout.py               CSV loading, per-90 indicators and deterministic hard-constraint filter
├── validator.py           Independent validator of mandatory constraints
├── data/players.csv       67 fictional players (14 columns)
├── tests/                 Regression tests (age/budget semantics, hallucinated filters, ranking, no-result case)
├── requirements.txt       Python dependencies
├── install_windows.bat    Creates the virtual environment and installs dependencies
├── run_app.bat            Starts the Streamlit app
├── agents_execution.log   Audit log of every agent input/output (created at run time)
└── README.md
```

## Audit and limitations

All agent inputs, outputs, fallback events and dropped constraints are written to `agents_execution.log`. The dataset is fictional and does not represent the real transfer market. The 1.5B model can make extraction or explanation mistakes; the deterministic Python filters and validator are authoritative for mandatory constraints, and human review remains necessary. If Ollama is not running, the pipeline stops with an error message instead of producing a report. Numbers written as words ("twenty million") are not recognised by the request check.

## Use of generative AI

(Declare here, and in the report, how generative AI tools were used to write or code this project, as required by the submission guidelines.)


## Version 4.4 — Consistent ranking

The validated-candidates table and Recruitment Advisor report now share one
canonical Python ranking: goal contributions per 90 minutes, followed by
minutes played (descending). The LLM only supplies explanations for those
already-ranked players; its generated order cannot change the ranking. If the
LLM explanation is unavailable, deterministic explanations are shown without
changing player order.

Run automated checks with:

```powershell
python -m unittest discover -s tests -v
```
