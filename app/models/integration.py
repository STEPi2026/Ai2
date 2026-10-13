import re
from typing import Literal
from urllib.parse import urlparse, parse_qs
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.models.learning import LearningRequest, LearningResponse, RetryRequest, LessonRequest, LessonAnswerRequest
from app.models.planning import PlanningRequest, StateUpdateRequest
from app.models.diagnostic import DiagnosticStart, DiagnosticAnswer


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConceptRecord(ContractModel):
    concept_id: str = Field(min_length=1)
    explanation_easy: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    example: str = Field(min_length=1)
    check_question: str = Field(min_length=1)
    check_answer: str = Field(min_length=1, max_length=200)


class SkillRecord(ContractModel):
    skill_id: str = Field(min_length=1)
    name_ko: str = Field(min_length=1)
    concept_id: str = Field(min_length=1)
    prerequisites: list[str] = Field(default_factory=list, max_length=100)
    templates: list[Literal["signed_multiplication", "binomial_expansion"]] = Field(default_factory=list)
    answer_form: Literal["integer", "expanded", "factored"]


class VideoCandidate(ContractModel):
    content_id: str = Field(min_length=1)
    skill_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: str = Field(min_length=1, max_length=2000)
    source: Literal["BACKEND", "YOUTUBE"] = "BACKEND"
    approved: bool = False
    language: str = "ko"
    min_mastery: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)
    max_mastery: float = Field(default=1, ge=0, le=1, allow_inf_nan=False)
    duration_seconds: int = Field(default=300, ge=1, le=86400, strict=True)
    quality_score: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_video(self):
        if self.min_mastery > self.max_mastery:
            raise ValueError("video mastery range is inverted")
        url = urlparse(self.url)
        if url.scheme != 'https' or not url.hostname or url.username or url.password:
            raise ValueError("video url must be an HTTPS URL without credentials")
        if self.source == 'YOUTUBE':
            if url.hostname in ('youtube.com', 'www.youtube.com'):
                video_id = parse_qs(url.query).get('v', [''])[0] if url.path == '/watch' else ''
            elif url.hostname == 'youtu.be':
                video_id = url.path.lstrip('/')
            else:
                video_id = ''
            if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
                raise ValueError("YouTube candidate must have a valid watch/video URL")
        return self


class DiagnosticQuestion(ContractModel):
    question_id: str = Field(min_length=1)
    skill_id: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    answer: str = Field(min_length=1, max_length=200)


class ErrorRule(ContractModel):
    error_type: str | None = None
    error_subtype: str | None = None
    misconception_id: str | None = None
    action: Literal["SOCRATIC_HINT", "CONCEPT_REVIEW", "REMEDIATION"]

    @model_validator(mode="after")
    def validate_rule(self):
        if not any((self.error_type, self.error_subtype, self.misconception_id)):
            raise ValueError("error rule requires a matching condition")
        return self


class BackendCatalog(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    revision: str = Field(min_length=1)
    skills: list[SkillRecord] = Field(min_length=1, max_length=100)
    concepts: list[ConceptRecord] = Field(min_length=1, max_length=100)
    videos: list[VideoCandidate] = Field(default_factory=list, max_length=200)
    diagnostic_questions: list[DiagnosticQuestion] = Field(default_factory=list, max_length=500)
    error_rules: list[ErrorRule] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_catalog(self):
        ids = [s.skill_id for s in self.skills]
        concepts = [c.concept_id for c in self.concepts]
        if len(ids) != len(set(ids)) or len(concepts) != len(set(concepts)):
            raise ValueError("duplicate Skill/Concept ID")
        for values in ([v.content_id for v in self.videos], [q.question_id for q in self.diagnostic_questions]):
            if len(values) != len(set(values)):
                raise ValueError("duplicate content/question ID")
        graph = {s.skill_id: s.prerequisites for s in self.skills}
        for skill in self.skills:
            if skill.concept_id not in concepts or any(p not in graph for p in skill.prerequisites):
                raise ValueError("unknown concept/prerequisite reference")
            if len(skill.prerequisites) != len(set(skill.prerequisites)):
                raise ValueError("duplicate prerequisite")
        visiting, visited = set(), set()
        def walk(current):
            if current in visiting:
                raise ValueError("cyclic prerequisite graph")
            if current in visited:
                return
            visiting.add(current)
            for predecessor in graph[current]:
                walk(predecessor)
            visiting.remove(current)
            visited.add(current)
        for skill_id in graph:
            walk(skill_id)
        if any(v.skill_id not in graph for v in self.videos) or any(q.skill_id not in graph for q in self.diagnostic_questions):
            raise ValueError("unknown content/question Skill reference")
        return self


class DecisionEnvelope(ContractModel):
    catalog: BackendCatalog
    learning: LearningRequest


class PlanEnvelope(ContractModel):
    catalog: BackendCatalog
    planning: PlanningRequest


class UpdateEnvelope(ContractModel):
    catalog: BackendCatalog
    update: StateUpdateRequest


class RetryEnvelope(ContractModel):
    catalog: BackendCatalog
    retry: RetryRequest


class LessonEnvelope(ContractModel):
    catalog: BackendCatalog
    lesson: LessonRequest


class CheckEnvelope(ContractModel):
    catalog: BackendCatalog
    check: LessonAnswerRequest


class DiagnosticEnvelope(ContractModel):
    catalog: BackendCatalog
    start: DiagnosticStart


class DiagnosticAnswerEnvelope(ContractModel):
    catalog: BackendCatalog
    answer: DiagnosticAnswer


class VideoRankRequest(ContractModel):
    skill_id: str = Field(min_length=1)
    mastery: float = Field(ge=0, le=1, allow_inf_nan=False)
    candidates: list[VideoCandidate] = Field(default_factory=list, max_length=200)
    limit: int = Field(default=3, ge=1, le=20, strict=True)
    language: str = "ko"
    max_duration_seconds: int = Field(default=1800, ge=1, le=86400, strict=True)


class RankedVideo(BaseModel):
    candidate: VideoCandidate
    score: float
    reasons: list[str]


class VideoRankResponse(BaseModel):
    skill_id: str
    items: list[RankedVideo]
    policy_version: str = "video-ranking-1.0"


class RemoteDecisionResult(BaseModel):
    status: Literal["OK", "UNAVAILABLE", "REJECTED"]
    response: LearningResponse | None = None
    fallback_action: Literal["RETRY"] | None = None
    reason: str | None = None
