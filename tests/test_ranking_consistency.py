import json
import unittest
from unittest.mock import patch

from agents import recruitment_advisor


class RankingConsistencyTests(unittest.TestCase):
    def test_model_cannot_reorder_python_ranking(self):
        players = [
            {"name": "Ben Carter", "goal_contributions_per90": 0.28, "minutes": 1300, "value_m": 10},
            {"name": "Youssef Amrani", "goal_contributions_per90": 0.24, "minutes": 1100, "value_m": 8},
            {"name": "Matteo Ricci", "goal_contributions_per90": 0.13, "minutes": 900, "value_m": 12},
        ]
        # Simulate the LLM returning the candidates in the wrong order.
        bad_reply = json.dumps({
            "summary": "Model-generated report",
            "recommendations": [
                {"name": "Matteo Ricci", "rank": 1, "rationale": "wrong model order", "strengths": [], "risks": []},
                {"name": "Youssef Amrani", "rank": 2, "rationale": "middle", "strengths": [], "risks": []},
                {"name": "Ben Carter", "rank": 3, "rationale": "last", "strengths": [], "risks": []},
            ],
        })
        with patch("agents.ollama_chat", return_value=bad_reply):
            report = recruitment_advisor({}, players)
        self.assertEqual(
            [(r["rank"], r["name"]) for r in report["recommendations"]],
            [(1, "Ben Carter"), (2, "Youssef Amrani"), (3, "Matteo Ricci")],
        )

    def test_fallback_and_report_use_same_canonical_order(self):
        players = [
            {"name": "Matteo Ricci", "goal_contributions_per90": 0.13, "minutes": 900, "value_m": 12},
            {"name": "Ben Carter", "goal_contributions_per90": 0.28, "minutes": 1300, "value_m": 10},
        ]
        with patch("agents.ollama_chat", side_effect=RuntimeError("offline")):
            report = recruitment_advisor({}, players)
        self.assertEqual([r["name"] for r in report["recommendations"]], ["Ben Carter", "Matteo Ricci"])
        self.assertTrue(all(r["strengths"] for r in report["recommendations"]))


if __name__ == "__main__":
    unittest.main()
