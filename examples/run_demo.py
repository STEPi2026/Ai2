"""Run public API workflow locally with TestClient; no network or database required."""
import json
import re
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app


def main():
    with TestClient(app) as client:
        def post(path, data):
            response = client.post('/api/tutor/' + path, json=data)
            response.raise_for_status()
            return response.json()

        diagnostic = post('diagnostic/start', {'student_id': '17'})
        for answer in ['6', '8']:
            diagnostic = post('diagnostic/answer', {'student_id': '17',
                'session_token': diagnostic['session_token'],
                'question_id': diagnostic['question']['question_id'], 'answer': answer})
        request = json.loads((Path(__file__).with_name('learning_request.json')).read_text())
        request['skills'] = diagnostic['knowledge_map']
        hint = post('learning/decision', request)
        request['stage'] = 'hint_complete'
        variant = post('learning/decision', request)
        problem = variant['content']['problem']
        # Demo simulates a student's correct arithmetic answer from the displayed prompt.
        a, b = map(int, re.findall(r'\(([+-]\d+)\)', problem['prompt']))
        retry = post('learning/retry', {'student_id': '17', 'attempt_id': 'demo-retry-1',
            'problem_token': problem['problem_token'], 'answer': str(a*b),
            'previous_mastery': 0.35, 'mastery_after': 0.85})
        print(json.dumps({'knowledge_map': diagnostic['knowledge_map'],
            'hint': hint['content']['message'], 'variant': problem['prompt'],
            'retry_action': retry['action_type'], 'next_skill': retry['next_skill_id'],
            'events': [event['event_type'] for event in retry['events']]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
