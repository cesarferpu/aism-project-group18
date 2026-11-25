# Football Scouting Assistant — Version 4.5

**Course:** Intelligent Agents and Multi-Agent Systems (AISM) — Final Project  
**Group members:** César Fernández Puerma and Óscar David Imbaquingo Yugsi

## 1. Project overview

The Football Scouting Assistant is a local multi-agent application that turns a football club's recruitment request, written in natural language, into a shortlist of up to three suitable players. It uses three specialised LLM agents, a CSV dataset of 67 fictional players, and deterministic Python filtering, validation, and ranking. The application runs locally with Ollama and does not require a paid API, account, or API key.

## 2. Multi-agent architecture

```text
User request
    |
    v
Agent 1 — Club Analyst (LLM)
    Extracts recruitment requirements as structured JSON
    |
    v
Agent 2 — Player Scout (LLM + Python + CSV)
    Searches and prioritises players from data/players.csv
    |
    v
Python Validator
    Independently checks every mandatory requirement
    |
    v
Python canonical ranking
    Orders all validated candidates deterministically
    |
    v
Agent 3 — Recruitment Advisor (LLM)
    Explains the already-ranked top three; cannot change the ranking
    |
    v
Final report and candidate table
```

### Agent responsibilities

1. **Agent 1 — Club Analyst:** interprets the user's natural-language request and returns a structured profile. Python checks the extracted constraints against the original request, removes unsupported constraints that the small model may have invented, and applies the explicit wording rules for age and budget.
2. **Agent 2 — Player Scout:** Python first filters the CSV using the mandatory requirements. The LLM then selects candidate names from the supplied records, and Python checks those names against the source dataset. If the model returns malformed or unusable output, the deterministic pre-filter provides a fallback.
3. **Python Validator:** independently enforces mandatory constraints before recommendations are produced. A player who fails a mandatory condition, or has missing data for a constrained field, is rejected.
4. **Agent 3 — Recruitment Advisor:** receives the candidates after Python has established their canonical order. It generates explanations, strengths, and risks using the supplied statistics. It cannot choose, add, remove, or reorder the recommended players. If its explanation is unavailable or invalid, deterministic explanations are used without changing the ranking.

All three agents use the same local model but have separate roles, prompts, inputs, outputs, and log entries. They communicate through a fixed sequential workflow using structured data. Python is authoritative for mandatory constraints and the final ranking.

### Strict and inclusive limits

The application distinguishes strict limits from inclusive limits:

| User wording | Rule applied |
|---|---|
| `under 25`, `younger than 25`, `below 25`, `less than 25` | `age < 25` |
| `at most 25`, `no older than 25`, `maximum age 25`, `up to 25` | `age <= 25` |
| `budget below €20 million`, `under 20 million`, `less than 20 million` | `value < 20` |
| `maximum value of 20 million`, `budget of 20 million` | `value <= 20` |

These rules are checked in Python. The language model cannot override them.

### Ranking rule

The validated-candidates table and the final report use the same canonical Python ranking:

1. Goal contributions per 90 minutes, in descending order.
2. Minutes played, in descending order, as the secondary criterion.

The application selects up to three players from this ordered list. Agent 3 only writes explanations for those players. If an explanation cannot be generated, the fallback explanation is attached to the same player and the order remains unchanged.

## 3. Dataset

The project includes `data/players.csv`, a self-contained dataset of **67 fictional players**. It contains 14 fields: player name, position, age, nationality, club, league, appearances, minutes played, goals, assists, height in centimetres, preferred foot, contract end year, and market value in millions of euros.

The records are invented for educational use and do not describe real footballers or the real transfer market. The application derives per-90-minute indicators, including goals, assists, and goal contributions. No external football database or online data API is required.

## 4. Requirements

- Windows 11 (the supplied setup scripts target Windows).
- Python **3.10 or newer**.
- Approximately **16 GB RAM recommended** for the selected local model.
- Ollama installed locally.
- No dedicated GPU, paid API, account, or API key is required. CPU inference is supported, although responses may take longer.

Python dependencies and their supported version ranges are listed in `requirements.txt`:

- `pandas` — CSV loading and data processing.
- `streamlit` — web interface.
- `requests` — communication with the local Ollama service.
- `json-repair` — recovery from malformed JSON responses.

## 5. Installation

### Step 1 — Install Ollama and download the model

