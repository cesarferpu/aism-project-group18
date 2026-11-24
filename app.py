import pandas as pd
import streamlit as st
from agents import OLLAMA_MODEL, OLLAMA_URL, run_scouting_pipeline
from scout import load_players
from validator import validate_players

st.set_page_config(page_title="Football Scouting Assistant", page_icon="⚽", layout="wide")
st.title("⚽ Football Scouting Assistant")
st.caption("Local multi-agent system · Ollama + Qwen 2.5 1.5B · No paid API")
st.info("Educational project: the database contains 67 fictional football players. The language model runs locally on your computer.")

with st.sidebar:
    st.header("Local configuration")
    st.code(f"Model: {OLLAMA_MODEL}\nServer: {OLLAMA_URL}")
    st.caption("Make sure Ollama is running and the model is installed.")
    if st.button("Check Ollama connection", use_container_width=True):
        try:
            import requests
            response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
            response.raise_for_status()
            models = [m.get("name") for m in response.json().get("models", [])]
            st.success("Ollama is running.")
            st.write("Installed models:", models or "None")
        except Exception as exc:
            st.error(f"Connection failed: {exc}")

all_players = load_players()
st.subheader("New recruitment request")
request_text = st.text_area(
    "Describe the club's requirements in natural language",
    value="We are looking for a striker under the age of 25 years, with at least 8 goals and a maximum value of 25 million euros.",
    height=110,
    help="Example: We need a centre-back under 23 years old, with at least 20 appearances and a maximum budget of 15 million euros."
)
run = st.button("🚀 Run multi-agent system", type="primary", use_container_width=True)

if run:
    if not request_text.strip():
        st.warning("Please enter a recruitment request before running the system.")
    else:
        with st.spinner("The three agents are working. On CPU, this may take several minutes..."):
            try:
                result = run_scouting_pipeline(request_text.strip(), all_players, validate_players)
                st.session_state["pipeline_result"] = result
            except Exception as exc:
                st.error(str(exc))
                st.info("Make sure Ollama is running. In PowerShell, run: ollama pull qwen2.5:1.5b")

result = st.session_state.get("pipeline_result")
if result:
    profile = result["profile"]
    candidates = result["candidates"]
    report = result["report"]
    st.divider()
    st.header("Pipeline results")
    st.subheader("1. Club Analyst — Extracted profile")
    st.json(profile)
    st.subheader("2. Player Scout + Python Validator — Eligible candidates")
    c1, c2, c3 = st.columns(3)
    c1.metric("Players in CSV", len(all_players))
    c2.metric("Validated candidates", len(candidates))
    c3.metric("Recommendations", len(report.get("recommendations", [])))
    if candidates:
        df = pd.DataFrame(candidates)
        labels = {"name":"Player", "position":"Position", "age":"Age", "nationality":"Nationality", "club":"Club", "league":"League", "appearances":"Appearances", "minutes":"Minutes", "goals":"Goals", "assists":"Assists", "goals_per90":"Goals/90", "assists_per90":"Assists/90", "height_cm":"Height (cm)", "preferred_foot":"Preferred foot", "contract_until":"Contract until", "value_m":"Value (€M)"}
        st.dataframe(df.rename(columns=labels)[list(labels.values())], use_container_width=True, hide_index=True)
        st.download_button("⬇️ Download candidates CSV", df.to_csv(index=False).encode("utf-8-sig"), "scouting_candidates.csv", "text/csv")
    else:
        st.warning("No players satisfy all mandatory requirements. No fictional recommendations will be generated.")
    st.subheader("3. Recruitment Advisor — Final report")
    st.write(report.get("summary", ""))
    for rec in report.get("recommendations", []):
        with st.expander(f"#{rec.get('rank', '?')} · {rec.get('name', 'Candidate')}", expanded=True):
            st.write(rec.get("rationale", ""))
            left, right = st.columns(2)
            left.markdown("**Strengths**")
            for item in rec.get("strengths", []):
                left.write(f"• {item}")
            right.markdown("**Risks / limitations**")
            for item in rec.get("risks", []):
                right.write(f"• {item}")
    with st.expander("View agent exchange data (JSON)"):
        st.json({"profile": profile, "validated_candidates": candidates, "final_report": report})
    st.caption("Audit log: agent inputs and outputs are stored in agents_execution.log.")

st.divider()
st.caption("Academic demonstration tool. The database contains fictional data. Recommendations depend on the CSV and local model quality and require human review.")
