import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpk6_oracle import classify

class OracleTests(unittest.TestCase):
    def test_deletion_and_duplicate(self):
        self.assertEqual(classify('x', '', 'a\nb'), ('applied-deletion', None))
        self.assertEqual(classify('x', '', 'x\nx')[0], 'ambiguous')
    def test_added_lines_containing_original(self):
        self.assertEqual(classify('x', 'before\nx\nafter', ' \nbefore\n x \nafter\n'), ('applied', (2, 4)))
        self.assertEqual(classify('x', 'before\nx\nafter', 'before\nx\nafter\nx')[0], 'ambiguous')
    def test_rewritten_and_moved(self):
        self.assertEqual(classify('x', 'y', 'z')[0], 'rewritten')
        self.assertEqual(classify('x', 'y', '\n z\n\n x\n'), ('untouched', (4, 4)))
    def test_gone(self):
        self.assertEqual(classify('x', 'y', None), ('gone-file', None))

if __name__ == '__main__': unittest.main()

