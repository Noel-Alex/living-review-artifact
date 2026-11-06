"""Independent arithmetic cases for the frozen research analysis and reporting."""
import math
import unittest
from analyze_wpb import exact_binomial,paired


class ReportingTests(unittest.TestCase):
    def test_exact_paired_tail_hand_counts_and_extreme_log(self):
        for b,c,want in ((0,0,1.),(1,0,1.),(5,0,.0625),(4,1,.375)):
            self.assertAlmostEqual(exact_binomial(b,c)['p'],want)
            self.assertAlmostEqual(exact_binomial(c,b)['p'],want)
        extreme=exact_binomial(2000,0)
        self.assertTrue(math.isfinite(extreme['log10_p']))
        self.assertAlmostEqual(extreme['log10_p'],-1999*math.log10(2))

    def test_paired_resampling_preserves_whole_source_clusters(self):
        records=[]
        for file in ('a.py','b.py'):
            for _ in range(2):
                truth=[file,1]
                base=dict(label='removed',placement=None,range=None,recheck=True) if file=='a.py' else dict(label='exact',placement=truth,range=truth+[1],recheck=False)
                refined=dict(label='changed',placement=truth,range=truth+[1],recheck=True) if file=='a.py' else base
                records.append(dict(suite='original',source_file=file,cls='in place',truth_at=truth,
                    anchor_at=truth,reference_range=truth+[1],methods={'t0.85-deployed':base,'t0.85-IG':refined}))
        result=paired(records)
        self.assertEqual(result['clusters'],2)
        contrast=result['contrasts']['t0.85-IG minus t0.85-deployed']['accuracy']
        self.assertEqual((contrast['n'],contrast['difference'],contrast['cluster95']),(4,.5,[0.,1.]))
        self.assertAlmostEqual(contrast['exact_paired']['p'],.5)


if __name__=='__main__':unittest.main()
