import json
import hashlib
from pathlib import Path
from app.models.learning import SkillState


class UnknownSkill(ValueError):
    pass


class FixtureCatalog:
    def __init__(self, path: Path | None = None, data: dict | None = None):
        self.data = data if data is not None else json.loads((path or Path(__file__).resolve().parents[2] / "data/tutor_fixtures.json").read_text())
        self.data_source = self.data.get('data_source', 'fixture')
        self.skills = {skill['skill_id']: skill for skill in self.data['skills']}

    @property
    def identity(self) -> str:
        return hashlib.sha256(json.dumps(self.data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

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
        if self.data_source == 'backend_payload':
            from app.models.integration import VideoRankRequest, VideoCandidate
            from app.services.video_service import VideoService
            ranked = VideoService().rank(VideoRankRequest(skill_id=skill_id, mastery=mastery,
                candidates=[VideoCandidate.model_validate(v) for v in self.data['videos']], limit=1))
            if ranked.items:
                video = ranked.items[0].candidate
                return {k: str(getattr(video, k)) for k in ['content_id', 'title', 'url']}
            return None
        for video in self.data['videos']:
            if video['skill_id'] == skill_id and video['min_mastery'] <= mastery <= video['max_mastery']:
                return {k: str(video[k]) for k in ['content_id', 'title', 'url']}
        return None
