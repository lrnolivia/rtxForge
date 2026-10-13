import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from user_messages import friendly_error,friendly_status
class Messages(unittest.TestCase):
    def test_recovery_route(self):
        text=friendly_error('No terminal-engine baseline; use legacy Undo for an older app install')
        self.assertIn('Previous Changes',text);self.assertNotIn('baseline',text)
    def test_next_steps(self):
        for raw,next_step in [('Executable selection changed; refresh the library','Refresh'),('Provider archive hash mismatch','Download'),('Permission denied','permissions'),('Close Steam before applying','Close Steam')]:
            self.assertIn(next_step,friendly_error(raw))
    def test_unknown_never_claims_rollback(self):
        raw='TransactionError: surprising failure /tmp/example'
        text=friendly_error(raw)
        self.assertIn('Technical details',text);self.assertNotIn('No files',text)
        self.assertEqual(raw,'TransactionError: surprising failure /tmp/example')
    def test_status_keeps_game_names(self):
        self.assertEqual(friendly_status('Cyberpunk 2077 · Saving baseline'),'Cyberpunk 2077 · Saving saved backup')
if __name__=='__main__':unittest.main()
