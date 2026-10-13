"""Local catalog → roadmap → lesson → result → update → replan demonstration."""
import json
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app


def main():
    catalog = json.loads(Path(__file__).with_name('backend_catalog.json').read_text())
    states = [{'skill_id': 'arithmetic', 'mastery': 0.79, 'evidence_count': 2},
              {'skill_id': 'polynomial', 'mastery': 0.35}, {'skill_id': 'factoring', 'mastery': None}]
    with TestClient(app) as client:
        def post(path, data):
            response = client.post('/api/tutor/integration/' + path, json={'catalog': catalog, **data})
            response.raise_for_status()
            return response.json()
        initial = post('roadmap', {'planning': {'student_id': 'demo-student', 'skills': states,
            'goal_skill_ids': ['factoring']}})
        for stage in ['explanation', 'example', 'check']:
            lesson = post('lesson', {'lesson': {'student_id': 'demo-student', 'skill_id': initial['next_skill_id'], 'stage': stage}})
        checked = post('check', {'check': {'student_id': 'demo-student',
            'check_token': lesson['content']['problem']['check_token'], 'answer': '-12'}})
        if not checked['answer_correct']:
            raise RuntimeError('Demo answer was not correct')
        proposal = post('state-update', {'update': {'student_id': 'demo-student', 'expected_version': 0,
            'skills': states, 'observation': {'attempt_id': 'check-1', 'skill_id': 'arithmetic', 'correct': True}}})
        replanned = post('roadmap', {'planning': {'student_id': 'demo-student', 'skills': proposal['skills'],
            'goal_skill_ids': ['factoring'], 'previous_roadmap_id': initial['roadmap_id']}})
        print(json.dumps({'source': 'local_example_catalog', 'original_roadmap': [s['skill_id'] for s in initial['steps']],
            'check_correct': checked['answer_correct'], 'mastery_update_proposal': proposal['changed_skill'],
            'replanned_roadmap': [s['skill_id'] for s in replanned['steps']],
            'next_skill': replanned['next_skill_id'], 'db_saved': False}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
