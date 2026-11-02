import unittest

from engine.collector import ATTACHMENT_TYPES
from engine.run_scan import changed_fields, notice_key
from engine.sync_supabase import clean, exam_identity, exam_names, is_complete_notice


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

    def test_vacancy_tracking_uses_specific_recruitment_title(self):
        draft = {
            "is_recruitment_notice": True,
            "post_title": "CSIR CGCRI Kolkata Director Recruitment 2026",
            "post_names": ["Director"],
        }
        self.assertEqual(exam_names(draft), ["CSIR CGCRI Kolkata Director Recruitment 2026"])

    def test_result_tracking_uses_post_and_advertisement_cycle(self):
        draft = {
            "is_recruitment_notice": False,
            "post_names": ["Additional Director General"],
            "cycle_label": "Advt. No. ICMRHQ/01/2026",
        }
        self.assertEqual(exam_names(draft), ["Additional Director General"])

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

    def test_vacancy_and_later_result_share_the_same_exam_identity(self):
        vacancy = {
            "organisation": "State Bank of India",
            "exam_name": "SBI Specialist Cadre Officers Recruitment 2026-27",
            "post_names": ["Specialist Cadre Officers"],
        }
        result = {
            "organisation": "State Bank of India",
            "exam_name": "SBI Specialist Cadre Officers Recruitment 2026-27",
            "post_names": [],
        }
        self.assertEqual(notice_key(vacancy), notice_key(result))

    def test_related_exam_order_does_not_create_a_duplicate_update(self):
        first = {"related_exams": ["JEE Main 2027", "UGC NET December 2026"]}
        second = {"related_exams": ["UGC NET December 2026", "JEE Main 2027"]}
        self.assertEqual(changed_fields(first, second), [])

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

    def test_result_link_change_is_a_new_update(self):
        before = {"exam_name": "JEE Main 2027", "event_type": "result", "result_url": "https://official.gov.in/result"}
        after = {**before, "result_url": "https://official.gov.in/result-check"}
        self.assertIn("Result link:", changed_fields(before, after)[0])

    def test_text_normalization_collapses_whitespace(self):
        self.assertEqual(clean("  National   Testing" + chr(10) + " Agency  "), "National Testing Agency")

    def test_supported_official_attachment_types(self):
        self.assertEqual(ATTACHMENT_TYPES[".pdf"], "application/pdf")
        self.assertIn(".xlsx", ATTACHMENT_TYPES)
        self.assertIn(".docx", ATTACHMENT_TYPES)
        self.assertIn(".zip", ATTACHMENT_TYPES)

if __name__ == "__main__":
    unittest.main()
