import unittest
from fastapi.testclient import TestClient
from app.main import app
from tests.helpers import payload


class DecisionApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_example_response(self):
        response = self.client.post('/api/tutor/decision', json=payload())
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['action_type'], 'SOCRATIC_HINT')
        self.assertEqual(body['target'], {'skill_id': 'arithmetic', 'error_type': 'calculation',
                                          'error_subtype': 'arithmetic_slip'})
        self.assertIn('3번째', body['content']['message'])
        self.assertNotIn('-6', body['content']['message'])
        self.assertEqual(body['next_step'], 'RETRY')
        self.assertIsNone(body['reward_event'])

    def test_no_error_mastery_response(self):
        data = payload()
        data['first_error'] = None
        data['focus_skill']['mastery_after'] = 0.8
        response = self.client.post('/api/tutor/decision', json=data)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['action_type'], 'NEXT_SKILL')
        self.assertIsNone(body['target']['error_type'])
        self.assertIsNone(body['next_step'])
        self.assertIsNone(body['reward_event'])

    def test_unavailable_analysis(self):
        data = payload()
        data['analysis_status'] = 'FAILED'
        response = self.client.post('/api/tutor/decision', json=data)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['detail']['code'], 'ANALYSIS_UNAVAILABLE')

    def test_invalid_inputs(self):
        mutations = [
            lambda d: d.update(schema_version='2.0'),
            lambda d: d.pop('student_id'),
            lambda d: d.update(student_id=''),
            lambda d: d.update(hint_count=-1),
            lambda d: d.update(consecutive_wrong=1.5),
            lambda d: d.update(hint_count=True),
            lambda d: d['focus_skill'].update(mastery_after=1.1),
            lambda d: d['focus_skill'].update(mastery_after=-0.1),
            lambda d: d['first_error'].update(confidence=2),
            lambda d: d['first_error'].update(step_no=0),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                data = payload()
                mutate(data)
                self.assertEqual(self.client.post('/api/tutor/decision', json=data).status_code, 422)

    def test_swagger_and_openapi(self):
        self.assertEqual(self.client.get('/docs').status_code, 200)
        schema = self.client.get('/openapi.json').json()
        self.assertIn('/api/tutor/decision', schema['paths'])
        self.assertEqual(schema['components']['schemas']['TutorRequest']['examples'][0], payload())
        self.assertEqual(len(schema['components']['schemas']['TutorAction']['enum']), 9)
