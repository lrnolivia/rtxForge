"""Secret Service boundary tests with fake credentials; no system wallet or API access."""
import os,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import steamgrid_credentials as credentials

KEY='fixture-key-never-a-real-credential'
class Token:
    def __init__(self):self.cancelled=False
    def cancel(self):self.cancelled=True
    def is_cancelled(self):return self.cancelled
class Gio:
    Cancellable=Token
class Store:
    def __init__(self):self.key=None;self.calls=[];self.fail=False
    def password_lookup_sync(self,schema,attrs,token):
        self.calls.append(('lookup',attrs))
        if self.fail:raise RuntimeError(KEY)
        return self.key
    def password_store_sync(self,schema,attrs,collection,label,key,token):
        self.calls.append(('store',attrs,collection,label))
        if self.fail:raise RuntimeError(KEY)
        self.key=key;return True
    def password_clear_sync(self,schema,attrs,token):
        self.calls.append(('clear',attrs));self.key=None;return True

class CredentialsTest(unittest.TestCase):
    def setUp(self):
        self.store=Store()
        self.backend=patch.object(credentials,'_backend',return_value=(self.store,Gio,object()))
        self.env=patch.dict(os.environ,{},clear=True)
        self.backend.start();self.env.start()
    def tearDown(self):self.backend.stop();self.env.stop()
    def test_round_trip_replace_and_disconnect(self):
        self.assertEqual(credentials.load_key(),'')
        credentials.save_key(' '+KEY+' ')
        self.assertEqual(credentials.load_key(),KEY)
        credentials.save_key(KEY+'-replacement')
        self.assertEqual(credentials.load_key(),KEY+'-replacement')
        self.assertFalse(credentials.clear_key())
        self.assertEqual(credentials.load_key(),'')
        self.assertNotIn(KEY,repr(self.store.calls))
        self.assertEqual(self.store.calls[1][2],'default')
    def test_cancel_prevents_store(self):
        token=Token();token.cancel()
        with self.assertRaises(credentials.CredentialError):credentials.save_key(KEY,cancel=token)
        self.assertIsNone(self.store.key)
        self.assertEqual(self.store.calls,[])
    def test_wallet_failure_never_echoes_secret(self):
        self.store.fail=True
        with self.assertRaises(credentials.CredentialError) as caught:credentials.save_key(KEY)
        self.assertNotIn(KEY,str(caught.exception))
        self.assertIn('wallet',str(caught.exception))
    def test_external_compatibility_without_wallet(self):
        os.environ['STEAMGRIDDB_API_KEY']=KEY
        self.store.fail=True
        self.assertEqual(credentials.load_key(),KEY)
    def test_saved_key_preferred_to_external(self):
        self.store.key=KEY+'-saved';os.environ['STEAMGRIDDB_API_KEY']=KEY
        self.assertEqual(credentials.load_key(),KEY+'-saved')
        self.assertTrue(credentials.clear_key())
        self.assertEqual(os.environ['STEAMGRIDDB_API_KEY'],KEY)
    def test_invalid_input_never_touches_wallet(self):
        for value in ('', 'short', 'key with whitespace','x'*513,'é'*32):
            with self.subTest(value=value):
                with self.assertRaises(credentials.CredentialError):credentials.save_key(value)
        self.assertEqual(self.store.calls,[])
if __name__=='__main__':unittest.main()
