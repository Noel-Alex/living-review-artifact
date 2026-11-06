"""Hand-derived safety fixtures; run before freezing the B variants."""
import importlib.util
import unittest
from wpa_core import loaders


def trial(old, new, start, end, path='a.py', others=None):
    from wpa_core import hashlib
    digest = lambda s: hashlib.sha256(s.encode()).hexdigest()
    anchor = dict(path=path, line_start=start, line_end=end,
                  quotation='\n'.join(old.splitlines()[start-1:end]), content_hash=digest(old))
    files = {path: (digest(new), new)}
    files.update({p: (digest(t), t) for p, t in (others or {}).items()})
    return dict(anchor=anchor, old_lines=old.splitlines(), version=files)


class VariantTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('wpb_variants'), 'Frozen variant implementation missing')
        from wpb_variants import relocate
        self.run_variant = relocate

    def test_python_base_indent_changes_request(self):
        t = trial('if ready:\n    run_task()\n    keep()\n', 'if ready:\n    keep()\nrun_task()\n', 2, 2)
        o = self.run_variant(t, {}, ig=True)
        self.assertEqual((o['label'], o['placement'], o['recheck'], o['reasons']),
                         ('changed', ['a.py', 3], True, ['layout']))

    def test_hash_and_expanded_tabs_do_not_request(self):
        old = 'if ready:\n\trun_task()\n'
        for new in (old, 'if ready:\n        run_task()\n# outside\n'):
            self.assertFalse(self.run_variant(trial(old, new, 2, 2), {}, ig=True)['recheck'])

    def test_nonpython_base_shift_ignored_relative_shift_caught(self):
        old = '  first();\n    second();\n'
        a = self.run_variant(trial(old, '    first();\n      second();\n', 1, 2, 'a.js'), {}, ig=True)
        b = self.run_variant(trial(old, '    first();\n        second();\n', 1, 2, 'a.js'), {}, ig=True)
        self.assertFalse(a['recheck'])
        self.assertTrue(b['recheck'])

    def test_blank_lines_and_trailing_spaces_do_not_request(self):
        o = self.run_variant(trial('first()\nsecond()\n', 'first()  \n\nsecond()\t\n', 1, 2), {}, ig=True)
        self.assertEqual((o['range'], o['recheck']), (['a.py', 1, 3], False))

    def test_ag_prefers_diff_predicted_original_over_nearer_copy(self):
        old = 'before()\ntarget_call()\nafter()\n'
        new = 'before()\ntarget_call()\n' + '# spacer\n'*20 + 'before()\ntarget_call()\nafter()\n'
        t = trial(old, new, 2, 2)
        base = self.run_variant(t, {'a.py': old})
        guarded = self.run_variant(t, {'a.py': old}, ag=True)
        self.assertEqual(base['placement'], ['a.py', 2])
        self.assertEqual(guarded['placement'], ['a.py', 24])
        self.assertFalse(guarded['recheck'])

    def test_ag_preexisting_crossfile_copy_requests_without_relabel(self):
        t = trial('target_call()\n', 'totally_unrelated_content()\n', 1, 1,
                  others={'b.py': 'target_call()\n'})
        o = self.run_variant(t, {'a.py': 'target_call()\n', 'b.py': 'target_call()\n'}, ag=True)
        self.assertEqual((o['label'], o['recheck'], o['reasons']), ('moved', True, ['pre-existing-copy']))

    def test_ag_new_file_and_increased_count_are_clean_moves(self):
        t = trial('target_call()\n', 'totally_unrelated_content()\n', 1, 1,
                  others={'b.py': 'target_call()\n'})
        self.assertFalse(self.run_variant(t, {'a.py': 'target_call()\n'}, ag=True)['recheck'])
        t['version']['b.py'] = ('different', 'target_call()\ntarget_call()\n')
        self.assertFalse(self.run_variant(t, {'b.py': 'target_call()\n'}, ag=True)['recheck'])

    def test_variable_height_returns_inserted_line_in_range(self):
        old = 'alpha_long_call()\nbeta_long_call()\n'
        new = 'alpha_long_call()\n# x\nbeta_long_call()\n'
        # Exact normalized matching would skip blank lines, but not this inserted comment.
        t = trial(old, new, 1, 2)
        o = self.run_variant(t, {'a.py': old}, theta=.55, vw=True)
        self.assertEqual((o['label'], o['range']), ('changed', ['a.py', 1, 3]))

    def test_zero_switch_matches_deployed_range_and_label(self):
        m, _ = loaders()
        for old, new in [('one()\ntwo()\n', '# added\none()\ntwo()\n'),
                         ('long_original_call()\n', 'long_changed_call()\n')]:
            t = trial(old, new, 1, 1)
            expected = m.relocate_code(t['anchor'], t['version'], old)
            got = self.run_variant(t, {'a.py': old})
            self.assertEqual(got['label'], expected['match'])
            self.assertEqual(got['range'], None if expected['match']=='removed' else
                             [expected['path'], expected['line_start'], expected['line_end']])

    def test_duplicate_near_cells_measure_starts_not_insertion_gap(self):
        import random
        from wpb_stress import corpus,duplicate_trial
        bench,files,old_files=corpus()
        rng=random.Random(20261018)
        for direction in ('near-above','near-below'):
            for _ in range(20):
                t=duplicate_trial(rng,bench,files,old_files,direction,'unchanged')
                self.assertIsNotNone(t)
                c=t['duplicate_construction']
                self.assertLessEqual(abs(c['copy_before_fate'][1]-c['original_before_fate'][1]),10)

    def test_explicit_ag_request_overrides_workflow_metrics_not_label(self):
        from analyze_wpb import event
        r=dict(cls='edited',truth_at=['a.py',2],anchor_at=['a.py',1],reference_range=['a.py',2,2])
        o=dict(label='moved',placement=['b.py',1],range=['b.py',1,1],recheck=True)
        e=event(r,o)
        self.assertEqual((e['missed'],e['wrong_silent'],e['wrong_with_recheck'],e['classification_accuracy']),
                         (0,0,1,0))


if __name__ == '__main__':
    unittest.main()
