"""Optional library artwork/metadata. Never participates in an installation decision."""
from pathlib import Path
import json,urllib.request,urllib.parse,urllib.error,re,time,hashlib,html,math
import transactions as t
from storage import storage
DEFAULTS={'library_columns':7,'presets_hint_seen':False,'manage_dlss_files':True,'game_accents':{},'sharpening_strength':0.5,'mfg_multiplier':2,'nr_strength':2.0,'runtime_provider':'y4my','enable_effects':True,'nr_runtime':'','dark':True,'library_view':'posters','art_scale':80,'cache_days':7,'network_timeout':10,'default_profile':'mfg-only','online_art':True,'steam_metadata':True,'recognize_previous':False,'extra_folders':[]}

LEGACY_NR_STRENGTH={
    'off':0.0,
    'light':1.0,
    'medium':1.5,
    'strong':2.0,
}

LEGACY_SHARPENING_STRENGTH={
    'off':0.0,
    'light':0.3,
    'medium':0.4,
    'strong':0.5,
}

def normalize_strength(value,kind):
    legacy=LEGACY_NR_STRENGTH if kind=='nr' else LEGACY_SHARPENING_STRENGTH
    default=2.0 if kind=='nr' else 0.5
    upper=2.0 if kind=='nr' else 1.0

    if isinstance(value,str):
        value=legacy.get(value,default)

    if isinstance(value,bool):
        return default

    try:number=float(value)
    except (TypeError,ValueError):return default

    if not math.isfinite(number) or not 0.0<=number<=upper:
        return default

    return round(number,1)

def settings_path(config):return storage(config)/'desktop/settings.json'
def load_settings(config):
    try:
        settings={**DEFAULTS,**json.loads(settings_path(config).read_text())}
        settings['library_columns']=max(3,min(9,int(settings.get('library_columns',7))))
        settings['nr_strength']=normalize_strength(settings.get('nr_strength'),'nr')
        settings['sharpening_strength']=normalize_strength(settings.get('sharpening_strength'),'sharpness')
        if type(settings.get('mfg_multiplier')) is not int or settings['mfg_multiplier'] not in (0,2,3,4,5,6):settings['mfg_multiplier']=2
        return settings
    except (OSError,ValueError,t.Refusal):return {**DEFAULTS,'extra_folders':[]}
def save_settings(config,settings):
    path=settings_path(config);t.atomic_file(path,json.dumps({k:settings[k] for k in DEFAULTS},indent=2).encode(),0o600)

ALLOWED={'www.steamgriddb.com','cdn2.steamgriddb.com','cdn.steamgriddb.com','store.steampowered.com','shared.akamai.steamstatic.com','shared.fastly.steamstatic.com','cdn.akamai.steamstatic.com','cdn.cloudflare.steamstatic.com'}
def allowed(url):
    u=urllib.parse.urlparse(url)
    if u.scheme!='https' or u.hostname not in ALLOWED or u.username or u.password:raise ValueError('Unsupported artwork address')
class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        allowed(newurl)
        if req.has_header('Authorization') and urllib.parse.urlparse(newurl).hostname!=urllib.parse.urlparse(req.full_url).hostname:raise ValueError('Authentication redirect refused')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def request(url,limit=3*1024**2,payload=None,timeout=10):
    allowed(url);headers={'User-Agent':'RTXForge/0.3.1 (Linux desktop)'}
    if payload is not None:headers['Content-Type']='application/json'
    with urllib.request.build_opener(Redirect).open(urllib.request.Request(url,headers=headers,data=json.dumps(payload).encode() if payload is not None else None),timeout=timeout) as response:
        data=response.read(limit+1)
        if len(data)>limit:raise ValueError('Artwork response too large')
        return data

def json_request(url,payload=None,timeout=10):return json.loads(request(url,payload=payload,timeout=timeout))
def normalized(text):return re.sub(r'[^a-z0-9]','',text.casefold())

