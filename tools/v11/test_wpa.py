"""Independent fixtures for workflow risk and exact per-observation gates."""
import importlib.util
import unittest


class MetricsTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('wpa_core'), 'WPA implementation missing')
        import wpa_core
        return wpa_core

    def test_moved_wrong_is_workflow_silent_but_adapter_flagged(self):
        m = self.module()
        row = {'cls': 'edited', 'truth_at': ['a.py', 8]}
        result = m.events(row, {'label': 'moved', 'placement': ['b.py', 2], 'adapter_recheck': True})
        self.assertEqual((result['missed'], result['wrong_silent'], result['adapter_missed']), (1, 1, 0))

    def test_lost_and_false_recheck_have_different_denominators(self):
        m = self.module()
        rows = [{'cls': 'shifted', 'truth_at': ['a', 3]}, {'cls': 'gone', 'truth_at': None}]
        outputs = [{'label': 'removed', 'placement': None}, {'label': 'removed', 'placement': None}]
        summary = m.summarize(rows, outputs)
        self.assertEqual(summary['lost']['k'], 1)
        self.assertEqual(summary['lost']['n'], 1)
        self.assertEqual(summary['false_recheck']['k'], 1)
        self.assertEqual(summary['false_recheck']['n'], 1)
        self.assertEqual(summary['accuracy']['k'], 1)
        self.assertEqual(summary['accuracy']['n'], 2)

    def test_gate_cannot_accept_equal_aggregate_counts_with_swapped_outcomes(self):
        m = self.module()
        with self.assertRaises(AssertionError):
            m.check_gate([{'outcome': 'correct'}, {'outcome': 'lost'}],
                         [{'outcome': 'lost'}, {'outcome': 'correct'}], ['outcome'])

    def test_gone_wrong_and_execution_failure_are_not_correct(self):
        m = self.module()
        rows = [{'cls': 'gone', 'truth_at': None}, {'cls': 'edited', 'truth_at': ['a', 2]}]
        outputs = [{'label': 'changed', 'placement': ['a', 1]},
                   {'label': 'execution_error', 'placement': None}]
        s = m.summarize(rows, outputs)
        self.assertEqual(s['accuracy']['k'], 0)
        self.assertEqual(s['execution_errors'], 1)
        self.assertEqual(s['gone_misreported']['k'], 1)
        self.assertEqual(s['lost']['k'], 0)
        self.assertEqual(s['classification_accuracy']['n'], 2)

    def test_factorial_order_recovers_cross_file_before_fuzzy(self):
        m = self.module()
        features = {'hash': None, 'same': None, 'cross': ['b', 4],
                    'local': [0.9, ['a', 9]], 'whole_full': [0.95, ['a', 30]],
                    'whole_legacy': [0.95, ['a', 30]]}
        self.assertEqual(m.cell_output(features, 'fuzzy_first', 'local', 'full', .85)['label'], 'changed')
        self.assertEqual(m.cell_output(features, 'cross_first', 'local', 'full', .85)['placement'], ['b', 4])
        self.assertEqual(m.cell_output(features, 'fuzzy_first', 'local', 'full', .95)['placement'], ['b', 4])

    def test_legacy_partial_window_corner_is_explicit(self):
        m = self.module()
        matcher, bench = m.loaders()
        trial = {'anchor': {'path': 'a', 'line_start': 1, 'line_end': 3,
                            'content_hash': 'old', 'quotation': 'abcdefghij\nklmnopqrst\nuvwxyz'},
                 'old_lines': ['abcdefghij', 'klmnopqrst', 'uvwxyz'],
                 'version': {'a': ('new', 'abcdefghij\nklmnopqrstu\n')}}
        f = m.features(trial, matcher)
        self.assertTrue(f['short_file'])
        self.assertIsNone(m.cell_output(f,'cross_first','whole','full',.5)['placement'])
        self.assertEqual(m.cell_output(f,'cross_first','whole','legacy',.5)['placement'], ['a',1])
        self.assertEqual(bench.m_cascade_v1(trial,.5)[0], ('a',0))

    def test_classification_and_placement_are_independent(self):
        m = self.module()
        r = {'cls': 'edited', 'truth_at': ['a', 8]}
        e = m.events(r, {'label':'moved', 'placement':['a',8]})
        self.assertEqual((e['accuracy'],e['classification_accuracy'],e['missed']), (1,0,1))

    def test_zero_denominator_is_unmeasured_not_zero_risk(self):
        self.assertIsNone(self.module().rate(0,0)['rate'])

    def test_five_class_prediction_uses_movement_coordinates(self):
        m = self.module()
        r = {'cls':'shifted','truth_at':['a',8],'anchor_at':['a',1]}
        e = m.events(r,{'label':'moved','placement':['a',8]})
        self.assertEqual(e.get('classification_five_accuracy'),1)

    def test_compressed_outcomes_do_not_invent_movement_classification(self):
        m = self.module()
        r = {'cls':'shifted','truth_at':['a',8],'anchor_at':['a',1]}
        compressed = m.decode_output(1*4+1,r)
        s = m.summarize([r],[compressed])
        self.assertIsNone(s['classification_five_accuracy']['rate'])


if __name__ == '__main__':
    unittest.main()
