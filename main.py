from agents import run_scouting_pipeline
from scout import load_players
from validator import validate_players

if __name__ == "__main__":
    request = "We are looking for a striker under the age of 25 years, with at least 8 goals and a maximum value of 25 million euros."
    result = run_scouting_pipeline(request, load_players(), validate_players)
    print("\n--- FOOTBALL SCOUTING ASSISTANT · LOCAL MULTI-AGENT SYSTEM ---")
    print("Extracted profile:", result["profile"])
    print("Validated candidates:", len(result["candidates"]))
    print("Report:", result["report"])
