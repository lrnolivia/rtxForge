import copy,sys,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import artwork_overrides as art
import library_media
from steamgrid_client import Client

class ArtworkTests(unittest.TestCase):
    def test_import_persists_separate_roles_and_reset_retains_bytes(self):
        with TemporaryDirectory() as folder:
            config={'storage':{'root':folder+'/state','reserve_bytes':0}}
            settings=copy.deepcopy(library_media.DEFAULTS);game={'game':folder+'/game','name':'Game'}
            data=b'\x89PNG\r\n\x1a\nfixture'
            path=art.store(config,settings,game,'poster',data,validate=lambda _:(600,900))
            loaded=library_media.load_settings(config)
            self.assertEqual(art.apply(loaded,game,{})['poster'],path)
            self.assertEqual(Path(path).read_bytes(),data)
            self.assertNotIn('capsule',art.apply(loaded,game,{}))
            art.reset(config,settings,game,'poster')
            self.assertEqual(art.apply(library_media.load_settings(config),game,{}),{})
            self.assertTrue(Path(path).exists())
            with self.assertRaisesRegex(ValueError,'portrait'):art.store(config,settings,game,'poster',data,validate=lambda _:(900,600))
            with self.assertRaisesRegex(ValueError,'landscape'):art.store(config,settings,game,'hero',data,validate=lambda _:(600,900))
            with self.assertRaisesRegex(ValueError,'PNG'):art.store(config,settings,game,'poster',b'<svg/>')

    def test_failed_settings_write_leaves_previous_selection(self):
        with TemporaryDirectory() as folder:
            config={'storage':{'root':folder+'/state','reserve_bytes':0}};settings=copy.deepcopy(library_media.DEFAULTS);original=copy.deepcopy(settings)
            with patch.object(library_media,'save_settings',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):art.store(config,settings,{'game':'g'},'hero',b'\x89PNG\r\n\x1a\nfixture',validate=lambda _:(900,600))
            self.assertEqual(settings,original)

    def test_api_search_and_role_routes_no_automatic_selection(self):
        client=Client(key='fixture-not-a-real-key')
        with patch.object(client,'_json',return_value=[{'id':1},{'id':2}]) as request:
            self.assertEqual(len(client.search('Half-Life / 2')),2)
            self.assertIn('Half-Life%20%2F%202',request.call_args.args[0])
            client.artwork(1,'poster');self.assertIn('dimensions=600x900',request.call_args.args[0])
            client.artwork(1,'hero');self.assertTrue(request.call_args.args[0].startswith('heroes/game/1?'))
            with self.assertRaises(ValueError):client.artwork('../x','poster')
        with patch.dict('os.environ',{'STEAMGRIDDB_API_KEY':''}):
            with self.assertRaisesRegex(ValueError,'not configured'):Client()

if __name__=='__main__':unittest.main()

class SteamGridFilterTests(unittest.TestCase):
    def test_filters_and_pagination_are_role_scoped(self):
        from urllib.parse import urlparse,parse_qs
        client=Client('fixture-not-a-real-key')
        with patch.object(client,'_json',return_value=[]) as request:
            client.artwork(12,'hero',page=2,style='blurred',dimensions='3840x1240',mime='image/png',humor=True)
            path=request.call_args.args[0];query=parse_qs(urlparse(path).query)
            self.assertTrue(path.startswith('heroes/game/12?'))
            self.assertEqual(query['page'],['2']);self.assertEqual(query['styles'],['blurred'])
            self.assertEqual(query['nsfw'],['false']);self.assertEqual(query['types'],['static'])
            self.assertEqual(query['humor'],['any'])
            client.artwork(12,'logo',style='white');self.assertTrue(request.call_args.args[0].startswith('logos/game/12?'))
    def test_unknown_filters_are_rejected_before_network(self):
        client=Client('fixture-not-a-real-key')
        with patch.object(client,'_json') as request:
            for options in ({'style':'<script>'},{'dimensions':'600x900'},{'page':-1},{'page':True},{'mime':'text/html'},{'humor':'true'}):
                with self.subTest(options=options),self.assertRaises(ValueError):client.artwork(1,'hero',**options)
            request.assert_not_called()
    def test_thumbnail_has_no_auth_and_is_bounded(self):
        with patch('library_media.request',return_value=b'preview') as request:
            self.assertEqual(Client.thumbnail({'thumb':'https://cdn2.steamgriddb.com/preview.png','url':'https://cdn2.steamgriddb.com/full.png'}),b'preview')
            request.assert_called_once_with('https://cdn2.steamgriddb.com/preview.png',limit=2*1024*1024)
