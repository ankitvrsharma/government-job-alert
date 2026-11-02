import unittest

from engine.run_scan import changed_fields, notice_key
from engine.sync_supabase import exam_identity, exam_names, is_complete_notice


class ExamLifecycleTests(unittest.TestCase):
    def test_related_exams_are_deduplicated(self):
        draft = {
            "exam_name": "UGC NET December 2026",
            "related_exams": ["UGC NET December 2026", "JEE Main 2027 Session 1", "CSIR NET June 2027"],
        }
        self.assertEqual(
            exam_names(draft),
            ["UGC NET December 2026", "JEE Main 2027 Session 1", "CSIR NET June 2027"],
        )

    def test_exam_key_is_stable_and_cycle_specific(self):
        key_a, org, cycle = exam_identity("JEE Main 2027 Session 1", {
            "organisation": "National Testing Agency",
            "cycle_label": "January 2027",
        })
        key_b, _, _ = exam_identity("JEE Main 2027 Session 1", {
            "organisation": "National Testing Agency",
            "cycle_label": "January 2027",
        })
        key_c, _, _ = exam_identity("JEE Main 2027 Session 1", {
            "organisation": "National Testing Agency",
            "cycle_label": "April 2027",
        })
        self.assertEqual(key_a, key_b)
        self.assertNotEqual(key_a, key_c)
        self.assertIn("national-testing-agency", key_a)
        self.assertEqual(org, "National Testing Agency")
        self.assertEqual(cycle, "January 2027")

    def test_one_multi_exam_source_has_one_stable_notice_identity(self):
        first = {
            "organisation": "NTA",
            "related_exams": ["JEE Main 2027", "UGC NET December 2026"],
        }
        second = {
            "organisation": "NTA",
            "related_exams": ["UGC NET December 2026", "JEE Main 2027"],
        }
        self.assertEqual(notice_key(first), notice_key(second))

    def test_complete_official_notice_is_retained(self):
        row = {"ai_draft": {
            "status": "ai_draft",
            "is_relevant_notice": True,
            "is_recruitment_notice": False,
            "event_evidence": "Official result notification released by the authority.",
            "summary": "The authority has published the official result and provides the next steps for candidates.",
            "event_type": "result",
        }}
        self.assertTrue(is_complete_notice(row))

    def test_incomplete_notice_is_not_retained(self):
        row = {"ai_draft": {
            "status": "ai_draft",
            "is_relevant_notice": True,
            "event_evidence": "",
            "summary": "A short notice.",
            "event_type": "result",
        }}
        self.assertFalse(is_complete_notice(row))

    def test_no_change_means_no_second_post(self):
        draft = {"exam_name": "JEE Main 2027", "event_type": "result", "important_dates": ["10 May 2027"]}
        self.assertEqual(changed_fields(draft, dict(draft)), [])


if __name__ == "__main__":
    unittest.main()
