from app.models.integration import VideoRankRequest, VideoRankResponse, RankedVideo


class VideoService:
    def rank(self, request: VideoRankRequest) -> VideoRankResponse:
        ids = [item.content_id for item in request.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("영상 후보 content_id가 중복되었습니다.")
        items = []
        for candidate in request.candidates:
            if (candidate.skill_id != request.skill_id or not candidate.approved
                    or candidate.language != request.language
                    or candidate.duration_seconds > request.max_duration_seconds
                    or not candidate.min_mastery <= request.mastery <= candidate.max_mastery):
                continue
            middle = (candidate.min_mastery + candidate.max_mastery) / 2
            match = 1 - abs(request.mastery - middle)
            brevity = 1 - candidate.duration_seconds / request.max_duration_seconds
            score = 0.55 * match + 0.3 * candidate.quality_score + 0.15 * brevity
            items.append(RankedVideo(candidate=candidate, score=round(score, 6), reasons=[
                "현재 Skill 및 숙련도 구간 일치", "검토 승인된 후보", "언어·길이 조건 충족",
                f"수준 적합도 {match:.2f}, 자료 품질 {candidate.quality_score:.2f}"]))
        items.sort(key=lambda item: (-item.score, item.candidate.content_id))
        return VideoRankResponse(skill_id=request.skill_id, items=items[:request.limit])
