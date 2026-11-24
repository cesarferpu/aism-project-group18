"""Three LLM-backed agents orchestrated through a local Ollama model.
All agent exchanges are logged to agents_execution.log for auditability.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import requests

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")
LOG_FILE = os.path.join(os.path.dirname(__file__), "agents_execution.log")

logger = logging.getLogger("football_scouting_agents")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
    logger.addHandler(handler)

POSITIONS = {"GK", "CB", "DM", "CM", "RW", "LW", "ST"}
CRITERIA_SCHEMA = {
    "type": "object",
    "properties": {
        "position": {"type": ["string", "null"], "enum": ["GK", "CB", "DM", "CM", "RW", "LW", "ST", None]},
        "max_age": {"type": ["integer", "null"]},
        "age_limit_exclusive": {"type": "boolean"},
        "max_value_m": {"type": ["number", "null"]},
        "value_limit_exclusive": {"type": "boolean"},
        "min_goals": {"type": ["integer", "null"]},
        "min_assists": {"type": ["integer", "null"]},
        "min_appearances": {"type": ["integer", "null"]},
        "min_minutes": {"type": ["integer", "null"]},
        "nationality": {"type": ["string", "null"]},
        "league": {"type": ["string", "null"]},
        "club": {"type": ["string", "null"]},
        "max_height_cm": {"type": ["integer", "null"]},
        "soft_preferences": {"type": "array", "items": {"type": "string"}},
        "original_request": {"type": "string"}
    },
    "required": ["position", "max_age", "age_limit_exclusive", "max_value_m", "min_goals", "min_assists", "min_appearances", "min_minutes", "nationality", "league", "club", "max_height_cm", "soft_preferences", "original_request"]
}


def _log(agent: str, direction: str, payload: Any) -> None:
    logger.info("%s %s: %s", agent, direction, json.dumps(payload, ensure_ascii=False, default=str))


def ollama_chat(agent: str, system_prompt: str, user_payload: Any, *, json_mode: bool = False, temperature: float = 0.1) -> str:
    """Call the locally running Ollama server; no cloud API or API key is used."""
    body = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False) if not isinstance(user_payload, str) else user_payload},
        ],
        "stream": False,
        "options": {"temperature": temperature, "num_ctx": 2048, "num_predict": 350},
        "keep_alive": "10m",
    }
    if json_mode:
        body["format"] = "json"
    _log(agent, "INPUT", {"model": OLLAMA_MODEL, "messages": body["messages"]})
    try:
        response = requests.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=(10, 600))
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(
            "Ollama did not complete the response within the allowed time. "
            "Make sure Ollama is running and the model is installed with: "
            "ollama pull qwen2.5:1.5b. On CPU, the first response may take several minutes. "
            f"Details: {exc}"
        ) from exc
    content = response.json().get("message", {}).get("content", "")
    _log(agent, "OUTPUT", content)
    return content


def _extract_json(text: str) -> dict:
    """Parse model JSON defensively; tolerate fences and surrounding prose."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("The model returned an empty response.")
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    candidates = [cleaned]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start >= 0 and end > start:
        candidates.append(cleaned[start:end + 1])
    last_error = None
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError as exc:
            last_error = exc
    # Optional repair library: if installed, recover common comma/quote mistakes.
    try:
        from json_repair import repair_json
        for candidate in candidates:
            try:
                parsed = json.loads(repair_json(candidate))
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
    except ImportError:
        pass
    detail = f" ({last_error})" if last_error else ""
    raise ValueError("Qwen returned malformed JSON" + detail)


_NO_UNIT = r"(?!\d|\.\d|\s*(?:million|millones|millón|m€|€m|m\b))"
_AGE_STRICT = re.compile(r"\b(?:under(?:\s+the\s+age\s+of)?|younger than|below|less than|menor(?:es)? de)\s*(\d+)" + _NO_UNIT + r"\s*(?:years? old|years?|años)?\b")
_AGE_INCLUSIVE = re.compile(r"\b(?:at most|maximum age(?: of)?|up to|no older than|hasta|máximo de)\s*(\d+)" + _NO_UNIT + r"\s*(?:years? old|years?|años)?\b")
_BUDGET = re.compile(r"(?:€|eur\s*)?\s*(\d+(?:\.\d+)?)\s*(?:million(?:s)?|millones|millón|m€|€m|m\b)")
_STRICT_BUDGET_WORDS = re.compile(r"\b(?:under|below|less than|lower than|cheaper than|menos de|por debajo de)\b")
_CLAUSE_BREAK = re.compile(r"[.;,]|\band\b|\bwith\b|\by\b|\bcon\b")


