import base64
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from .models import StrictModel


Identifier = Annotated[str, Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')]
Text = Annotated[str, Field(min_length=1, max_length=2000)]
ObjectKind = Literal['building', 'entrance', 'road', 'resource', 'other']
Observation = Literal['obstacle_visible', 'no_obstacle_visible', 'unknown']


class Coordinates(StrictModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class MapEntity(StrictModel):
    id: Identifier
    name: str = Field(min_length=1, max_length=200)
    kind: ObjectKind
    coordinates: Coordinates | None = None


class Dataset(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    exercise: Literal[True] = True
    coordinate_basis: Literal['exercise', 'measured']
    coordinate_reference_system: Literal['WGS84'] = 'WGS84'
    map_source: Text
    curator: str = Field(min_length=1, max_length=100)
    entities: list[MapEntity] = Field(min_length=1, max_length=200)

    @model_validator(mode='after')
    def unique_entities(self):
        if len({e.id for e in self.entities}) != len(self.entities):
            raise ValueError('Map entity IDs must be unique')
        return self


class ImageInput(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    captured_at: datetime
    source: Text
    evidence_basis: Literal['exercise', 'field_image']
    mime_type: Literal['image/png', 'image/jpeg']
    content_base64: str = Field(min_length=1, max_length=7_000_000)

    @model_validator(mode='after')
    def valid_image(self):
        if self.captured_at.tzinfo is None:
            raise ValueError('captured_at must include timezone')
        try:
            data = base64.b64decode(self.content_base64, validate=True)
        except ValueError as exc:
            raise ValueError('Invalid base64 image') from exc
        signature = b'\x89PNG\r\n\x1a\n' if self.mime_type == 'image/png' else b'\xff\xd8\xff'
        if len(data) > 5_000_000 or not data.startswith(signature):
            raise ValueError('Image must match the declared PNG/JPEG type and be at most 5 MB')
        return self


class Box(StrictModel):
    x_min: float = Field(ge=0, le=1)
    y_min: float = Field(ge=0, le=1)
    x_max: float = Field(ge=0, le=1)
    y_max: float = Field(ge=0, le=1)

    @model_validator(mode='after')
    def ordered(self):
        if self.x_min >= self.x_max or self.y_min >= self.y_max:
            raise ValueError('Bounding box must have positive area')
        return self


class Annotation(StrictModel):
    entity_id: Identifier | None = None
    observation: Observation
    description: Text
    bbox: Box
    confidence: float = Field(ge=0, le=1)


class ProposalBatch(StrictModel):
    annotations: list[Annotation] = Field(max_length=30)


class ImportedProposal(StrictModel):
    image_id: UUID
    annotation: Annotation
    source_note: Text


class Review(StrictModel):
    reviewer: str = Field(min_length=1, max_length=100)
    action: Literal['approve', 'reject']
    note: Text
    corrected_annotation: Annotation | None = None

    @model_validator(mode='after')
    def reject_without_correction(self):
        if self.action == 'reject' and self.corrected_annotation is not None:
            raise ValueError('Rejected annotations cannot have an approved correction')
        return self


class Retraction(StrictModel):
    reviewer: str = Field(min_length=1, max_length=100)
    note: Text


class SpatialQuery(StrictModel):
    center_entity_id: Identifier
    radius_m: float = Field(gt=0, le=5000)
    kind: ObjectKind = 'entrance'
    observation: Observation = 'obstacle_visible'
    as_of: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    max_age_hours: int = Field(default=24, ge=1, le=8760)

    @model_validator(mode='after')
    def aware_time(self):
        if self.as_of.tzinfo is None:
            raise ValueError('as_of must include timezone')
        return self


class NaturalQuestion(StrictModel):
    question: str = Field(min_length=2, max_length=1000)


class QueryIntent(StrictModel):
    center_entity_id: Identifier | None
    radius_m: float | None = Field(gt=0, le=5000)
    kind: ObjectKind
    observation: Observation
    max_age_hours: int | None = Field(ge=1, le=8760)


class NaturalAnswer(StrictModel):
    status: Literal['answered', 'clarification_needed']
    answer: str
    run_id: UUID
    interpreted_query: QueryIntent
    evidence: SpatialAnswer | None
    clarification: str | None


class Citation(StrictModel):
    annotation_id: UUID
    image_id: UUID
    image_url: str
    entity_id: str
    entity_name: str
    coordinates: Coordinates
    distance_m: float
    captured_at: datetime
    source: str
    evidence_basis: Literal['exercise', 'field_image']
    origin: Literal['ai', 'imported_unverified']
    annotation: Annotation
    reviewer: str
    review_note: str
    reviewed_at: datetime


class SpatialAnswer(StrictModel):
    dataset_id: UUID
    status: Literal['evidence_found', 'insufficient_evidence']
    answer: str
    coordinate_basis: Literal['exercise', 'measured']
    query: SpatialQuery
    citations: list[Citation]
    missing_coordinates: list[str]
    limitations: list[str]
