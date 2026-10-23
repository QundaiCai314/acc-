"""Explicit units, frames and validity intervals for reviewable spatial artifacts."""
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from .models import StrictModel, validate_query_time
from .spatial_models import Coordinates, Identifier, ObjectKind, Observation, Text


Number = Annotated[float, Field(ge=-10_000_000, le=10_000_000)]
Point3 = tuple[Number, Number, Number]


class Validity(StrictModel):
    valid_from: datetime
    valid_until: datetime
    source_note: Text

    @model_validator(mode='after')
    def valid_interval(self):
        if self.valid_from.tzinfo is None or self.valid_until.tzinfo is None:
            raise ValueError('Validity timestamps must include timezone')
        if self.valid_until <= self.valid_from:
            raise ValueError('valid_until must be later than valid_from')
        return self


class RoadEdge(StrictModel):
    id: Identifier
    source: Identifier
    target: Identifier
    length_m: float = Field(gt=0, le=100_000)
    bidirectional: bool = True
    modes: set[Literal['walk', 'vehicle']] = Field(min_length=1)
    status: Literal['open', 'blocked', 'unknown'] = 'unknown'
    source_note: Text
    annotation_ids: list[UUID] = Field(default_factory=list, max_length=30)


class RoadNetwork(Validity):
    edges: list[RoadEdge] = Field(min_length=1, max_length=2000)

    @model_validator(mode='after')
    def unique_edges(self):
        if len({e.id for e in self.edges}) != len(self.edges):
            raise ValueError('Edge IDs must be unique')
        if any(e.source == e.target for e in self.edges):
            raise ValueError('Self-loop roads are not supported')
        return self


class TimedQuery(StrictModel):
    as_of: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode='after')
    def aware(self):
        validate_query_time(self.as_of, getattr(self, 'max_age_hours', 0))
        return self


class RouteQuery(TimedQuery):
    network_id: UUID
    start_entity_id: Identifier
    end_entity_id: Identifier
    mode: Literal['walk', 'vehicle'] = 'walk'
    basis: Literal['reviewed_status', 'mapped_topology'] = 'reviewed_status'
    avoid_edge_ids: set[Identifier] = Field(default_factory=set, max_length=2000)


class ControlPoint(StrictModel):
    label: Identifier
    scene: Point3
    enu_m: Point3 | None = None
    local_m: Point3 | None = None

    @model_validator(mode='after')
    def one_target(self):
        if (self.enu_m is None) == (self.local_m is None):
            raise ValueError('Provide exactly one of enu_m or local_m')
        return self

    @property
    def target(self):
        return self.enu_m if self.enu_m is not None else self.local_m


class SceneObject(StrictModel):
    entity_id: Identifier
    min_corner: Point3
    max_corner: Point3

    @model_validator(mode='after')
    def positive_volume(self):
        if any(a >= b for a, b in zip(self.min_corner, self.max_corner)):
            raise ValueError('Scene bounds must have positive volume')
        return self


class Registration(Validity):
    scene_name: str = Field(min_length=1, max_length=200)
    target_frame: Literal['enu', 'local'] = 'enu'
    origin: Coordinates | None = None
    origin_altitude_m: float | None = Field(default=None, ge=-1000, le=10000)
    scene_unit_m: float = Field(default=1, gt=0, le=1000)
    solve_scale: bool = False
    control_points: list[ControlPoint] = Field(min_length=3, max_length=100)
    check_points: list[ControlPoint] = Field(min_length=1, max_length=100)
    objects: list[SceneObject] = Field(default_factory=list, max_length=200)
    max_rmse_m: float = Field(default=0.5, gt=0, le=100)
    max_error_m: float = Field(default=1, gt=0, le=100)

    @model_validator(mode='after')
    def distinct(self):
        points = self.control_points + self.check_points
        if self.target_frame == 'enu':
            if self.origin is None or self.origin_altitude_m is None or any(p.enu_m is None for p in points):
                raise ValueError('ENU registration requires origin, ellipsoid altitude and enu_m targets')
        elif self.origin is not None or self.origin_altitude_m is not None or any(p.local_m is None for p in points):
            raise ValueError('Local registration requires local_m targets and must not specify a geographic origin')
        if len({p.label for p in points}) != len(points):
            raise ValueError('Control/check point labels must be unique')
        if len({p.scene for p in points}) != len(points) or len({p.target for p in points}) != len(points):
            raise ValueError('Independent check points must not repeat control points')
        if any(sum(v*v for v in p.target) > 10_000**2 for p in points):
            raise ValueError('Target frame is limited to 10 km around its origin')
        if len({o.entity_id for o in self.objects}) != len(self.objects):
            raise ValueError('Each entity may have only one scene object')
        return self


class TransformQuery(TimedQuery):
    points: list[Point3] = Field(min_length=1, max_length=10000)


class Relation(StrictModel):
    subject: Identifier
    predicate: Literal['inside', 'part_of', 'connects_to', 'blocks']
    object: Identifier
    annotation_ids: list[UUID] = Field(default_factory=list, max_length=30)
    source_note: Text


class RelationSet(Validity):
    relations: list[Relation] = Field(min_length=1, max_length=1000)

    @model_validator(mode='after')
    def no_duplicates_or_self_links(self):
        keys = [(r.subject, r.predicate, r.object) for r in self.relations]
        if len(set(keys)) != len(keys) or any(s == o for s, _, o in keys):
            raise ValueError('Duplicate or self-referential relation')
        graph = {}
        for s, p, o in keys:
            if p in ('inside', 'part_of'):
                graph.setdefault(s, set()).add(o)
        # Iterative traversal avoids recursion limits on externally supplied graphs.
        for start in graph:
            stack, seen = list(graph[start]), set()
            while stack:
                item = stack.pop()
                if item == start:
                    raise ValueError('Containment relations must be acyclic')
                if item not in seen:
                    seen.add(item)
                    stack.extend(graph.get(item, ()))
        return self


class Condition(StrictModel):
    relation: Literal['near', 'north_of', 'south_of', 'east_of', 'west_of', 'inside', 'part_of',
                      'connects_to', 'blocks', 'above', 'below', 'reachable_from']
    reference_entity_id: Identifier
    distance_m: float | None = Field(default=None, gt=0, le=100_000)

    @model_validator(mode='after')
    def explicit_distance(self):
        if (self.relation == 'near') != (self.distance_m is not None):
            raise ValueError('distance_m is required only for near')
        return self


class ReasonQuery(TimedQuery):
    all_of: list[Condition] = Field(min_length=1, max_length=12)
    kind: ObjectKind | None = None
    relation_set_id: UUID | None = None
    registration_id: UUID | None = None
    network_id: UUID | None = None
    mode: Literal['walk', 'vehicle'] = 'walk'
    max_hops: int = Field(default=8, ge=1, le=20)
    observation: Observation | None = None
    max_age_hours: int = Field(default=24, ge=1, le=8760)


class ArtifactReview(StrictModel):
    action: Literal['approve', 'reject']
    note: Text


class ReasonIntent(StrictModel):
    query: ReasonQuery | None
    clarification: str | None = Field(max_length=1000)

    @model_validator(mode='after')
    def query_or_clarification(self):
        if (self.query is None) == (not self.clarification):
            raise ValueError('Return either a query or a nonempty clarification')
        return self
