import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from frontend_session import FrontendSession,library_columns

class SessionTests(unittest.TestCase):
    def test_both_layouts_keep_selection(self):
        s=FrontendSession(demo=True);s.games=[{'game':'/demo/game','name':'Game'}]
        s.select('/demo/game',True);s.preferences(ui_mode='new')
        self.assertEqual(s.selected,{'/demo/game'})
        s.preferences(ui_mode='classic');self.assertEqual(s.selected,{'/demo/game'})
    def test_no_selection_has_no_plan(self):
        with self.assertRaises(ValueError):FrontendSession(demo=True).prepare()
    def test_demo_never_executes(self):
        s=FrontendSession(demo=True);s.games=[{'game':'/demo/game','name':'Game'}];s.select('/demo/game',True)
        review=s.prepare();self.assertTrue(review['demo'])
        with self.assertRaises(ValueError):s.apply(review['revision'])
    def test_changed_selection_invalidates_review(self):
        s=FrontendSession(demo=True);s.games=[{'game':'/demo/game','name':'Game'}];s.select('/demo/game',True);s.prepare()
        s.select('/demo/game',False);self.assertIsNone(s.review)
    def test_density_matches_canonical_thresholds(self):
        self.assertEqual(library_columns(1280),5)
        self.assertEqual(library_columns(1000),4)
        self.assertEqual(library_columns(760),3)
        self.assertEqual(library_columns(5000),9)

if __name__=='__main__':unittest.main()
