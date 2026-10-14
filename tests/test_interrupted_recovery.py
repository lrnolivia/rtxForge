"""An install run cut off partway (crash, forced shutdown, stalled drive) recovers only the game in progress."""
from pathlib import Path
from unittest.mock import patch
import json, os, sys, tempfile, unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import operation_session, engine_bridge, transactions as t
from operation_session import Session


class InterruptedSessionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.ops = root / 'state' / 'desktop-operations'
        self.a = root / 'library' / 'Finished Game'
        self.b = root / 'library' / 'Cut Off Game'
        for game in (self.a, self.b):
            game.mkdir(parents=True)
            (game / 'dxgi.dll').write_bytes(b'the game ships its own dxgi')
        self.steam = root / 'steam' / 'localconfig.vdf'
        self.steam.parent.mkdir()
        self.steam.write_text('"LaunchOptions" ""')

    def tearDown(self):
        operation_session.LIVE.clear()
        self.tmp.cleanup()

    def run_until_crash(self):
        """Game A installs and seals; game B is captured and half-written, then the process dies."""
        session = Session(self.ops)
        start = session.capture([self.a / 'dxgi.dll', self.a / 'OptiScaler.ini'], label='Finished Game')
        (self.a / 'dxgi.dll').write_bytes(b'optiscaler')
        (self.a / 'OptiScaler.ini').write_text('[a]\n')
        session.seal(start)
        session.capture([self.b / 'dxgi.dll', self.b / 'OptiScaler.ini', self.steam], label='Cut Off Game')
        (self.b / 'dxgi.dll').write_bytes(b'half written')
        (self.b / 'OptiScaler.ini').write_text('[partial')
        self.steam.write_text('"LaunchOptions" "WINEDLLOVERRIDES=dxgi=n,b %command%"')
        operation_session.LIVE.clear()  # the process that owned it is gone
        return session.root

    def test_only_the_interrupted_game_is_put_back(self):
        root = self.run_until_crash()
        [found] = operation_session.unfinished(self.ops)
        self.assertEqual(found.root, root)
        self.assertEqual(found.interrupted()['label'], 'Cut Off Game')
        plan = found.recover(engine_bridge.steam_owned)
        self.assertEqual(plan['completed'], 1)
        self.assertEqual((self.b / 'dxgi.dll').read_bytes(), b'the game ships its own dxgi')
        self.assertFalse((self.b / 'OptiScaler.ini').exists())
        self.assertEqual((self.a / 'dxgi.dll').read_bytes(), b'optiscaler', 'finished games keep their changes')
        self.assertTrue((self.a / 'OptiScaler.ini').exists())
        self.assertIn('WINEDLLOVERRIDES', self.steam.read_text(), "Steam's own file is reported, not rewritten")
        self.assertEqual([Path(e['path']).name for e in plan['leave']], ['localconfig.vdf'])
        self.assertEqual(json.loads((root / 'session.json').read_text())['status'], 'recovered')
        self.assertEqual(operation_session.unfinished(self.ops), [])

    def test_the_running_session_is_never_offered(self):
        session = Session(self.ops)
        session.capture([self.a / 'dxgi.dll'], label='Finished Game')
        self.assertEqual(operation_session.unfinished(self.ops), [])

    def test_older_sessions_without_checkpoints_can_only_be_closed(self):
        root = self.run_until_crash()
        doc = json.loads((root / 'session.json').read_text())
        doc.pop('checkpoints')
        (root / 'session.json').write_text(json.dumps(doc))
        [legacy] = operation_session.unfinished(self.ops)
        self.assertIsNone(legacy.interrupted())
        self.assertEqual(legacy.recovery_plan()['restore'], [])
        legacy.close('closed')
        self.assertEqual(operation_session.unfinished(self.ops), [])
        self.assertTrue(any(p.name != 'session.json' for p in root.iterdir()), 'copies are kept when closing')
        self.assertEqual((self.b / 'OptiScaler.ini').read_text(), '[partial', 'closing restores nothing')

    def test_cancel_still_undoes_the_whole_run(self):
        session = Session(self.ops)
        start = session.capture([self.a / 'dxgi.dll'], label='Finished Game')
        (self.a / 'dxgi.dll').write_bytes(b'optiscaler')
        session.seal(start)
        session.rollback()
        self.assertEqual((self.a / 'dxgi.dll').read_bytes(), b'the game ships its own dxgi')

    def test_recovery_is_a_reviewed_row_in_the_service(self):
        self.run_until_crash()
        import desktop_service
        service = desktop_service.DesktopService.__new__(desktop_service.DesktopService)
        service.config = {}
        with patch.object(engine_bridge, 'operations_root', return_value=self.ops):
            [row] = self.operation_rows(service)
            self.assertEqual((row['kind'], row['name']), ('operation', 'Interrupted: Cut Off Game'))
            review = service.review_recovery(row)
            self.assertEqual(review['title'], 'Recover interrupted operation')
            self.assertEqual((self.b / 'OptiScaler.ini').read_text(), '[partial', 'reviewing writes nothing')
            service.execute(review)
        self.assertFalse((self.b / 'OptiScaler.ini').exists())
        self.assertEqual((self.a / 'dxgi.dll').read_bytes(), b'optiscaler')

    def operation_rows(self, service):
        """recoveries() also lists batch and cleanup records from storage; this test only needs operation rows."""
        with patch.object(sys.modules['desktop_service'], 'storage', return_value=Path(self.tmp.name) / 'storage'):
            return [r for r in service.recoveries() if r['kind'] == 'operation']


class InterruptedInstallTest(unittest.TestCase):
    """A game whose first install was cut off is finished by installing again, not refused."""

    class Engine:
        Y4MY_PROVIDER = {'id': 'dlss-unlocked'}

    def test_interrupted_first_install_is_not_a_provider_switch(self):
        baseline = {'status': 'applying', 'current': None, 'pending_install': {'proxy': 'winhttp.dll'}}
        self.assertTrue(engine_bridge.interrupted_install(baseline))
        self.assertIsNone(engine_bridge.installed_package(baseline))
        engine_bridge.check_switch(self.Engine, engine_bridge.installed_package(baseline), 'mfg-only')

    def test_switching_over_a_real_install_still_needs_a_restore(self):
        baseline = {'status': 'active', 'current': {'provider_id': 'y4my', 'feature_mode': 'mfg-only'}}
        self.assertFalse(engine_bridge.interrupted_install(baseline))
        with self.assertRaisesRegex(t.Refusal, 'switching providers'):
            engine_bridge.check_switch(self.Engine, engine_bridge.installed_package(baseline), 'mfg-only')
        with self.assertRaisesRegex(t.Refusal, 'changing feature profiles'):
            engine_bridge.check_switch(self.Engine, {'provider_id': 'dlss-unlocked', 'feature_mode': 'nr-mfg'}, 'mfg-only')


if __name__ == '__main__':
    unittest.main()
