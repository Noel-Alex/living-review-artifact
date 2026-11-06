"""Adapter boundary tests; synthetic examples only, never benchmark labels."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import wpc_core as c
class AdapterTests(unittest.TestCase):
    def test_character_roundtrip_and_unicode(self):
        text='alpha\nβ😀end\n'
        self.assertEqual(c.region_text(text,[2,1,2,2]),'β😀')
        self.assertEqual(c.line_region(text,1,2),[1,1,2,5])
        self.assertEqual(c.region_lines([1,1,2,0]),[1,1])
    def test_exact_and_deleted_scores(self):
        a=c.character_score('abc\ndef\n',[1,1,1,3],[1,1,1,3],True)
        self.assertEqual((a['exact'],a['precision'],a['recall']),(1,1,1))
        b=c.character_score('',None,None,True)
        self.assertEqual(b['exact'],1)
        self.assertEqual(c.character_score('',None,None,False)['exact'],0)
    def test_partial_and_wrong_file(self):
        a=c.character_score('abcdef\n',[1,2,1,5],[1,3,1,6],True)
        self.assertEqual(a['distance'],2)
        self.assertEqual((a['precision'],a['recall']),(0.75,0.75))
        self.assertEqual(c.character_score('abcdef\n',[1,2,1,5],[1,3,1,6],False)['overlap'],0)
    def test_ast_selection_mapping_and_actions(self):
        d={'old':[[0,-1,0,10],[1,0,0,3],[2,0,4,3]],'new':[[0,-1,0,10],[1,0,4,3],[2,0,0,3]],'matches':[[1,1],[2,2]],'actions':[]}
        a=c.gumtree_output(d,'a.py','foo\nbar\n','bar\nfoo\n',1,1)
        self.assertEqual(a['range'],['a.py',2,2]);self.assertEqual(a['label'],'moved')
        d['actions']=[['move',0,1]]
        self.assertEqual(c.gumtree_output(d,'a.py','foo\nbar\n','bar\nfoo\n',1,1)['label'],'changed')
        d['matches']=[]
        self.assertEqual(c.gumtree_output(d,'a.py','foo\nbar\n','bar\nfoo\n',1,1)['label'],'removed')
    def test_fallback_covering_node(self):
        d={'old':[[0,-1,0,9]],'new':[[0,-1,0,9]],'matches':[[0,0]],'actions':[['update',0,0]]}
        self.assertEqual(c.gumtree_output(d,'a.py','foo\nbar\n','foo\nbaz\n',2,2)['label'],'changed')
    def test_utf16_offsets(self):
        self.assertEqual(c.utf16_line('😀\nx',3),2)
    def test_no_false_success_for_crash(self):
        self.assertEqual(c.failed('timeout')['label'],'execution_error')
        self.assertIsNone(c.failed('timeout')['range'])
    def test_upstream_deletion_still_checks_explicit_native_file(self):
        o=dict(c.removed(),native=[dict(target_file='wrong.py',target_range=None)])
        self.assertFalse(c.upstream_file_agrees('right.py',None,o))
        self.assertTrue(c.upstream_file_agrees('wrong.py',None,o))
        self.assertTrue(c.upstream_file_agrees('right.py',None,c.removed()))
    def test_upstream_text_overlap_differs_from_positional_overlap(self):
        positional=c.character_score('aaaaaaaaaa\n',[1,1,1,4],[1,3,1,6],True)
        upstream=c.character_score('aaaaaaaaaa\n',[1,1,1,4],[1,3,1,6],True,upstream=True)
        self.assertEqual(positional['precision'],.5)
        self.assertEqual(upstream['precision'],1.)
        self.assertEqual(upstream['exact'],0)
        edge=c.character_score('aaaaaa\n',[1,1,1,4],[1,3,1,6],True,upstream=True)
        self.assertEqual(edge['precision'],.75) # artifact's +1 index includes the newline
if __name__=='__main__':unittest.main()
