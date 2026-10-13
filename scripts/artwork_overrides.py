"""Per-installation artwork, copied into app storage without modifying games."""
from pathlib import Path
import copy
import hashlib
import library_media
import transactions as t
from storage import storage

ROLES=('poster','capsule','hero','logo')
MAX_BYTES=20*1024*1024

def dimensions(data):
    from gi.repository import GdkPixbuf
    loader=GdkPixbuf.PixbufLoader.new()
    oversized=[]
    def prepared(loader,width,height):
        if width*height>40_000_000:
            oversized.append(True);loader.set_size(1,1)
    loader.connect('size-prepared',prepared)
    loader.write(data);loader.close()
    image=loader.get_pixbuf()
    if oversized or image is None:raise ValueError('Choose an image smaller than 40 megapixels.')
    return image.get_width(),image.get_height()

def store(config,settings,game,role,data,*,credit='Your artwork',link='',validate=dimensions):
    if role not in ROLES:raise ValueError('Unknown artwork role.')
    if not data or len(data)>MAX_BYTES:raise ValueError('Choose an image smaller than 20 MB.')
    extension='.png' if data.startswith(b'\x89PNG\r\n\x1a\n') else '.jpg' if data.startswith(b'\xff\xd8\xff') else '.webp' if data[:4]==b'RIFF' and data[8:12]==b'WEBP' else None
    if extension is None:raise ValueError('Choose a PNG, JPEG, or WebP image.')
    width,height=validate(data)
    if min(width,height)<=0 or width*height>40_000_000:raise ValueError('Invalid artwork dimensions.')
    if role=='poster' and width>=height:raise ValueError('Poster artwork must be portrait, taller than it is wide.')
    if role in ('capsule','hero') and width<=height:raise ValueError('Wide capsule and hero artwork must be landscape.')
    if extension=='.webp':
        from gi.repository import GdkPixbuf
        loader=GdkPixbuf.PixbufLoader.new();loader.write(data);loader.close()
        success,converted=loader.get_pixbuf().save_to_bufferv('png',[],[])
        if not success or len(converted)>MAX_BYTES:raise ValueError('Converted artwork exceeds the safe PNG size. Choose a smaller image.')
        data=bytes(converted);extension='.png'
    folder=storage(config,len(data))/'desktop/custom-artwork'
    path=folder/(hashlib.sha256(data).hexdigest()+extension)
    t.atomic_file(path,data,0o600)
    updated=copy.deepcopy(settings)
    updated.setdefault('game_artwork',{}).setdefault(game['game'],{})[role]={'path':str(path),'credit':credit,'link':link}
    updated.setdefault('steam_artwork_pending',{}).setdefault(game['game'],{})[role]='sync'
    library_media.save_settings(config,updated)
    settings.clear();settings.update(updated)
    return str(path)

def reset(config,settings,game,role):
    if role not in ROLES:raise ValueError('Unknown artwork role.')
    updated=copy.deepcopy(settings)
    values=updated.setdefault('game_artwork',{}).get(game['game'],{})
    values.pop(role,None)
    if not values:updated['game_artwork'].pop(game['game'],None)
    updated.setdefault('steam_artwork_pending',{}).setdefault(game['game'],{})[role]='reset'
    library_media.save_settings(config,updated)
    settings.clear();settings.update(updated)
    # Keep cached bytes for recovery; reset returns to automatic art only.

def apply(settings,row,result):
    result=dict(result)
    overrides=settings.get('game_artwork',{})
    values=overrides.get(row['game'],{}) if isinstance(overrides,dict) else {}
    for role in ROLES:
        item=values.get(role,{}) if isinstance(values,dict) else {}
        if not isinstance(item,dict):continue
        path=item.get('path')
        if path and Path(path).is_file():
            result[role]=path
            prefix='art' if role=='poster' else role
            result[prefix+'_credit']=item.get('credit','Your artwork')
            result[prefix+'_link']=item.get('link','')
    return result