def _parse_age_limit(text: str):
    """Return (limit, exclusive) from explicit wording, or (None, False)."""
    text = text.lower()
    strict = _AGE_STRICT.search(text)
    if strict:
        return int(strict.group(1)), True
    inclusive = _AGE_INCLUSIVE.search(text)
    if inclusive:
        return int(inclusive.group(1)), False
    return None, False


def _parse_budget_limit(text: str):
    """Return (millions, exclusive) for an explicit budget/value limit, or (None, False).

    'below/under/less than €20 million' is strict (value < 20); any other wording such as
    'maximum value of 20 million' is inclusive (value <= 20). Only the words in the same
    clause as the amount are considered, so 'under 25 years old, budget 20 million' stays inclusive.
    """
    text = text.lower()
    match = _BUDGET.search(text)
    if not match:
        return None, False
    window = text[max(0, match.start() - 40):match.start()]
    parts = _CLAUSE_BREAK.split(window)
    clause = parts[-1] if parts else window
    return float(match.group(1)), bool(_STRICT_BUDGET_WORDS.search(clause))


_COUNTRY_ALIASES = {
    "argentina": ("argentin",), "brazil": ("brazil", "brasil"), "croatia": ("croat", "croacia"),
    "england": ("english", "inglaterra", "inglés", "ingles"), "france": ("french", "francia", "francés", "frances"),
    "germany": ("german", "alemania", "alemán", "aleman"), "italy": ("italian", "italia"),
    "japan": ("japan", "japón", "japones", "japonés"), "morocco": ("morocc", "marruecos", "marroquí", "marroqui"),
    "netherlands": ("dutch", "holland", "países bajos", "paises bajos", "holand", "neerland"),
    "portugal": ("portugu",), "serbia": ("serb",), "spain": ("spanish", "españa", "español", "espanol", "espana"),
    "sweden": ("swed", "suecia", "sueco"),
}


def _text_supports(value: str, text: str) -> bool:
    """True if a nationality/league/club value can be traced to the request text."""
    value = value.lower()
    if value in text:
        return True
    if any(alias in text for alias in _COUNTRY_ALIASES.get(value, ())):
        return True
    # League and club names: accept if any distinctive word (4+ letters) of the value is mentioned.
    return any(len(word) >= 4 and word in text for word in re.findall(r"\w+", value))


_NUMERIC_KEYS = ("max_age", "min_goals", "min_assists", "min_appearances", "min_minutes", "max_value_m", "max_height_cm")
_TEXT_KEYS = ("nationality", "league", "club")


def _sanitize_against_request(criteria: dict, user_request: str) -> dict:
    """Drop mandatory constraints the small LLM invented: they must be traceable to the request text.

    Numbers must literally appear in the request; nationality/league/club must be mentioned in it (demonyms such as
    'Spanish' still support 'Spain'). Dropped fields are logged.
    """
    text = user_request.lower().replace(",", ".")
    numbers = set()
    for raw in re.findall(r"\d+(?:\.\d+)?", text):
        numbers.add(float(raw))
    dropped = {}
    for key in _NUMERIC_KEYS:
        value = criteria.get(key)
        if value in (None, ""):
            continue
        try:
            supported = float(value) in numbers
        except (TypeError, ValueError):
            supported = False
        if not supported:
            dropped[key] = value
            criteria[key] = None
    for key in _TEXT_KEYS:
        value = criteria.get(key)
        if value in (None, "", "Any", "Cualquiera"):
            continue
        if not _text_supports(str(value), text):
            dropped[key] = value
            criteria[key] = None
    if dropped:
        _log("AGENT_1_CLUB_ANALYST", "DROPPED_UNSUPPORTED_CONSTRAINTS", dropped)
    return criteria


