"""Deterministic WCAG contrast for text; decorative accents remain unchanged."""
import colorsys


def rgb(color):
    raw=color.lstrip('#')
    return tuple(int(raw[i:i+2],16)/255 for i in (0,2,4))


def hex_color(values):
    return '#'+''.join(f'{max(0,min(255,round(v*255))):02x}' for v in values)


def mix(foreground,background,opacity):
    return hex_color(tuple(a*opacity+b*(1-opacity) for a,b in zip(rgb(foreground),rgb(background))))


def luminance(color):
    values=[v/12.92 if v<=0.04045 else ((v+0.055)/1.055)**2.4 for v in rgb(color)]
    return sum(v*w for v,w in zip(values,(0.2126,0.7152,0.0722)))


def contrast(a,b):
    x,y=sorted((luminance(a),luminance(b)))
    return (y+0.05)/(x+0.05)


def readable(color,backgrounds,minimum=4.5):
    """Find the nearest passing HSL lightness, preserving hue and saturation."""
    backgrounds=[backgrounds] if isinstance(backgrounds,str) else backgrounds
    passes=lambda candidate:all(contrast(candidate,b)>=minimum for b in backgrounds)
    if passes(color):return color
    h,lightness,s=colorsys.rgb_to_hls(*rgb(color))
    choices=[]
    for endpoint in (0.0,1.0):
        candidate=hex_color(colorsys.hls_to_rgb(h,endpoint,s))
        if not passes(candidate):continue
        low,high=0.0,1.0
        for _ in range(24):
            amount=(low+high)/2
            candidate=hex_color(colorsys.hls_to_rgb(h,lightness+(endpoint-lightness)*amount,s))
            if passes(candidate):high=amount
            else:low=amount
        candidate=hex_color(colorsys.hls_to_rgb(h,lightness+(endpoint-lightness)*high,s))
        choices.append((abs(endpoint-lightness)*high,candidate))
    if choices:return min(choices)[1]
    return max(('#000000','#ffffff'),key=lambda c:min(contrast(c,b) for b in backgrounds))


def vibrant_readable(color, background, minimum=3.0):
    """Prefer lifting value over washing out saturation for large accent text."""
    if contrast(color,background)>=minimum:return color
    h,s,v=colorsys.rgb_to_hsv(*rgb(color))
    for step in range(1,101):
        candidate=hex_color(colorsys.hsv_to_rgb(h,s,v+(1-v)*step/100))
        if contrast(candidate,background)>=minimum:return candidate
    return readable(color,background,minimum)


# ---------------------------------------------------------------------------
# Artwork accents, chosen perceptually in OKLab / OKLCH. Shared with the
# Windows build (Services/ArtAccent.cs): the same samples give the same picks.
# ---------------------------------------------------------------------------

import math

NO_ARTWORK='#b4b4b4'  # games without usable artwork: a light neutral grey


def _linear(channel):
    v=channel/255
    return v/12.92 if v<=0.04045 else ((v+0.055)/1.055)**2.4


def oklab(r8,g8,b8):
    r,g,b=_linear(r8),_linear(g8),_linear(b8)
    x=0.4122214708*r+0.5363325363*g+0.0514459929*b;l=math.copysign(abs(x)**(1/3),x)
    x=0.2119034982*r+0.6806995451*g+0.1073969566*b;m=math.copysign(abs(x)**(1/3),x)
    x=0.0883024619*r+0.2817188376*g+0.6299787005*b;s=math.copysign(abs(x)**(1/3),x)
    return (0.2104542553*l+0.7936177850*m-0.0040720468*s,
            1.9779984951*l-2.4285922050*m+0.4505937099*s,
            0.0259040371*l+0.7827717662*m-0.8086757660*s)


def _gamma(v):
    v=max(0.0,min(1.0,v))
    s=12.92*v if v<=0.0031308 else 1.055*v**(1/2.4)-0.055
    return round(s*255)


def from_oklch(l,c,h):
    """OKLCH to sRGB hex, reducing chroma until the color is inside the sRGB gamut."""
    chroma=c
    while True:
        a,b=chroma*math.cos(h),chroma*math.sin(h)
        lp=(l+0.3963377774*a+0.2158037573*b)**3
        mp=(l-0.1055613458*a-0.0638541728*b)**3
        sp=(l-0.0894841775*a-1.2914855480*b)**3
        r=4.0767416621*lp-3.3077115913*mp+0.2309699292*sp
        g=-1.2684380046*lp+2.6097574011*mp-0.3413193965*sp
        bl=-0.0041960863*lp-0.7034186147*mp+1.7076147010*sp
        e=0.0005
        if all(-e<=v<=1+e for v in (r,g,bl)) or chroma<=0:
            return '#%02x%02x%02x'%(_gamma(r),_gamma(g),_gamma(bl))
        chroma-=0.005


