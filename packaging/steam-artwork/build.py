from pathlib import Path
import base64, xml.etree.ElementTree as ET, subprocess, json, zipfile, shutil, hashlib
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'exports'; OUT.mkdir(exist_ok=True)
F={n:TTFont(ROOT/'source'/p) for n,p in [('brand','BakbakOne-Regular.ttf'),('body','Inter-Regular.ttf')]}
ART=ET.parse(ROOT/'source/approved-icon.svg').getroot()
ARTBODY=''.join(ET.tostring(n,encoding='unicode') for n in ART)
PHOTO='data:image/png;base64,'+base64.b64encode((ROOT/'assets/cooling-study.png').read_bytes()).decode()
INK='#f3f2ef'

def text(t,x,y,size,fill=INK,family='body',tracking=0):
 f=F[family]; gs=f.getGlyphSet(); cm=f.getBestCmap(); upem=f['head'].unitsPerEm
 pen=SVGPathPen(gs);adv=0
 for c in t:
  g=gs[cm[ord(c)]];g.draw(TransformPen(pen,(1,0,0,1,adv,0)));adv+=g.width+tracking*upem/size
 return f'<path aria-label="{t}" fill="{fill}" transform="translate({x} {y}) scale({size/upem} {-size/upem})" d="{pen.getCommands()}"/>'

def icon(x,y,w):return f'<g id="approved-icon" transform="translate({x} {y}) scale({w/512})">{ARTBODY}</g>'

def lockup(ink=INK,sub='#c7cac2'):
 return icon(0,0,232)+text('rtxForge',248,143,160,ink,'brand')+text('new tricks for old cards',254,193,33,sub)

LOGO=lockup()
def asset(name,x,y,w,h):
 data='data:image/png;base64,'+base64.b64encode((OUT/(name+'.png')).read_bytes()).decode()
 return f'<image x="{x}" y="{y}" width="{w}" height="{h}" href="{data}"/>'
