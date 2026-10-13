import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch
import httpx
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.main import app
from app.api.learning import catalog
from app.models.integration import BackendCatalog, DecisionEnvelope, VideoRankRequest
from app.models.planning import PlanningRequest, StateUpdateRequest
from app.policies.planning_policy import PlanningPolicy
from app.policies.diagnostic_policy import DiagnosticPolicy
from app.services.backend_adapter import runtime_catalog
from app.services.diagnostic_service import DiagnosticService
from app.services.math_validator import MathValidator
from app.services.planning_service import PlanningService, classify
from app.services.remote_client import TutorApiClient
from app.services.tokens import TokenService
from tests.helpers import payload

ROOT = Path(__file__).resolve().parents[1]


def backend_catalog():
    return json.loads((ROOT / 'examples/backend_catalog.json').read_text())


def envelope():
    return json.loads((ROOT / 'examples/backend_decision.json').read_text())


def states(a=0.2, p=0.4, f=0.1):
    return [{'skill_id': name, 'mastery': value, 'evidence_count': 2} for name, value in
            [('arithmetic', a), ('polynomial', p), ('factoring', f)]]


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def post(self, path, data):
        response = self.client.post('/api/tutor/' + path, json=data)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_five_levels_at_boundaries(self):
        for score, level in [(0, 'NOVICE'), (0.199, 'NOVICE'), (0.2, 'BASIC'),
                             (0.4, 'DEVELOPING'), (0.6, 'PROFICIENT'), (0.8, 'MASTERED'), (1, 'MASTERED')]:
            with self.subTest(score=score):
                self.assertEqual(classify(score).level.value, level)
        self.assertIsNone(classify(None).level)
        self.assertEqual(self.client.get('/api/tutor/mastery/level?mastery=0.6').json()['level'], 'PROFICIENT')
        for score in ['-1', '2', 'nan', 'inf']:
            self.assertEqual(self.client.get('/api/tutor/mastery/level?mastery=' + score).status_code, 422)

    def test_invalid_planning_policies(self):
        for values in [dict(level_boundaries=(0.2, 0.1, 0.6, 0.8)),
                       dict(level_boundaries=(0.2, 0.4, 0.6, float('nan'))),
                       dict(deficit_weight=0.1), dict(success_gain=0)]:
            with self.assertRaises(ValidationError):
                PlanningPolicy(**values)

    def test_roadmap_respects_prerequisites_before_weakest_skill(self):
        body = self.post('planning/roadmap', {'student_id': '17', 'skills': states(), 'goal_skill_ids': ['factoring']})
        self.assertEqual([s['skill_id'] for s in body['steps']], ['arithmetic', 'polynomial', 'factoring'])
        self.assertTrue(body['steps'][0]['ready'])
        self.assertFalse(body['steps'][1]['ready'])
        self.assertEqual(body['next_skill_id'], 'arithmetic')
        self.assertEqual(body['data_source'], 'fixture')

    def test_roadmap_unknown_requires_diagnosis(self):
        body = self.post('planning/roadmap', {'student_id': '17', 'goal_skill_ids': ['factoring']})
        self.assertTrue(all(s['kind'] == 'DIAGNOSTIC' for s in body['steps']))
        self.assertTrue(all(p['level'] is None for p in body['priorities']))

    def test_roadmap_completed_and_goal_scope(self):
        body = self.post('planning/roadmap', {'student_id': '17', 'skills': states(0.9, 0.9, 0.9)})
        self.assertTrue(body['completed'])
        self.assertEqual(body['steps'], [])
        self.assertIsNone(body['next_skill_id'])
        scoped = self.post('planning/roadmap', {'student_id': '17', 'skills': states(), 'goal_skill_ids': ['arithmetic']})
        self.assertEqual(len(scoped['steps']), 1)

    def test_priority_recent_failures_and_replan(self):
        initial = {'student_id': '17', 'skills': states(0.7, 0.7, 0.7)}
        first = self.post('planning/roadmap', initial)
        initial['recent_attempts'] = [{'attempt_id': f'a-{i}', 'skill_id': 'factoring', 'correct': False}
                                      for i in range(3)]
        second = self.post('planning/roadmap', initial)
        self.assertEqual(second['priorities'][0]['skill_id'], 'factoring')
        self.assertEqual(second['steps'][0]['skill_id'], 'arithmetic')
        initial.update(skills=states(0.9, 0.7, 0.7), previous_roadmap_id=first['roadmap_id'])
        third = self.post('planning/roadmap', initial)
        self.assertEqual(third['next_skill_id'], 'polynomial')
        self.assertEqual(third['previous_roadmap_id'], first['roadmap_id'])
        self.assertNotEqual(third['roadmap_id'], first['roadmap_id'])

    def test_duplicate_unknown_planning_input(self):
        for extra in [{'goal_skill_ids': ['arithmetic'] * 2}, {'goal_skill_ids': ['SKL-unknown']},
                      {'skills': states() + states()},
                      {'recent_attempts': [{'attempt_id': 'a', 'skill_id': 'arithmetic', 'correct': False}] * 2}]:
            response = self.client.post('/api/tutor/planning/roadmap', json={'student_id': '17', **extra})
            self.assertEqual(response.status_code, 422)

    def test_state_success_failure_and_hint_weight(self):
        request = {'student_id': '17', 'expected_version': 2, 'skills': states(0.5),
                   'observation': {'attempt_id': 'update-a', 'skill_id': 'arithmetic', 'correct': True}}
        first = self.post('state/update', request)
        changed = next(s for s in first['skills'] if s['skill_id'] == 'arithmetic')
        self.assertEqual(changed['mastery'], 0.575)
        self.assertEqual(changed['evidence_count'], 3)
        self.assertEqual(first['proposed_version'], 3)
        self.assertEqual(first['persistence_owner'], 'Backend')
        request['observation']['used_hint'] = True
        hinted = self.post('state/update', request)
        self.assertEqual(hinted['changed_skill']['mastery'], 0.5375)
        request['observation']['correct'] = False
        failed = self.post('state/update', request)
        self.assertEqual(failed['changed_skill']['mastery'], 0.45)

    def test_state_duplicate_is_noop_and_id_stable(self):
        request = {'student_id': '17', 'expected_version': 0, 'skills': states(0.5),
                   'observation': {'attempt_id': 'once', 'skill_id': 'arithmetic', 'correct': True}}
        first = self.post('state/update', request)
        request.update(skills=first['skills'], expected_version=1, applied_attempt_ids=['once'])
        second = self.post('state/update', request)
        self.assertFalse(second['applied'])
        self.assertEqual(second['proposed_version'], 1)
        self.assertEqual(second['skills'], first['skills'])
        self.assertEqual(second['update_id'], first['update_id'])

    def test_state_unknown_prior_and_invalid_data(self):
        request = {'student_id': '17', 'expected_version': 0,
                   'observation': {'attempt_id': 'first', 'skill_id': 'arithmetic', 'correct': True}}
        body = self.post('state/update', request)
        self.assertEqual(body['changed_skill']['mastery'], 0.575)
        for mutation in [{'expected_version': -1}, {'expected_version': True}, {'extra': 'no'}]:
            response = self.client.post('/api/tutor/state/update', json={**request, **mutation})
            self.assertEqual(response.status_code, 422)

    def test_diagnostic_policy_caps_questions(self):
        service = DiagnosticService(catalog, MathValidator(), TokenService(b'test'),
                                    DiagnosticPolicy(max_questions=1))
        from app.models.diagnostic import DiagnosticAnswer
        start = service.start('17')
        result = service.answer(DiagnosticAnswer(student_id='17', session_token=start.session_token,
                question_id=start.question['question_id'], answer='-6'))
        self.assertTrue(result.completed)
        self.assertEqual(result.answered_count, 1)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def post(self, path, data):
        response = self.client.post('/api/tutor/integration/' + path, json=data)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_backend_catalog_accepts_opaque_skill_codes(self):
        data = envelope()
        data['catalog']['skills'][0]['skill_id'] = 'SKL-001'
        data['catalog']['skills'][1]['prerequisites'] = ['SKL-001']
        for q in data['catalog']['diagnostic_questions']:
            if q['skill_id'] == 'arithmetic': q['skill_id'] = 'SKL-001'
        data['catalog']['videos'][0]['skill_id'] = 'SKL-001'
        data['learning']['analysis']['focus_skill']['skill_id'] = 'SKL-001'
        data['learning']['skills'][0]['skill_id'] = 'SKL-001'
        data['learning']['recent_attempts'][0]['skill_id'] = 'SKL-001'
        body = self.post('decision', data)
        self.assertEqual(body['target_skill_id'], 'SKL-001')
        self.assertEqual(body['data_source'], 'backend_payload')
        self.assertEqual(body['focus_mastery_level'], 'BASIC')

    def test_catalog_rejects_cycles_and_missing_references(self):
        for mutate in [lambda c: c['skills'][0].update(prerequisites=['factoring']),
                       lambda c: c['skills'][0].update(concept_id='missing'),
                       lambda c: c['skills'].append(c['skills'][0]),
                       lambda c: c['diagnostic_questions'][0].update(skill_id='missing')]:
            data = backend_catalog()
            mutate(data)
            with self.assertRaises(ValidationError):
                BackendCatalog.model_validate(data)

    def test_invalid_backend_content_is_422(self):
        data = envelope()
        data['catalog']['concepts'][0]['check_answer'] = "__import__('os')"
        self.assertEqual(self.client.post('/api/tutor/integration/decision', json=data).status_code, 422)

    def test_misconception_rule_is_configurable(self):
        data = envelope()
        data['learning']['analysis']['first_error']['misconception_ids'] = ['MIS-001']
        data['catalog']['error_rules'] = [{'misconception_id': 'MIS-001', 'action': 'CONCEPT_REVIEW'}]
        self.assertEqual(self.post('decision', data)['action_type'], 'CONCEPT_REVIEW')
        data['catalog']['error_rules'][0]['action'] = 'REMEDIATION'
        self.assertEqual(self.post('decision', data)['action_type'], 'REMEDIATION')

    def test_catalog_change_invalidates_issued_token(self):
        data = envelope()
        data['learning']['stage'] = 'check'
        problem = self.post('decision', data)['content']['problem']
        changed = copy.deepcopy(data['catalog'])
        changed['revision'] = 'next'
        response = self.client.post('/api/tutor/integration/retry', json={'catalog': changed,
            'retry': {'student_id': '17', 'attempt_id': 'retry', 'problem_token': problem['problem_token'], 'answer': '0'}})
        self.assertEqual(response.status_code, 422)

    def test_backend_roadmap_concept_check_update_replan_e2e(self):
        contract = backend_catalog()
        initial = self.post('roadmap', {'catalog': contract, 'planning': {
            'student_id': '17', 'skills': states(0.5), 'goal_skill_ids': ['factoring']}})
        self.assertEqual(initial['next_skill_id'], 'arithmetic')
        for stage in ['explanation', 'example', 'check']:
            lesson = self.post('lesson', {'catalog': contract, 'lesson': {
                'student_id': '17', 'skill_id': initial['next_skill_id'], 'stage': stage}})
        check = self.post('check', {'catalog': contract, 'check': {'student_id': '17',
            'check_token': lesson['content']['problem']['check_token'], 'answer': '-12'}})
        self.assertEqual(check['action_type'], 'PRAISE')
        update = self.post('state-update', {'catalog': contract, 'update': {'student_id': '17',
            'expected_version': 4, 'skills': states(0.79), 'observation': {
                'attempt_id': 'lesson-check', 'skill_id': 'arithmetic', 'correct': True}}})
        replanned = self.post('roadmap', {'catalog': contract, 'planning': {'student_id': '17',
            'skills': update['skills'], 'goal_skill_ids': ['factoring'], 'previous_roadmap_id': initial['roadmap_id']}})
        self.assertEqual(replanned['next_skill_id'], 'polynomial')
        self.assertEqual(update['proposed_version'], 5)

    def test_backend_diagnostic_to_map_e2e(self):
        contract = backend_catalog()
        body = self.post('diagnostic/start', {'catalog': contract, 'start': {'student_id': '17'}})
        answers = {q['question_id']: q['answer'] for q in contract['diagnostic_questions']}
        while not body['completed']:
            question_id = body['question']['question_id']
            body = self.post('diagnostic/answer', {'catalog': contract, 'answer': {'student_id': '17',
                'session_token': body['session_token'], 'question_id': question_id, 'answer': answers[question_id]}})
        self.assertEqual(body['data_source'], 'backend_payload')
        self.assertTrue(all(s['mastery'] == 1 for s in body['knowledge_map']))

    def test_ai1_backend_tutor_pipeline_mock_only(self):
        data = envelope()
        data['learning']['analysis'] = payload()  # AI① result fixture, not real OCR/AI①.
        def gateway(request):
            response = self.client.post(request.url.path, json=json.loads(request.content))
            return httpx.Response(response.status_code, json=response.json())
        remote = TutorApiClient('http://tutor.test', transport=httpx.MockTransport(gateway))
        self.addCleanup(remote.close)
        result = remote.decide(DecisionEnvelope.model_validate(data))
        self.assertEqual(result.status, 'OK')
        self.assertEqual(result.response.action_type.value, 'SOCRATIC_HINT')

    def test_timeouts_are_bounded_and_have_fallback(self):
        calls = []
        def timeout(request):
            calls.append(request)
            raise httpx.ReadTimeout('timeout')
        remote = TutorApiClient('http://tutor.test', transport=httpx.MockTransport(timeout), max_attempts=2)
        self.addCleanup(remote.close)
        result = remote.decide(DecisionEnvelope.model_validate(envelope()))
        self.assertEqual(len(calls), 2)
        self.assertEqual(result.status, 'UNAVAILABLE')
        self.assertEqual(result.fallback_action, 'RETRY')

    def test_4xx_is_not_retried(self):
        calls = []
        def reject(request):
            calls.append(request)
            return httpx.Response(422, json={'detail': 'invalid'})
        remote = TutorApiClient('http://tutor.test', transport=httpx.MockTransport(reject))
        self.addCleanup(remote.close)
        self.assertEqual(remote.decide(DecisionEnvelope.model_validate(envelope())).status, 'REJECTED')
        self.assertEqual(len(calls), 1)

    def test_transient_503_retries_and_recovers(self):
        calls = []
        def gateway(request):
            calls.append(request)
            if len(calls) == 1: return httpx.Response(503)
            response = self.client.post(request.url.path, json=json.loads(request.content))
            return httpx.Response(response.status_code, json=response.json())
        remote = TutorApiClient('http://tutor.test', transport=httpx.MockTransport(gateway))
        self.addCleanup(remote.close)
        self.assertEqual(remote.decide(DecisionEnvelope.model_validate(envelope())).status, 'OK')
        self.assertEqual(len(calls), 2)

    def test_invalid_remote_json_has_fallback(self):
        remote = TutorApiClient('http://tutor.test', transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={'unexpected': True})))
        self.addCleanup(remote.close)
        self.assertEqual(remote.decide(DecisionEnvelope.model_validate(envelope())).status, 'UNAVAILABLE')

    def test_contract_is_explicitly_proposed(self):
        body = self.client.get('/api/tutor/integration/contract-status').json()
        self.assertEqual(body['agreement_status'], 'PROPOSED')
        self.assertFalse(body['real_backend_e2e_verified'])


class VideoRankingTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def candidate(self, content_id='v1', **extra):
        return {'content_id': content_id, 'skill_id': 'arithmetic', 'title': '후보',
                'url': 'https://example.com/video', 'approved': True,
                'min_mastery': 0, 'max_mastery': 0.6, 'quality_score': 0.5, **extra}

    def test_rank_filters_and_orders_quality(self):
        candidates = [self.candidate('low', quality_score=0.1), self.candidate('high', quality_score=0.9),
            self.candidate('unreviewed', approved=False), self.candidate('other', skill_id='factoring'),
            self.candidate('wrong-level', min_mastery=0.8, max_mastery=1),
            self.candidate('long', duration_seconds=2000), self.candidate('en', language='en')]
        response = self.client.post('/api/tutor/videos/rank', json={'skill_id': 'arithmetic',
            'mastery': 0.3, 'candidates': candidates})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([v['candidate']['content_id'] for v in response.json()['items']], ['high', 'low'])

    def test_no_approved_candidates_returns_empty(self):
        response = self.client.post('/api/tutor/videos/rank', json={'skill_id': 'arithmetic', 'mastery': 0.3,
            'candidates': [self.candidate(approved=False)]})
        self.assertEqual(response.json()['items'], [])

    def test_youtube_contract_and_unsafe_url_validation(self):
        for url in ['https://www.youtube.com/watch?v=abcdefghijk', 'https://youtu.be/abcdefghijk']:
            VideoRankRequest(skill_id='arithmetic', mastery=0.3, candidates=[self.candidate(source='YOUTUBE', url=url)])
        for url in ['javascript:alert(1)', 'http://example.com/video', 'https://evil.test/watch?v=abcdefghijk',
                    'https://www.youtube.com/channel/abc']:
            with self.assertRaises(ValidationError):
                VideoRankRequest(skill_id='arithmetic', mastery=0.3, candidates=[self.candidate(source='YOUTUBE', url=url)])

    def test_duplicate_candidates_are_rejected(self):
        response = self.client.post('/api/tutor/videos/rank', json={'skill_id': 'arithmetic', 'mastery': 0.3,
            'candidates': [self.candidate()] * 2})
        self.assertEqual(response.status_code, 422)

    def test_backend_review_uses_only_approved_video(self):
        data = envelope()
        data['learning']['analysis']['focus_skill']['mastery_after'] = 0.1
        rejected = self.client.post('/api/tutor/integration/decision', json=data)
        self.assertIsNone(rejected.json()['content']['video'])
        data['catalog']['videos'][0]['approved'] = True
        approved = self.client.post('/api/tutor/integration/decision', json=data)
        self.assertEqual(approved.json()['content']['video']['content_id'], 'fixture-sign-01')


class OpenApiTests(unittest.TestCase):
    def test_every_api_has_valid_documentation_and_body_validation(self):
        with TestClient(app) as client:
            self.assertEqual(client.get('/docs').status_code, 200)
            self.assertEqual(client.get('/health').json(), {'status': 'ok'})
            schema = client.get('/openapi.json').json()
            for path, operations in schema['paths'].items():
                if 'post' in operations:
                    with self.subTest(path=path):
                        self.assertIn('requestBody', operations['post'])
                        self.assertEqual(client.post(path, json={}).status_code, 422)
