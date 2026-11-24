from pathlib import Path
import pandas as pd

DATA_FILE = Path(__file__).resolve().parent / "data" / "players.csv"
REQUIRED_COLUMNS = ["name", "position", "age", "nationality", "club", "league", "appearances", "minutes", "goals", "assists", "height_cm", "preferred_foot", "contract_until", "value_m"]


def load_players():
    """Load the local CSV and calculate transparent per-90-minute indicators."""
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Player database not found: {DATA_FILE}")
    players = pd.read_csv(DATA_FILE)
    missing = [column for column in REQUIRED_COLUMNS if column not in players.columns]
    if missing:
        raise ValueError("Missing columns in players.csv: " + ", ".join(missing))
    numeric = ["age", "appearances", "minutes", "goals", "assists", "height_cm", "contract_until", "value_m"]
    for column in numeric:
        players[column] = pd.to_numeric(players[column], errors="coerce")
    players = players.dropna(subset=["name", "position"])
    safe_minutes = players["minutes"].replace(0, pd.NA)
    players["goals_per90"] = (players["goals"] / safe_minutes * 90).fillna(0).round(2)
    players["assists_per90"] = (players["assists"] / safe_minutes * 90).fillna(0).round(2)
    players["goal_contributions_per90"] = (players["goals_per90"] + players["assists_per90"]).round(2)
    return players.fillna("").to_dict(orient="records")


def filter_players(criteria, players=None):
    """Apply only explicit hard constraints; missing criteria do not filter data."""
    if players is None:
        players = load_players()
    result = list(players)
    for field in ("position", "nationality", "club", "league"):
        value = criteria.get(field)
        if value not in (None, "", "Any", "Cualquiera"):
            result = [p for p in result if str(p.get(field)) == str(value)]
    for criterion, column in (("min_goals", "goals"), ("min_assists", "assists"), ("min_appearances", "appearances"), ("min_minutes", "minutes")):
        value = criteria.get(criterion)
        if value is not None:
            result = [p for p in result if _number(p.get(column)) is not None and _number(p.get(column)) >= float(value)]
    age_limit = criteria.get("max_age")
    if age_limit is not None:
        if criteria.get("age_limit_exclusive", False):
            result = [p for p in result if _number(p.get("age")) is not None and _number(p.get("age")) < float(age_limit)]
        else:
            result = [p for p in result if _number(p.get("age")) is not None and _number(p.get("age")) <= float(age_limit)]
    value_limit = criteria.get("max_value_m")
    if value_limit is not None:
        if criteria.get("value_limit_exclusive", False):
            result = [p for p in result if _number(p.get("value_m")) is not None and _number(p.get("value_m")) < float(value_limit)]
        else:
            result = [p for p in result if _number(p.get("value_m")) is not None and _number(p.get("value_m")) <= float(value_limit)]
    height_limit = criteria.get("max_height_cm")
    if height_limit is not None:
        result = [p for p in result if _number(p.get("height_cm")) is not None and _number(p.get("height_cm")) <= float(height_limit)]
    return sorted(result, key=lambda p: (_number(p.get("goal_contributions_per90")) or 0, _number(p.get("minutes")) or 0), reverse=True)


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def player_scout(criteria):
    """Backward-compatible deterministic CSV search used by tests/CLI."""
    return filter_players(criteria)
