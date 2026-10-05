import unittest
from pydantic import ValidationError
from app.agent.orchestrator import AnalysisUnavailableError, TutorOrchestrator
from app.models.tutor_request import TutorRequest
from app.models.tutor_response import TutorAction
from app.policies.tutor_policy import TutorPolicy
from tests.helpers import payload


class OrchestratorTests(unittest.TestCase):
    def test_policy_decisions_and_precedence(self):
        cases = [
            (0.35, True, 2, 0, TutorAction.SOCRATIC_HINT),
            (0.24, True, 3, 0, TutorAction.CONCEPT_REVIEW),
            (0.25, True, 0, 0, TutorAction.SOCRATIC_HINT),
            (0.35, True, 3, 0, TutorAction.REMEDIATION),
            (0.35, True, 2, 1, TutorAction.RETRY),
            (0.95, True, 1, 0, TutorAction.SOCRATIC_HINT),
            (0.8, False, 0, 0, TutorAction.NEXT_SKILL),
            (0.799, False, 0, 0, TutorAction.RETRY),
            (0.1, False, 0, 0, TutorAction.CONCEPT_REVIEW),
        ]
        for mastery, error, wrong, hints, expected in cases:
            with self.subTest(mastery=mastery, error=error, wrong=wrong, hints=hints):
                data = payload()
                data['focus_skill']['mastery_after'] = mastery
                if not error:
                    data['first_error'] = None
                data.update(consecutive_wrong=wrong, hint_count=hints)
                self.assertEqual(TutorOrchestrator().decide(TutorRequest(**data)), expected)

    def test_analysis_unavailable_has_first_priority(self):
        for status in ['PENDING', 'FAILED', 'UNKNOWN']:
            data = payload()
            data['analysis_status'] = status
            data['focus_skill']['mastery_after'] = 0.01
            with self.assertRaises(AnalysisUnavailableError):
                TutorOrchestrator().decide(TutorRequest(**data))

    def test_policy_is_replaceable_and_ids_are_opaque(self):
        data = payload()
        data['focus_skill']['skill_id'] = 'SKL-999'
        data['first_error']['error_subtype'] = 'new-error-code'
        self.assertEqual(TutorOrchestrator(TutorPolicy(concept_review_threshold=0.4)).decide(
            TutorRequest(**data)), TutorAction.CONCEPT_REVIEW)

    def test_policy_rejects_invalid_thresholds(self):
        for settings in [dict(concept_review_threshold=0.9), dict(repeated_wrong_threshold=1),
                         dict(mastery_threshold=float('nan'))]:
            with self.assertRaises(ValidationError):
                TutorPolicy(**settings)
