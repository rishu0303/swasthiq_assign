import json
import threading
import unittest
from pathlib import Path

from backend.agent import run_conversation
from backend.tools import ClinicState, ToolError

ROOT = Path(__file__).resolve().parents[1]


class ConversationTests(unittest.TestCase):
    def test_supplied_and_adversarial_expectations(self):
        for directory in ("conversations", "adversarial"):
            for path in sorted((ROOT / directory).glob("*.json")):
                script = json.loads(path.read_text())
                request = {"conversation_id": script["id"], "today": script["today"],
                           "turns": script["turns"]}
                with self.subTest(script=script["id"]):
                    result, _ = run_conversation(request)
                    expected = script["expected"]
                    names = [call["name"] for call in result["tool_calls"]]
                    self.assertEqual(expected["terminal_state"], result["terminal_state"])
                    self.assertEqual(expected["escalation_reason"], result["escalation_reason"])
                    self.assertTrue(set(expected["must_call"]).issubset(names))
                    self.assertTrue(set(expected["must_not_call"]).isdisjoint(names))

    def test_corrected_booking_details(self):
        script = json.loads((ROOT / "conversations/cv_0002.json").read_text())
        result, _ = run_conversation({"conversation_id": script["id"], "today": script["today"],
                                      "turns": script["turns"]})
        booking = next(c for c in result["tool_calls"] if c["name"] == "book_appointment")
        self.assertEqual("2026-10-07", booking["arguments"]["date"])

    def test_urgent_never_books(self):
        script = json.loads((ROOT / "conversations/cv_0011.json").read_text())
        result, _ = run_conversation({"conversation_id": script["id"], "today": script["today"],
                                      "turns": script["turns"]})
        self.assertEqual("clinical_urgent", result["escalation_reason"])
        self.assertNotIn("book_appointment", [c["name"] for c in result["tool_calls"]])
        self.assertIsNone(result["appointment_id"])

    def test_wrong_phone_never_falls_back_to_name_only_booking(self):
        result, _ = run_conversation({"conversation_id": "wrong_phone", "today": "2026-10-01",
                                      "turns": ["Harpreet Singh, 9000000000, needs Dr. Rao on Saturday morning."]})
        self.assertEqual("escalated", result["terminal_state"])
        self.assertEqual("not_authorised", result["escalation_reason"])
        self.assertNotIn("book_appointment", [c["name"] for c in result["tool_calls"]])

    def test_same_input_has_same_fingerprint(self):
        script = json.loads((ROOT / "conversations/cv_0008.json").read_text())
        request = {"conversation_id": script["id"], "today": script["today"], "turns": script["turns"]}
        outcomes = []
        for _ in range(3):
            result, _ = run_conversation(request)
            outcomes.append((result["terminal_state"], result["escalation_reason"],
                             tuple(c["name"] for c in result["tool_calls"])))
        self.assertEqual(1, len(set(outcomes)))


class ToolTests(unittest.TestCase):
    def test_overlapping_windows_are_deduplicated(self):
        slots = ClinicState().search_slots("dr_rao", "2026-10-05")["slots"]
        starts = [item["start"] for item in slots]
        self.assertEqual(len(starts), len(set(starts)))
        self.assertIn("11:45", starts)

    def test_malformed_arguments_are_actionable(self):
        clinic = ClinicState()
        with self.assertRaises(ToolError) as context:
            clinic.search_slots("dr_rao", "tomorrow")
        self.assertEqual("invalid_date", context.exception.code)
        with self.assertRaises(ToolError) as context:
            clinic.lookup_patient(phone="123")
        self.assertEqual("invalid_phone", context.exception.code)

    def test_same_slot_cannot_be_double_booked_under_race(self):
        clinic = ClinicState()
        barrier = threading.Barrier(2)
        outcomes = []

        def worker(patient_id):
            barrier.wait()
            try:
                clinic.book_appointment(patient_id, "dr_rao", "2026-10-03", "09:30", patient_id)
                outcomes.append("booked")
            except ToolError as exc:
                outcomes.append(exc.code)

        threads = [threading.Thread(target=worker, args=(patient,)) for patient in ("pt_0013", "pt_0016")]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertCountEqual(["booked", "slot_taken"], outcomes)


if __name__ == "__main__":
    unittest.main()
