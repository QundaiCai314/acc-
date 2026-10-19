from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Evidence(StrictModel):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    kind: Literal['observation', 'human_input', 'exercise_assumption']
    source: str = Field(min_length=1, max_length=2000)
    observed_at: datetime
    confidence: float = Field(ge=0, le=1)
    note: str = Field(min_length=1, max_length=4000)

    @model_validator(mode='after')
    def timezone_required(self):
        if self.observed_at.tzinfo is None:
            raise ValueError('observed_at must include a timezone')
        return self


class Team(StrictModel):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    skills: set[str] = Field(default_factory=set, max_length=30)


class Site(StrictModel):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    people: int = Field(ge=1, le=1000)
    urgency: int = Field(ge=1, le=5)
    risk: int = Field(ge=0, le=5)
    accessible: bool
    required_skills: set[str] = Field(default_factory=set, max_length=30)
    equipment: dict[str, int] = Field(default_factory=dict, max_length=30)
    travel_minutes: int = Field(ge=0, le=1440)
    work_minutes: int = Field(ge=1, le=1440)
    evidence_ids: list[str] = Field(min_length=1, max_length=50)


class Scenario(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    exercise: Literal[True] = True
    teams: list[Team] = Field(min_length=1, max_length=20)
    sites: list[Site] = Field(min_length=1, max_length=50)
    equipment: dict[str, int] = Field(default_factory=dict, max_length=30)
    evidence: list[Evidence] = Field(min_length=1, max_length=200)
    horizon_minutes: int = Field(default=120, ge=1, le=1440)
    max_risk: int = Field(default=3, ge=0, le=5)

    @model_validator(mode='after')
    def consistent(self):
        for objects in (self.teams, self.sites, self.evidence):
            ids = [obj.id for obj in objects]
            if len(ids) != len(set(ids)):
                raise ValueError('Duplicate IDs within an entity type')
        known = {e.id for e in self.evidence}
        for site in self.sites:
            if not set(site.evidence_ids) <= known:
                raise ValueError(f'Unknown evidence at {site.id}')
        for quantities in [self.equipment, *(s.equipment for s in self.sites)]:
            if any(not key.strip() or amount < 0 or amount > 10000 for key, amount in quantities.items()):
                raise ValueError('Equipment quantities must be between 0 and 10000')
        return self


class Decision(StrictModel):
    reviewer: str = Field(min_length=1, max_length=100)
    action: Literal['approve', 'reject']
    note: str = Field(min_length=1, max_length=2000)
