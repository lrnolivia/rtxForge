"""Read-only SteamGridDB v2 browsing. API setup is optional and kept out of settings."""
import json
import os
import urllib.request
import urllib.parse
import urllib.error
import library_media

BASE='https://www.steamgriddb.com/api/v2/'

def configured():return bool(os.environ.get('STEAMGRIDDB_API_KEY','').strip())

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('SteamGridDB authentication redirect refused.')

class Client:
    def __init__(self,key=None):
        self._key=key if key is not None else os.environ.get('STEAMGRIDDB_API_KEY','').strip()
        if not self._key:raise ValueError('SteamGridDB API setup is not configured yet.')

    def _json(self,path):
        request=urllib.request.Request(BASE+path,headers={'Authorization':'Bearer '+self._key,'User-Agent':'rtxForge/1.0'})
        try:
            with urllib.request.build_opener(NoRedirect).open(request,timeout=10) as response:
                data=response.read(2*1024*1024+1)
        except urllib.error.HTTPError as error:
            if error.code in (401,403):raise ValueError('SteamGridDB API access was not accepted. Check API setup.') from None
            if error.code==429:raise ValueError('SteamGridDB is busy. Try again later.') from None
            raise ValueError('SteamGridDB could not complete the request.') from None
        except urllib.error.URLError:
            raise ValueError('SteamGridDB could not be reached.') from None
        if len(data)>2*1024*1024:raise ValueError('SteamGridDB response is too large.')
        result=json.loads(data)
        if not result.get('success'):raise ValueError('SteamGridDB could not complete the request.')
        return result.get('data',[])

    def search(self,title):
        title=title.strip()
        if not title:return []
        return self._json('search/autocomplete/'+urllib.parse.quote(title[:200],safe=''))[:20]

    def artwork(self,game_id,role):
        if role not in ('poster','capsule','hero'):raise ValueError('Unknown artwork role.')
        if isinstance(game_id,bool) or not str(game_id).isdigit():raise ValueError('Invalid SteamGridDB game.')
        endpoint='heroes' if role=='hero' else 'grids'
        query={'types':'static','nsfw':'false','humor':'false','page':'0'}
        if role=='poster':query['dimensions']='600x900'
        if role=='capsule':query['dimensions']='920x430,460x215'
        return self._json(f'{endpoint}/game/{game_id}?'+urllib.parse.urlencode(query))[:24]

    @staticmethod
    def download(asset):
        # API key never follows artwork/CDN requests.
        return library_media.request(asset['url'],limit=20*1024*1024)
