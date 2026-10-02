"""Public artwork fixtures for write-disabled native screenshots only."""
import json
from pathlib import Path
import urllib.request


def prepare(root):
    media=Path(root)/'dist/demo-media';media.mkdir(parents=True,exist_ok=True)
    for appid in ('1091500','990080','3357650','2842040','2840770'):
        try:
            image=media/(appid+'.jpg')
            if not image.exists():
                url=f'https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/library_600x900.jpg'
                with urllib.request.urlopen(url,timeout=10) as response:data=response.read(8*1024**2)
                if not data.startswith((b'\xff\xd8',b'\x89PNG')):continue
                image.write_bytes(data)
            (media/(appid+'.json')).write_text(json.dumps({'poster':str(image),'art_credit':'Steam'}))
        except Exception as ex:print('Demo artwork unavailable:',appid,type(ex).__name__)
