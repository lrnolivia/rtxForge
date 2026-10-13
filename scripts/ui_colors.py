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