def lch(color):
    l,a,b=oklab(*(round(v*255) for v in rgb(color)))
    return l,math.hypot(a,b),math.atan2(b,a)


def _delta_e(x,y):
    ax,bx,ay,by=x[1]*math.cos(x[2]),x[1]*math.sin(x[2]),y[1]*math.cos(y[2]),y[1]*math.sin(y[2])
    return math.sqrt((x[0]-y[0])**2+(ax-ay)**2+(bx-by)**2)


def ui_accent(lab):
    """UI accent range: readable on dark and light surfaces, still the artwork's color."""
    l,a,b=lab
    return from_oklch(max(0.62,min(0.84,l)),max(0.09,min(0.24,math.hypot(a,b))),math.atan2(b,a))


def analyze(pixels):
    """Signature, alternate and background tones of RGBA pixels (a 64×64 sample).

    1. Group pixels into 36 hue × 3 lightness clusters.
    2. Score each cluster by area × vividness (chroma²), with a gentle
       preference for mid lightness, so a vivid logo or key light beats a
       large hazy sky or a dark backdrop.
    3. Use the chroma-weighted average of the real pixels in the winner, so
       two red posters get their own reds.
    Greyscale artwork has no signature.
    """
    samples=[oklab(r,g,b) for r,g,b,alpha in pixels if alpha>=128]
    hues,levels=36,3
    size=hues*levels
    score=[0.0]*size;sum_l=[0.0]*size;sum_a=[0.0]*size;sum_b=[0.0]*size;weight=[0.0]*size
    area_hues,area_levels,neutral_bins=12,4,6
    count=area_hues*area_levels+neutral_bins
    area=[0.0]*count;area_l=[0.0]*count;area_a=[0.0]*count;area_b=[0.0]*count
    chromatic=0
    for l,a,b in samples:
        c=math.hypot(a,b)
        hue=(math.atan2(b,a)/(2*math.pi)+1)%1
        if c<0.04:abin=area_hues*area_levels+min(neutral_bins-1,int(l*neutral_bins))
        else:abin=int(hue*area_hues)%area_hues*area_levels+min(area_levels-1,int(l*area_levels))
        area[abin]+=1;area_l[abin]+=l;area_a[abin]+=a;area_b[abin]+=b
        if c<0.05 or l<0.18 or l>0.97:continue  # near-neutral, near-black, blown out
        chromatic+=1
        index=int(hue*hues)%hues*levels+min(levels-1,int((l-0.18)/(0.79/levels)))
        midness=1-abs(l-0.65)*0.9
        score[index]+=c*c*midness
        sum_l[index]+=l*c;sum_a[index]+=a*c;sum_b[index]+=b*c;weight[index]+=c
    background=None
    if area and max(area)>0:
        top=area.index(max(area))
        background=(area_l[top]/area[top],area_a[top]/area[top],area_b[top]/area[top])
    if not samples or chromatic<len(samples)*0.02:return None,None,background
    # Merge each cluster with its hue neighbours so a color split across a bin edge is not undercounted.
    merged=[score[i]+0.5*(score[((i//levels)+hues-1)%hues*levels+i%levels]+score[((i//levels)+1)%hues*levels+i%levels]) for i in range(size)]
    def mean(i):return (sum_l[i]/weight[i],sum_a[i]/weight[i],sum_b[i]/weight[i]) if weight[i]>0 else None
    best=max(range(size),key=lambda i:merged[i])
    if merged[best]<=0:return None,None,background
    def gap(x,y):
        d=abs(x//levels-y//levels);return min(d,hues-d)
    alternates=[i for i in range(size) if gap(i,best)>=4 and merged[i]>merged[best]*0.08]
    alternate=max(alternates,key=lambda i:merged[i]) if alternates else None
    return mean(best),(mean(alternate) if alternate is not None else None),background


def signature_color(pixels):
    """The artwork's signature UI accent, or None for greyscale art."""
    signature,_alternate,_background=analyze(pixels)
    return ui_accent(signature) if signature else None


def _background_tone(lab):
    l,a,b=lab
    return max(0.6,min(0.9,l)),math.hypot(a,b),math.atan2(b,a)


def accent_suggestions(pixels):
    """Signature, Background, Alternate, Light and Deep; near-duplicates dropped."""
    signature,alternate,background=analyze(pixels)
    options=[]
    if signature:
        ui=lch(ui_accent(signature))
        options.append(('Signature',ui))
        if background:options.append(('Background',_background_tone(background)))
        if alternate:options.append(('Alternate',lch(ui_accent(alternate))))
        options.append(('Light',(0.88,min(ui[1],0.10),ui[2])))
        options.append(('Deep',(0.52,max(ui[1],0.14),ui[2])))
    elif background:
        options.append(('Background',_background_tone(background)))
    result=[]
    for name,value in options:
        if any(_delta_e(lch(color),value)<0.045 for _name,color in result):continue
        result.append((name,from_oklch(*value)))
    return result
