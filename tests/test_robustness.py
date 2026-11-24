import json
import unittest
from unittest import mock

import agents
from agents import (
    _enforce_explicit_age_semantics,
    _fallback_criteria,
    _normalise_recommendations,
    _sanitize_against_request,
)
from scout import filter_players, load_players
from validator import validate_players

GOOD_PROFILE = {
    "position": "ST", "max_age": 25, "age_limit_exclusive": False, "max_value_m": 25,
    "min_goals": 8, "min_assists": None, "min_appearances": None, "min_minutes": None,
    "nationality": None, "league": None, "club": None, "max_height_cm": None,
    "soft_preferences": [],
}
REQUEST = "We are looking for a striker under the age of 25 years, with at least 8 goals and a maximum value of 25 million euros."


def _fake_ollama(profile, scout_reply="{}", advisor_reply="{}"):
    replies = {
        "AGENT_1_CLUB_ANALYST": json.dumps(profile),
        "AGENT_2_PLAYER_SCOUT": scout_reply,
        "AGENT_3_RECRUITMENT_ADVISOR": advisor_reply,
    }
    return lambda agent, *args, **kwargs: replies[agent]


class BudgetSemanticsTests(unittest.TestCase):
    def setUp(self):
        self.players = load_players()

    def test_below_budget_is_strict(self):
        request = "We need a striker with at least 8 goals and a transfer budget below €15 million."
        criteria = _enforce_explicit_age_semantics(_fallback_criteria(request), request)
        self.assertEqual(criteria["max_value_m"], 15.0)
        self.assertTrue(criteria["value_limit_exclusive"])
        names = {p["name"] for p in validate_players(criteria, filter_players(criteria, self.players))}
        self.assertNotIn("Daniel Costa", names)   # value exactly 15.0
        self.assertIn("Amir Haddad", names)       # value 14.0

    def test_maximum_value_is_inclusive(self):
        request = "We need a striker with at least 8 goals and a maximum value of 15 million euros."
        criteria = _enforce_explicit_age_semantics(_fallback_criteria(request), request)
        self.assertFalse(criteria["value_limit_exclusive"])
        names = {p["name"] for p in validate_players(criteria, filter_players(criteria, self.players))}
        self.assertIn("Daniel Costa", names)

    def test_age_and_budget_in_same_sentence_do_not_mix(self):
        request = "We need a striker under 25 years old, with a maximum value of 20 million euros."
        criteria = _enforce_explicit_age_semantics(_fallback_criteria(request), request)
        self.assertTrue(criteria["age_limit_exclusive"])
        self.assertFalse(criteria["value_limit_exclusive"])
        self.assertEqual((criteria["max_age"], criteria["max_value_m"]), (25, 20.0))

    def test_under_amount_of_million_is_not_read_as_age(self):
        request = "A striker under 20 million euros."
        criteria = _fallback_criteria(request)
        self.assertIsNone(criteria["max_age"])
        self.assertEqual(criteria["max_value_m"], 20.0)
        self.assertTrue(criteria["value_limit_exclusive"])

    def test_spanish_age_is_enforced(self):
        criteria = _enforce_explicit_age_semantics({"max_age": 25, "age_limit_exclusive": False}, "Buscamos un delantero menor de 25 años")
        self.assertTrue(criteria["age_limit_exclusive"])


class HallucinatedConstraintTests(unittest.TestCase):
    def test_invented_nationality_is_dropped(self):
        profile = dict(GOOD_PROFILE, nationality="Spain", min_assists=5)
        cleaned = _sanitize_against_request(dict(profile), REQUEST)
        self.assertIsNone(cleaned["nationality"])
        self.assertIsNone(cleaned["min_assists"])
        self.assertEqual(cleaned["min_goals"], 8)
        self.assertEqual(cleaned["max_value_m"], 25)

    def test_demonym_supports_nationality(self):
        cleaned = _sanitize_against_request(dict(GOOD_PROFILE, nationality="Spain"), "A Spanish striker under 25")
        self.assertEqual(cleaned["nationality"], "Spain")

    def test_pipeline_ignores_hallucinated_filters(self):
        players = load_players()
        profile = dict(GOOD_PROFILE, nationality="Spain")
        with mock.patch.object(agents, "ollama_chat", _fake_ollama(profile)):
            result = agents.run_scouting_pipeline(REQUEST, players, validate_players)
        self.assertIsNone(result["profile"]["nationality"])
        self.assertGreater(len(result["candidates"]), 1)
        self.assertTrue(all(float(p["age"]) < 25 for p in result["candidates"]))


class OmittedConstraintTests(unittest.TestCase):
    def test_goals_omitted_by_llm_are_recovered_from_request(self):
        request = "We need a striker under 25 years old, with at least 10 goals per season and a transfer budget below €20 million."
        profile = dict(GOOD_PROFILE, min_goals=None)
        with mock.patch.object(agents, "ollama_chat", _fake_ollama(profile)):
            result = agents.run_scouting_pipeline(request, load_players(), validate_players)
        self.assertEqual(result["profile"]["min_goals"], 10)
        self.assertTrue(result["candidates"])
        self.assertTrue(all(int(p["goals"]) >= 10 and float(p["age"]) < 25 and float(p["value_m"]) < 20 for p in result["candidates"]))


class RankingTests(unittest.TestCase):
    NAMES = {"A", "B", "C", "D"}

    def test_unknown_and_duplicate_names_removed_and_ranks_renumbered(self):
        items = [
            {"name": "Fake", "rank": 1}, {"name": "C", "rank": 7}, {"name": "A", "rank": 3},
            {"name": "A", "rank": 4}, {"name": "B", "rank": "x"},
        ]
        result = _normalise_recommendations(items, self.NAMES)
        self.assertEqual([(r["rank"], r["name"]) for r in result], [(1, "A"), (2, "C"), (3, "B")])

    def test_garbage_input(self):
        self.assertEqual(_normalise_recommendations("not a list", self.NAMES), [])

    def test_pipeline_report_has_ranks_starting_at_one(self):
        players = load_players()
        names = [p["name"] for p in filter_players(_enforce_explicit_age_semantics(dict(GOOD_PROFILE), REQUEST), players)]
        advisor = json.dumps({"summary": "ok", "recommendations": [{"name": names[0], "rank": 3, "rationale": "r", "strengths": [], "risks": []}]})
        with mock.patch.object(agents, "ollama_chat", _fake_ollama(GOOD_PROFILE, json.dumps({"candidate_names": names}), advisor)):
            result = agents.run_scouting_pipeline(REQUEST, players, validate_players)
        self.assertEqual([r["rank"] for r in result["report"]["recommendations"]], [1, 2, 3])
        self.assertEqual(
            [r["name"] for r in result["report"]["recommendations"]],
            [p["name"] for p in sorted(
                result["candidates"],
                key=lambda p: (float(p.get("goal_contributions_per90") or 0), float(p.get("minutes") or 0)),
                reverse=True,
            )[:3]],
        )


class NoResultTests(unittest.TestCase):
    def test_impossible_request_returns_nothing(self):
        request = "a goalkeeper aged 18 with at least 50 goals and a maximum value of 1 million euros"
        profile = dict(GOOD_PROFILE, position="GK", max_age=18, min_goals=50, max_value_m=1)
        with mock.patch.object(agents, "ollama_chat", _fake_ollama(profile)):
            result = agents.run_scouting_pipeline(request, load_players(), validate_players)
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["report"]["recommendations"], [])


if __name__ == "__main__":
    unittest.main()