class LibraryMedia:
    def __init__(self,config,settings):
        self.root=storage(config)/'desktop/media';self.settings=settings;self.config=config;self.shortcut_cache={}

    def steam_art(self,row):
        """Match the signed-in Steam user's custom grid, then Steam's own cache."""
        from discovery import steam_roots
        appid=str(row.get('appid') or '')
        result={}
        for root in steam_roots():
            try:login=(root/'config/loginusers.vdf').read_text()
            except OSError:login=''
            accounts=[]
            for uid,body in re.findall(r'"(7656119\d+)"\s*\{([^}]+)\}',login):
                stamp=re.search(r'"Timestamp"\s*"(\d+)"',body)
                accounts.append((int(stamp[1]) if stamp else 0,int(uid)-76561197960265728))
            grid=root/'userdata'/str(max(accounts)[1])/'config/grid' if accounts else None
            if grid and row.get('source')!='Steam':
                try:
                    import engine_bridge
                    if not hasattr(self,'engine'):self.engine=engine_bridge.module(self.config)
                    shortcuts=grid.parent/'shortcuts.vdf'
                    if str(shortcuts) not in self.shortcut_cache:self.shortcut_cache[str(shortcuts)]=self.engine.parse_shortcuts_spans(shortcuts.read_bytes())
                    game=self.engine.Game('',row['name'],Path(row['game']),row.get('source',''),exe=Path(row['game'])/row['exe'])
                    match=self.engine.match_shortcut_span(game,self.shortcut_cache[str(shortcuts)])
                    if match:appid=str(self.engine._shortcut_int(match,'appid') & 0xffffffff)
                except Exception:pass
            if not appid.isdigit():continue
            for kind,custom,native in [('poster',appid+'p','library_600x900'),('capsule',appid,'header'),('hero',appid+'_hero','library_hero')]:
                paths=[]
                if grid:paths.extend(grid/(custom+ext) for ext in ('.png','.jpg','.jpeg','.webp'))
                cache=root/'appcache/librarycache'
                cached=[]
                for variant in ([native,'library_header'] if kind=='capsule' else [native]):
                    for ext in ('.jpg','.png','.webp'):
                        cached.extend([cache/appid/(variant+ext),cache/(appid+'_'+variant+ext)])
                        cached.extend((cache/appid).glob('*/'+variant+ext))
                paths.extend(sorted((p for p in cached if p.is_file()),key=lambda p:p.stat().st_mtime,reverse=True))
                match=next((p for p in paths if p.is_file()),None)
                if match:
                    result[kind]=str(match);prefix={'poster':'art','capsule':'capsule','hero':'hero'}[kind]
                    result[prefix+'_credit']='Your Steam library';result[prefix+'_link']=''
        return result

    def enrich(self,row,refresh=False):
        ident=hashlib.sha256((str(row.get('appid') or '')+row['name']).encode()).hexdigest()[:24]
        record=self.root/(ident+'.json');result={};errors=[];local=self.steam_art(row)
        timeout=max(5,min(30,int(self.settings.get('network_timeout',10))))
        if record.exists():
            try:
                saved=json.loads(record.read_text());result=saved['data']
                if not refresh:return {**result,**local}
            except (OSError,ValueError,KeyError):result={}
        appid=str(row.get('appid') or '')
        if not appid.isdigit():appid=''
        if local.get('poster') or not self.settings['online_art']:
            result.update(local)
            if local:t.atomic_file(record,json.dumps({'data':result}).encode(),0o600)
            return result
        if appid and self.settings['steam_metadata']:
            try:
                response=json_request('https://store.steampowered.com/api/appdetails?'+urllib.parse.urlencode({'appids':appid,'l':'english','filters':'basic,genres,developers,release_date'})).get(appid,{})
                if response.get('success'):
                    data=response['data'];result.update({'description':html.unescape(re.sub('<[^>]+>','',data.get('short_description',''))),'developers':', '.join(data.get('developers',[])),'genres':', '.join(g['description'] for g in data.get('genres',[])[:3]),'release':data.get('release_date',{}).get('date',''),'metadata_source':'Steam','capsule_url':data.get('header_image','')})
            except Exception:errors.append('Steam metadata unavailable')
        image_url='';credit='';link=''
        try:
            base='https://www.steamgriddb.com/api/public/'
            matches=json_request(base+'search/autocomplete?'+urllib.parse.urlencode({'term':row['name'].lower()})).get('data',[])
            exact=[m for m in matches if normalized(m['name'])==normalized(row['name'])]
            if len(exact)==1:
                game=exact[0];game_id=int(game['id'])
                payload={'asset_type':'grid','game_id':[game_id],'page':0,'limit':8,'styles':['all'],'dimensions':['600x900'],'formats':['all'],'languages':['all'],'order':'score_desc','static':True,'animated':False,'nsfw':False,'humor':False,'epilepsy':False,'untagged':True}
                grids=json_request(base+'search/assets',payload,timeout=timeout).get('data',{}).get('assets',[])
                grids=[g for g in grids if not any(g.get(k) for k in ('nsfw','humor','epilepsy','is_animated','is_deleted','processing')) and g.get('width')==600 and g.get('height')==900]
                if grids:
                    grid=grids[0];image_url=grid['url'];credit='SteamGridDB · '+grid.get('author',{}).get('name','Community artwork');link='https://www.steamgriddb.com/grid/'+str(int(grid['id']))
                result['sgdb_game_id']=game_id
                if not result.get('release') and game.get('release_date'):
                    result['release']=time.strftime('%Y',time.gmtime(game['release_date']))
            else:errors.append('No unique SteamGridDB title match')
        except Exception:errors.append('SteamGridDB temporarily unavailable')
        candidates=[(image_url,credit,link)] if image_url else []
        if appid:candidates.append((f'https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/library_600x900.jpg','Steam','https://store.steampowered.com/app/'+appid))
        for url,credit,link in candidates:
            try:
                image=request(url,limit=8*1024**2,timeout=timeout)
                if not (image.startswith(b'\x89PNG\r\n') or image.startswith(b'\xff\xd8') or image[:4]==b'RIFF'):raise ValueError('Unsupported image')
                path=self.root/(ident+'.image');t.atomic_file(path,image,0o600)
                result.update({'poster':str(path),'art_credit':credit,'art_link':link});break
            except Exception:errors.append('Artwork unavailable')
        if True:
            wide_url=f'https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg' if appid else ''
            try:
                if result.get('sgdb_game_id'):
                    wide_payload={'asset_type':'grid','game_id':[result['sgdb_game_id']],'page':0,'limit':4,'dimensions':['920x430'],'static':True,'animated':False,'nsfw':False,'humor':False,'epilepsy':False,'untagged':True}
                    wide=json_request('https://www.steamgriddb.com/api/public/search/assets',wide_payload,timeout=timeout).get('data',{}).get('assets',[])
                    wide=[g for g in wide if g.get('width')==920 and g.get('height')==430 and not any(g.get(k) for k in ('nsfw','humor','epilepsy','is_animated','is_deleted'))]
                    if wide:wide_url=wide[0]['url'];result['capsule_credit']='SteamGridDB · '+wide[0].get('author',{}).get('name','Community artwork')
                if wide_url:
                    data=request(wide_url,limit=8*1024**2,timeout=timeout);path=self.root/(ident+'.wide');t.atomic_file(path,data,0o600);result['capsule']=str(path)
            except Exception:pass
        hero_candidates=[]
        if result.get('sgdb_game_id'):
            try:
                payload={'asset_type':'hero','game_id':[result['sgdb_game_id']],'page':0,'limit':4,'static':True,'animated':False,'nsfw':False,'humor':False,'epilepsy':False,'untagged':True,'order':'score_desc'}
                assets=json_request('https://www.steamgriddb.com/api/public/search/assets',payload,timeout=timeout).get('data',{}).get('assets',[])
                for asset in assets:
                    if not any(asset.get(k) for k in ('nsfw','humor','epilepsy','is_animated','is_deleted','processing')) and asset.get('width',0)>asset.get('height',0):
                        hero_candidates.append((asset['url'],'SteamGridDB · '+asset.get('author',{}).get('name','Community artwork'),'https://www.steamgriddb.com/hero/'+str(int(asset['id']))));break
            except Exception:pass
        if appid:hero_candidates.append((f'https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/library_hero.jpg','Steam','https://store.steampowered.com/app/'+appid))
        for url,credit,link in hero_candidates:
            try:
                data=request(url,limit=12*1024**2,timeout=timeout)
                if not (data.startswith(b'\x89PNG\r\n') or data.startswith(b'\xff\xd8') or data[:4]==b'RIFF'):continue
                path=self.root/(ident+'.hero');t.atomic_file(path,data,0o600)
                result.update({'hero':str(path),'hero_credit':credit,'hero_link':link});break
            except Exception:pass
        result.update(local)
        if errors:result['media_note']='; '.join(dict.fromkeys(errors))
        else:result.pop('media_note',None)
        t.atomic_file(record,json.dumps({'time':time.time(),'provider':'sgdb-public-v3','data':result}).encode(),0o600)
        return result
