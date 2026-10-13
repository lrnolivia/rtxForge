"""Read-only SteamGridDB v2 browsing. API setup is optional and kept out of settings."""
import json
import os
import urllib.request
import urllib.parse
import urllib.error
import library_media
import steamgrid_credentials

BASE='https://www.steamgriddb.com/api/v2/'
# Provider filter vocabulary verified against SteamGridDB's Decky plugin constants.
# Static assets only: animated files must never silently become still images.
STYLES={'poster':('alternate','white_logo','no_logo','blurred','material'),
        'capsule':('alternate','white_logo','no_logo','blurred','material'),
        'hero':('alternate','blurred','material'),'logo':('official','white','black','custom')}
DIMENSIONS={'poster':('600x900','342x482','660x930'),'capsule':('920x430','460x215'),
            'hero':('1920x620','3840x1240','1600x650'),'logo':()}
MIMES=('image/png','image/jpeg','image/webp')

def configured():return bool(os.environ.get('STEAMGRIDDB_API_KEY','').strip())

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('SteamGridDB authentication redirect refused.')

class Client:
    def __init__(self,key=None):
        self._key=key if key is not None else steamgrid_credentials.load_key()
        if not self._key:raise ValueError('SteamGridDB API setup is not configured yet.')

    def validate(self):
        self._json('search/autocomplete/Portal')
        return True

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

    def artwork(self,game_id,role,*,page=0,style='',dimensions='',mime='',humor=False):
        if role not in DIMENSIONS:raise ValueError('Unknown artwork role.')
        if isinstance(game_id,bool) or not str(game_id).isdigit():raise ValueError('Invalid SteamGridDB game.')
        if isinstance(page,bool) or not isinstance(page,int) or not 0<=page<=100:raise ValueError('Invalid artwork page.')
        if style and style not in STYLES[role]:raise ValueError('Unsupported artwork style.')
        if dimensions and dimensions not in DIMENSIONS[role]:raise ValueError('Unsupported artwork dimensions.')
        if mime and mime not in MIMES:raise ValueError('Unsupported artwork format.')
        if not isinstance(humor,bool):raise ValueError('Invalid humor filter.')
        endpoint={'hero':'heroes','logo':'logos'}.get(role,'grids')
        query={'types':'static','nsfw':'false','humor':'any' if humor else 'false','epilepsy':'false','page':str(page)}
        if style:query['styles']=style
        if dimensions:query['dimensions']=dimensions
        elif role=='poster':query['dimensions']=','.join(DIMENSIONS['poster'])
        elif role=='capsule':query['dimensions']='920x430,460x215'
        if mime:query['mimes']=mime
        result=self._json(f'{endpoint}/game/{game_id}?'+urllib.parse.urlencode(query))
        if not isinstance(result,list):raise ValueError('SteamGridDB returned invalid artwork results.')
        return result[:50]

    @staticmethod
    def thumbnail(asset):
        return library_media.request(asset.get('thumb') or asset['url'],limit=2*1024*1024)

    @staticmethod
    def download(asset):
        # API key never follows artwork/CDN requests.
        return library_media.request(asset['url'],limit=20*1024*1024)
