"""Public artwork fixtures for write-disabled native screenshots only."""
import json
from pathlib import Path
import urllib.request
from concurrent.futures import ThreadPoolExecutor


def prepare(root):
    media=Path(root)/'dist/demo-media';media.mkdir(parents=True,exist_ok=True)
    def fetch(spec):
        appid,kind,asset=spec
        try:
            image=media/(appid+('' if kind=='poster' else '-'+kind)+'.jpg')
            if not image.exists():
                url=f'https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/{asset}.jpg'
                with urllib.request.urlopen(url,timeout=10) as response:data=response.read(8*1024**2)
                if not data.startswith((b'\xff\xd8',b'\x89PNG')):return None
                image.write_bytes(data)
            return appid,kind,str(image)
        except Exception as ex:print('Demo artwork unavailable:',appid,kind,type(ex).__name__)
    ids=('1091500','990080','3357650','2842040','2840770')
    specs=[(appid,kind,asset) for appid in ids for kind,asset in [('poster','library_600x900'),('capsule','header'),('hero','library_hero')]]
    records={appid:{'art_credit':'Steam'} for appid in ids}
    with ThreadPoolExecutor(max_workers=5) as workers:
        for result in workers.map(fetch,specs):
            if result:
                appid,kind,path=result;records[appid][kind]=path
    for appid,record in records.items():(media/(appid+'.json')).write_text(json.dumps(record))