def photo(x,y,w,h):return f'<image id="cooling-study" x="{x}" y="{y}" width="{w}" height="{h}" href="{PHOTO}"/>'
def svg(w,h,b,title):return f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><title>{title}</title><desc>rtxForge Steam library artwork. Static image. Bakbak One wordmark; Inter tagline. Original approved icon.</desc>{b}</svg>'
def save(name,w,h,b,folder=OUT,png_source=None):
 p=folder/(name+'.svg');p.write_text(svg(w,h,b,name))
 if png_source:shutil.copyfile(png_source,folder/(name+'.png'))
 else:subprocess.run(['inkscape',str(p),'--export-filename='+str(folder/(name+'.png'))],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 return b

# Separate transparent PNGs with white or dark lettering and a soft offset shadow.
# Extra transparent padding allows the blur to decay before the image boundary.
def shadowed_logo(ink,sub,opacity):
 shadow=f'<defs><filter id="logo-shadow" x="-20%" y="-50%" width="140%" height="220%"><feGaussianBlur in="SourceAlpha" stdDeviation="7"/><feOffset dx="0" dy="7"/><feComponentTransfer><feFuncA type="linear" slope="{opacity}"/></feComponentTransfer><feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>'
 return shadow+f'<g transform="translate(48 44) scale({1184/912})"><g filter="url(#logo-shadow)">{lockup(ink,sub)}</g></g>'
save('rtxforge-logo-white',1280,400,shadowed_logo('#ffffff','#ffffff',.72))
save('rtxforge-logo-dark',1280,400,shadowed_logo('#242925','#48534b',.40))

# Portrait uses a taller image-window. Cooling curves occupy the top two thirds;
# the lower brand group has its own clear floor. No logo plate or surrounding tile.
portrait='<defs><linearGradient id="portrait-fade" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#080b0a" stop-opacity="0"/><stop offset="1" stop-color="#080b0a"/></linearGradient></defs>'
portrait+='<rect width="600" height="900" fill="#080b0a"/>'
portrait+=photo(-520,-65,1200,800)
portrait+='<rect y="450" width="600" height="295" fill="url(#portrait-fade)"/>'
portrait+=f'<g transform="translate(35 664) scale(.576)">{LOGO}</g>'
portrait=save('rtxforge-steam-portrait',600,900,portrait)

# The wide card positions the cooling hub on the right, leaving measured space for the mark.
wide='<defs><linearGradient id="wide-fade"><stop stop-color="#070a09"/><stop offset=".65" stop-color="#070a09" stop-opacity=".94"/><stop offset="1" stop-color="#070a09" stop-opacity="0"/></linearGradient></defs>'
wide+='<rect width="920" height="430" fill="#080b0a"/>'
wide+=photo(20,-91,1000,666.6667)
wide+='<rect width="700" height="430" fill="url(#wide-fade)"/>'
wide+=f'<g transform="translate(37 137) scale(.56)">{LOGO}</g>'
wide=save('rtxforge-steam-wide',920,430,wide)

# Hero is intentionally background-only. Logo placement belongs to Steam.
hero_source=ROOT/'assets/rtxhero.png'
hero_data='data:image/png;base64,'+base64.b64encode(hero_source.read_bytes()).decode()
hero=f'<image width="3840" height="1240" href="{hero_data}"/>'
hero=save('rtxforge-steam-hero',3840,1240,hero,png_source=hero_source)

# Review board: actual asset proportions, precise gallery-like framing, no mock UI.
B='<rect width="1880" height="1820" fill="#eeeDE8"/>'
B+=text('rtxForge',60,90,56,'#1c211d','brand')
B+=text('Hardware study / 35mm',1490,71,21,'#505a52')
B+=text('Fine grain · soft vignette',1490,102,16,'#6f756f')
B+='<path d="M60 135H1820" stroke="#c5cbc0"/>'
B+=asset('rtxforge-steam-portrait',60,180,510,765)
B+=text('Portrait',60,983,19,'#1c211d')+text('600 × 900',450,983,16,'#60695f')
B+=asset('rtxforge-steam-wide',625,180,1195,558.5326)
B+=text('Wide capsule',625,777,19,'#1c211d')+text('920 × 430',1700,777,16,'#60695f')
# Checkerboard is a review-only transparency indicator, never part of the PNG.
B+='<defs><pattern id="checker" width="32" height="32" patternUnits="userSpaceOnUse"><rect width="32" height="32" fill="#a1a69f"/><rect width="16" height="16" fill="#92978f"/><rect x="16" y="16" width="16" height="16" fill="#92978f"/></pattern></defs>'
B+='<rect x="625" y="815" width="1195" height="220" fill="url(#checker)"/>'
B+=asset('rtxforge-logo-white',659,817,696,217.5)
B+=text('Separate white transparent logo · soft shadow',625,1070,18,'#1c211d')
B+=text('1280 × 400',1680,1070,16,'#60695f')
# Hero shown exactly as exported: background only. No composited placement demo.
B+=asset('rtxforge-steam-hero',60,1140,1760,568.333)
B+=text('Hero image only · Steam places the logo separately',60,1755,19,'#1c211d')+text('3840 × 1240',1675,1755,16,'#60695f')
save('rtxforge-hardware-film-review',1880,1820,B,ROOT)

manifest={'direction':'Hardware study — fine 35mm grain and soft vignette','artwork':{'rtxforge-steam-portrait.png':[600,900],'rtxforge-steam-wide.png':[920,430],'rtxforge-steam-hero.png':[3840,1240],'rtxforge-logo-white.png':[1280,400],'rtxforge-logo-dark.png':[1280,400]},'hero':'Background only, no embedded icon, lettering, or logo. White transparent logo supplied independently with a soft shadow and uncut transparent padding.','typography':{'wordmark':'Bakbak One','tagline':'Inter 450'},'background':'AI-generated conceptual unbranded cooling hardware, 1536×1024 source. Embedded and upscaled for hero export; not true 4K detail.','sources':'SVG files contain outlined exact lettering, original vector icon and embedded raster plate. Original fonts and licenses included.'}
manifest['hero']='User-revised background-only hero, preserved byte-for-byte. Separate transparent logo with stronger padded shadow.'
manifest['hero_source']={'filename':'assets/rtxhero.png','sha256':hashlib.sha256(hero_source.read_bytes()).hexdigest(),'size':[3840,1240]}
(ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(ROOT/'README.txt').write_text('rtxForge — Hardware study / 35mm edition\n\nSteam artwork review, not installed.\n\nexports/: production PNG and editable outlined SVG pairs.\nPortrait 600×900. Wide 920×430. Hero 3840×1240. White and dark logos 1280×400, transparent with padded soft drop shadow.\nHero contains only background art. The review board shows the hero image-only. The white logo is shown separately on a checkerboard transparency indicator; the checkerboard is not present in the actual PNG.\n\nApproved icon preserved as vector. Bakbak One appears only in rtxForge. Tagline is Inter (450).\nBackground is AI-generated illustrative hardware, not an exact commercial graphics card. The 1536×1024 image source is embedded in the SVG and upscaled for the hero; raster source is not native 4K.\n\nRun: /usr/bin/python3 build.py (fontTools, Inkscape required).\nFine 35mm grain and a soft vignette are applied only to the image plate. All vector artwork stays crisp. Approved crops and layout transforms are unchanged. Original approved edition remains one directory above for rollback. Original assets unchanged. Files were not deployed or installed.\n')
with zipfile.ZipFile(ROOT/'rtxforge-steam-hardware-film.zip','w',zipfile.ZIP_DEFLATED) as z:
 for p in sorted(ROOT.rglob('*')):
  if p.is_file() and (p.parent in [ROOT/'exports',ROOT/'source',ROOT/'assets'] or p.name in ['build.py','README.txt','manifest.json']):z.write(p,p.relative_to(ROOT))
print('Built',ROOT)
