from app.services.catalog import FixtureCatalog


class ConceptAgent:
    def __init__(self, catalog: FixtureCatalog):
        self.catalog = catalog

    def build(self, skill_id: str, mastery: float) -> dict[str, str]:
        skill = self.catalog.skill(skill_id)
        return {"explanation": skill['explanation_easy'] if mastery < 0.4 else skill['explanation'],
                "example": skill['example'], "check_question": skill['check_question']}