def _fallback_criteria(user_request: str) -> dict:
    """Extract common explicit requirements in English or Spanish as a safe fallback."""
    text = user_request.lower().replace(",", ".")
    result = {"position": None, "max_age": None, "age_limit_exclusive": False,
              "max_value_m": None, "value_limit_exclusive": False, "min_goals": None, "min_assists": None,
              "min_appearances": None, "min_minutes": None, "nationality": None,
              "league": None, "club": None, "max_height_cm": None,
              "soft_preferences": [], "original_request": user_request}
    position_patterns = [
        (r"\b(striker|forward|centre[- ]forward|center[- ]forward|delanter[oa]|ariete)\b", "ST"),
        (r"\b(goalkeeper|keeper|portero|guardameta)\b", "GK"),
        (r"\b(centre[- ]back|center[- ]back|central|defender)\b", "CB"),
        (r"\b(defensive midfielder|holding midfielder|pivote)\b", "DM"),
        (r"\b(midfielder|central midfielder|mediocentro|centrocampista)\b", "CM"),
        (r"\b(right winger|right wing|extremo derecho)\b", "RW"),
        (r"\b(left winger|left wing|extremo izquierdo)\b", "LW"),
    ]
    for pattern, code in position_patterns:
        if re.search(pattern, text):
            result["position"] = code
            break

    # Strict language: under/younger than/less than N means age < N.
    age, exclusive = _parse_age_limit(text)
    if age is not None:
        result["max_age"], result["age_limit_exclusive"] = age, exclusive

    patterns = [
        ("min_goals", r"(?:at least|minimum of|a minimum of|more than|al menos|mínimo de|más de)\s*(\d+)\s*(?:goals?|goles?)"),
        ("min_assists", r"(?:at least|minimum of|a minimum of|more than|al menos|mínimo de|más de)\s*(\d+)\s*(?:assists?|asistencias?)"),
        ("min_appearances", r"(?:at least|minimum of|a minimum of|al menos|mínimo de)\s*(\d+)\s*(?:appearances?|matches?|games?|partidos?)"),
        ("min_minutes", r"(?:at least|minimum of|a minimum of|al menos|mínimo de)\s*(\d+)\s*(?:minutes?|minutos?)"),
    ]
    for key, pattern in patterns:
        match = re.search(pattern, text)
        if match:
            number = float(match.group(1))
            result[key] = int(number)
    budget, budget_exclusive = _parse_budget_limit(text)
    if budget is not None:
        result["max_value_m"], result["value_limit_exclusive"] = budget, budget_exclusive
    return result


def _enforce_explicit_age_semantics(criteria: dict, user_request: str) -> dict:
    """Override ambiguous LLM age/budget output when the request explicitly says under/at most.

    Strict wording ('under 25', 'below 20 million') becomes '<'; any other wording stays '<='.
    """
    age, exclusive = _parse_age_limit(user_request)
    if age is not None:
        criteria["max_age"] = age
        criteria["age_limit_exclusive"] = exclusive
    budget, budget_exclusive = _parse_budget_limit(user_request.replace(",", "."))
    if budget is not None:
        criteria["max_value_m"] = budget
        criteria["value_limit_exclusive"] = budget_exclusive
    return criteria