Install Ollama for Windows from [ollama.com/download](https://ollama.com/download). Open PowerShell and download the model used by the project:

```powershell
ollama pull qwen2.5:1.5b
```

Ollama normally runs as a Windows background application. If it is not running, start it from the Start menu. Check that the model is available with:

```powershell
ollama list
```

### Step 2 — Create the Python environment and install dependencies

Open PowerShell in the project directory (the directory containing `requirements.txt`) and run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
```

Alternatively, run `install_windows.bat` from the project directory. If PowerShell blocks script activation, use Command Prompt and run:

```cmd
.venv\Scripts\activate.bat
```

## 6. How to run

Make sure Ollama is running and that `qwen2.5:1.5b` has been downloaded. From the project directory, activate the virtual environment and choose one of the following commands.

### Web application (recommended)

```powershell
py -m streamlit run app.py
```

The application opens at `http://localhost:8501`. Alternatively, run `run_app.bat` after completing installation.

### Command-line application

```powershell
py main.py
```

This runs the default example recruitment request and prints the extracted profile, candidate information, and final report in the terminal.

### Automated tests

```powershell
py -m unittest discover -s tests -v
```

The regression tests use a mocked LLM where appropriate, so they do not require Ollama to be running. The test suite contains **17 tests** covering strict and inclusive age and budget limits, unsupported constraints, malformed or incomplete model output, no-result requests, and ranking consistency.

## 7. Expected output

When the Streamlit application runs correctly, it provides:

1. The recruitment request and the structured profile extracted by Agent 1.
2. The number of records in the dataset, the number of candidates that pass validation, and a table of eligible players. The table can be downloaded as a CSV file.
3. A final report with up to three recommendations, their ranking, rationale, strengths, and risks or limitations.
4. An expandable view of the structured information exchanged during the agent workflow.

For example, a request for a striker under 25 years old, with at least 8 goals and a maximum value of €25 million should apply the strict age rule (`age < 25`), the minimum-goals rule, and the inclusive maximum-value rule. A player aged exactly 25 must not pass the age condition.

For an impossible request, such as a goalkeeper aged at most 18 with at least 50 goals and a maximum value of €1 million, the application should report that no suitable candidate was found and should not invent recommendations.

On a CPU-only computer, the first response can take several minutes while the model loads and generates its answer. Later requests may be faster while the model remains loaded.

## 8. Repository structure

```text
football_scouting_assistant/
├── app.py                         Streamlit web interface
├── main.py                        Command-line entry point
├── agents.py                      Three agent roles, Ollama client, prompts, pipeline and logging
├── scout.py                       CSV loading, derived statistics and Python pre-filter
├── validator.py                   Independent validation of mandatory constraints
├── data/
│   └── players.csv                67 fictional players (14 fields)
├── tests/
│   ├── test_age_constraints.py    Strict and inclusive age tests
│   ├── test_ranking_consistency.py Canonical ranking and fallback tests
│   └── test_robustness.py         Budget, hallucination, no-result and robustness tests
├── requirements.txt               Python dependencies and version ranges
├── install_windows.bat             Creates the virtual environment and installs dependencies
├── run_app.bat                     Starts the Streamlit application
├── .gitignore                      Excludes local environments, logs and temporary files
└── README.md                       Project documentation
```

`agents_execution.log` is created when the application runs. It records agent inputs and outputs, dropped unsupported constraints, and fallback events. It is excluded from version control because it is a runtime log and may contain user-entered recruitment requests. The local `.venv/` directory and Python cache files should also not be committed.

## 9. Configuration, privacy, and limitations

The Ollama connection can be configured with these optional environment variables:

- `OLLAMA_URL` — Ollama server URL; default: `http://localhost:11434`.
- `OLLAMA_MODEL` — model name; default: `qwen2.5:1.5b`.

The model runs locally. Recruitment requests and the fictional dataset are sent to the local Ollama service on the same computer, not to a paid cloud API. An internet connection is needed to install Ollama, download the model, and install Python packages; normal model inference is local.

The Qwen 2.5 1.5B model is small and can make mistakes when extracting requirements or writing explanations. Python filtering and validation are authoritative for mandatory constraints, and Python determines the final ranking. The dataset is fictional and limited in size, and it does not contain every metric required for professional scouting. The system should therefore be treated as an educational prototype, and its recommendations should be reviewed by a human. The request parser supports common numeric requirements; numbers written only as words (for example, `twenty million`) may not be recognised reliably.

If Ollama is not running or the model is unavailable, the application cannot complete the LLM workflow and displays a connection or execution error.

## 10. Use of generative AI

ChatGPT (OpenAI) was used as an assistance tool during project development to draft and revise Python code, diagnose implementation errors, prepare and review tests and help us with the referencing. The group members are responsible for reviewing the code, running the application and tests, checking the results, develop the project documentation and understanding the submitted work.

## 11. Version 4.5 — Ranking consistency

Version 4.5 uses one canonical Python ranking for both the validated-candidates table and the Recruitment Advisor report. The model can explain the selected players but cannot alter their order or replace them. If an LLM explanation is unavailable, deterministic fallback explanations are displayed while the ranking remains unchanged.

The regression suite included in this project was run with:

```text
Ran 17 tests ... OK
```

The tests use a mocked language model for repeatability; they do not replace a separate end-to-end check with Ollama running locally.
