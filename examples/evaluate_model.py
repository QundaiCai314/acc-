"""Offline held-out evaluation; never calls providers or manufactures ground truth."""
import argparse
import json
from pathlib import Path

from pydantic import Field, model_validator
from app.models import StrictModel
from app.spatial_models import Box


class Detection(StrictModel):
    label: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    bbox: Box
    confidence: float = Field(default=1, ge=0, le=1)


class ImageCase(StrictModel):
    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    image_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    human_reviewer: str = Field(min_length=1)
    prediction_run: str = Field(min_length=1)
    gold: list[Detection]
    predicted: list[Detection]


class AnswerCase(StrictModel):
    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    human_reviewer: str = Field(min_length=1)
    prediction_run: str = Field(min_length=1)
    should_abstain: bool
    did_abstain: bool
    allowed_evidence: set[str]
    citations: set[str]


class EvaluationSet(StrictModel):
    images: list[ImageCase]
    answers: list[AnswerCase]

    @model_validator(mode='after')
    def unique_cases(self):
        for cases in (self.images, self.answers):
            if len({case.id for case in cases}) != len(cases):
                raise ValueError('Duplicate case id would inflate sample size')
        if len({case.image_sha256 for case in self.images}) != len(self.images):
            raise ValueError('Duplicate image would inflate sample size')
        return self


def iou(a, b):
    intersection = max(0, min(a.x_max, b.x_max) - max(a.x_min, b.x_min)) * max(
        0, min(a.y_max, b.y_max) - max(a.y_min, b.y_min))
    area_a = (a.x_max - a.x_min) * (a.y_max - a.y_min)
    area_b = (b.x_max - b.x_min) * (b.y_max - b.y_min)
    return intersection / (area_a + area_b - intersection)


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def evaluate(dataset, threshold=.5):
    if not 0 < threshold <= 1:
        raise ValueError('IoU threshold must be in (0, 1]')
    tp = fp = fn = 0
    cases = []
    for case in dataset.images:
        unmatched = set(range(len(case.gold)))
        matches = 0
        # Confidence-ordered, one-to-one matching; labels AND entity links must agree.
        for prediction in sorted(case.predicted, key=lambda item: item.confidence, reverse=True):
            eligible = [(iou(prediction.bbox, case.gold[index].bbox), index) for index in unmatched
                if (prediction.label, prediction.entity_id) ==
                   (case.gold[index].label, case.gold[index].entity_id)]
            overlap, index = max(eligible, default=(0, -1))
            if overlap >= threshold:
                unmatched.remove(index)
                matches += 1
        false_positive, missed = len(case.predicted) - matches, len(unmatched)
        tp, fp, fn = tp + matches, fp + false_positive, fn + missed
        cases.append({'id': case.id, 'true_positive': matches, 'false_positive': false_positive, 'missed': missed})
    abstention_cases = [case for case in dataset.answers if case.should_abstain]
    answerable_cases = [case for case in dataset.answers if not case.should_abstain]
    cited = sum(len(case.citations) for case in dataset.answers)
    valid = sum(len(case.citations & case.allowed_evidence) for case in dataset.answers)
    return {
        'status': 'sample_metrics_only' if dataset.images or dataset.answers else 'blocked_no_human_gold',
        'image_count': len(dataset.images), 'question_count': len(dataset.answers), 'iou_threshold': threshold,
        'detection': {'true_positive': tp, 'false_positive': fp, 'missed': fn,
                      'precision': ratio(tp, tp + fp), 'recall': ratio(tp, tp + fn),
                      'f1': ratio(2 * tp, 2 * tp + fp + fn), 'cases': cases},
        'answer': {'unanswerable_count': len(abstention_cases), 'answerable_count': len(answerable_cases),
                   'correct_abstention_rate': ratio(sum(c.did_abstain for c in abstention_cases), len(abstention_cases)),
                   'false_abstention_rate': ratio(sum(c.did_abstain for c in answerable_cases), len(answerable_cases)),
                   'citation_id_precision': ratio(valid, cited),
                   'answerable_citation_coverage': ratio(sum(not c.did_abstain and bool(c.citations & c.allowed_evidence)
                       for c in answerable_cases), len(answerable_cases))},
        'limits': 'Human labels and source identity are supplied, not authenticated by this tool. '
                  'Citation IDs do not prove semantic entailment. No production or same-scene acceptance implied.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--iou', type=float, default=.5)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    dataset = EvaluationSet.model_validate_json(args.manifest.read_text(encoding='utf-8'))
    result = evaluate(dataset, args.iou)
    content = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(content, encoding='utf-8')
    print(content)
    return 2 if result['status'].startswith('blocked') else 0


if __name__ == '__main__':
    raise SystemExit(main())
