from app.models.integration import BackendCatalog
from app.services.catalog import FixtureCatalog
from app.services.math_validator import MathValidator


def runtime_catalog(contract: BackendCatalog) -> FixtureCatalog:
    concepts = {c.concept_id: c for c in contract.concepts}
    validator = MathValidator()
    skills = []
    for skill in contract.skills:
        content = concepts[skill.concept_id].model_dump(exclude={'concept_id'})
        validator.expression(content['check_answer'])
        record = skill.model_dump(exclude={'concept_id'})
        record.update(content)
        record['next_skills'] = sorted(s.skill_id for s in contract.skills if skill.skill_id in s.prerequisites)
        skills.append(record)
    for question in contract.diagnostic_questions:
        validator.expression(question.answer)
    return FixtureCatalog(data={'data_source': 'backend_payload', 'revision': contract.revision,
        'skills': skills, 'videos': [v.model_dump() for v in contract.videos],
        'diagnostic_questions': [q.model_dump() for q in contract.diagnostic_questions],
        'error_rules': [r.model_dump() for r in contract.error_rules]})
