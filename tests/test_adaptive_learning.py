import json
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.api.learning import learning, catalog, validator
from app.services.math_validator import InvalidMathAnswer, MathValidator
from app.services.tokens import TokenService, InvalidToken
from tests.helpers import payload


def learning_payload(skill='arithmetic', stage='decision'):
    analysis = payload()
    analysis['focus_skill']['skill_id'] = skill
    analysis['focus_skill']['name_ko'] = catalog.skill(skill)['name_ko']
    return {'analysis': analysis, 'stage': stage, 'source_problem': {
        'template': 'signed_multiplication' if skill == 'arithmetic' else 'binomial_expansion',
        'a': 2, 'b': -3}, 'skills': [{'skill_id': 'arithmetic', 'mastery': 0.9}]
    }


class AdaptiveApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def post(self, path, data):
        response = self.client.post('/api/tutor/' + path, json=data)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def variant(self, skill='arithmetic'):
        return self.post('learning/decision', learning_payload(skill, 'hint_complete'))['content']['problem']

    def retry_payload(self, problem, correct=True):
        signed = learning.tokens.read(problem['problem_token'], 'problem', '17')
        answer = str(signed['a'] * signed['b']) if signed['template'] == 'signed_multiplication' else f"(x+({signed['a']}))*(x+({signed['b']}))"
        answer = str(validator.expression(answer))
        return {'student_id': '17', 'attempt_id': 'retry-1', 'problem_token': problem['problem_token'],
                'answer': answer if correct else '0'}

    def test_hint_levels_and_no_answer_leak(self):
        messages = []
        for count in range(3):
            data = learning_payload()
            data['analysis']['hint_count'] = count
            body = self.post('learning/decision', data)
            self.assertEqual(body['action_type'], 'SOCRATIC_HINT')
            self.assertEqual(body['content']['hint_level'], count + 1)
            self.assertNotIn('-6', body['content']['message'])
            messages.append(body['content']['message'])
        self.assertEqual(len(set(messages)), 3)

    def test_unknown_error_has_generic_hint(self):
        data = learning_payload()
        data['analysis']['first_error'].update(latex_text='unknown', error_subtype='MIS-NEW')
        body = self.post('learning/decision', data)
        self.assertIn('3번째', body['content']['message'])
        self.assertNotIn('양수', body['content']['message'])

    def test_concept_has_real_explanation_example_and_fixture_video(self):
        data = learning_payload()
        data['analysis']['focus_skill']['mastery_after'] = 0.1
        body = self.post('learning/decision', data)
        self.assertEqual(body['action_type'], 'CONCEPT_REVIEW')
        self.assertIn('부호', body['content']['explanation'])
        self.assertTrue(body['content']['example'])
        self.assertTrue(body['content']['check_question'])
        self.assertEqual(body['content']['video']['content_id'], 'fixture-sign-01')
        self.assertEqual(body['data_source'], 'fixture')

    def test_prerequisite_precedes_low_current_mastery(self):
        data = learning_payload('polynomial')
        data['skills'][0]['mastery'] = 0.2
        data['analysis']['focus_skill']['mastery_after'] = 0.1
        body = self.post('learning/decision', data)
        self.assertEqual(body['action_type'], 'PREREQUISITE_REVIEW')
        self.assertEqual(body['target_skill_id'], 'arithmetic')

    def test_unknown_prerequisite_is_not_invented(self):
        data = learning_payload('polynomial')
        data['skills'] = []
        body = self.post('learning/decision', data)
        self.assertEqual(body['action_type'], 'PREREQUISITE_REVIEW')
        self.assertIn('정보가 없어', body['content']['message'])

    def test_transitive_prerequisite(self):
        data = learning_payload('factoring')
        data['skills'] = [{'skill_id': 'arithmetic', 'mastery': 0.2}, {'skill_id': 'polynomial', 'mastery': 0.4}]
        body = self.post('learning/decision', data)
        self.assertEqual(body['target_skill_id'], 'arithmetic')

    def test_repeated_error_remediation(self):
        data = learning_payload()
        data['analysis']['consecutive_wrong'] = 3
        body = self.post('learning/decision', data)
        self.assertEqual(body['action_type'], 'REMEDIATION')
        self.assertTrue(body['content']['explanation'])

    def test_recent_history_recognizes_same_error_only(self):
        data = learning_payload()
        data['analysis']['consecutive_wrong'] = 9
        data['recent_attempts'] = [
            {'attempt_id': 'old-1', 'skill_id': 'arithmetic', 'correct': False, 'error_subtype': 'arithmetic_slip'},
            {'attempt_id': 'old-2', 'skill_id': 'arithmetic', 'correct': False, 'error_subtype': 'arithmetic_slip'}]
        self.assertEqual(self.post('learning/decision', data)['action_type'], 'REMEDIATION')
        data['recent_attempts'][-1]['error_subtype'] = 'another_error'
        self.assertEqual(self.post('learning/decision', data)['action_type'], 'SOCRATIC_HINT')
        data['recent_attempts'][-1]['attempt_id'] = 'old-1'
        self.assertEqual(self.client.post('/api/tutor/learning/decision', json=data).status_code, 422)

    def test_path_skips_mastered_successor(self):
        data = learning_payload()
        data['analysis']['first_error'] = None
        data['analysis']['focus_skill']['mastery_after'] = 0.9
        data['skills'].append({'skill_id': 'polynomial', 'mastery': 0.9})
        self.assertEqual(self.post('learning/decision', data)['next_skill_id'], 'factoring')

    def test_exhausted_hint_reviews_concept(self):
        data = learning_payload()
        data['analysis']['hint_count'] = 3
        self.assertEqual(self.post('learning/decision', data)['action_type'], 'CONCEPT_REVIEW')

    def test_next_skill_selects_concrete_id(self):
        data = learning_payload()
        data['analysis']['first_error'] = None
        data['analysis']['focus_skill']['mastery_after'] = 0.9
        body = self.post('learning/decision', data)
        self.assertEqual(body['action_type'], 'NEXT_SKILL')
        self.assertEqual(body['next_skill_id'], 'polynomial')
        self.assertEqual(body['events'], [])

    def test_current_error_blocks_next_skill(self):
        data = learning_payload()
        data['analysis']['focus_skill']['mastery_after'] = 0.99
        self.assertEqual(self.post('learning/decision', data)['action_type'], 'SOCRATIC_HINT')

    def test_disengagement_small_goal(self):
        data = learning_payload()
        data.update(disengaged=True, recent_failures=3)
        body = self.post('learning/decision', data)
        self.assertEqual(body['action_type'], 'MOTIVATION')
        self.assertIn('작은 목표', body['content']['message'])

    def test_lesson_sequence_and_answer(self):
        for stage, next_stage, field in [('explanation', 'example', 'explanation'),
                                        ('example', 'check', 'example'), ('check', None, 'check_question')]:
            body = self.post('learning/step', {'student_id': '17', 'skill_id': 'arithmetic', 'stage': stage})
            self.assertEqual(body['next_stage'], next_stage)
            self.assertTrue(body['content'][field])
        token = body['content']['problem']['check_token']
        correct = self.post('learning/check', {'student_id': '17', 'check_token': token, 'answer': '-12'})
        self.assertEqual(correct['action_type'], 'PRAISE')
        wrong = self.post('learning/check', {'student_id': '17', 'check_token': token, 'answer': '12'})
        self.assertEqual(wrong['next_stage'], 'example')

    def test_variant_preserves_template_sign_and_changes_numbers(self):
        for skill in ['arithmetic', 'polynomial']:
            problem = self.variant(skill)
            self.assertNotIn('answer', problem)
            data = learning.tokens.read(problem['problem_token'], 'problem', '17')
            self.assertGreater(data['a'], 0)
            self.assertLess(data['b'], 0)
            self.assertNotEqual(data['a'], 2)
            self.assertNotEqual(data['b'], -3)
            self.assertEqual(problem['difficulty'], 'easy')
            self.assertEqual(self.variant(skill)['problem_id'], problem['problem_id'])

    def test_problem_validation_failure_returns_no_problem(self):
        with patch.object(validator, 'validate_problem', return_value=False):
            body = self.post('learning/decision', learning_payload(stage='hint_complete'))
        self.assertEqual(body['action_type'], 'RETRY')
        self.assertIsNone(body['content']['problem'])

    def test_missing_or_unsupported_source_returns_retry(self):
        for source in [None, {'template': 'binomial_expansion', 'a': 2, 'b': -3},
                       {'template': 'signed_multiplication', 'a': 0, 'b': 3}]:
            data = learning_payload(stage='check')
            data['source_problem'] = source
            self.assertIsNone(self.post('learning/decision', data)['content']['problem'])

    def test_retry_success_and_event_deduplication(self):
        request = self.retry_payload(self.variant())
        first = self.post('learning/retry', request)
        self.assertEqual(first['action_type'], 'PRAISE')
        self.assertIn('원리', first['content']['message'])
        self.assertEqual({e['event_type'] for e in first['events']}, {'RETRY_SUCCESS', 'DAILY_GOAL_PROGRESS'})
        request['attempt_id'] = 'retry-2'
        second = self.post('learning/retry', request)
        self.assertEqual([e['event_id'] for e in first['events']], [e['event_id'] for e in second['events']])

    def test_mastery_and_misconception_events_require_evidence(self):
        data = learning_payload(stage='check')
        data['analysis']['first_error']['misconception_ids'] = ['MIS-test']
        problem = self.post('learning/decision', data)['content']['problem']
        request = self.retry_payload(problem)
        request.update(previous_mastery=0.4, mastery_after=0.85, misconception_resolved=True)
        body = self.post('learning/retry', request)
        self.assertEqual(body['next_skill_id'], 'polynomial')
        self.assertEqual({e['event_type'] for e in body['events']}, {'RETRY_SUCCESS', 'DAILY_GOAL_PROGRESS',
            'SKILL_IMPROVED', 'SKILL_MASTERED', 'MISCONCEPTION_OVERCOME'})
        request.update(previous_mastery=0.9, mastery_after=0.9)
        events = self.post('learning/retry', request)['events']
        self.assertNotIn('SKILL_MASTERED', {e['event_type'] for e in events})

    def test_no_misconception_event_without_original_misconception(self):
        request = self.retry_payload(self.variant())
        request['misconception_resolved'] = True
        kinds = {e['event_type'] for e in self.post('learning/retry', request)['events']}
        self.assertNotIn('MISCONCEPTION_OVERCOME', kinds)

    def test_wrong_retry_no_reward_and_different_intervention(self):
        request = self.retry_payload(self.variant(), correct=False)
        body = self.post('learning/retry', request)
        self.assertEqual(body['action_type'], 'REMEDIATION')
        self.assertEqual(body['events'], [])
        request['retry_count'] = 2
        body = self.post('learning/retry', request)
        self.assertEqual(body['action_type'], 'MOTIVATION')
        self.assertEqual(body['events'], [])

    def test_polynomial_retry(self):
        body = self.post('learning/retry', self.retry_payload(self.variant('polynomial')))
        self.assertEqual(body['action_type'], 'PRAISE')

    def test_token_tampering_and_student_mismatch(self):
        request = self.retry_payload(self.variant())
        request['student_id'] = 'other-student'
        self.assertEqual(self.client.post('/api/tutor/learning/retry', json=request).status_code, 422)
        request['student_id'] = '17'
        request['problem_token'] += 'tampered'
        self.assertEqual(self.client.post('/api/tutor/learning/retry', json=request).status_code, 422)

    def test_unknown_and_duplicate_skill_are_rejected(self):
        for states in [[{'skill_id': 'unknown', 'mastery': 0.9}],
                       [{'skill_id': 'arithmetic', 'mastery': 0.9}] * 2]:
            data = learning_payload()
            data['skills'] = states
            self.assertEqual(self.client.post('/api/tutor/learning/decision', json=data).status_code, 422)

    def test_unavailable_analysis_prevents_interventions(self):
        data = learning_payload(stage='check')
        data['analysis']['analysis_status'] = 'FAILED'
        response = self.client.post('/api/tutor/learning/decision', json=data)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['detail']['code'], 'ANALYSIS_UNAVAILABLE')

    def test_diagnostic_wrong_answer_stays_on_skill_then_stops(self):
        body = self.post('diagnostic/start', {'student_id': '17'})
        self.assertTrue(all(s['mastery'] is None for s in body['knowledge_map']))
        for answer in ['6', '-8']:
            body = self.post('diagnostic/answer', {'student_id': '17', 'session_token': body['session_token'],
                'question_id': body['question']['question_id'], 'answer': answer})
        self.assertTrue(body['completed'])
        self.assertEqual(body['knowledge_map'][0]['mastery'], 0)
        self.assertIsNone(body['knowledge_map'][1]['mastery'])
        self.assertIsNone(body['session_token'])

    def test_diagnostic_full_success_knowledge_map(self):
        body = self.post('diagnostic/start', {'student_id': '17'})
        answers = {q['question_id']: q['answer'] for q in catalog.data['diagnostic_questions']}
        while not body['completed']:
            question_id = body['question']['question_id']
            self.assertNotIn('answer', body['question'])
            body = self.post('diagnostic/answer', {'student_id': '17', 'session_token': body['session_token'],
                'question_id': question_id, 'answer': answers[question_id]})
        self.assertEqual(body['answered_count'], 6)
        self.assertTrue(all(s['mastery'] == 1 and s['evidence_count'] == 2 for s in body['knowledge_map']))

    def test_diagnostic_rejects_different_question_and_student(self):
        body = self.post('diagnostic/start', {'student_id': '17'})
        request = {'student_id': '17', 'session_token': body['session_token'], 'question_id': 'diag-p1', 'answer': '0'}
        self.assertEqual(self.client.post('/api/tutor/diagnostic/answer', json=request).status_code, 422)
        request.update(student_id='18', question_id='diag-a1')
        self.assertEqual(self.client.post('/api/tutor/diagnostic/answer', json=request).status_code, 422)

    def test_end_to_end_diagnosis_hint_variant_retry(self):
        diagnostic = self.post('diagnostic/start', {'student_id': '17'})
        for answer in ['6', '8']:
            diagnostic = self.post('diagnostic/answer', {'student_id': '17', 'session_token': diagnostic['session_token'],
                'question_id': diagnostic['question']['question_id'], 'answer': answer})
        data = learning_payload()
        data['skills'] = diagnostic['knowledge_map']
        self.assertEqual(self.post('learning/decision', data)['action_type'], 'SOCRATIC_HINT')
        data['stage'] = 'hint_complete'
        problem = self.post('learning/decision', data)['content']['problem']
        request = self.retry_payload(problem)
        request.update(previous_mastery=0.35, mastery_after=0.85)
        body = self.post('learning/retry', request)
        self.assertEqual(body['action_type'], 'NEXT_SKILL')
        self.assertEqual(body['next_skill_id'], 'polynomial')


