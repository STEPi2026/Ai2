import importlib.util
import unittest
from pathlib import Path


@unittest.skipUnless(importlib.util.find_spec('streamlit'), 'Optional dashboard dependency not installed')
class DashboardTests(unittest.TestCase):
    def test_policy_comparison_and_state_experiment(self):
        from streamlit.testing.v1 import AppTest
        page = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'dashboard/app.py'), default_timeout=30).run()
        self.assertFalse(page.exception)
        self.assertEqual(page.metric[0].value, 'SOCRATIC_HINT')
        next(item for item in page.slider if item.label == '개념 복습 기준 (미만)').set_value(0.4).run()
        self.assertFalse(page.exception)
        self.assertEqual(page.metric[1].value, 'CONCEPT_REVIEW')
        next(item for item in page.button if item.label == '가상 학생 상태에 결과 반영').click().run()
        self.assertFalse(page.exception)
        values = page.session_state['map_skills']
        self.assertGreater(values[0]['mastery'], 0.35)
        next(item for item in page.button if item.label == '가상 학생 상태에 결과 반영').click().run()
        self.assertFalse(page.exception)
        self.assertEqual(page.session_state['map_skills'], values)
