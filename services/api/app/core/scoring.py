"""Initial match-score weights (percent). Used by the Phase 2 rule-based matcher."""

DEFAULT_SCORE_WEIGHTS: dict[str, int] = {
    "skills_experience": 35,
    "role_responsibilities": 25,
    "domain_experience": 15,
    "location_work_arrangement": 15,
    "compensation_fit": 10,
}
