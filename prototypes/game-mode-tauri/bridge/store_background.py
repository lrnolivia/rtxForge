"""On-demand Steam Store screenshots, in a bounded application-owned disk cache."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import tempfile
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

try:
    from screening_admission import decision as screening_decision, screen as screen_images, VERSION as SCREEN_VERSION
except ModuleNotFoundError:
    import importlib.util
    _spec = importlib.util.spec_from_file_location('screening_admission', Path(__file__).with_name('screening_admission.py'))
    _admission = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_admission)
    screening_decision, screen_images, SCREEN_VERSION = _admission.decision, _admission.screen, _admission.VERSION

IMAGE_LIMIT = 8 * 1024 * 1024
CACHE_LIMIT = 128 * 1024 * 1024
TTL = 30 * 86400
REJECTED_SCREENSHOTS = frozenset((
    'ef374e5e4ede8c71f32d455652bc00f2fa7c035e',  # First Light review collage
    '18787f52adabf0e5248548ed83562e6aac88f94d',  # Deluxe contents panel
))

# Reviewed against the Store's actual images. Immutable filename hashes keep
# a reordered or replaced Store gallery from silently approving a HUD frame.
CLEAN_SCREENSHOTS = {
    # Assassin's Creed Black Flag Resynced
    '3751950': frozenset((
        '5de8c44752bdbc724b905b76bc5023bbff57547f',
        'a79f6dada7c7ca555c1be440793ee46813acf9ca',
        '2fc01441720a7f301b3f0abced79b7d9159cb105',
    )),
    # Assassin's Creed Unity
    '289650': frozenset((
        '19c1c8d52d714fe8d0a0277c36832b4e0ad5def3',
        'd825c8fd7c5472d17732bf3480760dd88924e551',
        '42c6e1765549541d5576ec5bdb01cbc45f376444',
        'facd76eb6789402e9caea63d0d0b18b84abdabae',
    )),
    # Assassin's Creed Valhalla
    '2208920': frozenset((
        '103481084a59b34837113daf27c04679caf743f3',
        'e7310b36689ec722d2ea4643efc15bd8fa720c67',
        'c3bff917ead50268eb7708ef3bf30e07b58929e9',
        '5e527e1e063ef041ca6680f503081274dcc5513a',
    )),
    # Avatar: Frontiers of Pandora
    '2840770': frozenset((
        '5d96569712304414f21cddbedbe82d5d2b598bcb',
        '75b20da8e11285fb3f33f550dafb7d842b70e31f',
        'b441eb8a77c901dae889a8605d2266b6defd7851',
        'f75613a079f078740df1d898d55e0aebf8031fb9',
    )),
    # Avowed
    '2457220': frozenset((
        '4ce0337503b8aa740fd84c0ec19a850a5efb8569',
        '6cbf7b81f6b1604bbe02886c666eafa0bd2d5f6e',
        '082ba9d5d0ed6718de9a138bce5da847fcd05a61',
        'f757a8184327a7a53d148ecf62eb7e8823cf2fdf',
    )),
    # Baldur's Gate 3
    '1086940': frozenset((
        'c73bc54415178c07fef85f54ee26621728c77504',
        '73d93bea842b93914d966622104dcb8c0f42972b',
        'cf936d31061b58e98e0c646aee00e6030c410cda',
        'b6a6ee6e046426d08ceea7a4506a1b5f44181543',
    )),
    # Clair Obscur: Expedition 33
    '1903340': frozenset((
        '483a27df5072beb3a4650634a764bda750fbcb82',
        'e49800e906e8a0f00707458c836567c933603bac',
        'b8089016095e6a16e324a59c45b2f24a439bd0b3',
        '8439c07d7b1f2fcfc6449db5f051f8d0867f4785',
    )),
    # CONTROL Resonant
    '3669870': frozenset((
        '422f3eed36d3033c4b0f4fde485c29b980e49454',
        '195a46fccb4276003092c87c9d6d034a0dfbe355',
        'e9e5561bffc6ac8630ff63cbeb1fbb9e2d702e13',
        '4ce55d730791b45afae9fe2573ff764b34103a75',
    )),
    # Control Ultimate Edition
    '870780': frozenset((
        '8376498631b089e52fb5c75ffe119e0de5e6aed1',
        '5a16ce565951479e142c56a23f19d88333d84945',
        'c038bb7b20d72ba5d33cc95f7235aefa0b84a706',
        '949cf39deee737fec3aadff903ec5311dd22bdab',
    )),
    # Crimson Desert Enhanced
    '3321460': frozenset((
        '667d1763ae26137aafbc3140963621f530b43289',
        'b154a083ff9a746c71a1513334042e1bb9403a8b',
        '286938f408f5f0c6409f49584f33e8d497433123',
        '91f6ddd6a4cc0f704bee1956701a3f36447fe02a',
    )),
    # Cyberpunk 2077
    '1091500': frozenset((
        '2f649b68d579bf87011487d29bc4ccbfdd97d34f',
        'f678ed77c2fe7060ac9c64e32e1472e3ec3ab7dc',
        '0ed9487e305983d60646ba163a3d8970efb6b347',
    )),
    # DEATH STRANDING 2: ON THE BEACH
    '3280350': frozenset((
        '702c9ed8dc25f26be07539cd5cfb9f08046d210a',
        '9732214efafbe68e6618806556cd448578217a04',
        '1a78ae746ca46713e3c2cb2e5c4f197fea72fe50',
        'f8c42434fe7d51fdb3f039ca06a99f5f18518a31',
    )),
    # Dispatch
    '2592160': frozenset((
        '6aa03b03ee710fe218e3be4bc54975e4c34d7d8a',
    )),
    # Dragon Age™: The Veilguard
    '1845910': frozenset((
        'a252774678fde933d4fbee722db855b731b0e627',
        '94c6e6f26435702105b83e76804cd27710543fcc',
        'e1cb223c41c80599db057d4101266b4da0d254d3',
        '89d0a2e20fd17f28f78bffefc563d2ff246f0e65',
    )),
    # Far Cry 5
    '552520': frozenset((
        '8c2c63dfb8711e3bdaaeb2400668f690f24ab5b3',
        '93e1fad73390e7d7a73ab886300e7c26717a5c00',
        '7a3b7b4d6e56aa71b59367e4467cfc49715b6914',
    )),
    # FINAL FANTASY VII REBIRTH
    '2909400': frozenset((
        '7a83a64967a06edbf0d43821153a0188471d596a',
        '7c389d8ed52b6bd2350a3bc9866ac45c919fb2e9',
        '5540aef3258019f77559ca77ef29ba893b61010f',
        '45513682d4c2e77b2a89e7bea00ec2851c110116',
    )),
    # Forza Horizon 6
    '2483190': frozenset((
        '706eb79418b2a74192de059693ddcbfaa803108a',
        '383ace7815eaa8f8f5128a58fd8ca7df911d3e14',
        'd4b81f0cafcfba410371e53bd696fb5cc9b434c0',
        '041b9a2854dc647bf54d7d8b36d2f4186ed72c13',
    )),
    # Gears of War: E-Day
    '3010850': frozenset((
        '82631b6762963c60ad1ea684fac235686a10027b',
    )),
    # Halo: Campaign Evolved
    '2806050': frozenset((
        '4288a35884445fcf22f4fe7315944c376ecb1cf5',
        'e3a3facf1d3f02fc13ef6e95a40cf1fad52a9087',
        '8a7b831ea8a306b1f13321f027c1410ac378941b',
        'a05dce36b81730fcd2a4ddd4a1106cfcc74dbf0b',
    )),
    # Hogwarts Legacy
    '990080': frozenset((
        '725bf58485beb4aa37a3a69c1e2baa69bf3e4653',
        'df93b5e8a183f7232d68be94ae78920a90de1443',
        '94058497bf0f8fabdde17ee8d59bece609a60663',
        '8e08976236d29b1897769257ac3c64e9264792a5',
    )),
    # inZOI
    '2456740': frozenset((
        '654a0eb86c9d38620c5a5992bc2a58a4b4b894f8',
        '42ebcfae05adf2fdf955d9da13af76e8a8986a40',
        'bd72883480124cda61c1826aa192d9da98961db4',
        '3b1b5f8a5b483e4348f92e080f0a508e61991286',
    )),
    # Kingdom Come: Deliverance II
    '1771300': frozenset((
        '935ddb59f90bc2c21c706132cb9b446fe7851c19',
        '709f3329562cd2cfe6db70bac908b3e72eaef83b',
        'bd668f4d12300c019fa3fa73108aa62929fbf862',
        '5580d672302cdc5f8b7161dc94f266341e61a182',
    )),
    # Mafia: The Old Country
    '1941540': frozenset((
        'abe3b20e3bdddb8dad947828efbf7f7110c3cae5',
        'a6ab7a19e69f59d741072c089ca7ad9f6bb60814',
        '3bc232192813ab9250abafd627333f1d8bd53bb9',
        '8c5af3a1b47337fe9d2f4f48d21975964eb23ccb',
    )),
    # Marvel's Guardians of the Galaxy
    '1088850': frozenset((
        '762e9aa91609ac1ef1f20c7dd1a2de2b32060234',
        '815ef8c726e21a388d8ca331c2609c2d46ceeb32',
        'd8190bc069fb9c182068811af9914fc333184657',
        '31f2ca046af6f0c5ee896b421394b415f21ce3d6',
    )),
    # Mass Effect™ Legendary Edition
    '1328670': frozenset((
        '3cfdbd8a5d94f9005d33ba17bb6b163dc458ddf7',
        '4e226eb092381ba6c4ea9c164a1d18574c993a8a',
        '8994024759b1e6afb09a99381637c8b6fb4e4075',
        '4b2b412307b72a21f68148c32fab7a278875d139',
    )),
    # Mass Effect™: Andromeda
    '1238000': frozenset((
        '3bebdd5c7575faf743e28ecbf51d73cbcea491a3',
        '7cf27c2a247bb46834764760b7e4a30afa785ba9',
        '016aed121b497aa916a69b6e33d15ab8371c4283',
        'fcc2e4827d905d971e2d1a5e0e23dc0be050cc7f',
    )),
    # Mixtape
    '2582320': frozenset((
        '24acc55682b75be77cb5f4bfef6502fbafd66f10',
        'a86ec3a65b9697f6011bcc576066bd5d6e5642f2',
        '08f1c5e644a5dcd172a892e2bd41bae6e47d1fe1',
        'ad1ca02ddc791e937ca6ad03b02bef893dd2da20',
    )),
    # No Man's Sky
    '275850': frozenset((
        '7d45478fbac8b1a41172adf8e598784a7d04b41d',
        '53afb343452e839000d5eab38d0656fcdad9547b',
        '6c2ddcffe192b0e155a69aa2a1dd3f33b863033d',
        'd4884d4d208b3f6a3ecef898559da7a36102fc70',
    )),
    # PRAGMATA-22357085
    '3357650': frozenset((
        '9699288b90d0aad320e998f107b59edd27e9ea61',
        '62486c0475c7bf1a14889d61a51ad24f09e5f044',
        '26773713a2435c8edc2eac5e7eb234324b3b002f',
        '8913ab7128c72ddd1b407c274e9615b2f6e658a2',
    )),
    # Red Dead Redemption 2
    '1174180': frozenset((
        '66b553f4c209476d3e4ce25fa4714002cc914c4f',
        'bac60bacbf5da8945103648c08d27d5e202444ca',
        '668dafe477743f8b50b818d5bbfcec669e9ba93e',
        '4ce07ae360b166f0f650e9a895a3b4b7bf15e34f',
    )),
    # Sonic Adventure DX
    '71250': frozenset(()),
    # Sonic Adventure™ 2
    '213610': frozenset(()),
    # Sonic Frontiers
    '1237320': frozenset((
        '8ac5bfdc998b20e4a54ee27b68ef175f7cd9f1a9',
        'd9c769a9346e5b1d7e1f9109d0c317c81213c021',
        '45369645d9c1c1b1fd9483b48c8a15f21b8693c5',
        'cddd10b31502d648f964c5df550499d041212759',
    )),
    # Sonic Racing: CrossWorlds
    '2486820': frozenset((
        '3d0d2e2f1ec38bc6e5cb19766f104bfe1442e3c3',
        '68d04858202b2f8fa8f84e5497962cb22c09e22c',
        'bf3f2046733d9bdf12e86a245ca716c01b6dcc88',
        '86d5c09bf44f310269c4d492135b9a6e911fac33',
    )),
    # Spyro™ Reignited Trilogy
    '996580': frozenset((
        'bcf2c7104b393806c478e7a324630487970ee829',
        '971529dd86fc64c4505e54fabb1847ec47118a5d',
        'd3398e9f6afc99bcc471bc85c419fe5cfbd8918f',
        '08eafc1dfc14b2869cd448e1442d9616e5252e3b',
    )),
    # STAR WARS Jedi: Survivor™
    '1774580': frozenset((
        'e589d6bb347c13f7226f0b294fd12880ced8d171',
        '6f2e72d773e4280f3a4860c7fb1d62e72932a9b0',
        'f14055548a6c51171036ebb3d00ddf5c97e5bd05',
        'bb84b8cbf9294c6166819c3d3328c4efbdb9d46c',
    )),
    # Star Wars Outlaws
    '2842040': frozenset((
        '34f55684c1a2d5232911b77b745d9496621bf5e1',
        'de4e5a72d13a6bbd62990a64c94e61ef0e7a277a',
    )),
    # Starfield
    '1716740': frozenset((
        'b2821283cb140cd5a6289a8160016b6a60d8f96e',
        '68f15d580bf91971f637be5e464bc803482d78f7',
        'aae99c177004bb5ec653d2fcb65a5d30489ec7b8',
    )),
    # The Outer Worlds 2
    '1449110': frozenset((
        'aed9141f12c197a06fb1d6a68b06ac9251f80370',
        '28c22a02a2c6341d94372826b24e163e59d4154c',
        'ab26c9f54d15037f18b4dd39f9c12b790d5bfb2f',
        '08a867275ba289445985a9249d519f264284735b',
    )),
    # The Sims™ 4
    '1222670': frozenset((
        '537683e5e29c2d6d02c64aa7321dcb26166f7d82',
        '2fc938d99a1e87893852cb2d2113478190607941',
        'e1f0ce3ca2c9a538e382cc8b040944fe05af4bb2',
    )),
    # The Witcher 3: Wild Hunt — Remastered
    '292030': frozenset((
        'f7f564ecedd09b3e503b071a637aeefdedbeedd8',
        '0a38e4d0d57f15934772dbe09b322d08132d5518',
        '19c03c2b997d3a393fc629fd42f55ddb4a3d8dd0',
        '3a3f430982cc3bccac1633d3ea60a30bf3d1ae9e',
    )),
    # Tiny Glade
    '2198150': frozenset(()),
    # Tony Hawk's™ Pro Skater™ 1 + 2
    '2395210': frozenset((
        'de7db46ee5f6164dfdb467ad1659f7981e285824',
        '866a178397cc58e5578e39e19c2233b05528d720',
        'ccc432a7c5c36283b40dc2460de7f0c40ad29e02',
        '98797b019081480c5a788f9557355b87d4bfc8bf',
    )),
    '3768760': frozenset((
        '43c8cf3875cb6643ac7d8244e9fd39381609814a',
        'c1e68b9b3d1c55b9d62f4041c6fbfefe329a236c',
        'd076a739da6136dc4da2c48750eb6f780d4f826d',
        '7683959b09f7863c5eb23bfdbcf039269765b5d6',
        '2e3f04c42cca344dd3ca0be30c5078719bce23ed',
        '22b94f7aa04496557f7b8b797abe8e81c8ac8d94',
        '5cef2b25b774b09bc30780457370f734021d207a',
        'ad4dfe02d7c437ba916114d8b1626dec348a6ca1',
        'd134165918bca5b3d420c68ccde8ace5c826c725',
        'd4b2566b28d98b12ac4f018b951c45d529894c05',
        '1550126dc773dde15731f670725e6880e0abf5ea',
        '77725bbd5a29b4bd0e7b563983a17591dd942233',
    )),
    '3159330': frozenset((
        '81bbd04dae05b0a52dc62818dc5219abeb849f8d',
        'e53dc9ec73e3de9b8e680472898de775f0dc1cae',
        '2e74c5442faa027ea699dcfa15be173b43a8d37a',
    )),
}


def screenshot_hash(url):
    match = re.search(r'/ss_([0-9a-f]{40})(?:\.|$)', urllib.parse.urlsplit(url).path)
    return match[1] if match else None


def clean_screenshot(url, appid, cache=None):
    approved = CLEAN_SCREENSHOTS.get(appid)
    identity = screenshot_hash(url)
    if not identity:
        return False
    if identity in REJECTED_SCREENSHOTS:
        return False
    if approved and identity in approved:
        return True
    result = screening_decision(cache, identity) if cache is not None else None
    return bool(result and result['clean'])


def clean_gallery(shots, appid, cache=None, download=None, screen=screen_images):
    # Corrections for known images are optional fast paths, not app admission.
    # Unknown libraries use exactly the same local screening worker on both OSes.
    if cache is not None and download is not None:
        pending = [shot for shot in shots if allowed(shot.get('full', ''), appid) and screenshot_hash(shot.get('full', ''))
                   and screenshot_hash(shot['full']) not in REJECTED_SCREENSHOTS
                   and not clean_screenshot(shot.get('full', ''), appid, cache)
                   and screening_decision(cache, screenshot_hash(shot['full'])) is None][:12]
        if pending:
            with tempfile.TemporaryDirectory(prefix='.screen-', dir=cache) as temporary:
                def prepare(shot):
                    try:
                        data = download(shot['full'], IMAGE_LIMIT)
                        width, height = dimensions(data)
                        if width*height > 40_000_000 or min(width, height) < 240:
                            return None
                        path = Path(temporary) / (screenshot_hash(shot['full']) + '.image')
                        path.write_bytes(data)
                        return (shot, path)
                    except (OSError, ValueError):
                        return None
                with ThreadPoolExecutor(max_workers=3) as pool:
                    prepared = [item for item in pool.map(prepare, pending) if item]
                verdicts = screen([path for _, path in prepared]) if prepared else []
                for index, (shot, _) in enumerate(prepared):
                    verdict = verdicts[index] if index < len(verdicts) else {'clean': False, 'reason': 'unavailable'}
                    clean = verdict.get('clean') is True
                    reason = str(verdict.get('reason', 'unavailable'))[:64]
                    atomic(Path(cache) / (screenshot_hash(shot['full']) + '.screen.json'),
                           json.dumps({'version': SCREEN_VERSION, 'clean': clean, 'reason': reason, 'checked': time.time()}).encode())
        receipts = [p for p in Path(cache).glob('*.screen.json') if re.fullmatch('[0-9a-f]{40}\\.screen\\.json', p.name)]
        if len(receipts) > 4096:
            for path in sorted(receipts, key=lambda p: p.stat().st_mtime)[:len(receipts)-4096]:
                path.unlink(missing_ok=True)
    return [shot for shot in shots if allowed(shot.get('full', ''), appid) and clean_screenshot(shot.get('full', ''), appid, cache)]


def dimensions(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n') and len(data) >= 24:
        return struct.unpack('>II', data[16:24])
    if data.startswith(b'\xff\xd8'):
        pos = 2
        while pos + 4 <= len(data):
            if data[pos] != 255:
                break
            marker = data[pos + 1]
            pos += 2
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                continue
            length = int.from_bytes(data[pos:pos + 2], 'big')
            if length < 2 or pos + length > len(data):
                break
            if marker in (0xC0, 0xC1, 0xC2) and length >= 7:
                height, width = struct.unpack('>HH', data[pos + 3:pos + 7])
                return width, height
            pos += length
    raise ValueError('Unsupported or incomplete screenshot')


def allowed(url, appid):
    parsed = urllib.parse.urlsplit(url)
    return (parsed.scheme == 'https' and parsed.port in (None, 443) and not parsed.username
            and (parsed.hostname or '').endswith('.steamstatic.com')
            and any(parsed.path.startswith(prefix + appid + '/') for prefix in ('/steam/apps/', '/store_item_assets/steam/apps/'))
            and parsed.path.rsplit('/', 1)[-1].startswith('ss_'))


def fetch(url, limit):
    class Redirects(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            # Store metadata stays on the Store; image redirects stay on Valve's CDN.
            host = urllib.parse.urlsplit(newurl)
            if host.scheme != 'https' or not (host.hostname == 'store.steampowered.com' or (host.hostname or '').endswith('.steamstatic.com')):
                raise ValueError('Unexpected screenshot redirect')
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    request = urllib.request.Request(url, headers={'User-Agent': 'rtxForge/1.0', 'Accept': '*/*'})
    with urllib.request.build_opener(Redirects()).open(request, timeout=8) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Screenshot response exceeds its limit')
    return data


def atomic(path, data):
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.download-', delete=False) as output:
        temporary = Path(output.name)
        try:
            output.write(data)
            output.flush()
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_appid(appid):
    if not isinstance(appid, str) or not re.fullmatch(r'[1-9][0-9]{0,9}', appid):
        raise ValueError('A Steam application ID is required')


def gallery(appid, cache, *, download=fetch, now=None, screen=screen_images):
    validate_appid(appid)
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    record = cache / (appid + '.gallery.json')
    current = time.time() if now is None else now
    stored = {}
    try:
        if record.is_symlink() or record.stat().st_size > 256 * 1024:
            raise ValueError('Invalid screenshot catalog')
        stored = json.loads(record.read_text('utf-8'))
        if current - stored['checked'] < (TTL if stored.get('screenshots') else 900):
            return clean_gallery(stored.get('screenshots', []), appid, cache, download, screen)
    except (OSError, ValueError, KeyError, TypeError):
        stored = {}
    try:
        endpoint = 'https://store.steampowered.com/api/appdetails?' + urllib.parse.urlencode({'appids': appid, 'filters': 'screenshots'})
        response = json.loads(download(endpoint, 2 * 1024 * 1024))
        result = response.get(appid, {}) if isinstance(response, dict) else {}
        details = result.get('data') if isinstance(result, dict) and result.get('success') else None
        candidates = details.get('screenshots', []) if isinstance(details, dict) else []
        shots = []
        for item in candidates[:100] if isinstance(candidates, list) else []:
            if not isinstance(item, dict) or not allowed(item.get('path_full', ''), appid):
                continue
            identity = str(item.get('id', len(shots)))
            thumbnail = item.get('path_thumbnail', '')
            if not identity.isdecimal() or len(identity) > 6:
                continue
            shots.append({'id': identity, 'full': item['path_full'], 'thumbnail': thumbnail if allowed(thumbnail, appid) else item['path_full']})
        atomic(record, json.dumps({'checked': current, 'screenshots': shots}).encode())
        return clean_gallery(shots, appid, cache, download, screen)
    except (OSError, ValueError, TypeError):
        return clean_gallery(stored.get('screenshots', []), appid, cache, download, screen)


def background(appid, cache, *, screenshot=None, download=fetch, now=None):
    validate_appid(appid)
    if screenshot is not None and (not isinstance(screenshot, str) or not re.fullmatch(r'[0-9]{1,6}', screenshot)):
        raise ValueError('Invalid screenshot ID')
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    if cache.is_symlink():
        raise ValueError('Screenshot cache must be a directory')
    identity = appid + ('-' + screenshot if screenshot is not None else '')
    image, receipt = cache / (identity + '.image'), cache / (identity + '.json')
    current = time.time() if now is None else now
    stored, data = {}, None
    try:
        if receipt.is_symlink() or image.is_symlink() or receipt.stat().st_size > 4096:
            raise ValueError('Invalid screenshot cache entry')
        stored = json.loads(receipt.read_text('utf-8'))
        if not clean_screenshot(stored.get('source', ''), appid, cache):
            raise ValueError('Cached screenshot is no longer approved for backgrounds')
        if stored.get('missing') and current - stored['checked'] < 900:
            return {'image': None}
        if image.stat().st_size > IMAGE_LIMIT:
            raise ValueError('Invalid cached screenshot size')
        data = image.read_bytes()
        if hashlib.sha256(data).hexdigest() != stored['sha256']:
            raise ValueError('Cached screenshot changed')
        dimensions(data)
    except (OSError, ValueError, KeyError, TypeError):
        stored, data = {}, None
    if data is None or stored.get('version') != 2 or current - stored.get('checked', 0) > TTL:
        try:
            candidates = gallery(appid, cache, download=download, now=current)
            if screenshot is not None:
                candidates = [item for item in candidates if item['id'] == screenshot]
            best = None
            for item in candidates[:3]:
                if not isinstance(item, dict):
                    continue
                url = item.get('full', '')
                if not allowed(url, appid):
                    continue
                # Steam's path_full can still name its 1920x1080 derivative.
                # Request the original of that exact screenshot before its derivative.
                original = re.sub(r'\.\d+x\d+(?=\.(?:jpg|png)(?:\?|$))', '', url)
                for source in dict.fromkeys((original, url)):
                    try:
                        content = download(source, IMAGE_LIMIT)
                        width, height = dimensions(content)
                        if width * height > 40_000_000 or min(width, height) < 480:
                            continue
                        if best is None or width * height > best[1] * best[2]:
                            best = content, width, height, source
                        break
                    except (OSError, ValueError):
                        continue
                if best and best[1] >= 3840 and best[2] >= 2160:
                    break
            if best:
                data, width, height, url = best
                stored = {'version': 2, 'width': width, 'height': height, 'source': url, 'checked': current, 'sha256': hashlib.sha256(data).hexdigest()}
                atomic(image, data)
                atomic(receipt, json.dumps(stored).encode())
                # Evict only old regular image/receipt pairs owned by this cache.
                files = sorted((p for p in cache.glob('*.image') if not p.is_symlink()), key=lambda p: p.stat().st_mtime, reverse=True)
                total = 0
                for path in files:
                    total += path.stat().st_size
                    if total > CACHE_LIMIT and path != image:
                        path.unlink(missing_ok=True)
                        path.with_suffix('.json').unlink(missing_ok=True)
            elif data is None:
                atomic(receipt, json.dumps({'missing': True, 'checked': current}).encode())
        except (OSError, ValueError, TypeError):
            pass  # Keep the last good image available offline.
    if data is None:
        return {'image': None}
    mime = 'image/png' if data.startswith(b'\x89PNG') else 'image/jpeg'
    return {**stored, 'image': 'data:' + mime + ';base64,' + base64.b64encode(data).decode('ascii')}
