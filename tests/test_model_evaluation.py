import unittest

from examples.evaluate_model import EvaluationSet, evaluate


class ModelEvaluationTests(unittest.TestCase):
    def manifest(self):
        # Synthetic evaluator unit fixture, never a real model accuracy result.
        box = {'label': 'obstacle_visible', 'entity_id': 'entrance',
               'bbox': {'x_min': .1, 'y_min': .1, 'x_max': .4, 'y_max': .4}}
        return {'images': [{'id': 'unit', 'source': 'synthetic-unit-test', 'image_sha256': '0' * 64,
            'human_reviewer': 'unit-fixture-not-a-person', 'prediction_run': 'stub',
            'gold': [box, {**box, 'entity_id': 'other'}], 'predicted': [box, box]}],
            'answers': [{'id': 'unknown', 'question': 'fixture', 'human_reviewer': 'unit-fixture',
                'prediction_run': 'stub', 'should_abstain': True, 'did_abstain': True,
                'allowed_evidence': [], 'citations': ['invented']},
                {'id': 'known', 'question': 'fixture', 'human_reviewer': 'unit-fixture',
                'prediction_run': 'stub', 'should_abstain': False, 'did_abstain': False,
                'allowed_evidence': ['e1'], 'citations': ['e1']} ]}

    def test_duplicates_misses_and_unsupported_citations_are_penalized(self):
        result = evaluate(EvaluationSet.model_validate(self.manifest()))
        self.assertEqual(result['detection']['precision'], .5)
        self.assertEqual(result['detection']['recall'], .5)
        self.assertEqual(result['answer']['citation_id_precision'], .5)
        self.assertEqual(result['answer']['correct_abstention_rate'], 1)
        self.assertEqual(result['answer']['false_abstention_rate'], 0)

    def test_no_gold_is_blocked_not_perfect(self):
        result = evaluate(EvaluationSet(images=[], answers=[]))
        self.assertEqual(result['status'], 'blocked_no_human_gold')
        self.assertIsNone(result['detection']['precision'])
        self.assertIsNone(result['answer']['correct_abstention_rate'])

    def test_wrong_link_and_no_overlap_are_false_positives(self):
        manifest = self.manifest()
        manifest['images'][0]['predicted'] = [{**manifest['images'][0]['gold'][0], 'entity_id': 'wrong'}]
        result = evaluate(EvaluationSet.model_validate(manifest))
        self.assertEqual(result['detection']['precision'], 0)
        manifest['images'][0]['predicted'][0].update(entity_id='entrance',
            bbox={'x_min': .6, 'y_min': .6, 'x_max': .9, 'y_max': .9})
        self.assertEqual(evaluate(EvaluationSet.model_validate(manifest))['detection']['recall'], 0)

    def test_duplicate_images_and_unreviewed_labels_rejected(self):
        manifest = self.manifest()
        manifest['images'].append({**manifest['images'][0], 'id': 'duplicate-image'})
        with self.assertRaises(ValueError):
            EvaluationSet.model_validate(manifest)
        manifest = self.manifest()
        manifest['images'][0]['human_reviewer'] = ''
        with self.assertRaises(ValueError):
            EvaluationSet.model_validate(manifest)