def club_analyst(user_request: str) -> dict:
    """Agent 1: translate natural-language recruitment requests into criteria."""
    prompt = (
        "You are the Club Analyst in a football recruitment scouting system. Extract ONLY explicit requirements. "
        "Never invent values or turn vague preferences into mandatory constraints. "
        "Use position codes GK, CB, DM, CM, RW, LW, ST. max_value_m is expressed in millions of euros. "
        "IMPORTANT AGE SEMANTICS: 'under N' or 'younger than N' means age < N (strictly less than N), "
        "while 'at most N' or 'no older than N' means age <= N. Set age_limit_exclusive=true for strict limits. "
        "Unknown fields must be null. Put non-mandatory preferences in soft_preferences. "
        "Return only a JSON object matching the schema."
    )
    raw = ollama_chat("AGENT_1_CLUB_ANALYST", prompt, user_request, json_mode=True)
    try:
        parsed = _extract_json(raw)
    except ValueError as exc:
        _log("AGENT_1_CLUB_ANALYST", "JSON_FALLBACK", {"error": str(exc), "raw": raw})
        parsed = _fallback_criteria(user_request)
    # Constraints that cannot be traced to the request text are removed (small models hallucinate filters).
    parsed = _sanitize_against_request(parsed, user_request)
    # Explicit numeric limits the model left null are recovered with the deterministic regex parser.
    regex_profile = _fallback_criteria(user_request)
    for key in ("min_goals", "min_assists", "min_appearances", "min_minutes"):
        if parsed.get(key) in (None, "", False) and regex_profile.get(key) is not None:
            parsed[key] = regex_profile[key]
    # Deterministic interpretation prevents the LLM from turning strict limits into inclusive ones.
    parsed = _enforce_explicit_age_semantics(parsed, user_request)
    parsed.setdefault("age_limit_exclusive", False)
    parsed.setdefault("value_limit_exclusive", False)
    # Defensive normalization; only recognized position codes are accepted.
    if parsed.get("position") not in POSITIONS:
        parsed["position"] = None
    for key in ("max_age", "min_goals", "min_assists", "min_appearances", "min_minutes", "max_value_m", "max_height_cm"):
        if parsed.get(key) == "" or parsed.get(key) is False:
            parsed[key] = None
    parsed.setdefault("soft_preferences", [])
    return parsed


def _player_summary(player: dict) -> dict:
    # Compact payload keeps all 67 demo records within the small model context.
    fields = ("name", "position", "age", "nationality", "club", "league", "appearances", "minutes", "goals", "assists", "goal_contributions_per90", "height_cm", "value_m")
    return {key: player.get(key) for key in fields}


def player_scout(criteria: dict, players: list[dict]) -> list[dict]:
    """Agent 2: use the LLM to prioritize CSV records; names are verified against source data."""
    if not players:
        return []
    # Reduce the LLM workload on CPU-only computers: apply explicit hard filters
    # first, then send at most 30 best statistical matches to the language model.
    # The independent Python Validator still checks all selected candidates later.
    from scout import filter_players
    prefiltered = filter_players(criteria, players)
    if not prefiltered:
        return []
    compact = [_player_summary(p) for p in prefiltered[:30]]
    prompt = (
        "You are the Player Scout. Analyze only the football players supplied from the CSV. "
        "Identify ALL players who satisfy every explicit mandatory requirement in the profile. "
        "Never invent players or statistics. Return JSON with the key candidate_names, "
        "a list of names copied exactly from the records. Do not add names absent from the CSV. "
        "Mandatory constraints will be independently checked again by Python."
    )
    raw = ollama_chat("AGENT_2_PLAYER_SCOUT", prompt, {"criteria": criteria, "csv_players": compact}, json_mode=True)
    try:
        result = _extract_json(raw)
    except ValueError as exc:
        _log("AGENT_2_PLAYER_SCOUT", "JSON_FALLBACK", {"error": str(exc), "raw": raw})
        # The Python pre-filter is deterministic and uses only records from the CSV.
        result = {"candidate_names": [p["name"] for p in prefiltered[:30]]}
    wanted = result.get("candidate_names", [])
    by_name = {str(p["name"]): p for p in prefiltered}
    selected = [by_name[name] for name in wanted if name in by_name]
    # Never allow an imperfect model response to erase all valid database matches.
    if not selected:
        # A malformed/empty model selection must not silently discard the source dataset.
        selected = prefiltered[:30]
    return selected


def _normalise_recommendations(items, valid_names: set) -> list:
    """Keep only known, non-duplicated candidates, order by the model's rank and renumber 1..3."""
    if not isinstance(items, list):
        return []
    clean, seen = [], set()
    for position, item in enumerate(items):
        if not isinstance(item, dict) or item.get("name") not in valid_names or item["name"] in seen:
            continue
        seen.add(item["name"])
        try:
            order = float(item.get("rank"))
        except (TypeError, ValueError):
            order = float("inf")
        clean.append((order, position, item))
    clean.sort(key=lambda t: (t[0], t[1]))
    result = []
    for new_rank, (_, _, item) in enumerate(clean[:3], 1):
        item = dict(item)
        item["rank"] = new_rank
        result.append(item)
    return result


