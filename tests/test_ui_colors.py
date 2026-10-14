from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ui_colors import readable,contrast,mix,vibrant_readable,rgb
import colorsys

class ContrastTest(unittest.TestCase):
    def test_standard_reference(self):
        self.assertAlmostEqual(contrast('#000000','#ffffff'),21.0)
    def test_accent_text_preserves_readable_colors(self):
        self.assertEqual(readable('#dddddd','#242424'),'#dddddd')
    def test_dark_light_and_selected_surfaces(self):
        accents=('#ec1629','#822222','#222222','#ffffff','#56b2e0','#76b900','#bbbb22')
        for color in accents:
            for backgrounds in (['#3d3d3d','#474747','#505050','#252525'],['#dedede','#d1d1d1','#c1c1c1'],[color]):
                adjusted=readable(color,backgrounds)
                for bg in backgrounds:
                    self.assertGreaterEqual(contrast(adjusted,bg),4.5,(color,adjusted,bg))
    def test_large_red_title_stays_saturated(self):
        for background in ('#242424','#080808'):
            result=vibrant_readable('#822222',background)
            self.assertGreaterEqual(contrast(result,background),3.0)
            self.assertAlmostEqual(colorsys.rgb_to_hsv(*rgb(result))[1],colorsys.rgb_to_hsv(*rgb('#822222'))[1],delta=.01)

    def test_sidebar_composite(self):
        for color in ('#822222','#ec1629','#56b2e0'):
            for bg in ('#2d2d2d','#ebebeb'):
                selected=mix(color,bg,.10)
                self.assertGreaterEqual(contrast(readable(color,selected),selected),4.5)


# Fixtures shared with the Windows build: Services/ArtAccent.cs produced these
# results for exactly these pixels (64×64 RGBA), so both platforms pick the
# same accent for the same artwork.
import colorsys,random
def accent_fixtures():
    out={}
    def make(name,fn):
        rnd=random.Random(name)
        px=[]
        for y in range(64):
            for x in range(64):
                px.extend(fn(x,y,rnd))
        out[name]=px
    def rgb(h,s,v):return [round(c*255) for c in colorsys.hsv_to_rgb(h,s,v)]
    make('red-poster',lambda x,y,r:rgb(0.99+r.uniform(-.01,.01),0.85,0.7+r.uniform(-.1,.1))+[255])
    make('dark-with-vivid-logo',lambda x,y,r:(rgb(0.55,0.9,0.95) if 20<x<44 and 26<y<38 else rgb(0.6,0.2,0.12+r.uniform(0,.05)))+[255])
    make('hazy-sky-orange-hero',lambda x,y,r:(rgb(0.07,0.9,0.9) if (x-32)**2+(y-48)**2<90 else rgb(0.58,0.18,0.85-y/200))+[255])
    make('greyscale',lambda x,y,r:[round((x+y)*2)]*3+[255])
    make('two-hue-split',lambda x,y,r:(rgb(0.33,0.8,0.7) if x<32 else rgb(0.8,0.7,0.65))+[255])
    make('cream-and-teal',lambda x,y,r:(rgb(0.12,0.12,0.94) if y<40 else rgb(0.48,0.75,0.6+r.uniform(-.05,.05)))+[255])
    make('transparent-edges',lambda x,y,r:(rgb(0.15,0.9,0.95)+[255]) if 16<x<48 and 16<y<48 else [0,0,0,0])
    make('noise',lambda x,y,r:[r.randrange(256),r.randrange(256),r.randrange(256),255])
    return out

WINDOWS_PICKS={
 "red-poster": {
  "signature": "#e04b49",
  "suggestions": [
   [
    "Signature",
    "#e04b49"
   ],
   [
    "Light",
    "#fdc9c4"
   ],
   [
    "Deep",
    "#bc262c"
   ]
  ]
 },
 "dark-with-vivid-logo": {
  "signature": "#18b1f2",
  "suggestions": [
   [
    "Signature",
    "#18b1f2"
   ],
   [
    "Background",
    "#7d8086"
   ],
   [
    "Light",
    "#aedffd"
   ],
   [
    "Deep",
    "#09729d"
   ]
  ]
 },
 "hazy-sky-orange-hero": {
  "signature": "#e66e17",
  "suggestions": [
   [
    "Signature",
    "#e66e17"
   ],
   [
    "Background",
    "#9dafbf"
   ],
   [
    "Light",
    "#ffcbaf"
   ],
   [
    "Deep",
    "#a54b05"
   ]
  ]
 },
 "greyscale": {
  "signature": None,
  "suggestions": [
   [
    "Background",
    "#808080"
   ]
  ]
 },
 "two-hue-split": {
  "signature": "#27b224",
  "suggestions": [
   [
    "Signature",
    "#27b224"
   ],
   [
    "Alternate",
    "#b558cd"
   ],
   [
    "Light",
    "#b1e9ac"
   ],
   [
    "Deep",
    "#058005"
   ]
  ]
 },
 "cream-and-teal": {
  "signature": "#279a8c",
  "suggestions": [
   [
    "Signature",
    "#279a8c"
   ],
   [
    "Background",
    "#e6dec9"
   ],
   [
    "Light",
    "#86eddd"
   ],
   [
    "Deep",
    "#0c796e"
   ]
  ]
 },
 "transparent-edges": {
  "signature": "#e2cd19",
  "suggestions": [
   [
    "Signature",
    "#e2cd19"
   ],
   [
    "Background",
    "#f2dc18"
   ],
   [
    "Light",
    "#e5da8c"
   ],
   [
    "Deep",
    "#766a06"
   ]
  ]
 },
 "noise": {
  "signature": "#4ce451",
  "suggestions": [
   [
    "Signature",
    "#4ce451"
   ],
   [
    "Background",
    "#83e75c"
   ],
   [
    "Alternate",
    "#c83fd1"
   ],
   [
    "Light",
    "#b0e9ad"
   ],
   [
    "Deep",
    "#097f17"
   ]
  ]
 }
}

class AccentTest(unittest.TestCase):
    def test_matches_windows_picks(self):
        from ui_colors import signature_color,accent_suggestions
        for name,px in accent_fixtures().items():
            rgba=[tuple(px[i:i+4]) for i in range(0,len(px),4)]
            with self.subTest(name):
                self.assertEqual(signature_color(rgba),WINDOWS_PICKS[name]['signature'])
                self.assertEqual([list(x) for x in accent_suggestions(rgba)],WINDOWS_PICKS[name]['suggestions'])
    def test_greyscale_has_no_signature(self):
        from ui_colors import signature_color
        self.assertIsNone(signature_color([(90,90,90,255)]*4096))
    def test_accents_stay_in_ui_range(self):
        from ui_colors import ui_accent,lch
        for lab in ((0.2,0.3,0.0),(0.99,0.01,0.01),(0.5,-0.2,0.2)):
            l,c,_h=lch(ui_accent(lab))
            self.assertTrue(0.6<=l<=0.86,(lab,l))
            self.assertLessEqual(c,0.245)

if __name__=='__main__':unittest.main()
