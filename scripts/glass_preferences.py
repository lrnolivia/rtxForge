"""Portable appearance values shared by the manager and native glass renderer."""
import transactions as t

DEFAULTS = dict(ThemeVersion=4, Theme=3, Custom=0, Layout='floating', TextFont='roboto', TextSize=22,
                Scale=100, ScaleBaseline=120, LightTint=100, DarkTint=80, ClearTint=20, AccentCharacter=35, AccentTint=67,
                Blur=48, Grain=40, BlendStrength=50, SurfaceBlend='soft-light', TextDepth=1,
                InvertDark=0, ToastPill=0, Motion=1, ShowNotifications=1)
BLENDS = ('normal','overlay','soft-light','multiply','screen','hard-light','darken','lighten','color','luminosity','difference')
ENUMS = dict(Layout=('floating','centered','bar'), TextFont=('roboto','inter'), SurfaceBlend=BLENDS)
RANGES = dict(ThemeVersion=(4,4), Theme=(1,4), Custom=(0,1), TextSize=(16,26), Scale=(70,150),
              ScaleBaseline=(120,120), LightTint=(0,100), DarkTint=(0,100), ClearTint=(0,100), AccentCharacter=(0,100), AccentTint=(0,100),
              Blur=(16,48), Grain=(0,80), BlendStrength=(0,100), TextDepth=(0,1), InvertDark=(0,1),
              ToastPill=(0,1), Motion=(0,1), ShowNotifications=(0,1))
FINE = {'LightTint','DarkTint','ClearTint','AccentTint','Blur','Grain','BlendStrength','SurfaceBlend','InvertDark'}


def validate(values):
    t.need(isinstance(values,dict) and set(values) <= set(DEFAULTS), 'Unknown overlay appearance option.')
    for key, value in values.items():
        if key in ENUMS: t.need(value in ENUMS[key], 'Choose a supported '+key+'.')
        else:
            low, high = RANGES[key]
            t.need(type(value) is int and low <= value <= high, 'Overlay '+key+' is outside its supported range.')
    return dict(values)


def current(settings):
    return DEFAULTS | validate(settings.get('overlay_appearance', {}))


def edit(settings, key, value):
    result = current(settings) | {key:value}
    if key == 'AccentCharacter':
        t.need(type(value) is int and 0 <= value <= 100, 'Choose an accent character from Clear to Dark.')
        x = min(value / 50, 1)
        result['AccentTint'] = round(20 + 60 * x * x * (3 - 2 * x))
    if key in FINE: result['Custom'] = 1
    settings['overlay_appearance'] = validate(result)


def theme(settings, mode):
    t.need(mode in ('clear','light','dark','accent'), 'Choose Clear, Light, Dark or Accent.')
    values = current(settings)
    values.update({key:DEFAULTS[key] for key in (*FINE, 'TextDepth')})
    values.update(Theme={'clear':3,'light':1,'dark':2,'accent':4}[mode], Custom=0,
                  Blur=44 if mode=='light' else 48,
                  BlendStrength=35 if mode=='light' else 15 if mode=='dark' else 50,
                  SurfaceBlend='normal' if mode=='accent' else 'soft-light' if mode=='clear' else 'overlay',
                  AccentCharacter=35, AccentTint=67)
    if mode == 'accent': values['BlendStrength'] = 0
    settings['overlay_appearance'] = values
    settings['overlay_theme'] = mode
