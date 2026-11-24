import unittest
from agents import _enforce_explicit_age_semantics, _fallback_criteria
from scout import filter_players, load_players
from validator import validate_players


class AgeConstraintTests(unittest.TestCase):
    def setUp(self):
        self.players = load_players()

    def test_under_25_excludes_age_25_even_if_llm_says_inclusive(self):
        request = "We are looking for a striker under the age of 25 years, with at least 8 goals and a maximum value of 25 million euros."
        criteria = _fallback_criteria(request)
        criteria["age_limit_exclusive"] = False  # Simulate an incorrect LLM interpretation.
        criteria = _enforce_explicit_age_semantics(criteria, request)
        candidates = validate_players(criteria, filter_players(criteria, self.players))
        self.assertTrue(criteria["age_limit_exclusive"])
        self.assertTrue(all(float(player["age"]) < 25 for player in candidates))
        age_25 = next(player for player in self.players if float(player["age"]) == 25)
        self.assertNotIn(age_25, validate_players(criteria, [age_25]))

    def test_at_most_25_is_inclusive(self):
        request = "We need a striker at most 25 years old."
        criteria = _fallback_criteria(request)
        criteria = _enforce_explicit_age_semantics(criteria, request)
        self.assertFalse(criteria["age_limit_exclusive"])
        self.assertTrue(any(float(player["age"]) == 25 for player in filter_players(criteria, self.players)))


if __name__ == "__main__":
    unittest.main()
