import json
from pathlib import Path
from app.models.learning import SkillState


class UnknownSkill(ValueError):
    pass


class FixtureCatalog:
    def __init__(self, path: Path | None = None):
        self.data = json.loads((path or Path(__file__).resolve().parents[2] / "data/tutor_fixtures.json").read_text())
        self.skills = {skill['skill_id']: skill for skill in self.data['skills']}

    def skill(self, skill_id: str) -> dict:
        if skill_id not in self.skills:
            raise UnknownSkill("테스트용 Skill 목록에 없는 Skill입니다.")
        return self.skills[skill_id]

    def state_map(self, states: list[SkillState]) -> dict[str, float | None]:
        result = {}
        for state in states:
            self.skill(state.skill_id)
            if state.skill_id in result:
                raise ValueError("Skill 상태가 중복되었습니다.")
            result[state.skill_id] = state.mastery
        return result

    def deficient_prerequisite(self, skill_id: str, states: list[SkillState], threshold: float) -> str | None:
        mastery = self.state_map(states)
        visited = set()
        def walk(current):
            if current in visited:
                return None
            visited.add(current)
            for prerequisite in self.skill(current)['prerequisites']:
                earlier = walk(prerequisite)
                if earlier:
                    return earlier
                value = mastery.get(prerequisite)
                if value is not None and value < threshold:
                    return prerequisite
            return None
        return walk(skill_id)

    def unknown_prerequisite(self, skill_id: str, states: list[SkillState]) -> str | None:
        mastery = self.state_map(states)
        visited = set()
        def walk(current):
            if current in visited:
                return None
            visited.add(current)
            for prerequisite in self.skill(current)['prerequisites']:
                earlier = walk(prerequisite)
                if earlier:
                    return earlier
                if mastery.get(prerequisite) is None:
                    return prerequisite
            return None
        return walk(skill_id)

    def next_skill(self, skill_id: str, states: list[SkillState], threshold: float) -> str | None:
        mastery = self.state_map(states)
        visited = set()
        def walk(current):
            if current in visited:
                return None
            visited.add(current)
            for candidate in self.skill(current)['next_skills']:
                skill = self.skill(candidate)
                if mastery.get(candidate) is not None and mastery[candidate] >= threshold:
                    following = walk(candidate)
                    if following:
                        return following
                    continue
                if all(mastery.get(p) is not None and mastery[p] >= threshold for p in skill['prerequisites']):
                    return candidate
            return None
        return walk(skill_id)

    def video(self, skill_id: str, mastery: float) -> dict[str, str] | None:
        self.skill(skill_id)
        for video in self.data['videos']:
            if video['skill_id'] == skill_id and video['min_mastery'] <= mastery <= video['max_mastery']:
                return {k: str(video[k]) for k in ['content_id', 'title', 'url']}
        return None
