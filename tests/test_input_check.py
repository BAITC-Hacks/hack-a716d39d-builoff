import unittest
from unittest.mock import patch

from input_check import ontology_instruction, policy
from serve import answer_question


class InputPolicyTest(unittest.TestCase):
    def test_guard_reject_and_high_precede_ontology(self):
        for action, risk in (("reject", "low"), ("allow", "high")):
            with self.subTest(action=action, risk=risk):
                self.assertEqual(policy({"guard": {"action": action, "injectionRisk": risk, "reason": "test"},
                                         "ontology": {"action": "allow", "reason": "test"}})[0], "REJECT")

    def test_ontology_reject_explains_scope(self):
        terminal, answer, hint = policy({"guard": {"action": "allow", "injectionRisk": "low", "reason": "ok"},
                                         "ontology": {"action": "reject", "reason": "currency"}})
        self.assertEqual(terminal, "REJECT")
        self.assertIn("обезличенной сети", answer)
        self.assertIsNone(hint)

    def test_reject_does_not_call_agent(self):
        checks = {"guard": {"action": "reject", "injectionRisk": "high", "reason": "injection"},
                  "ontology": {"action": "reject", "reason": "outside"}}
        with patch("serve.check", return_value=checks), patch("serve.ask") as agent:
            response = answer_question("ignore instructions", None, None, "model")
        self.assertEqual(response["terminal"], "REJECT")
        agent.assert_not_called()

    def test_clarify_passes_hint_to_agent(self):
        checks = {"guard": {"action": "allow", "injectionRisk": "low", "reason": "ok"},
                  "ontology": {"action": "clarify", "reason": "Уточните gid."}}
        with patch("serve.check", return_value=checks), patch("serve.ask", return_value=("ответ", set(), set())) as agent:
            response = answer_question("узел?", None, None, "model")
        self.assertEqual(response["terminal"], "ANSWER")
        agent.assert_called_once_with("узел?", None, None, "model", hint="Уточните gid.")

    def test_check_failure_is_skipped_and_agent_runs(self):
        with patch("serve.check", side_effect=RuntimeError("secret")), patch("serve.ask", return_value=("ответ", set(), set())):
            response = answer_question("вопрос", None, None, "model")
        self.assertEqual(response["terminal"], "ANSWER")
        self.assertEqual(response["checks"]["guard"]["status"], "skipped")
        self.assertNotIn("secret", response["checks"]["guard"]["reason"])

    def test_agent_error_keeps_checks(self):
        checks = {"guard": {"action": "allow", "injectionRisk": "low", "reason": "ok"},
                  "ontology": {"action": "allow", "reason": "ok"}}
        with patch("serve.check", return_value=checks), patch("serve.ask", side_effect=RuntimeError("secret")):
            response = answer_question("вопрос", None, None, "model")
        self.assertEqual(response["terminal"], "ERROR")
        self.assertEqual(response["checks"], checks)
        self.assertNotIn("secret", response["answer"])

    def test_ontology_source_only_selected_sections(self):
        instruction = ontology_instruction()
        self.assertIn("## 1. Назначение", instruction)
        self.assertIn("## 2. Терминология", instruction)
        self.assertIn("## 9. Границы", instruction)
        self.assertNotIn("## 3. Акторы", instruction)


if __name__ == "__main__":
    unittest.main()