def recruitment_advisor(criteria: dict, players: list[dict]) -> dict:
    """Agent 3: explain a deterministic Python ranking without changing its order.

    Python is the single source of truth for rank order. The LLM may add grounded
    explanations, but it cannot add, remove, or reorder the recommended players.
    """
    if not players:
        return {"summary": "No players matched all mandatory requirements.", "recommendations": []}

    def number(player, key):
        try:
            return float(player.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0

    # One canonical ordering is shared by the UI, report and JSON output.
    ranked_players = sorted(
        players,
        key=lambda p: (
            number(p, "goal_contributions_per90"),
            number(p, "minutes"),
        ),
        reverse=True,
    )[:3]

    prompt = (
        "You are the Recruitment Advisor. Write concise, evidence-based explanations for the "
        "provided players. The input list is ALREADY ranked by Python and its order is final. "
        "Do not rank, reorder, omit, or add players. Return JSON with a summary and a "
        "recommendations array containing one object for EACH supplied player, preserving "
        "the exact input order and exact name. Each object must contain name, rationale, "
        "strengths (list), and risks (list). Use only supplied statistics; do not invent "
        "injuries, personality, potential, or missing data. If evidence is limited, say so."
    )
    payload_players = [_player_summary(p) for p in ranked_players]
    explanations = {}
    summary = "Candidates are ranked by goal contributions per 90 minutes, then minutes played (both in descending order)."
    try:
        raw = ollama_chat(
            "AGENT_3_RECRUITMENT_ADVISOR",
            prompt,
            {"criteria": criteria, "already_ranked_candidates": payload_players},
            json_mode=True,
        )
        result = _extract_json(raw)
        summary = result.get("summary") or summary
        items = result.get("recommendations", [])
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and item.get("name") in {p["name"] for p in ranked_players}:
                    explanations[item["name"]] = item
    except (ValueError, RuntimeError, requests.RequestException) as exc:
        _log("AGENT_3_RECRUITMENT_ADVISOR", "EXPLANATION_FALLBACK", {"error": str(exc)})

    recommendations = []
    for rank, player in enumerate(ranked_players, 1):
        item = explanations.get(player["name"], {})
        contribution = number(player, "goal_contributions_per90")
        minutes = number(player, "minutes")
        strengths = item.get("strengths")
        if not isinstance(strengths, list) or not strengths:
            strengths = [
                f"{contribution:.2f} goal contributions per 90 minutes",
                f"{int(minutes)} minutes played",
            ]
        risks = item.get("risks")
        if not isinstance(risks, list) or not risks:
            risks = ["The dataset does not include every metric needed for a professional scouting assessment."]
        rationale = item.get("rationale") or (
            f"Ranked #{rank} based on {contribution:.2f} goal contributions per 90 minutes "
            f"and {int(minutes)} minutes played."
        )
        recommendations.append({
            "name": player["name"],
            "rank": rank,
            "rationale": rationale,
            "strengths": strengths,
            "risks": risks,
            # Include the exact source metrics used for ordering and auditability.
            "goal_contributions_per90": contribution,
            "minutes": int(minutes),
            "value_m": number(player, "value_m"),
        })

    return {"summary": summary, "recommendations": recommendations}


def run_scouting_pipeline(user_request: str, all_players: list[dict], validator):
    """Autonomous sequential hand-off: Agent 1 -> Agent 2 -> Python validator -> Agent 3."""
    profile = club_analyst(user_request)
    # Agent 2 searches the supplied CSV; the independent Python validator then enforces hard constraints.
    scouted = player_scout(profile, all_players)
    validated = validator(profile, scouted)

    def metric(player, field):
        try:
            return float(player.get(field) or 0)
        except (TypeError, ValueError):
            return 0.0

    # Canonical order: the same ordering is used in the candidate table and final report.
    validated = sorted(
        validated,
        key=lambda p: (metric(p, "goal_contributions_per90"), metric(p, "minutes")),
        reverse=True,
    )
    report = recruitment_advisor(profile, validated)
    _log("PIPELINE", "FINAL", {"profile": profile, "eligible_count": len(validated), "report": report})
    return {"profile": profile, "candidates": validated, "report": report}