class MathAndTokenTests(unittest.TestCase):
    def test_equivalent_polynomials_and_integers(self):
        validator = MathValidator()
        self.assertTrue(validator.equivalent('(x+4)*(x-2)', 'x^2+2*x-8'))
        self.assertTrue(validator.equivalent('(-3)*4', '-12'))
        self.assertFalse(validator.equivalent('12', '-12'))

    def test_disallowed_and_expensive_expressions(self):
        validator = MathValidator()
        for expression in ["__import__('os').system('echo unsafe')", 'x.__class__', '1/0',
                           'x**999999', 'y+1', 'True', '1.5', 'x*x*x*x*x',
                           '((((10000**4)**4)**4)**4)', 'x[0]', 'abs(-1)', '(' * 200]:
            with self.subTest(expression=expression), self.assertRaises(InvalidMathAnswer):
                validator.expression(expression)

    def test_generated_answer_validation(self):
        validator = MathValidator()
        self.assertTrue(validator.validate_problem('signed_multiplication', 4, -2, '-8'))
        self.assertFalse(validator.validate_problem('signed_multiplication', 4, -2, '8'))
        self.assertTrue(validator.validate_problem('binomial_expansion', 4, -2, 'x*x+2*x-8'))
        self.assertFalse(validator.validate_problem('unsupported', 1, 2, '2'))

    def test_answer_representation_matches_learning_task(self):
        validator = MathValidator()
        self.assertFalse(validator.matches_task('(x+2)*(x-3)', 'x^2-x-6', 'expanded'))
        self.assertTrue(validator.matches_task('x*x-x-6', 'x^2-x-6', 'expanded'))
        self.assertFalse(validator.matches_task('x^2+3*x+2', '(x+1)*(x+2)', 'factored'))
        self.assertTrue(validator.matches_task('(x+2)*(x+1)', '(x+1)*(x+2)', 'factored'))

    def test_tokens_expire_and_have_purpose(self):
        service = TokenService(b'test-secret', ttl_seconds=-1)
        token = service.issue('problem', {'student_id': '17'})
        with self.assertRaises(InvalidToken):
            service.read(token, 'problem', '17')
        service = TokenService(b'test-secret')
        token = service.issue('lesson', {'student_id': '17'})
        with self.assertRaises(InvalidToken):
            service.read(token, 'problem', '17')
