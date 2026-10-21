#!/usr/bin/env python3
"""Native GNOME poster library. All engine work is serialized off the GTK thread."""
from pathlib import Path
import sys,threading,time,traceback,argparse,datetime,colorsys
from collections import Counter
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
APP_VERSION=(ROOT/'VERSION').read_text(encoding='utf-8').strip() if (ROOT/'VERSION').exists() else 'dev'
import gi
gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
from gi.repository import Gtk,Adw,GLib,Gio,Gdk,Gsk,Graphene,Pango,GdkPixbuf,GObject
import ui,library_media,os,game_notes,ui_colors,user_messages,weakref,game_launch
from desktop_service import DesktopService
from package_browser import build_packages,show_packages
from native_shell import new_shell
from ui_scaling import ScaledContent, content_scale, SCALES
from operation_scope import operation_targets, ScopeError

ACCENT_PROVIDERS={}
ACCENT_SOURCES={}
NEUTRAL_PROVIDER=None
THEME_MODE='dark'
NATIVE_PALETTE={}
COUCH_MODE='auto'


def register_brand_font():
    # Register only for this process; do not install into the user's font folders.
    import ctypes,ctypes.util
    font=ROOT/'gui/fonts/BakbakOne-Regular.ttf'
    if not font.is_file():return False
    try:
        library=ctypes.CDLL(ctypes.util.find_library('fontconfig') or 'libfontconfig.so.1')
        library.FcConfigGetCurrent.restype=ctypes.c_void_p
        library.FcConfigAppFontAddFile.argtypes=[ctypes.c_void_p,ctypes.c_char_p]
        library.FcConfigAppFontAddFile.restype=ctypes.c_int
        return bool(library.FcConfigAppFontAddFile(library.FcConfigGetCurrent(),str(font).encode()))
    except (OSError,AttributeError):return False

register_brand_font()

BRAND_IMAGES=weakref.WeakSet()
BRAND_THEME_CONNECTED=False
BRAND_TEXTURES={}


def refresh_brand_icons(*_):
    name='io.github.lrnolivia.RTXForge'
    if not Adw.StyleManager.get_default().get_dark():name+='-light'
    path=ROOT/'gui/icons/rtxforge-mark.svg'
    if 'plain' not in BRAND_TEXTURES:BRAND_TEXTURES['plain']=Gdk.Texture.new_from_filename(str(path))
    for image in list(BRAND_IMAGES):image.set_from_paintable(BRAND_TEXTURES['plain'])
    Gtk.Window.set_default_icon_name(name)
    try:
        import desktop_install
        desktop_install.refresh_launcher_icon(Adw.StyleManager.get_default().get_dark())
    except (OSError,ValueError,RuntimeError):
        # A read-only/unregistered development environment has no shell icon to update.
        pass


def make_brand_icon(size):
    """Use approved matching assets and follow the effective native appearance."""
    global BRAND_THEME_CONNECTED
    if not BRAND_THEME_CONNECTED:
        Adw.StyleManager.get_default().connect('notify::dark',refresh_brand_icons)
        BRAND_THEME_CONNECTED=True
    image=Gtk.Image(pixel_size=size)
    BRAND_IMAGES.add(image)
    refresh_brand_icons()
    return image


def neutral_palette():
    dark=Adw.StyleManager.get_default().get_dark()
    if dark and THEME_MODE=='night':
        return dict(window='#080808',view='#000000',sidebar='#101010',card='#171717',fg='#e7e7e7',popover='#181818')
    if NATIVE_PALETTE:return dict(NATIVE_PALETTE)
    return dict(window='#242424' if dark else '#f5f5f5',
                view='#1e1e1e' if dark else '#fafafa',
                sidebar='#2d2d2d' if dark else '#ebebeb',
                card='#383838' if dark else '#ffffff',
                fg='#f2f2f2' if dark else '#222222',
                popover='#303030' if dark else '#ffffff')


def apply_neutral_palette():
    global NEUTRAL_PROVIDER
    if NEUTRAL_PROVIDER is None:
        NEUTRAL_PROVIDER=Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),NEUTRAL_PROVIDER,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+2)
    # Remove our previous Night definitions before reading native Adwaita roles.
    NEUTRAL_PROVIDER.load_from_data(b'')
    probe=Gtk.Label().get_style_context()
    for role in ('window','view','sidebar','card','popover'):
        found,color=probe.lookup_color(role+'_bg_color')
        if found:
            background=NATIVE_PALETTE.get('window','#242424')
            channels=(color.red,color.green,color.blue)
            NATIVE_PALETTE[role]='#'+''.join(f'{round(c*255*color.alpha+int(background[1+i*2:3+i*2],16)*(1-color.alpha)):02x}' for i,c in enumerate(channels))
    found,color=probe.lookup_color('window_fg_color')
    if found:NATIVE_PALETTE['fg']='#'+''.join(f'{round(c*255):02x}' for c in (color.red,color.green,color.blue))
    palette=neutral_palette()
    names={'window_bg_color':'window','view_bg_color':'view','sidebar_bg_color':'sidebar',
           'card_bg_color':'card','dialog_bg_color':'window','popover_bg_color':'popover',
           'window_fg_color':'fg','view_fg_color':'fg','sidebar_fg_color':'fg','card_fg_color':'fg','dialog_fg_color':'fg','popover_fg_color':'fg',
           'headerbar_bg_color':'window','headerbar_fg_color':'fg','headerbar_backdrop_color':'window',
           'secondary_sidebar_bg_color':'sidebar','secondary_sidebar_fg_color':'fg'}
    theme_css=''.join(f'@define-color {name} {palette[value]};' for name,value in names.items()) if THEME_MODE=='night' else ''
    if THEME_MODE!='night':theme_css+='columnview.library-column-view header { background: mix(@sidebar_bg_color,black,0.12); }'
    theme_css+='list.boxed-list, list.content, list.boxed-list-separate > row, .card { box-shadow: 0 0 0 1px alpha(black,0.03), 0 1px 3px 1px alpha(black,0.07), 0 2px 6px 2px alpha(black,0.03); }'
    theme_css+='\n    button.bulk-remove { border: 1px solid alpha(currentColor,0.18); }\n    .library-selection-tools button, button.view-action, \n    button.game-details, .library-column-actions button,\n    .progress-inline-cancel {\n        border: 1px solid alpha(@window_fg_color,0.035);\n    }\n    '
    if THEME_MODE=='night':
        theme_css+='@define-color forge_top_bg #000000; @define-color forge_lower_bg #181818; @define-color forge_library_card_a #222222; @define-color forge_library_card_b #262626; @define-color forge_panel_bg #171717;'
        theme_css+='''
        .bulk-remove { background: #352828; color: #ffaaa3; border: 1px solid alpha(#ffaaa3,0.18); }
        .bulk-remove:hover { background: #473030; }
        .library-selection-tools button, button.view-action, .control-pod button,
        .game-card:not(.selected) .game-details { background: #303030; border: 1px solid alpha(white,0.10); color: @window_fg_color; }
        .library-selection-tools button:hover, button.view-action:hover, .control-pod button:hover,
        .game-card:not(.selected) .game-details:hover { background: #3b3b3b; }
        '''
    elif Adw.StyleManager.get_default().get_dark():
        theme_css+='@define-color forge_library_card_a mix(@window_bg_color,@window_fg_color,0.06); @define-color forge_library_card_b mix(@window_bg_color,@window_fg_color,0.09); @define-color forge_panel_bg alpha(@window_fg_color,0.08); @define-color forge_library_list_hover mix(@window_bg_color,@window_fg_color,0.12);'
    else:
        theme_css+="""
        @define-color forge_lower_bg @window_bg_color;
        @define-color forge_library_card_a @card_bg_color;
        @define-color forge_library_card_b mix(@card_bg_color,@sidebar_bg_color,0.2);
        @define-color forge_library_card_hover #e2e2e2;
        @define-color forge_library_list_hover #e2e2e2;
        @define-color forge_panel_bg @card_bg_color;
        @define-color accent_color #437500;
        .game-card { box-shadow: 0 1px 3px alpha(black,0.06), 0 0 8px alpha(black,0.035); }
        .game-card .card-footer { background: alpha(black,0.025); }
        .game-card:not(.selected) .game-details { background: alpha(black,0.055); }
        .game-card:not(.selected) .game-details:hover { background: alpha(black,0.085); }
        .game-banner .game-banner-title { text-shadow: none; }
        .game-detail-meta, .game-detail-summary { color: #414141; text-shadow: none; }
        .library-test-pill.test-untested { background: #e6e6e6; color: #795000; }
        .library-test-pill.test-untested .library-pill-text,
        .library-test-pill.test-untested .library-pill-icon { color: #795000; }
        .library-test-pill.test-tested, .library-test-pill.pill-working { background: #dce9cf; color: #315b15; }
        .library-test-pill.test-tested .library-pill-text,
        .library-test-pill.test-tested .library-pill-icon { color: inherit; }
        .library-test-pill.pill-issue { background: #f1d8d5; color: #922d25; }
        .library-test-pill.pill-na { background: #dddddd; color: #4a4a4a; }
        .library-test-pill.pill-na .library-pill-icon, .library-test-pill.pill-na .library-pill-text { color: inherit; }
        list.boxed-list, list.content, list.boxed-list-separate > row, .card {
            box-shadow: 0 0 0 1px alpha(black,0.015), 0 1px 3px 1px alpha(black,0.035), 0 2px 6px 2px alpha(black,0.015);
        }
        floating-sheet > sheet { box-shadow: 0 0 14px 2px alpha(black,0.015), 0 0 5px 2px alpha(black,0.05), 0 0 0 1px alpha(black,0.025); }
        .operation-bubble { box-shadow: 0 5px 18px alpha(black,0.16); }
        .selection-count-pill { box-shadow: 0 1px 3px alpha(black,0.10); }
        .bulk-remove { color: #9b3028; }
        .library-list-chip.active, .library-list-status-dot.installed { color: #437500; }
        .operation-complete, .operation-bubble .operation-complete { color: #376b18; }
        .operation-bubble .operation-error { color: #a02d25; }
        .eyebrow { color: #437500; }
        .game-banner-title { text-shadow: none; }
        .done-title { color: #376b18; }
        .job-title { color: @window_fg_color; }
        .library-column-actions button:hover { background: #d4d4d4; color: #222222; }
        """
    theme_css+='''
    .linked button, spinbutton button, .control-pod spinbutton button { border-color: transparent; box-shadow: none; }
    button.view-action:checked { background: alpha(@window_fg_color,0.24); color: @window_fg_color; }
    .game-notes { border-radius: 12px; padding: 14px; background: @view_bg_color; border: 1px solid alpha(@window_fg_color,0.15); }
    .game-notes text { background: transparent; color: @window_fg_color; }
    .library-status-primary { background: alpha(black,0.16); padding: 0; border-radius: 99px; }
    '''
    if not Adw.StyleManager.get_default().get_dark():
        theme_css+='button.forge-primary, button.suggested-action { background: #deebc9; color: #345b00; } button.forge-primary label, button.suggested-action label, button.forge-primary image, button.suggested-action image { color: #345b00; }'
    NEUTRAL_PROVIDER.load_from_data(theme_css.encode())
    sources=list(ACCENT_SOURCES.values())
    for provider in ACCENT_PROVIDERS.values():
        Gtk.StyleContext.remove_provider_for_display(Gdk.Display.get_default(),provider)
    ACCENT_PROVIDERS.clear()
    for path,color in sources:artwork_accent(path,color)



def gamescope_session():
    """Return True for Steam Gaming Mode / gamescope-session."""

    if COUCH_MODE!='auto':return COUCH_MODE=='couch'
    desktop=' '.join(
        os.environ.get(key,'')
        for key in (
            'XDG_CURRENT_DESKTOP',
            'XDG_SESSION_DESKTOP',
            'DESKTOP_SESSION',
        )
    ).casefold()

    return (
        'gamescope' in desktop
        or os.environ.get('SteamGamepadUI','')=='1'
        or os.environ.get('STEAM_GAMEPADUI','')=='1'
    )


class GameModeChoice(Gtk.Box):
    """Popup-free replacement for Gtk.DropDown in Gamescope."""

    selected=GObject.Property(
        type=int,
        default=0,
    )

    def __init__(self,strings):
        super().__init__(
            spacing=0,
            valign=Gtk.Align.CENTER,
        )

        self.items=[
            str(item)
            for item in strings
        ]

        self.add_css_class(
            'linked'
        )

        previous=Gtk.Button(
            icon_name='go-previous-symbolic',
        )
        previous.set_tooltip_text(
            'Previous option'
        )

        self.value_label=Gtk.Label(
            xalign=0.5,
        )
        self.value_label.set_size_request(
            72,
            -1,
        )

        following=Gtk.Button(
            icon_name='go-next-symbolic',
        )
        following.set_tooltip_text(
            'Next option'
        )

        previous.connect(
            'clicked',
            lambda *_:self._move(-1),
        )

        following.connect(
            'clicked',
            lambda *_:self._move(1),
        )

        self.append(previous)
        self.append(self.value_label)
        self.append(following)

        self.connect(
            'notify::selected',
            lambda *_:self._sync(),
        )

        self._sync()

    def _sync(self):
        if not self.items:
            self.value_label.set_text('')
            return

        index=max(
            0,
            min(
                len(self.items)-1,
                int(self.props.selected),
            ),
        )

        self.value_label.set_text(
            self.items[index]
        )

    def _move(self,delta):
        if not self.items:
            return

        self.set_selected(
            (
                self.get_selected()+delta
            ) % len(self.items)
        )

    def get_selected(self):
        return int(
            self.props.selected
        )

    def set_selected(self,index):
        if not self.items:
            index=0
        else:
            index=max(
                0,
                min(
                    len(self.items)-1,
                    int(index),
                ),
            )

        if self.props.selected!=index:
            self.props.selected=index
        else:
            self._sync()


class GameModeComboRow(Adw.ActionRow):
    """Popup-free Adw.ComboRow equivalent for Gamescope."""

    selected=GObject.Property(type=int,default=0)

    def __init__(
        self,
        *,
        title,
        model,
        selected=0,
        **kwargs,
    ):
        super().__init__(
            title=title,
            **kwargs,
        )

        strings=[
            model.get_string(i)
            for i in range(
                model.get_n_items()
            )
        ]

        self.choice=GameModeChoice(
            strings
        )
        self.choice.set_selected(
            selected
        )
        self.choice.set_valign(
            Gtk.Align.CENTER
        )

        self.add_suffix(
            self.choice
        )
        self.props.selected=self.choice.get_selected()
        self.choice.connect('notify::selected',lambda *_:setattr(self.props,'selected',self.choice.get_selected()))
        self.connect('notify::selected',lambda *_:self.choice.set_selected(self.props.selected))

    def get_selected(self):
        return self.choice.get_selected()

    def set_selected(self,index):
        self.choice.set_selected(index)


def caution_image(size):
    # Safety warnings are bundled, independent of icon themes and optional action glyphs.
    pix=GdkPixbuf.Pixbuf.new_from_file_at_scale(str(Path(__file__).parent/'icons'/'rtxforge-caution.svg'),size,size,True)
    return Gtk.Image(paintable=Gdk.Texture.new_for_pixbuf(pix),pixel_size=size)

def safe_dropdown(strings):
    if gamescope_session():
        return GameModeChoice(strings)

    return Gtk.DropDown.new_from_strings(
        strings
    )


def safe_combo_row(**kwargs):
    if gamescope_session():
        return GameModeComboRow(
            **kwargs
        )

    return Adw.ComboRow(
        **kwargs
    )
def accent_source(game):
    """The artwork an accent is read from; the Windows build uses the same order."""
    return game.get('poster') or game.get('capsule') or game.get('hero')


def artwork_pixels(path,size=64):
    """RGBA samples of artwork scaled to size × size."""
    pix=GdkPixbuf.Pixbuf.new_from_file_at_scale(path,size,size,False)
    if not pix.get_has_alpha():pix=pix.add_alpha(False,0,0,0)
    data=pix.get_pixels();stride=pix.get_rowstride()
    return [tuple(data[y*stride+x*4:y*stride+x*4+4]) for y in range(pix.get_height()) for x in range(pix.get_width())]


SIGNATURES={}


def artwork_signature(path):
    """Cached signature accent of an artwork file (None for greyscale art)."""
    try:key=(str(path),os.stat(path).st_mtime_ns)
    except OSError:key=(str(path),None)
    if key not in SIGNATURES:SIGNATURES[key]=ui_colors.signature_color(artwork_pixels(path))
    return SIGNATURES[key]


def artwork_accent(path,color=None,muted=False):
    # A custom accent always wins; otherwise the artwork's signature color,
    # chosen perceptually (OKLab), or a light neutral for greyscale art.
    color=color or artwork_signature(path) or ui_colors.NO_ARTWORK

    if muted:
        rgb=[int(color[i:i+2],16)/255 for i in (1,3,5)]
        h,s,v=colorsys.rgb_to_hsv(*rgb)
        color='#%02x%02x%02x'%tuple(round(c*255) for c in colorsys.hsv_to_rgb(h,s*0.1,v))

    try:
        raw=color.lstrip('#')

        cr=int(raw[0:2],16)/255
        cg=int(raw[2:4],16)/255
        cb=int(raw[4:6],16)/255

        fh,fs,fv=colorsys.rgb_to_hsv(
            cr,
            cg,
            cb,
        )

        luminance=(
            0.2126*cr
            + 0.7152*cg
            + 0.0722*cb
        )

        if luminance>=0.48:
            fr,fg,fb=colorsys.hsv_to_rgb(
                fh,
                max(
                    0.55,
                    min(
                        1.0,
                        fs*1.05,
                    ),
                ),
                0.20,
            )

            accent_fg='#%02x%02x%02x'%(
                round(fr*255),
                round(fg*255),
                round(fb*255),
            )
        else:
            accent_fg='#ffffff'

        # Selected card controls/checkmarks always use a darker version
        # of the SAME game hue, never plain white.
        dr,dg,db=colorsys.hsv_to_rgb(
            fh,
            max(
                0.78,
                min(
                    1.0,
                    fs*1.12,
                ),
            ),
            max(
                0.20,
                min(
                    0.34,
                    fv*0.42,
                ),
            ),
        )

        if fs < 0.08:
            # Achromatic accents have no meaningful hue: keep contrast neutral.
            fr=fg=fb=0.20
            accent_fg='#333333' if luminance>=0.48 else '#ffffff'
            dr=dg=db=min(0.34,max(0.20,fv*0.42))

        accent_dark='#%02x%02x%02x'%(
            round(dr*255),
            round(dg*255),
            round(db*255),
        )

    except Exception:
        accent_fg='#ffffff'
        accent_dark='#181818'

    palette=neutral_palette()
    nav_accent=ui_colors.readable(color,ui_colors.mix(color,palette['sidebar'],0.10))
    accent_shadow=accent_dark
    accent_fg=ui_colors.readable(accent_fg,color)
    accent_dark=ui_colors.readable(accent_dark,color)
    button_fg=ui_colors.readable(accent_dark,ui_colors.mix('#ffffff',color,0.44))
    selected_title=ui_colors.mix('#ffffff',color,0.88) if sum(int(accent_dark[i:i+2],16) for i in (1,3,5))>600 else accent_dark
    source_bg=ui_colors.mix('#ffffff',color,0.26)
    source_fg=ui_colors.readable(accent_shadow,source_bg)
    hero_accent=ui_colors.vibrant_readable(color,palette['window'],3.0)

    name='art-'+color[1:]

    ACCENT_SOURCES[name]=(path,color)
    if name not in ACCENT_PROVIDERS:
        provider=Gtk.CssProvider()

        provider.load_from_data((
            f'.review-game.{name} .review-bezel {{ border-color: {color}; }} '
            f'.artwork-editor.{name} .artwork-preview {{ border-color: {color}; }} '
            f'.review-game.{name} .review-badge {{ color: {ui_colors.readable(color,palette["card"])}; background: {ui_colors.mix(color,palette["card"],0.10)}; }} '
            f'columnview row.{name}.game-selected {{ background: {color}; color: {accent_dark}; }} '
            f'columnview row.{name}.game-selected label, columnview row.{name}.game-selected .library-pill-icon {{ color: {accent_dark}; }} '
            f'columnview row.{name}.game-selected .library-source-pill {{ background: {source_bg}; }} '
            f'columnview row.{name}.game-selected .library-test-pill, columnview row.{name}.game-selected .library-list-chip {{ background: alpha(black,0.16); color: {accent_dark}; border-color: transparent; }} '
            f'columnview row.{name}.game-selected .library-list-status-dot.installed {{ color: #76b900; }} '
            f'columnview row.{name}.game-selected .library-list-status-dot.available {{ color: #ff928c; }} '
            f'columnview row.{name} check:checked {{ background: alpha(white,0.72); color: {ui_colors.readable(color,ui_colors.mix("#ffffff",color,0.72))}; border-color: transparent; }} '
            # Poster / Wide Capsule selection border.
            f'.game-card.{name}.selected {{ '
            f'background: {color}; '
            f'border-color: transparent; '
            f'box-shadow: none; '
            f'}} '

            f'.game-card.{name}.selected .library-source-pill {{ background: {source_bg}; color: {source_fg}; }} '
            f'.game-card.{name}.selected .library-source-pill .library-pill-icon, '
            f'.game-card.{name}.selected .library-source-pill .library-pill-text {{ color: {source_fg}; }} '

            f'.game-card.{name}.selected .library-test-pill {{ '
            f'background: alpha({accent_shadow},0.94); '
            f'border-color: transparent; '
            f'box-shadow: none; '
            f'color: white; '
            f'}} '

            f'.game-card.{name}.selected .library-test-pill .library-pill-text, '
            f'.game-card.{name}.selected .library-test-pill .library-pill-icon {{ '
            f'color: white; '
            f'}} '

            f'.game-card.{name}:hover .gallery-artwork-ring, '
            f'.game-card.{name}:focus-within .gallery-artwork-ring, '
            f'.game-card.{name}.selected .gallery-artwork-ring {{ '
            f'border-color: {color}; '
            f'}} '

            # Gtk.ColumnView: accent stays inside the Game and
            # Actions cells. The row itself never gets an accent border.
            f'.library-column-game.{name} '
            f'.library-column-art.selected-art {{ '
            f'border-color: {color}; '
            f'box-shadow: none; '
            f'}} '

            f'.library-column-game.{name}:hover '
            f'.library-column-art {{ '
            f'border-color: alpha({color},0.68); '
            f'}} '

            f'.library-column-actions.{name}.selected-actions button {{ '
            f'background: {color}; '
            f'color: {accent_dark}; '
            f'border-color: transparent; '
            f'box-shadow: none; '
            f'}} '

            f'.library-column-actions.{name}.selected-actions button label, '
            f'.library-column-actions.{name}.selected-actions button image {{ '
            f'color: {accent_dark}; '
            f'}} '

            # Checked indicators use accent background + dark same-hue glyph.
            f'.{name} check:checked {{ '
            f'background: {color}; '
            f'color: {accent_dark}; '
            f'border-color: {color}; '
            f'}} '

            # Poster / Wide Capsule Details button is neutral at rest;
            # it becomes accent-filled only while the card is selected.
            f'.game-card.{name}.selected .gallery-artwork-frame {{ background: alpha(white,0.44); }} '
            f'.game-card.{name}.selected .game-details {{ '
            f'background: alpha(white,0.44); '
            f'color: {button_fg}; '
            f'border-color: transparent; '
            f'box-shadow: none; '
            f'}} '

            f'.game-card.{name}.selected .game-details label {{ '
            f'color: {button_fg}; '
            f'font-weight: 700; '
            f'}} '

            f'.game-card.{name}:hover .card-title {{ '
            f'color: {ui_colors.readable(ui_colors.mix("#ffffff",color,0.78),palette["card"])}; '
            f'}} '

            f'.game-card.{name}.selected .card-title, '
            f'.game-card.{name}.selected:hover .card-title {{ '
            f'color: {selected_title}; '
            f'}} '

            f'columnview.library-column-view row:not(.game-selected):hover '
            f'.library-column-game.{name} .library-column-title {{ '
            f'color: {ui_colors.readable(color,palette["card"])}; '
            f'}} '

            f'columnview.library-column-view row.{name}.game-selected .library-column-title, '
            f'columnview.library-column-view row.{name}.game-selected:hover .library-column-game.{name} .library-column-title {{ '
            f'color: {accent_dark}; '
            f'}} '

            # Game Detail window keeps its accent semantics.
            f'.{name} toggle-group toggle:checked {{ '
            f'background: {color}; '
            f'color: {accent_fg}; '
            f'}} '

            f'.{name} toggle-group toggle:checked label {{ '
            f'color: {accent_fg}; '
            f'}} '

            f'.{name} .game-detail-main button.suggested-action {{ '
            f'background: {color}; '
            f'color: {accent_fg}; '
            f'}} '

            f'.{name} .game-detail-main button.suggested-action label {{ '
            f'color: {accent_fg}; '
            f'}} '

            f'.{name} .game-detail-nav row:selected {{ '
            f'background: alpha({color},0.10); '
            f'}} '

            f'.{name} .game-detail-nav row:selected label, '
            f'.{name} .game-detail-nav row:selected image {{ '
            f'color: {nav_accent}; '
            f'}} '

            f'.{name} progressbar progress {{ '
            f'background: {color}; '
            f'}} '

            f'.{name} .progress-poster-frame {{ '
            f'border-color: {color}; '
            f'}} '

            f'.{name} scale highlight {{ '
            f'background: {color}; '
            f'}} '

            # Detail/progress identity remains accent colored.
            # Library titles are neutral until hover; selected gallery
            # cards use the darker same-hue foreground above.
            f'.{name} .game-banner-title {{ color: {hero_accent}; }} '

            f'.{name} .job-title, '
            f'.{name} .eyebrow {{ '
            f'color: {color}; '
            f'}} '

            # The operation dialog's primary button follows the current game.
            f'.operation-flow.{name} headerbar button.suggested-action {{ '
            f'background: {color}; '
            f'color: {accent_fg}; '
            f'}} '

            f'.{name} button:focus-visible {{ '
            f'outline-color: {color}; '
            f'}}'
        ).encode())

        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+1,
        )

        ACCENT_PROVIDERS[
            name
        ]=provider

    return name


def hero_title_background_is_light(path):
    """Estimate brightness beneath the lower-left game title area."""
    try:
        pix=GdkPixbuf.Pixbuf.new_from_file_at_scale(
            str(path),
            32,
            18,
            False,
        )

        data=pix.get_pixels()
        stride=pix.get_rowstride()
        channels=pix.get_n_channels()

        # Lower-left region, roughly where the game title lives.
        x0=0
        x1=max(1,int(pix.get_width()*0.48))
        y0=max(0,int(pix.get_height()*0.55))
        y1=pix.get_height()

        total=0.0
        count=0

        for y in range(y0,y1):
            for x in range(x0,x1):
                off=y*stride+x*channels

                r=data[off]
                g=data[off+1]
                b=data[off+2]

                # Perceived luminance rather than raw RGB average.
                total += (
                    0.2126*r +
                    0.7152*g +
                    0.0722*b
                )

                count += 1

        return bool(count and total/count >= 150)

    except Exception:
        return False


CORNER_STYLE='system'
CORNER_PROVIDER=None

def apply_corner_style(value):
    global CORNER_STYLE,CORNER_PROVIDER
    CORNER_STYLE=value if value in ('system','rounded','square') else 'system'
    if CORNER_PROVIDER is None:
        CORNER_PROVIDER=Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),CORNER_PROVIDER,Gtk.STYLE_PROVIDER_PRIORITY_USER)
    css='* { border-radius: 0; border-top-left-radius: 0; border-top-right-radius: 0; border-bottom-left-radius: 0; border-bottom-right-radius: 0; } window, dialog { --window-radius: 0px; --dialog-radius: 0px; }' if CORNER_STYLE=='square' else ''
    if CORNER_STYLE=='rounded':css='window.background { border-radius: 12px; }'
    # Game Mode navigation remains a pill, including with square cards.
    css+=' .couch-tabs, .couch-tabs .couch-tab { border-radius: 999px; border-top-left-radius: 999px; border-top-right-radius: 999px; border-bottom-left-radius: 999px; border-bottom-right-radius: 999px; }'
    CORNER_PROVIDER.load_from_data(css.encode())


class ArtworkButton(Gtk.Button):
    """Keep button input/accessibility without painting a second artwork frame."""
    def do_snapshot(self,snapshot):
        child=self.get_child()
        if child is not None:
            # The image must never occupy the frame's three-pixel band.
            # CSS borders alone paint over an already rounded image and leave
            # its antialiased edge visible through the surrounding surface.
            bounds=Graphene.Rect().init(3,3,max(0,self.get_width()-6),max(0,self.get_height()-6))
            clip=Gsk.RoundedRect()
            clip.init_from_rect(bounds,0.0 if CORNER_STYLE=="square" else 11.0)
            snapshot.push_rounded_clip(clip)
            self.snapshot_child(child,snapshot)
            snapshot.pop()


class CoverPicture(Gtk.Picture):
    # The gallery solver owns width; ignore unbounded GTK measurement probes.
    cover_width=158
    cover_ratio=2/3
    def do_get_request_mode(self):return Gtk.SizeRequestMode.CONSTANT_SIZE
    def do_measure(self, orientation, for_size):
        if orientation==Gtk.Orientation.HORIZONTAL:return (self.cover_width,self.cover_width,-1,-1)
        height=__import__('math').ceil(self.cover_width/self.cover_ratio)
        return (height,height,-1,-1)

# Final frozen Library geometry.
#
# Every List row uses exactly the same art allocation.
# Every source/test pill uses exactly the same geometry.
LIST_ART_WIDTH=96
LIST_ART_HEIGHT=45
LIST_ART_FRAME_WIDTH=100
LIST_ART_FRAME_HEIGHT=49

LIBRARY_PILL_WIDTH=78
LIBRARY_PILL_HEIGHT=20
LIBRARY_PILL_ICON_SIZE=13
LIBRARY_PILL_HPAD_START=9
LIBRARY_PILL_HPAD_END=8
LIBRARY_PILL_VPAD=4
LIBRARY_PILL_GAP=4
LIBRARY_LIST_STATUS_WIDTH=108
LIBRARY_BOTTOM_CLEARANCE=16
LIBRARY_STEAM_ICON=ROOT/'gui/icons/rtxforge-steam.svg'
LIBRARY_GHOST_TEXTURE=ROOT/'gui/icons/rtxforge-transparent-capsule.png'


def _library_icon_name(*candidates):
    display=Gdk.Display.get_default()

    if display is not None:
        try:
            theme=Gtk.IconTheme.get_for_display(
                display
            )

            for candidate in candidates:
                if (
                    candidate
                    and theme.has_icon(
                        candidate
                    )
                ):
                    return candidate
        except Exception:
            pass

    return candidates[-1]


def library_display_test_status(game):
    if (
        not game.get('installed')
        or game.get('blocked')
    ):
        return 'N/A'

    status=str(
        game.get(
            'test_record',
            {},
        ).get(
            'status',
            'Untested',
        )
    ).strip()

    # Bench is not a meaningful Library-facing status.
    if status.casefold()=='bench':
        return 'N/A'

    return status


class LibraryPill(Gtk.Box):
    """One exact source/test pill geometry everywhere."""

    def __init__(
        self,
        kind='source',
    ):
        super().__init__(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=0,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
            hexpand=False,
            vexpand=False,
        )

        self.kind=kind
        self._fixed_width=LIBRARY_PILL_WIDTH

        self.add_css_class(
            'library-meta-pill'
        )

        content=Gtk.Box(
            spacing=LIBRARY_PILL_GAP,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
            hexpand=True,
        )

        content.set_margin_start(
            LIBRARY_PILL_HPAD_START
        )
        content.set_margin_end(
            LIBRARY_PILL_HPAD_END
        )
        content.set_margin_top(
            LIBRARY_PILL_VPAD
        )
        content.set_margin_bottom(
            LIBRARY_PILL_VPAD
        )

        self._icon=Gtk.Image()
        self._icon.set_pixel_size(
            LIBRARY_PILL_ICON_SIZE
        )
        self._icon.set_halign(
            Gtk.Align.START
        )
        self._icon.set_valign(
            Gtk.Align.CENTER
        )
        self._icon.add_css_class(
            'library-pill-icon'
        )

        self._label=Gtk.Label(
            label='',
            xalign=0.0,
            single_line_mode=True,
            ellipsize=Pango.EllipsizeMode.NONE,
        )
        self._label.set_halign(
            Gtk.Align.START
        )
        self._label.set_valign(
            Gtk.Align.CENTER
        )
        self._label.set_hexpand(
            True
        )
        self._label.add_css_class(
            'library-pill-text'
        )

        content.append(
            self._icon
        )
        content.append(
            self._label
        )
        # Tiny OS mark: which rtxForge (Linux or Windows) installed the features.
        self._os=Gtk.Image(pixel_size=10,visible=False,valign=Gtk.Align.CENTER)
        self._os.add_css_class('library-pill-os')
        content.append(self._os)

        self._content=content
        self.append(
            content
        )

    def do_get_request_mode(self):
        return Gtk.SizeRequestMode.CONSTANT_SIZE

    def do_measure(
        self,
        orientation,
        for_size,
    ):
        size=(
            self._fixed_width
            if orientation==Gtk.Orientation.HORIZONTAL
            else LIBRARY_PILL_HEIGHT
        )

        return (
            size,
            size,
            -1,
            -1,
        )

    def set_fixed_width(self,width):
        self._fixed_width=max(
            1,
            int(width),
        )

        self.queue_resize()


    def set_os(self,name):
        """Show the tiny Linux or Windows mark (None hides it)."""
        self._os.set_visible(name in ('linux','windows'))
        if name in ('linux','windows'):
            self._os.set_from_icon_name('rtx-os-'+name+'-symbolic')
            self._os.set_tooltip_text('Installed with rtxForge on '+('Linux' if name=='linux' else 'Windows'))

    def _update_icon(self,text):
        value=str(
            text or ''
        ).strip().casefold()
        if self.kind=='state':
            icon={'installed':'object-select-symbolic','unsupported':'dialog-warning-symbolic'}.get(value,'folder-download-symbolic')
            self._icon.set_from_icon_name(icon)
            return
        if self.kind=='source':
            if (
                value=='steam'
                and LIBRARY_STEAM_ICON.exists()
            ):
                try:
                    self._icon.set_pixel_size(11)
                    self._icon.set_from_icon_name('rtx-steam-symbolic')

                    return

                except Exception:
                    pass

            if value in ('linux','windows'):
                self._icon.set_pixel_size(10)
                self._icon.set_from_icon_name('rtx-os-'+value+'-symbolic')
                return
            if value=='steam':
                icon=_library_icon_name(
                    'steam-symbolic',
                    'com.valvesoftware.Steam-symbolic',
                    'applications-games-symbolic',
                )
            else:
                icon=_library_icon_name(
                    'rtx-controller-symbolic',
                    'applications-games-symbolic',
                )

        else:
            if value=='working':
                icon=_library_icon_name(
                    'object-select-symbolic',
                    'object-select-symbolic',
                )

            elif value=='untested':
                icon=_library_icon_name(
                    'applications-science-symbolic',
                    'science-symbolic',
                    'applications-games-symbolic',
                )

            elif value in (
                'problem',
                'issue',
            ):
                icon=_library_icon_name(
                    'alarm-symbolic',
                    'dialog-error-symbolic',
                    'dialog-warning-symbolic',
                )

            elif value in (
                'bench',
                'n/a',
            ):
                icon=_library_icon_name(
                    'list-remove-symbolic',
                    'window-minimize-symbolic',
                )

            else:
                icon=_library_icon_name(
                    'list-remove-symbolic',
                    'window-minimize-symbolic',
                )

        self._icon.set_from_icon_name(
            icon
        )


    def set_text(self,text):
        raw=str(
            text or ''
        )

        value=raw.strip().casefold()

        self._update_icon(
            raw
        )

        if self.kind=='source':
            display={
                'steam':'STEAM',
                'non-steam':'OTHER',
                'non steam':'OTHER',
                'nonsteam':'OTHER',
            }.get(
                value,
                raw.upper(),
            )

        else:
            display={
                'working':'WORKS',
                'untested':'UNTESTED',
                'problem':'ISSUE',
                'issue':'ISSUE',
                'bench':'N/A',
                'n/a':'N/A',
            }.get(
                value,
                raw.upper(),
            )

            for css_class in (
                'pill-working',
                'pill-untested',
                'pill-issue',
                'pill-bench',
                'pill-na',
            ):
                self.remove_css_class(
                    css_class
                )

            state_class={
                'working':'pill-working',
                'untested':'pill-untested',
                'problem':'pill-issue',
                'issue':'pill-issue',
                'bench':'pill-na',
                'n/a':'pill-na',
            }.get(
                value
            )

            if state_class:
                self.add_css_class(
                    state_class
                )

        self._label.set_text(
            display
        )

    def set_label(self,text):
        self.set_text(
            text
        )

    def get_text(self):
        return self._label.get_text()

    # Compatibility with the Gtk.Label configuration currently used
    # by the frozen Library code. Geometry remains owned HERE.
    def set_wrap(self,value):
        self._label.set_wrap(
            bool(value)
        )

    def set_lines(self,value):
        self._label.set_lines(
            int(value)
        )

    def set_single_line_mode(self,value):
        self._label.set_single_line_mode(
            bool(value)
        )

    def set_ellipsize(self,value):
        # Library pills use deliberately short display labels.
        # Never sacrifice them to ellipsis.
        self._label.set_ellipsize(
            Pango.EllipsizeMode.NONE
        )

    def set_xalign(self,value):
        # Pills are intentionally always left aligned.
        self._label.set_xalign(
            0.0
        )

    def set_width_chars(self,value):
        # Fixed outer measurement owns width.
        return

    def set_max_width_chars(self,value):
        # Fixed outer measurement owns width.
        return


def poster_art_path(game):
    """Never crop a hero or capsule into a poster slot."""
    path=game.get('poster')
    if not path or not Path(path).is_file():return None
    if path in (game.get('hero'),game.get('capsule')):return None
    try:
        _,width,height=GdkPixbuf.Pixbuf.get_file_info(str(path))
        if not height or not 0.45<=width/height<=0.85:return None
    except Exception:return None
    return path

def capsule_art_path(game):
    """A capsule slot accepts only capsule artwork, never another art role."""
    path=game.get('capsule')
    if not path or not Path(path).is_file():return None
    if path in (game.get('hero'),game.get('poster')):return None
    try:
        _,width,height=GdkPixbuf.Pixbuf.get_file_info(str(path))
        if not height or not 1.6<=width/height<=2.6:return None
    except Exception:return None
    return path

class FixedArtworkPicture(Gtk.Picture):
    def __init__(self,width,height):
        self.art_width=width;self.art_height=height
        super().__init__(content_fit=Gtk.ContentFit.COVER,can_shrink=True)
    def do_get_request_mode(self):return Gtk.SizeRequestMode.CONSTANT_SIZE
    def do_measure(self,orientation,for_size):
        size=self.art_width if orientation==Gtk.Orientation.HORIZONTAL else self.art_height
        return size,size,-1,-1

class ListArtworkPicture(Gtk.Picture):
    """List thumbnails have constant geometry, independent of column allocation."""
    def do_get_request_mode(self):
        return Gtk.SizeRequestMode.CONSTANT_SIZE

    def do_measure(self,orientation,for_size):
        size=LIST_ART_WIDTH if orientation==Gtk.Orientation.HORIZONTAL else LIST_ART_HEIGHT
        return size,size,-1,-1


class ListArtwork(Gtk.Overlay):
    """Single authoritative List artwork widget."""

    def __init__(self):
        super().__init__(
            width_request=LIST_ART_FRAME_WIDTH,
            height_request=LIST_ART_FRAME_HEIGHT,
        )

        self.add_css_class(
            'library-column-art'
        )
        self.add_css_class(
            'list-artwork'
        )

        self.set_size_request(
            LIST_ART_FRAME_WIDTH,
            LIST_ART_FRAME_HEIGHT,
        )
        self.set_halign(
            Gtk.Align.CENTER
        )
        self.set_valign(
            Gtk.Align.CENTER
        )
        self.set_hexpand(
            False
        )
        self.set_vexpand(
            False
        )
        self.set_overflow(
            Gtk.Overflow.HIDDEN
        )

        self.picture=ListArtworkPicture(
            content_fit=Gtk.ContentFit.COVER,
            can_shrink=True,
        )
        self.picture.add_css_class(
            'list-artwork-picture'
        )
        self.picture.set_size_request(
            LIST_ART_WIDTH,
            LIST_ART_HEIGHT,
        )
        self.picture.set_halign(
            Gtk.Align.CENTER
        )
        self.picture.set_valign(
            Gtk.Align.CENTER
        )
        self.picture.set_hexpand(
            False
        )
        self.picture.set_vexpand(
            False
        )
        self.picture.set_overflow(
            Gtk.Overflow.HIDDEN
        )

        self.button=Gtk.Button(
            child=self.picture
        )
        self.button.add_css_class(
            'flat'
        )
        self.button.add_css_class(
            'list-artwork-button'
        )
        self.button.set_has_frame(
            False
        )
        self.button.set_size_request(
            LIST_ART_WIDTH,
            LIST_ART_HEIGHT,
        )
        self.button.set_halign(
            Gtk.Align.CENTER
        )
        self.button.set_valign(
            Gtk.Align.CENTER
        )
        self.button.set_hexpand(
            False
        )
        self.button.set_vexpand(
            False
        )
        self.button.set_overflow(
            Gtk.Overflow.HIDDEN
        )

        self.set_child(
            self.button
        )

        self.fallback=Gtk.CenterBox(
            width_request=LIST_ART_WIDTH,
            height_request=LIST_ART_HEIGHT,
            hexpand=False,
            vexpand=False,
        )
        self.fallback.add_css_class(
            'list-artwork-fallback'
        )
        self.fallback.set_size_request(
            LIST_ART_WIDTH,
            LIST_ART_HEIGHT,
        )
        self.fallback.set_halign(
            Gtk.Align.CENTER
        )
        self.fallback.set_valign(
            Gtk.Align.CENTER
        )

        self.ghost_icon=Gtk.Image.new_from_icon_name(
            'applications-games-symbolic'
        )
        self.ghost_icon.set_pixel_size(
            18
        )
        self.ghost_icon.add_css_class(
            'library-ghost-icon'
        )

        self.fallback.set_center_widget(
            self.ghost_icon
        )

        self.add_overlay(
            self.fallback
        )
        self.set_measure_overlay(
            self.fallback,
            False,
        )

        self.set_artwork(
            None
        )


    def do_get_request_mode(self):
        return Gtk.SizeRequestMode.CONSTANT_SIZE


    def do_measure(
        self,
        orientation,
        for_size,
    ):
        size=(
            LIST_ART_FRAME_WIDTH
            if orientation==Gtk.Orientation.HORIZONTAL
            else LIST_ART_FRAME_HEIGHT
        )

        return (
            size,
            size,
            -1,
            -1,
        )


    def set_artwork(self,path):
        missing=True
        texture=None

        if path:
            try:
                texture=Gdk.Texture.new_from_filename(
                    str(path)
                )
                missing=False
            except Exception:
                texture=None

        if texture is None:
            try:
                texture=Gdk.Texture.new_from_filename(
                    str(
                        LIBRARY_GHOST_TEXTURE
                    )
                )
            except Exception:
                texture=None

        self.picture.set_paintable(
            texture
        )

        self.fallback.set_visible(
            missing
        )


    def set_selected(self,selected):
        if selected:
            self.add_css_class(
                'selected-art'
            )
        else:
            self.remove_css_class(
                'selected-art'
            )


class FixedLibraryCard(Gtk.Box):
    fixed_width=1
    fixed_height=1

    def do_get_request_mode(self):
        return Gtk.SizeRequestMode.CONSTANT_SIZE

    def do_measure(self,orientation,for_size):
        size=(
            max(1,int(self.fixed_width))
            if orientation==Gtk.Orientation.HORIZONTAL
            else max(1,int(self.fixed_height))
        )

        return (
            size,
            size,
            -1,
            -1,
        )


class SoftBackdropPicture(Gtk.Picture):
    def do_snapshot(self,snapshot):
        snapshot.push_blur(5.0)
        Gtk.Picture.do_snapshot(self,snapshot)
        snapshot.pop()
        grain=Gdk.RGBA();grain.parse('rgba(255,255,255,0.025)')
        width=self.get_width();height=self.get_height()
        for index in range(400):
            x=(index*73+19)%max(1,width);y=(index*137+11)%max(1,height)
            snapshot.append_color(grain,Graphene.Rect().init(x,y,1,1))

class HeroPicture(Gtk.Picture):
    def do_snapshot(self,snapshot):
        Gtk.Picture.do_snapshot(self,snapshot)
        height=self.get_height();width=self.get_width()
        for band in range(16):
            fraction=(band+1)/16
            rect=Graphene.Rect().init(0,height*(0.35+0.65*band/16),width,height*0.65/16+0.5)
            snapshot.push_clip(rect)
            snapshot.push_opacity(fraction*0.85)
            snapshot.push_blur(fraction*8)
            Gtk.Picture.do_snapshot(self,snapshot)
            snapshot.pop();snapshot.pop();snapshot.pop()

    # The Game Details hero must crop as the window changes width,
    # not grow vertically with the artwork's aspect ratio.
    hero_height=280

    def do_get_request_mode(self):
        return Gtk.SizeRequestMode.CONSTANT_SIZE

    def do_measure(self,orientation,for_size):
        if orientation==Gtk.Orientation.HORIZONTAL:
            return (0,0,-1,-1)

        height=max(
            1,
            int(self.hero_height),
        )

        return (
            height,
            height,
            -1,
            -1,
        )


class BlurredTexture(Gtk.Widget):
    """Render a frozen Gdk.Texture through GTK/GSK blur."""
    def __init__(self,texture=None,radius=22.0):
        super().__init__(hexpand=True,vexpand=True)
        self.texture=texture
        self.radius=radius

    def set_texture(self,texture):
        self.texture=texture
        self.queue_draw()

    def do_snapshot(self,snapshot):
        texture=self.texture
        if texture is None:
            return

        width=max(1,self.get_width())
        height=max(1,self.get_height())

        tw=max(1,texture.get_width())
        th=max(1,texture.get_height())

        # Cover the available area while maintaining aspect ratio.
        scale=max(width/tw,height/th)
        draw_w=tw*scale
        draw_h=th*scale
        x=(width-draw_w)/2
        y=(height-draw_h)/2

        rect=Graphene.Rect()
        rect.init(x,y,draw_w,draw_h)

        snapshot.push_blur(self.radius)
        snapshot.append_texture(texture,rect)
        snapshot.pop()

CSS=b'''
@define-color accent_bg_color #76b900;
@define-color accent_color #95cf38;
@define-color accent_fg_color #102000;
.dim-label { opacity: 0.78; }
.operation-complete { color: #76b900; }

/*
 * Use libadwaita's native Nautilus-style surface hierarchy.
 *
 * view:
 *   light #ffffff
 *   dark  #1e1e1e
 *
 * sidebar:
 *   light #ececec
 *   dark  #2f2f2f
 *
 * Panels use the native foreground color translucently so they retain
 * clear separation in both appearances without introducing another
 * custom gray family.
 */
@define-color forge_top_bg @view_bg_color;
@define-color forge_lower_bg @window_bg_color;
@define-color forge_panel_bg alpha(@window_fg_color,0.12);
@define-color forge_library_card_a mix(@forge_lower_bg,@window_fg_color,0.08);
@define-color forge_library_card_b mix(@forge_lower_bg,@window_fg_color,0.13);
@define-color forge_library_card_hover mix(@forge_lower_bg,black,0.18);
@define-color forge_library_list_hover mix(@forge_lower_bg,@window_fg_color,0.18);


.forge-window-surface,
.forge-top-surface {
    background: @forge_top_bg;
}

.forge-library-surface {
    background: @forge_lower_bg;
}
.library-bottom-fade, .settings-bottom-fade { border: none; box-shadow: none; }
scrolledwindow undershoot, scrolledwindow overshoot { background: none; border: none; box-shadow: none; }
.library-bottom-fade {
    background-image: linear-gradient(to bottom, alpha(@forge_lower_bg,0), @forge_lower_bg 90%, @forge_lower_bg);
}
.settings-bottom-fade {
    background-image: linear-gradient(to bottom, alpha(@window_bg_color,0), @window_bg_color 90%, @window_bg_color);
}


.library-sticky-header.stuck {
    border-width: 0;
    border-style: none;
    box-shadow: none;
}


.library-sticky-header .view-action {
    min-width: 28px;
    padding: 4px 7px;
}


.library-sticky-header .library-filter-group button {
    padding: 4px 16px;
}

spinbutton.tuning-number-input text {
    padding-left: 10px;
    padding-right: 4px;
}


.library-sticky-header scale {
    padding: 0 2px;
}

/*
 * Compact dashboard state.
 *
 * This lives inside the native titlebar that already exists, so the
 * sticky state gains useful dashboard controls without adding another
 * vertical row.
 */

.sticky-dashboard-brand {
    margin-right: 2px;
}

.sticky-dashboard-app-icon {
    margin-right: 1px;
}

.sticky-dashboard-title {
    font-family: "Bakbak One";
    font-size: 14px;
    font-weight: 700;
    letter-spacing: -0.2px;
}

.sticky-mode-selector {
    padding: 2px;
    border-radius: 9px;
    background: alpha(@window_fg_color,0.07);
}

.sticky-mode-selector toggle {
    min-height: 24px;
    padding: 6px 14px;
    border-radius: 7px;
    background: transparent;
    border-color: transparent;
}

.sticky-mode-selector toggle:hover {
    background: alpha(@window_fg_color,0.06);
}

.sticky-mode-selector toggle:checked {
    background: alpha(@window_fg_color,0.12);
}

.sticky-mode-selector toggle label {
    font-size: 11px;
    font-weight: 600;
}

.sticky-dashboard-actions {
    margin-left: 1px;
}

.sticky-dashboard-actions button {
    min-height: 28px;
    padding: 4px 8px;
}

.sticky-dashboard-actions button label {
    font-size: 11px;
    font-weight: 600;
}

.sticky-dashboard-actions .forge-primary {
    padding: 4px 9px;
}

.settings-sidebar-surface {
    background: @sidebar_bg_color;
    min-width: 236px;
}

.settings-sidebar-header {
    padding: 24px 20px 12px;
}

.settings-navigation {
    background: transparent;
    padding: 8px 12px 20px;
}

.settings-navigation row {
    padding: 0;
    margin: 2px 0;
    border-radius: 10px;
}

.settings-navigation row box {
    padding: 11px 12px;
}

.settings-navigation row:selected {
    background: alpha(@window_fg_color,0.07);
    background-image: none;
    box-shadow: none;
}

.settings-navigation row:selected label {
    font-weight: 700;
}

.settings-main-surface {
    background: @window_bg_color;
}

.settings-content {
    padding: 24px 24px 28px;
}
.settings-content row { min-height: 56px; }
.settings-content popover row, dropdown popover row { min-height: 32px; padding: 4px 10px; margin: 0; }
.settings-content popover row > box, dropdown popover row > box { min-height: 0; padding: 0; margin: 0; }
.settings-navigation row:selected image { color: @accent_color; }

.settings-footer {
    padding: 14px 18px;
    background: @window_bg_color;
    border-top: none;
}


button.game-detail-close {
    min-width: 36px;
    min-height: 36px;
    padding: 0;
    border-radius: 999px;
    background: alpha(#161616,0.82);
    color: white;
}

button.game-detail-close.light {
    background: alpha(white,0.82);
    color: #161616;
}

button.game-detail-close:hover {
    background: alpha(#161616,0.88);
}

button.game-detail-close.light:hover {
    background: alpha(white,0.90);
}

.game-banner { background: @window_bg_color; }

.game-detail-root {
    background: @window_bg_color;
}

.game-detail-sidebar {
    min-width: 210px;
    background: @sidebar_bg_color;
    padding: 18px 10px 14px;
}

.game-detail-sidebar-header {
    padding: 4px 10px 14px;
}

.game-detail-nav {
    background: transparent;
}

.game-detail-nav row {
    margin: 2px 0;
    padding: 0;
    border-radius: 10px;
    border-left: 3px solid transparent;
}

.game-detail-nav row box {
    padding: 10px 11px 10px 9px;
}

.game-detail-nav row:selected {
    background: alpha(@window_fg_color,0.055);
    background-image: none;
    border: none;
    box-shadow: none;
}

.game-detail-nav row:selected label {
    font-weight: 700;
}

.game-detail-main {
    background: @window_bg_color;
}

.game-detail-meta {
    color: alpha(@window_fg_color,0.84);
    font-size: 13px;
    text-shadow: none;
}

/* Compact artwork credit cards. */
.art-credit-pods {
    margin-top: 4px;
}

.art-credit-pod {
    padding: 16px;
    border-radius: 12px;
    background: alpha(@window_fg_color,0.075);
}

.art-credit-pod .heading {
    font-size: 13px;
}

.art-credit-pod .dim-label {
    font-size: 11px;
}

.art-credit-pod button {
    margin-top: 4px;
}

.game-detail-summary {
    color: alpha(@window_fg_color,0.84);
    font-size: 12px;
    text-shadow: none;
}

.detail-footer {
    padding: 11px 16px;
    background: @window_bg_color;
    border-top: 1px solid alpha(@window_fg_color,0.10);
}

.detail-footer-actions {
    min-height: 32px;
}

.banner-shade {
    background: linear-gradient(
        to bottom,
        alpha(@window_bg_color,0.08) 0%,
        alpha(@window_bg_color,0.30) 28%,
        alpha(@window_bg_color,0.72) 52%,
        alpha(@window_bg_color,0.94) 76%,
        @window_bg_color 100%
    );
}

/*
 * Hero typography separation.
 * Apply the treatment to title, metadata, summary and status badge text.
 */
/* Compact, stable Library card labels. */
.game-card .card-info {
    padding: 0;
}
.game-card .card-footer {
    padding: 8px;
    background: alpha(black,0.09);
    border-radius: 0 0 12px 12px;
}
.game-card .card-footer .library-meta-row { margin-top: 0; }


.game-card .card-title {
    font-size: 16px;
    font-weight: 700;
    min-height: 0;
    margin: 12px 16px;
}

.game-card .card-meta {
    font-size: 9px;
    min-height: 0;
    margin: 0;
    opacity: 0.7;
}

.game-card .game-details {
    font-size: 11px;
    min-height: 28px;
    padding: 3px 8px;

    background: alpha(@window_fg_color,0.12);
    color: @window_fg_color;
    border-color: alpha(@window_fg_color,0.08);
    box-shadow: none;
}

.game-card .game-details label {
    color: inherit;
}

.game-card .game-details:hover {
    background: alpha(@window_fg_color,0.16);
    color: @window_fg_color;
    border-color: transparent;
}

.game-card .game-details:hover label {
    color: @window_fg_color;
}


.game-card .card-title.art-title-xs {
    font-size: 16px;
}

.game-card .card-title.art-title-sm {
    font-size: 16px;
}

.game-card .card-title.art-title-md {
    font-size: 16px;
}

.game-card .card-title.art-title-lg {
    font-size: 16px;
}

.game-card.art-card-xs .game-details {
    font-size: 9px;
    min-height: 22px;
    padding: 1px 5px;
}

.game-card.art-card-sm .game-details {
    font-size: 10px;
    min-height: 24px;
    padding: 2px 6px;
}

.game-card.art-card-md .game-details {
    font-size: 10px;
    min-height: 26px;
    padding: 2px 7px;
}

.game-card.art-card-lg .game-details {
    font-size: 11px;
    min-height: 28px;
    padding: 3px 8px;
}

/* Gtk.ColumnView utility classes still used by the current List view. */

.library-list-location {
    font-size: 10px;
    opacity: 0.72;
}

.library-list-status-text {
    font-size: 11px;
    font-weight: 600;
}

.library-list-status-dot {
    font-size: 11px;
}

.library-list-status-dot.installed {
    color: #76b900;
}

.library-list-status-dot.available {
    color: #f6c344;
}

.library-list-status-dot.unavailable {
    color: @error_color;
}

.library-list-chip {
    padding: 3px 6px;
    border-radius: 7px;

    background: alpha(@window_fg_color,0.08);
    border: 1px solid alpha(@window_fg_color,0.07);

    font-size: 10px;
    font-weight: 500;
}

.library-list-chip.active {
    color: #8fd400;
    background: alpha(#76b900,0.14);
    border-color: alpha(#76b900,0.28);
}


/* ==========================================================
 * STRUCTURED GTK COLUMN VIEW
 * RTXFORGE_COLUMNVIEW_SURGICAL_FIX_V2
 * ========================================================== */

columnview.library-column-view {
    background: transparent;
}


/* Thin, readable, interactive controller. */


columnview.library-column-view header button label {
    margin: 0;
    padding: 0;

    color: @window_fg_color;

    font-size: 13px;
    font-weight: 700;
    opacity: 1;
}

columnview.library-column-view header button image {
    opacity: 0.82;
}

columnview.library-column-view header button:hover {
    background: alpha(@window_fg_color,0.085);
}

columnview.library-column-view header button:active {
    background: alpha(@window_fg_color,0.13);
}


/* Equal physical padding at both List edges. */
columnview.library-column-view listview {
    background: transparent;
    padding: 16px 0 0;
}


columnview.library-column-view listview row:nth-child(even) {
    background: @forge_library_card_b;
}

columnview.library-column-view listview row:hover,
columnview.library-column-view listview row:nth-child(even):hover {
    background: @forge_library_list_hover;
}


/* Same horizontal inset as the controller. */
.library-column-cell {
    min-height: 0;
    padding: 0;
}

.library-column-game {
    padding-left: 8px;
    padding-right: 8px;
}

.library-column-actions {
    padding-left: 0;
    padding-right: 0;
}


/* 96x45 wide artwork with clipping at every layer. */



.library-meta-row {
    min-height: 24px;
}

.game-card .library-meta-row {
    margin-top: 6px;
}

.library-meta-pill {
    min-width: 0;
    min-height: 0;

    padding: 0;
    margin: 0;

    border: none;
    border-width: 0;
    border-color: transparent;
    border-radius: 999px;
    box-shadow: none;

    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.42px;
}

.library-pill-icon {
    min-width: 11px;
    min-height: 11px;

    color: #bfbfbf;
    opacity: 1;
}

.library-pill-text {
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.42px;
}


.library-test-pill.test-tested .library-pill-icon {
    color: #76b900;
}

/* STEAM / NON-STEAM */
.library-source-pill {
    background: alpha(#c5c5c5,0.55);
    border: none;
    border-color: transparent;
    box-shadow: none;
    color: #242424;
}


/* UNTESTED */


/* Tested/result */
.library-test-pill.test-tested {
    background: @view_bg_color;
    border: none;
    border-color: transparent;
    box-shadow: none;
    color: #dadada;
}

.library-test-pill.pill-working {
    background: mix(@view_bg_color,#76b900,0.18);
    color: #a8db4e;
}

.library-test-pill.pill-issue {
    background: mix(@view_bg_color,@error_color,0.20);
    color: #ffaaa5;
}

.library-test-pill.pill-bench {
    background: mix(@view_bg_color,@window_fg_color,0.10);
    color: #d2d2d2;
}


/* Before first bind, visually match UNTESTED. */
.library-test-pill:not(.test-untested):not(.test-tested) {
    background: #d3d3d3;
    border: none;
    border-color: transparent;
    box-shadow: none;
    color: #4c4c4c;
}


/* Pill glyphs belong to the state, not to a generic icon palette. */
.library-source-pill .library-pill-icon {
    color: #242424;
}


.library-test-pill.test-tested.pill-bench .library-pill-icon {
    color: #d2d2d2;
}


.library-test-pill.test-untested {
    background: mix(@view_bg_color,#f5a623,0.28);
    border: none;
    border-color: transparent;
    box-shadow: none;
    color: #ffb74f;
}

.library-test-pill.test-untested .library-pill-icon {
    color: #ffb74f;
}

.library-test-pill.pill-na {
    background: mix(@view_bg_color,@window_fg_color,0.10);
    border: none;
    border-color: transparent;
    box-shadow: none;
    color: #c9c9c9;
}

.library-test-pill.pill-na .library-pill-icon {
    color: #c9c9c9;
}

.library-test-pill.test-tested.pill-working .library-pill-icon {
    color: #a8db4e;
}

.library-test-pill.test-tested.pill-issue .library-pill-icon {
    color: #ffaaa5;
}


/* Dot/status and test pill use the same protected width. */
.library-status-stack {
    min-width: 108px;
}

.library-status-line {
    min-width: 108px;
    min-height: 20px;
}

.library-status-primary {
    background: transparent;
    border: none;
    border-radius: 999px;
    box-shadow: none;
}


/* Neutral actions. */
.library-column-actions button {
    min-width: 0;
    min-height: 30px;
    padding: 4px 8px;

    background: alpha(@window_fg_color,0.12);
    color: @window_fg_color;

    border-color: alpha(@window_fg_color,0.08);
    box-shadow: none;
}

.library-column-actions button label,
.library-column-actions button image {
    color: inherit;
}


.library-column-actions button:hover {
    background: alpha(@window_fg_color,0.16);
    color: @window_fg_color;
    border-color: transparent;
}

.library-column-actions button:hover label,
.library-column-actions button:hover image {
    color: @window_fg_color;
}


.game-card .poster-fallback {
    font-size: 14px;
    padding: 10px;
}


.game-banner-title {
    color: @window_fg_color;
    font-family: "Bakbak One";
    font-size: 42px;
    font-weight: 400;
    letter-spacing: -0.8px;
    text-shadow: 0 0 8px alpha(black,0.39), 0 0 20px alpha(black,0.21);
}

.game-banner-title.detail-title-md {
    font-size: 36px;
    letter-spacing: -0.6px;
}

.game-banner-title.detail-title-sm {
    font-size: 32px;
    letter-spacing: -0.4px;
}

.game-banner-title.detail-title-xs {
    font-size: 28px;
    letter-spacing: -0.2px;
}

.progress-content {
    /* More breathing room against the modal's outer edges. */
    padding: 24px;
    color: @window_fg_color;
}

.progress-shade {
    background: @window_bg_color;
}

.done-shade {
    background: alpha(#050505,0.60);
}

.done-fallback {
    background: @window_bg_color;
}

.art-progress {
    color: white;
}

/*
 * White translucent hairlines.
 * Previous patch used 2px; these are 70% thinner.
 */
.progress-panel {
    border-radius: 0;
    border: none;
    background: @window_bg_color;
}

.progress-panel.done {
    background: @window_bg_color;
}
.progress-panel.done .progress-content { padding: 20px 24px; }

.progress-poster-frame {
    border-radius: 14px;

    /*
     * Neutral fallback only.
     * artwork_accent() overrides the border color per game.
     *
     * Keep the frame itself outside the clipping surface so the
     * rounded accent edge stays clean instead of being cut off.
     */
    box-shadow: none;
    outline: none;
    border: 3px solid alpha(white,0.18);
    background: transparent;
    padding: 0;
}

.progress-poster {
    border-radius: 11px;
    background: transparent;
}

.job-title {
    font-size: 28px;
    font-weight: 600;
}

/* Operation dialog: one step layout for checking and progress. */
.operation-step .progress-poster-frame {
    border-width: 2px;
    border-radius: 12px;
}
.operation-step .job-title {
    font-size: 20px;
}
.operation-done .icon { color: @success_color; }
.operation-failed .icon { color: @warning_color; }

.result-success {
    color: white;
}

.result-success-circle {
    min-width: 56px;
    min-height: 56px;
    border-radius: 999px;
    background: #2fbf61;
    color: white;
    padding: 0;
}

.result-error {
    background: #b93340;
    color: white;
    border-radius: 99px;
    padding: 14px;
}

.done-title {
    color: #2fbf61;
    font-size: 28px;
    font-weight: 600;
}

button.done-button,
button.done-button.suggested-action {
    background: #2fbf61;
    color: #073b1b;

    border-radius: 11px;

    min-height: 36px;
    padding: 8px 20px;
}

button.done-button label,
button.done-button.suggested-action label {
    color: #073b1b;
    font-weight: 600;
}

button.done-button:hover,
button.done-button.suggested-action:hover {
    background: #35c96a;
}

.progress-footer {
    min-height: 0;
}

.progress-footer button {
    min-height: 34px;
    padding: 7px 14px;
}

.progress-inline-cancel {
    min-height: 30px;
    padding: 5px 14px;

    background: alpha(@window_fg_color,0.08);
    color: @window_fg_color;

    border: 1px solid alpha(white,0.10);
}

.progress-inline-cancel:hover {
    background: alpha(@window_fg_color,0.12);
}

.art-progress progressbar trough {
    min-height: 9px;
    border-radius: 99px;
}

.art-progress progressbar progress {
    min-height: 9px;
    border-radius: 99px;
}

.progress-content label {
    color: @window_fg_color;
}


.control-pod {
    padding: 16px 24px;
    border-radius: 12px;
    background: @forge_panel_bg;
    border: 1px solid transparent;
}
.control-pod scale { padding: 5px 2px; }

.view-action { padding: 5px 8px; margin: 0; min-width: 20px; }
.mode-selector {
    padding: 4px;
    border-radius: 12px;
    background: mix(@view_bg_color,@forge_panel_bg,0.72);
}

.mode-selector toggle {
    padding: 8px 18px;
    min-height: 24px;
    border-radius: 9px;
    background: transparent;
    border-color: transparent;
}

.mode-selector toggle:hover {
    background: alpha(@window_fg_color,0.06);
}

.mode-selector toggle:checked {
    background: alpha(@window_fg_color,0.12);
}
.dashboard-icon { margin: 0 6px 0 0; }
.dashboard-actions { margin: 0; }

.dashboard-actions button label { font-weight: 600; }
button.dlss-outline {
    background: alpha(@window_fg_color,0.14);
    background-image: none;
    border: 1px solid alpha(@window_fg_color,0.22);
    box-shadow: none;
    color: @window_fg_color;
}
button.dlss-outline:hover { background: alpha(@window_fg_color,0.20); }
button.dlss-outline:active { background: alpha(@window_fg_color,0.25); }
.dashboard-tuning .control-pod scale { padding: 2px; }

/* rtxForge dashboard tuning typography */
.dashboard-tuning .control-pod {
    padding: 16px 24px;
}

.dashboard-tuning .heading {
    font-size: 13px;
}

.dashboard-tuning .dim-label {
    font-size: 11px;
}

.dashboard-tuning spinbutton,
.dashboard-tuning dropdown {
    font-size: 12px;
}
.mode-bar {
    padding: 16px;

    /* Halfway between the base view and the normal tuning panels. */
    background: mix(@view_bg_color,@forge_panel_bg,0.50);
}
.mode-bar .mode-description {
    font-size: 10px;
}
.mode-bar toggle label {
    font-size: 11px;
}
.operation-bubble {
    border-radius: 15px;
    padding: 9px 10px 9px 12px;
    background: @view_bg_color;
    border: 1px solid alpha(@window_fg_color,0.10);
    box-shadow: 0 5px 18px alpha(black,0.32);
}
.operation-bubble .operation-complete { color: #2fbf61; }
.operation-bubble .operation-error { color: #ff7b72; }
.operation-dismiss {
    min-width: 28px;
    min-height: 28px;
    padding: 0;
    border-radius: 999px;
}
.title-action { min-width: 26px; min-height: 26px; padding: 8px 12px; margin: 3px; }

.hero-title { font-family: "Bakbak One"; font-size: 30px; font-weight: 400; letter-spacing: -0.6px; }
.eyebrow { color: #76b900; font-weight: 800; font-size: 9px; letter-spacing: 1.7px; }
.hero {
    background: transparent;
    border: 0;
    border-radius: 0;
    padding: 0;
}
.forge-primary {
    background: #76b900;
    color: #173000;
    font-weight: 600;
    padding: 10px 18px;
}

.forge-primary label {
    color: #173000;
}

.forge-primary:hover {
    background: #8fd000;
    color: #102600;
}

.forge-primary:hover label {
    color: #102600;
}
.bulk-remove { color: #ff928c; padding: 10px 16px; }
.pill { border-radius: 99px; padding: 5px 10px; background: alpha(@window_fg_color,0.07); font-size: 11px; }
.game-card {
    border-radius: 14px;
    background: @forge_library_card_a;
    border: 2px solid transparent;
}

.game-card.library-stripe-a {
    background: @forge_library_card_a;
}

.game-card.library-stripe-b {
    background: @forge_library_card_b;
}


.game-card.selected { border-color: transparent; box-shadow: none; }

.library-ghost-card {
    border-radius: 14px;
    background: alpha(@window_fg_color,0.06);
    border: 2px solid transparent;
}

.library-ghost-icon {
    color: alpha(@window_fg_color,0.66);
}

.poster-button { padding: 0; border: 0; border-radius: 11px 11px 0 0; }
.poster { border-radius: 11px 11px 0 0; background: #252525; }

/* Poster / Wide Capsule artwork is an inset rounded surface.
 * Transparent corners expose the card's own label-area background,
 * including the artwork accent while selected.
 */
.game-card .poster-button {
    outline: none;
    background-image: none;
    padding: 0;
    border: 0;
    border-width: 0;
    border-radius: 14px;
    background: transparent;
    box-shadow: none;
}

.game-card .poster {
    border-radius: 14px;
    background: transparent;
}


/* Poster / Wide Capsule artwork inset.
 * The frame itself owns both the 3.5px stroke and the corner-fill
 * color, so antialiased rounded corners cannot expose dark gaps.
 */


/* 14px outer radius - 3.5px inset = 10.5px inner artwork radius. */


.poster-fallback { color: #a6a6a6; padding: 22px; font-weight: 800; font-size: 19px; }
.card-info { padding: 10px 12px 12px; }
.card-title {
    color: @window_fg_color;
    font-weight: 500;
    font-size: 18px;
    letter-spacing: 0;
}
.card-meta { font-size: 10px; opacity: 0.7; }

.poster-os-badge { min-width: 22px; min-height: 22px; background: alpha(black,0.35); border: 1px solid alpha(white,0.22); border-radius: 6px; }
.poster-os-badge image { color: white; }
.cover-badge { background: alpha(black,0.65); color: white; text-shadow: 0 1px 3px black; padding: 5px 8px; border-radius: 8px; font-size: 10px; font-weight: 700; }
.cover-badge.unavailable { color: #ffb3ad; }



.selection-controls {
    padding: 0 17px 15px;
}


.selection-action {
    min-width: 34px;
    min-height: 34px;
    padding: 5px;
    border-radius: 8px;
}

.selection-action image {
    min-width: 16px;
    min-height: 16px;
}

.forge-toasts toast {
    background: @view_bg_color;
    background-image: none;
    color: @window_fg_color;
}

.panel-body { padding: 24px; }
.panel-body.review-check-body { padding: 16px 24px; }
.modal-panel .panel-shell, .modal-panel headerbar { background: @window_bg_color; background-image: none; }
floating-sheet > sheet { box-shadow: 0 16px 52px 8px alpha(black,0.38), 0 5px 18px alpha(black,0.24); }
.review-summary { padding: 0 0 8px; }
button, button label, toggle-group toggle { font-weight: 500; }
button.suggested-action,
button.suggested-action label {
    color: @accent_fg_color;
    font-weight: 500;
}


/* A little more air in the application titlebar. */


/* ----------------------------------------------------------
 * Library toolbar: dense, but not cramped.
 * Internal spacing stays inside the 8/12px system.
 * ---------------------------------------------------------- */


/* Library toolbar controls: 38 px, between GNOME's 34 px and the old 44 px. */
.library-sticky-header entry {
    min-height: 38px;
}

.library-sticky-header button, .library-sticky-header toggle {
    min-height: 28px;
    padding: 5px 10px;
}


/* Column header gets matching vertical room. */
columnview.library-column-view header {
    border-radius: 12px;
    background: alpha(@window_fg_color,0.025);
    border-bottom: 1px solid alpha(@window_fg_color,0.11);
    box-shadow: none;
    min-height: 34px;
}

columnview.library-column-view header button {
    margin: 0;
    padding: 1px 8px 1px 18px;
    border-width: 0;
    border-radius: 4px;
    background: transparent;
    box-shadow: none;
    color: @window_fg_color;
    font-size: 13px;
    font-weight: 700;
    opacity: 1;
    min-height: 32px;
    padding-top: 3px;
    padding-bottom: 3px;
}


/* ----------------------------------------------------------
 * List rows
 * ---------------------------------------------------------- */

/* Exact 10% reduction from the previous 12px title. */


/* 4px margin above + below adjacent rows = 8px row gap. */


/* ----------------------------------------------------------
 * Missing List artwork
 *
 * Same 96x45 surface as EVERY normal artwork widget.
 * No 100x49 ghost child. The 100x49 outer frame remains shared.
 * ---------------------------------------------------------- */


/* ----------------------------------------------------------
 * Bottom floating controls
 * ---------------------------------------------------------- */

.selection-count-pill {
    border-radius: 999px;
    background: alpha(@view_bg_color,0.92);
    border: 1px solid alpha(@window_fg_color,0.10);
    box-shadow: 0 1px 3px alpha(black,0.20);
    min-width: 0;
    min-height: 26px;
    padding: 4px 12px;
}

.selection-count {
    font-size: 11px;
    font-weight: 600;
    margin: 0;
    padding: 0;
}


/* ----------------------------------------------------------
 * FlowBox wrapper itself must NEVER paint a hover rectangle.
 * Only the artwork accent ring is the gallery hover affordance.
 * ---------------------------------------------------------- */


/* Do not brighten the whole Poster/Wide card on hover. */
.game-card.library-stripe-a:hover {
    background: @forge_library_card_a;
}

.game-card.library-stripe-b:hover {
    background: @forge_library_card_b;
}


/* ----------------------------------------------------------
 * Poster / Wide artwork frame
 *
 * The picture is clipped inside the 3px frame band, with an 11px inner radius.
 * The opaque border cannot blend with image pixels beneath it.
 * ---------------------------------------------------------- */

.game-card .gallery-artwork-ring {
    border-radius: 14px;
    border: 3px solid mix(@forge_library_card_a,@window_fg_color,0.12);
    box-shadow: none;
    background: transparent;
}

.game-card .gallery-artwork-frame {
    border: none;
    border-radius: 14px;
    background: alpha(@window_fg_color,0.16);
    box-shadow: none;
}

.game-card.library-stripe-a .gallery-artwork-frame {
    border-color: @forge_library_card_a;
    background: transparent;
    box-shadow: none;
}

.game-card.library-stripe-b .gallery-artwork-frame {
    border-color: @forge_library_card_b;
    background: transparent;
    box-shadow: none;
}

/* Image/button use the SAME outer radius.
 * The inset stroke paints above them rather than shrinking them.
 */
.game-card .gallery-artwork-frame .poster-button, .game-card .gallery-artwork-frame .poster {
    border-radius: 14px;
    background: transparent;
    margin: 0;
}


/* ----------------------------------------------------------
 * Native titlebar: slightly less cramped.
 * ---------------------------------------------------------- */

headerbar, .titlebar {
    background: @forge_top_bg;
    background-image: none;
    border-width: 0;
    border-style: none;
    border-color: transparent;
    box-shadow: none;
    padding-top: 6px;
    padding-bottom: 6px;
}

/* Main window sidebar: the Settings sidebar, with one native 1px edge. */
.forge-split > .sidebar-pane {
    background: @sidebar_bg_color;
}
.forge-split > .sidebar-pane .settings-sidebar-surface {
    min-width: 0;
    background: transparent;
}
.forge-sidebar-brand {
    padding: 18px 12px 12px 22px;
}
.library-status-pill.state-installed .library-pill-icon { color: #76b900; }
.library-status-pill.state-unsupported .library-pill-icon { color: @warning_color; }
.library-pill-os { opacity: 0.8; margin-left: 2px; }
.game-card.selected .library-status-pill .library-pill-icon { color: inherit; }
.forge-brand-title {
    font-family: "Bakbak One";
    font-size: 22px;
    font-weight: 400;
    letter-spacing: -0.4px;
}


/* ----------------------------------------------------------
 * Full hero spacing.
 *
 * The hero already lives inside the same 18px horizontal page gutter.
 * Make its internal panel/action rhythm 12px and let button horizontal
 * padding match the control-pod horizontal padding.
 * ---------------------------------------------------------- */

.dashboard-actions button {
    min-height: 34px;
    padding: 7px 12px;
    padding-left: 14px;
    padding-right: 14px;
}

.dashboard-tuning {
    margin-top: 0;
}


/* ----------------------------------------------------------
 * Search / ColumnView breathing room.
 * ---------------------------------------------------------- */

.library-sticky-header {
    min-height: 38px;
}


/* ----------------------------------------------------------
 * ONE List artwork implementation.
 *
 * Outer allocation: 100x49.
 * Visible image:    96x45.
 *
 * These values are identical for EVERY row.
 * ---------------------------------------------------------- */

.list-artwork {
    min-width: 96px;
    min-height: 45px;

    padding: 0;
    margin: 0;

    background: transparent;

    border: 2px solid transparent;
    border-radius: 10px;

    box-shadow: none;
}

.list-artwork-button {
    min-width: 96px;
    min-height: 45px;

    padding: 0;
    margin: 0;

    background: transparent;

    border: none;
    border-radius: 8px;

    box-shadow: none;
}

.list-artwork-picture {
    min-width: 96px;
    min-height: 45px;

    padding: 0;
    margin: 0;

    border-radius: 8px;

    background: transparent;
}

.list-artwork-fallback {
    min-width: 96px;
    min-height: 45px;

    padding: 0;
    margin: 0;

    border-radius: 8px;

    background: alpha(@window_fg_color,0.10);
}


/* ----------------------------------------------------------
 * List text rhythm.
 * ---------------------------------------------------------- */

.library-column-title {
    color: @window_fg_color;
    margin-bottom: 4px;
    font-size: 16px;
    font-weight: 700;
}

/* Joined Adwaita rows: only the collection boundary is rounded. */
columnview.library-column-view listview row {
    min-height: 0; margin: 0; padding: 0;
    border: 0; border-bottom: 1px solid @forge_lower_bg;
    border-radius: 0; background: @forge_library_card_a;
}
columnview.library-column-view listview row.joined-first { border-top-left-radius: 12px; border-top-right-radius: 12px; }
columnview.library-column-view listview row.joined-last { border-bottom-left-radius: 12px; border-bottom-right-radius: 12px; border-bottom: 0; }
list.review-list { border-radius: 12px; background: @forge_library_card_a; }
list.review-list > row { box-shadow: none; background-image: none; margin: 0; border-radius: 0; border-bottom: 1px solid @forge_lower_bg; }
list.review-list > row:first-child { border-top-left-radius: 12px; border-top-right-radius: 12px; }
list.review-list > row:last-child { border-bottom-left-radius: 12px; border-bottom-right-radius: 12px; border-bottom: 0; }
.artwork-editor { padding: 16px; border: 0; border-radius: 12px; background: @card_bg_color; }
.artwork-preview { border: 2px solid alpha(@window_fg_color,0.15); border-radius: 8px; }
.review-bezel { border: 2px solid alpha(@window_fg_color,0.15); border-radius: 8px; margin: 10px 0; }
.unsupported-notice, .unsupported-notice > row { background: mix(@window_bg_color, @error_bg_color, 0.48); box-shadow: none; }
.unsupported-caution, .unsupported-badge { color: #e5b54a; }
.support-info { color: #e5b54a; min-width: 28px; min-height: 28px; padding: 0; border-radius: 50%; background: alpha(@window_bg_color,0.9); }
.review-badge { font-size: 11px; font-weight: 700; border-radius: 6px; padding: 4px 8px; background: alpha(@window_fg_color,0.08); }
.review-game .title { font-weight: 700; }



/* ----------------------------------------------------------
 * Action buttons.
 *
 * No unavailable-specific width/min-width/padding exists.
 * All three states share the same primary button.
 * ---------------------------------------------------------- */

/* Width requests on the shared buttons include their padding and border. */


/* ----------------------------------------------------------
 * Gallery FlowBox wrapper never paints its own hover card.
 * ---------------------------------------------------------- */

flowbox.library-flow flowboxchild, flowbox.library-flow flowboxchild:hover, flowbox.library-flow flowboxchild:active, flowbox.library-flow flowboxchild:selected, flowbox.library-flow flowboxchild:focus {
    padding: 0;
    border-width: 0;
    background: transparent;
    background-image: none;
    border-color: transparent;
    box-shadow: none;
    outline: none;
}



columnview.library-column-view header button:first-child { padding-left: 52px; }
.presets-header { padding: 2px 0; border-radius: 6px; }
.presets-hint-light {
    min-width: 5px;
    min-height: 5px;
    border-radius: 99px;
    background: #c9c9c9;
    animation: presets-blink 1.3s step-end 3;
}
@keyframes presets-blink {
    0%, 40% { opacity: 1; }
    50%, 100% { opacity: 0; }
}
'''

def profile_icon(mode):
    return {'nr-only':'rtx-brush-symbolic','mfg-only':'rtx-windows-symbolic','nr-mfg':'rtx-sparkle-symbolic'}[mode]

def profile_label(mode,text):
    box=Gtk.Box(spacing=6)
    box.append(Gtk.Image.new_from_icon_name(profile_icon(mode)))
    caption=label(text);caption.set_wrap(False);caption.set_single_line_mode(True)
    box.append(caption)
    return box

def label(text,css=None):
    w=Gtk.Label(label=str(text),xalign=0,wrap=True)
    if css:w.add_css_class(css)
    return w
BUTTON_IMAGES=weakref.WeakSet()
BUTTON_GLYPHS=True

def set_button_glyphs(active):
    global BUTTON_GLYPHS
    BUTTON_GLYPHS=bool(active)
    for image in tuple(BUTTON_IMAGES):image.set_visible(BUTTON_GLYPHS)

def action_icon(text):
    text=text.lower()
    for words,icon in (
        (('diagnos','check','verify'),'system-search-symbolic'),
        (('restore','undo','recovery'),'edit-undo-symbolic'),
        (('install','apply','save'),'document-save-symbolic'),
        (('download','update'),'folder-download-symbolic'),
        (('refresh','retry'),'view-refresh-symbolic'),
        (('details',),'help-about-symbolic'),
        (('folder','browse','open'),'folder-open-symbolic'),
        (('cancel','close'),'window-close-symbolic'),
        (('continue','next'),'go-next-symbolic'),
        (('done','select','confirm'),'object-select-symbolic'),
        (('clear','remove','delete'),'edit-clear-symbolic'),
        (('settings','preset','configure'),'emblem-system-symbolic'),
        (('play',),'media-playback-start-symbolic'),
        (('tools',),'applications-utilities-symbolic'),
        (('report','activity','log','copy'),'text-x-generic-symbolic'),
        (('back','previous'),'go-previous-symbolic'),
    ):
        if any(word in text for word in words):return icon
    return 'go-next-symbolic'

class ActionButton(Gtk.Button):
    """Keep the Button label API while displaying an optional action icon."""
    def __init__(self,text,icon):
        super().__init__(valign=Gtk.Align.CENTER)
        content=Gtk.Box(spacing=10,halign=Gtk.Align.CENTER,valign=Gtk.Align.CENTER)
        if icon:
            theme=Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
            image=Gtk.Image.new_from_icon_name(icon if theme.has_icon(icon) else 'go-next-symbolic')
            image.set_pixel_size(14)
            image.set_visible(BUTTON_GLYPHS);BUTTON_IMAGES.add(image)
            content.append(image)
        self.text_label=label(text);self.text_label.set_wrap(False)
        content.append(self.text_label);self.set_child(content)
        self.update_property([Gtk.AccessibleProperty.LABEL],[text])
        self.connect('map',self._share_row_width)
    def _share_row_width(self,*_):
        ancestor=self.get_parent()
        while ancestor and not isinstance(ancestor,Adw.ActionRow):ancestor=ancestor.get_parent()
        if ancestor is None:return
        group=ancestor.get_parent()
        if group is None:return
        size_group=getattr(group,'_action_widths',None)
        if size_group is None:
            size_group=Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)
            group._action_widths=size_group
        size_group.add_widget(self)
    def get_label(self):return self.text_label.get_text()
    def set_label(self,text):
        self.text_label.set_text(text)
        self.update_property([Gtk.AccessibleProperty.LABEL],[text])

def button(text,fn,css=None):return icon_button(text,None if text.strip().lower()=='done' else action_icon(text),fn,css)
def icon_button(text,icon,fn,css=None):
    w=ActionButton(text,icon);w.connect('clicked',fn)
    if css:w.add_css_class(css)
    return w

def action_tiles(actions):
    tiles=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,homogeneous=True,
        min_children_per_line=4,max_children_per_line=4,row_spacing=12,column_spacing=12)
    for control in actions:
        control.set_hexpand(True);control.set_size_request(180,96)
        content=control.get_child();content.set_orientation(Gtk.Orientation.VERTICAL)
        content.set_halign(Gtk.Align.FILL)
        if hasattr(control,'text_label'):
            control.text_label.set_wrap(True);control.text_label.set_xalign(.5)
            control.text_label.set_justify(Gtk.Justification.CENTER)
        tiles.insert(control,-1)
    responsive=Adw.BreakpointBin(child=tiles,width_request=380,height_request=108)
    breakpoint=Adw.Breakpoint.new(Adw.BreakpointCondition.parse('max-width: 790px'))
    breakpoint.add_setter(tiles,'min-children-per-line',2)
    breakpoint.add_setter(tiles,'max-children-per-line',2)
    breakpoint.add_setter(responsive,'height-request',228)
    responsive.add_breakpoint(breakpoint)
    return responsive

def margins(w,n=16):
    for edge in ('start','end','top','bottom'):getattr(w,'set_margin_'+edge)(n)
def scroll_bottom_fade(scroll,css='settings-bottom-fade'):
    overlay=Gtk.Overlay(child=scroll)
    fade=Gtk.Box(height_request=28,valign=Gtk.Align.END,hexpand=True,can_target=False)
    fade.add_css_class(css)
    overlay.add_overlay(fade)
    def update(adj,*_):
        remaining=max(0,adj.get_upper()-adj.get_page_size()-adj.get_value())
        fade.set_opacity(1 if remaining>0.5 else 0)
        fade.set_size_request(-1,max(1,min(28,__import__('math').ceil(remaining))))
    adj=scroll.get_vadjustment()
    adj.connect('changed',update);adj.connect('value-changed',update)
    update(adj)
    overlay.bottom_fade=fade
    return overlay

def clear(box):
    while box.get_first_child():box.remove(box.get_first_child())
def row(title,subtitle=''):
    w=Adw.ActionRow(title=str(title),subtitle=str(subtitle));w.set_use_markup(False);return w

def demo_games():
    base=[
        ('Cyberpunk 2077','1091500'),
        ('Hogwarts Legacy','990080'),
        ('PRAGMATA','3357650'),
        ('Star Wars Outlaws','2842040'),
        ('Avatar: Frontiers of Pandora','2840770'),
        ('Forza Horizon 6',''),
    ]

    games=[]

    # Four complete copies = 24 cards. This is intentionally large
    # enough for visual smoke testing of the collapsing titlebar,
    # sticky Library controls, gradient and responsive card layout.
    for copy_index in range(4):
        for game_index,(name,appid) in enumerate(base):
            index=len(games)

            display_name=(
                name
                if copy_index==0
                else f'{name} · Demo {copy_index+1}'
            )

            games.append(
                {
                    'name':display_name,
                    'appid':appid,
                    'game':f'/preview/{name}/{copy_index}',
                    'exe':'Game.exe',
                    'source':'Steam' if appid else 'Non-Steam',
                    'library':'Games drive',
                    'blocked':'',
                    'installed':index<12,
                    'profile':(
                        'MFG Only'
                        if index<12
                        else 'Not installed'
                    ),
                }
            )

    return games


def library_state_smoke_games(games):
    """Build an exhaustive, write-disabled Library visual state matrix."""

    state_matrix=(
        {
            'suffix':'INSTALLED · REPAIR',
            'installed':True,
            'blocked':'',
            'profile':'NR + MFG',
            'feature_mode':'nr-mfg',
            'nr_strength':2.0,
            'sharpening_strength':0.5,
            'mfg_multiplier':4,
            'test_status':'Working',
        },
        {
            'suffix':'AVAILABLE · APPLY',
            'installed':False,
            'blocked':'',
            'profile':'Not installed',
            'feature_mode':'',
            'nr_strength':None,
            'sharpening_strength':None,
            'mfg_multiplier':None,
            'test_status':'Untested',
        },
        {
            'suffix':'NOT INSTALLED · BLOCKED',
            'installed':False,
            'blocked':(
                'State-smoke fixture: this game cannot currently '
                'receive features.'
            ),
            'profile':'Not installed',
            'feature_mode':'',
            'nr_strength':None,
            'sharpening_strength':None,
            'mfg_multiplier':None,
            'test_status':'Problem',
        },
        {
            'suffix':'NEEDS REPAIR · BLOCKED',
            'installed':True,
            'blocked':(
                'State-smoke fixture: managed files changed and '
                'require attention.'
            ),
            'profile':'MFG Only',
            'feature_mode':'mfg-only',
            'nr_strength':0.0,
            'sharpening_strength':0.1,
            'mfg_multiplier':4,
            'test_status':'Bench',
        },
    )

    # demo_games() already supplies four copies of every base title.
    # Group those copies together so each game's four states appear
    # directly beside/under one another rather than in four distant sets.
    grouped={}

    for game in games:
        base_name=str(
            game.get(
                'name',
                'Demo Game',
            )
        ).split(
            ' · Demo ',
            1,
        )[0]

        grouped.setdefault(
            base_name,
            [],
        ).append(game)

    result=[]

    for base_name,copies in grouped.items():
        for state_index,state in enumerate(state_matrix):
            template=(
                copies[state_index]
                if state_index < len(copies)
                else copies[0]
            )

            game=dict(template)

            game['name']=(
                base_name
                +' · '
                +state['suffix']
            )

            # Keep every row identity unique even if future demo data
            # supplies fewer than four physical copies.
            game['game']=(
                str(
                    template.get(
                        'game',
                        '/preview/'+base_name,
                    )
                )
                +f'/state-{state_index}'
            )

            game['installed']=state[
                'installed'
            ]

            game['blocked']=state[
                'blocked'
            ]

            game['profile']=state[
                'profile'
            ]

            game['feature_mode']=state[
                'feature_mode'
            ]

            game['nr_strength']=state[
                'nr_strength'
            ]

            game['sharpening_strength']=state[
                'sharpening_strength'
            ]

            game['mfg_multiplier']=state[
                'mfg_multiplier'
            ]

            game['test_record']={
                'status':state[
                    'test_status'
                ],
                'notes':'',
                'sessions':[],
            }

            result.append(
                game
            )

    # RTXFORGE_SMOKE_INSTALLED_STATUS_CYCLE
    # Exercise the three meaningful installed test states while keeping
    # Available / Not Installed fixtures available for N/A validation.
    installed_index=0

    for game in result:
        if (
            game.get('installed')
            and not game.get('blocked')
        ):
            game.setdefault(
                'test_record',
                {},
            )['status']=(
                'Working',
                'Untested',
                'Problem',
            )[
                installed_index % 3
            ]

            installed_index+=1

    return result


class PresentationDialog(Adw.Dialog):
    """Keep game-mode navigation and native zoom when a panel replaces its body."""
    def __init__(self,owner,**kwargs):
        self.owner=owner
        self._scaled_child=None
        self._raw_child=None
        factor=getattr(owner,'presentation_scale',1.0)
        for key in ('content_width','content_height'):
            if kwargs.get(key,0)>0:kwargs[key]=round(kwargs[key]*factor)
        super().__init__(**kwargs)

    def set_child(self,child):
        super().set_child(None)
        if self._scaled_child:self._scaled_child.release()
        self._raw_child=child
        if child is None:
            self._scaled_child=None
            return
        couch=getattr(self.owner,'couch',None)
        in_couch=couch and self.owner.input_stack.get_visible_child_name()=='couch'
        self.add_css_class('couch-dialog') if in_couch else self.remove_css_class('couch-dialog')
        game_controls=in_couch and couch.game and couch.page in ('game','features','tools','game_presets')
        self.add_css_class('couch-game-controls') if game_controls else self.remove_css_class('couch-game-controls')
        if not in_couch:
            super().set_child(child)
            self._scaled_child=None
            return
        host=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        nav=couch.panel_navigation(self)
        if nav and couch.navigation_position!='bottom':host.append(nav)
        host.append(child)
        if nav and couch.navigation_position=='bottom':host.append(nav)
        self._scaled_child=ScaledContent(host,getattr(self.owner,'presentation_scale',1.0))
        super().set_child(self._scaled_child)

    def get_child(self):
        return self._raw_child


class ResizablePanelWindow(Adw.Window):
    """Resizable transient panel with the small Adw.Dialog API we use."""

    def __init__(
        self,
        parent,
        title,
        width,
        height,
    ):
        super().__init__(
            application=parent.get_application(),
            transient_for=parent,
            modal=False,
            title=title,
            default_width=round(width*getattr(parent,'presentation_scale',1.0)),
            default_height=round(height*getattr(parent,'presentation_scale',1.0)),
            resizable=True,
        )

        keys=Gtk.EventControllerKey()
        keys.connect('key-pressed',lambda _,key,*args:(self.close(),True)[1] if key==Gdk.KEY_Escape and self._can_close else False)
        self.add_controller(keys)
        self._panel_parent=parent
        self._can_close=True
        self._requested_width=width
        self._requested_height=height

        # Keep the parent only for the compositor's initial placement.
        # Once mapped, detach so this becomes a normal independent
        # movable window instead of an attached transient panel.
        self._detach_scheduled=False

        try:
            self.set_destroy_with_parent(
                False
            )
        except Exception:
            pass

        self.connect(
            'map',
            self._schedule_parent_detach,
        )

        self.set_size_request(
            640,
            480,
        )

        self.connect(
            'close-request',
            self._on_close_request,
        )

    def _schedule_parent_detach(self,*_):
        if self._detach_scheduled:
            return

        self._detach_scheduled=True

        # Waiting until idle gives the compositor one mapped frame with
        # transient_for intact, which preserves initial centered placement.
        GLib.idle_add(
            self._detach_transient_parent
        )

    def _detach_transient_parent(self):
        try:
            self.set_transient_for(
                None
            )
        except Exception:
            pass

        return False

    def _on_close_request(self,*_):
        if not self._can_close:
            return True

        if getattr(
            self._panel_parent,
            'dialog',
            None,
        ) is self:
            self._panel_parent.dialog=None

        return False

    # Compatibility with Adw.Dialog callers.
    def set_child(self,child):
        self.set_content(None)
        old=getattr(self,'_scaled_child',None)
        if old:old.release()
        self._raw_child=child
        self._scaled_child=None
        self.set_content(child)

    def get_child(self):
        return getattr(self,'_raw_child',None)

    def force_close(self):
        # This is intentionally stronger than Gtk.Window.close().
        # The custom panel X must always dismiss this transient window.
        self._can_close=True

        parent=getattr(
            self,
            '_panel_parent',
            None,
        )

        if (
            parent is not None
            and getattr(
                parent,
                'dialog',
                None,
            ) is self
        ):
            parent.dialog=None

        try:
            self.set_modal(False)
        except Exception:
            pass

        self.destroy()

    def set_can_close(self,value):
        self._can_close=bool(value)

    def get_can_close(self):
        return self._can_close

    def set_content_width(self,width):
        self._requested_width=int(width)
        self.set_default_size(
            self._requested_width,
            self._requested_height,
        )

    def set_content_height(self,height):
        self._requested_height=int(height)
        self.set_default_size(
            self._requested_width,
            self._requested_height,
        )

    def get_content_width(self):
        return max(
            1,
            self.get_width(),
        )

    def get_content_height(self):
        return max(
            1,
            self.get_height(),
        )



OPERATION_WORDS={
    # operation: (review title, action verb, progress verb)
    'install':('Review Installation','Install','Installing'),
    'repair':('Review Repair','Repair','Repairing'),
    'uninstall':('Review Restoration','Restore','Restoring'),
    'reset':('Review Presets','Apply Presets','Applying'),
    'update-dlss':('Review DLSS Update','Update','Updating'),
    'restore-dlss':('Review DLSS Restoration','Restore','Restoring'),
    'recovery':('Review Restoration','Restore','Restoring'),
    'cleanup':('Review Cleanup','Remove','Removing'),
    'tool':('Review Tool Installation','Install','Installing'),
    'tool-restore':('Review Tool Restoration','Restore','Restoring'),
    'artwork':('Review Artwork Sync','Sync','Syncing'),
    'steam-shortcut':('Review rtxForge in Steam','Apply','Applying'),
    'report':('Review Support Report','Export','Exporting'),
}


class OperationStep(Gtk.Box):
    """One layout for every per-game step (checking and progress).

    Accent-stroked poster on the left; on the right the "Installing 3 of 20"
    counter, the game in its accent, the current phase and the progress bar.
    """
    POSTER=(96,144)

    def __init__(self):
        super().__init__(spacing=24,valign=Gtk.Align.CENTER)
        self.add_css_class('operation-step')
        self.frame=Gtk.Frame(valign=Gtk.Align.CENTER)
        self.frame.add_css_class('progress-poster-frame')
        self.frame.set_overflow(Gtk.Overflow.HIDDEN)
        self.poster=CoverPicture(content_fit=Gtk.ContentFit.COVER,can_shrink=True)
        self.poster.cover_width,self.poster.cover_ratio=self.POSTER[0],2/3
        self.poster.set_size_request(*self.POSTER)
        self.frame.set_child(self.poster)
        self.append(self.frame)
        text=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4,hexpand=True,valign=Gtk.Align.CENTER)
        self.counter=label('Preparing…','dim-label')
        self.counter.add_css_class('caption')
        self.title=label('','job-title')
        self.title.add_css_class('title-3')
        self.title.set_wrap(False);self.title.set_ellipsize(Pango.EllipsizeMode.END)
        self.phase=label('','dim-label')
        self.phase.set_wrap(False);self.phase.set_ellipsize(Pango.EllipsizeMode.END)
        self.bar=Gtk.ProgressBar(margin_top=8)
        for widget in (self.counter,self.title,self.phase,self.bar):text.append(widget)
        self.append(text)
        self.game=None
        self.determinate=False
        GLib.timeout_add(100,self._pulse)

    def _pulse(self):
        if self.get_root() is None and self.game is not None:return False
        if not self.determinate:self.bar.pulse()
        return True

    def show(self,verb,game,index,total,phase,fraction=None):
        """A step; without a total the bar stays indeterminate."""
        self.counter.set_text(f'{verb} {min(index+1,total)} of {total}' if total else 'Preparing…')
        if phase:self.phase.set_text(str(phase).rstrip('.…')+'…')
        if total:
            self.determinate=True
            self.bar.set_fraction(max(0.0,min(1.0,fraction if fraction is not None else index/total)))
        else:
            self.determinate=False
        if game is not None and game is not self.game:
            self.game=game
            self.title.set_text(game['name'])
            path=poster_art_path(game) or capsule_art_path(game)
            try:self.poster.set_paintable(Gdk.Texture.new_from_filename(path) if path else None)
            except Exception:self.poster.set_paintable(None)
            return True
        return False

    def complete(self):
        self.determinate=True;self.bar.set_fraction(1.0)


class OperationFlow:
    """Presets → Checking → Review → Progress → Done in one dialog.

    The dialog never closes between stages. Cancel sits at the start of its
    header bar and the action verb at the end, as in other GNOME dialogs.
    Nothing is written until the review is confirmed.
    """

    def __init__(self,owner,operation,games,title=None):
        self.owner=owner
        self.operation=operation
        self.games=list(games)
        words=OPERATION_WORDS.get(operation,OPERATION_WORDS['reset'])
        self.review_title=title or words[0]
        self.verb,self.progress_verb=words[1],words[2]
        self.stage=None
        self.review=None
        self.on_confirm=None
        self.accent=None
        self.dialog=PresentationDialog(owner,title=self.review_title,content_width=640)
        self.dialog.add_css_class('modal-panel')
        self.dialog.add_css_class('operation-flow')
        self.dialog.connect('closed',self._closed)
        self.dialog.connect('close-attempt',lambda *_:self.cancel())
        toolbar=Adw.ToolbarView()
        self.header=Adw.HeaderBar(show_start_title_buttons=False,show_end_title_buttons=False)
        self.header.set_title_widget(Adw.WindowTitle(title=self.review_title))
        self.cancel_button=Gtk.Button(label='Cancel')
        self.cancel_button.connect('clicked',lambda *_:self.cancel())
        self.primary=Gtk.Button(label=self.verb,sensitive=False)
        self.primary.add_css_class('suggested-action')
        self.primary.connect('clicked',lambda *_:self._primary_clicked())
        toolbar.add_top_bar(self.header)
        # Actions sit along the bottom: Cancel, then the action, right aligned.
        actions=Gtk.Box(spacing=12,halign=Gtk.Align.END)
        actions.add_css_class('operation-actions')
        actions.set_margin_start(24);actions.set_margin_end(24);actions.set_margin_top(4);actions.set_margin_bottom(24)
        actions.append(self.cancel_button)
        actions.append(self.primary)
        toolbar.add_bottom_bar(actions)
        self.actions=actions
        self.toolbar=toolbar
        self.content=None
        self.dialog.set_child(toolbar)
        self.closed=False
        # One modal at a time, as open_panel() does.
        if owner.dialog is not None:owner.dialog.force_close()
        owner.operation_flow=self
        owner.dialog=self.dialog
        self.dialog.present(owner)

    # ---------- helpers ----------

    def _page(self,name,child,width=640):
        self.content=child
        self.toolbar.set_content(child)
        self.dialog.set_content_width(width)
        self.stage=name
        self._fit(child,width)
        GLib.idle_add(self._fit,child,width)

    def _fit(self,child,width):
        """Size the dialog to the current stage, within the window."""
        if self.closed or self.content is not child:return False
        header=self.header.measure(Gtk.Orientation.VERTICAL,width)[1]+self.actions.measure(Gtk.Orientation.VERTICAL,width)[1]
        content=child.measure(Gtk.Orientation.VERTICAL,width)[1]
        if isinstance(child,Gtk.ScrolledWindow) and child.get_child() is not None:
            content=child.get_child().measure(Gtk.Orientation.VERTICAL,width)[1]
        limit=max(320,self.owner.get_height()-96)
        self.dialog.set_content_height(min(limit,header+content))
        return False

    def _rows_scroll(self,listing,visible=5):
        """At most five complete rows show; the rest scroll."""
        scroll=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,propagate_natural_height=True)
        scroll.set_child(listing)
        def cap(*_):
            rows=[];row=listing.get_first_child()
            while row:rows.append(row);row=row.get_next_sibling()
            last=rows[min(visible,len(rows))-1] if rows else None
            ok,bounds=last.compute_bounds(listing) if last is not None and last.get_height()>0 else (False,None)
            if ok:
                # The fifth row's lower edge, including the list's own border.
                height=round(bounds.get_y()+bounds.get_height())+(1 if len(rows)<=visible else 0)
            else:
                width=max(320,listing.get_width() or 560)
                height=sum(r.measure(Gtk.Orientation.VERTICAL,width)[1] for r in rows[:visible])+2
            if scroll.get_max_content_height()==height:return False
            scroll.set_max_content_height(height)
            if self.content is not None:self._fit(self.content,self.dialog.get_content_width())
            return False
        cap()
        GLib.idle_add(cap)
        GLib.timeout_add(120,cap)
        for row in [listing.get_row_at_index(i) for i in range(visible)]:
            if isinstance(row,Adw.ExpanderRow):row.connect('notify::expanded',lambda *_:GLib.idle_add(cap))
        return scroll

    def _title(self,text):
        self.dialog.set_title(text)
        self.header.get_title_widget().set_title(text)

    def _body(self):
        body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16)
        margins(body,24)
        # The action bar below brings its own spacing.
        body.set_margin_bottom(16)
        return body

    def _set_accent(self,game):
        accent=self.owner._ensure_game_accent(game) if game else None
        if accent==self.accent:return
        if self.accent:self.dialog.remove_css_class(self.accent)
        self.accent=accent
        if accent:self.dialog.add_css_class(accent)

    def _primary_clicked(self):
        if self.stage=='presets' and self.on_continue:self.on_continue()
        elif self.stage=='review' and self.on_confirm:self.on_confirm(self.review)
        elif self.stage=='done':self.dialog.force_close()

    def _closed(self,*_):
        self.closed=True
        if self.stage=='checking' and getattr(self.owner,'operation_cancel',None) is not None:
            self.owner.operation_cancel.set()
        if self.accent:self.dialog.remove_css_class(self.accent)
        if getattr(self.owner,'operation_flow',None) is self:self.owner.operation_flow=None
        if self.owner.dialog is self.dialog:self.owner.dialog=None
        if self.stage=='done' and getattr(self,'rescan',False):self.owner.scan()

    def cancel(self):
        owner=self.owner
        if self.stage=='progress':
            cancel=getattr(owner,'operation_cancel',None)
            if cancel is not None and self.cancel_button.get_sensitive():
                cancel.set()
                self.cancel_button.set_label('Cancelling…')
                self.cancel_button.set_sensitive(False)
                self.step.phase.set_text('Finishing safely, then undoing changes…')
            return
        if self.stage=='checking' and getattr(owner,'operation_cancel',None) is not None:
            owner.operation_cancel.set()
        self.dialog.force_close()

    # ---------- stages ----------

    def show_presets(self,tuning,on_continue):
        """Install only: tune presets, then Cancel or Continue."""
        self.on_continue=on_continue
        self._title('Install Features')
        body=self._body()
        body.append(label('Adjust your presets or continue. You can change these settings later in OptiScaler.','dim-label'))
        body.append(tuning)
        self.primary.set_label('Continue')
        self.primary.set_sensitive(True)
        self._page('presets',body,width=820)

    def show_checking(self):
        """The engine prepares every target; nothing is written yet."""
        self._title(self.review_title)
        body=self._body()
        self.step=OperationStep()
        self.step.show('Checking',self.games[0] if self.games else None,0,0,'Checking game files')
        self._set_accent(self.step.game)
        body.append(self.step)
        note=label('Your files will only change after you review and confirm.','dim-label')
        note.add_css_class('caption')
        body.append(note)
        self.primary.set_label(self.verb)
        self.primary.set_sensitive(False)
        self.cancel_button.set_visible(True)
        self._page('checking',body)

    def checking_event(self,event):
        if event.get('phase')!='review-check':
            if event.get('label'):self.step.phase.set_text(user_messages.friendly_status(event['label']).rstrip('.…')+'…')
            return
        game=next((g for g in self.games if g['name']==event.get('game')),None)
        total=event.get('total') or len(self.games)
        if self.step.show('Checking',game,max(0,event.get('checked',0)-1),total,user_messages.friendly_status(event.get('label','')),event.get('checked',0)/max(1,total)):
            self._set_accent(game)

    def show_review(self,review,on_confirm,details=None,enabled=True,trust=None,note=None,extra=None):
        """N games ready, Needs attention · N, then the verb."""
        self.review=review
        self.on_confirm=on_confirm
        owner=self.owner
        self._title(review.get('title') if review.get('title','').startswith('Review') else self.review_title)
        self._set_accent(None)
        body=self._body()
        count=len(review.get('rows',[]))
        summary=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4)
        summary.append(label(f"{count} game{'s' if count!=1 else ''} ready" if count else 'Nothing ready yet','title-2'))
        line=' · '.join(details or [self.verb])
        summary.append(label(line,'dim-label'))
        body.append(summary)
        if review.get('rows'):
            listing=Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
            listing.add_css_class('boxed-list');listing.add_css_class('review-list')
            for item in review['rows']:
                game=item.get('art') or owner.review_game(item['name'],item.get('game'))
                detail=user_messages.friendly_status(item.get('detail',''))
                if 'badge' in item:
                    # Rows that are not per-game changes (artwork roles) state their own status.
                    listing.append(owner.review_entry(item['name'],detail,game,item['badge']))
                else:
                    listing.append(owner.review_entry(item['name'],'Ready to '+self.verb.lower(),game,'Ready',detail or None))
            body.append(self._rows_scroll(listing))
        blocked=review.get('blocked',[])
        if blocked:
            body.append(label(f'Needs attention · {len(blocked)}','heading'))
            skipped=Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
            skipped.add_css_class('boxed-list');skipped.add_css_class('review-list')
            for item in blocked:
                skipped.append(owner.review_entry(item['name'],user_messages.friendly_error(item['reason']),owner.review_game(item['name']),'Skipped','Technical details\n'+str(item['reason']),icon='dialog-warning-symbolic'))
            body.append(skipped)
            if any('baseline' in str(item['reason']).lower() for item in blocked):
                previous=Gtk.Button(label='Previous Changes',halign=Gtk.Align.START)
                previous.connect('clicked',lambda *_:(self.dialog.force_close(),owner.show_undo()))
                body.append(previous)
        if not count:
            body.append(label('There are no games ready for this change. Check the messages above for your next step.','dim-label'))
        if extra is not None:body.append(extra)
        if note:
            hint=label(note,'dim-label');body.append(hint)
        trusted=Gtk.CheckButton(label=trust) if trust else None
        if trusted is not None:body.append(trusted)
        footer=label('Preview mode · all file changes are disabled.' if owner.options.demo else 'Your files will only change after you review and confirm.','dim-label')
        footer.add_css_class('caption')
        body.append(footer)
        scroll=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,vexpand=True)
        scroll.set_child(body)
        self.primary.set_label(self.verb)
        ready=bool(count) and enabled
        self.primary.set_sensitive(ready and trusted is None)
        # Where the engine asks for trust, the action waits for the checkbox.
        if trusted is not None:trusted.connect('toggled',lambda box:self.primary.set_sensitive(ready and box.get_active()))
        self.cancel_button.set_label('Cancel' if count else 'Close')
        self._page('review',scroll)

    def show_working(self,text,cancellable=False):
        """Checking or working without per-game steps (tools, recovery, reports)."""
        if self.stage=='review':self.dialog.set_can_close(False)
        body=self._body()
        body.set_valign(Gtk.Align.CENTER)
        line=Gtk.Box(spacing=16,halign=Gtk.Align.CENTER)
        line.append(Adw.Spinner(width_request=32,height_request=32))
        self.working_label=label(text)
        self.working_label.set_valign(Gtk.Align.CENTER)
        line.append(self.working_label)
        body.append(line)
        body.set_margin_top(36);body.set_margin_bottom(36)
        self.primary.set_visible(self.stage in (None,'checking'))
        self.primary.set_sensitive(False)
        self.cancel_button.set_visible(cancellable)
        self._page('working',body)

    def show_progress(self,total):
        self.dialog.set_can_close(False)
        self._title(self.review_title.replace('Review ','',1))
        body=self._body()
        self.step=OperationStep()
        first=next((g for g in self.games if any(r['name']==g['name'] for r in (self.review or {}).get('rows',[]))),self.games[0] if self.games else None)
        self.step.show(self.progress_verb,first,0,total,'Starting')
        self._set_accent(first)
        body.append(self.step)
        self.total=total
        self.primary.set_visible(False)
        self.cancel_button.set_label('Cancel')
        self.cancel_button.set_sensitive(True)
        self._page('progress',body)

    def progress_event(self,event):
        game=next((g for g in self.games if g['name']==event.get('game')),None)
        total=event.get('total') or self.total
        index=max(0,int(event.get('current',1))-1) if 'current' in event else self.games.index(game) if game in self.games else 0
        if self.step.show(self.progress_verb,game,index,total,user_messages.friendly_status(event.get('label','')),event.get('fraction')):
            self._set_accent(game)

    def finalizing(self):
        """The engine is committing; a late Cancel can no longer undo."""
        self.cancel_button.set_sensitive(False)
        if not getattr(self.owner,'operation_cancel',None) or not self.owner.operation_cancel.is_set():
            self.step.phase.set_text('Finishing file management…')

    def show_done(self,success,message,title=None,technical=None):
        if getattr(self,'step',None) is not None and self.stage=='progress' and success:self.step.complete()
        self.dialog.set_can_close(True)
        self._set_accent(None)
        heading=title or ('Done' if success else 'Could not finish')
        # The status page carries the heading; the header bar stays plain.
        self._title('')
        page=Adw.StatusPage(
            icon_name='object-select-symbolic' if success else 'dialog-warning-symbolic',
            title=heading,
            description=str(message),
        )
        page.add_css_class('compact')
        page.add_css_class('operation-done' if success else 'operation-failed')
        if technical:page.set_child(self.owner.technical_details(technical))
        self.cancel_button.set_visible(False)
        self.primary.set_visible(True)
        self.primary.set_label('Done')
        self.primary.set_sensitive(True)
        self._page('done',page,width=520)


class LibraryGameItem(GObject.Object):
    """ColumnView model wrapper around one mutable game dictionary."""

    name=GObject.Property(
        type=str,
        default='',
    )

    location=GObject.Property(
        type=str,
        default='',
    )

    status=GObject.Property(
        type=str,
        default='',
    )

    features=GObject.Property(
        type=str,
        default='',
    )

    def __init__(self,game):
        super().__init__()

        self.game=game

        self.name=str(
            game.get(
                'name',
                '',
            )
        ).casefold()

        self.location=(
            str(
                game.get(
                    'source',
                    '',
                )
            )
            +' '
            +str(
                game.get(
                    'game',
                    '',
                )
            )
        ).casefold()

        if game.get('blocked'):
            status='2 unavailable'
        elif game.get('installed'):
            status='0 installed'
        else:
            status='1 available'

        self.status=status

        self.features=str(
            game.get(
                'profile',
                '',
            )
        ).casefold()


class Window(Adw.ApplicationWindow):
    def apply_display_preferences(self):
        surface=self.get_surface()
        monitor=self.get_display().get_monitor_at_surface(surface) if surface else None
        if monitor:
            geometry=monitor.get_geometry()
            system_scale=monitor.get_scale_factor()
            width,height=geometry.width*system_scale,geometry.height*system_scale
        else:width,height,system_scale=1280,820,1
        in_couch=hasattr(self,'input_stack') and self.input_stack.get_visible_child_name()=='couch'
        factor=content_scale(self.settings.get('ui_scale','auto'),width,height,system_scale) if in_couch else 1.0
        self.presentation_scale=factor
        if getattr(self,'couch_content',None):self.couch_content.set_factor(factor)
        dialog=getattr(self,'dialog',None)
        if getattr(dialog,'_scaled_child',None):dialog._scaled_child.set_factor(factor)
        if hasattr(self,'couch'):
            self.couch.resize(round(self.get_width()/factor),round(self.get_height()/factor))
            self.couch.apply_navigation_preferences()

    def set_big_picture_ui(self,enabled):
        global COUCH_MODE
        self.settings['big_picture_ui']=bool(enabled)
        self.settings['input_mode']='couch' if enabled else 'desktop'
        COUCH_MODE=self.settings['input_mode']
        if not self.options.demo:library_media.save_settings(self.service.config,self.settings)
        GLib.idle_add(lambda:(self.set_input_surface(bool(enabled)),False)[1])

    def set_display_preference(self,key,value):
        self.settings[key]=value
        if not self.options.demo:library_media.save_settings(self.service.config,self.settings)
        self.apply_display_preferences()
        if hasattr(self,'couch') and self.input_stack.get_visible_child_name()=='couch':
            GLib.idle_add(lambda:(self.couch.render(self.couch.current),False)[1])


    def game_status_label(self,game):
        return library_display_test_status(game)

    def __init__(self,application,options):
        super().__init__(application=application,title='rtxForge',default_width=1280,default_height=820)
        self.options=options;self.service=DesktopService(options.provider)
        self.settings=dict(library_media.DEFAULTS) if options.demo else library_media.load_settings(self.service.config)
        set_button_glyphs(self.settings.get('button_glyphs',True))
        global COUCH_MODE
        COUCH_MODE=self.settings.get('input_mode','auto') if self.settings.get('big_picture_ui',True) else 'desktop'

        # Demo/smoke modes are deliberately write-disabled and must not
        # require the real Bazzite Games mount merely to construct the UI.
        #
        # Use the same legacy values already owned by library_media rather
        # than importing the transaction engine, whose initialization
        # intentionally verifies the configured Btrfs storage mount.
        if options.demo:
            self.strength_presets={
                name:{
                    'nr':nr,
                    'sharpness':library_media.LEGACY_SHARPENING_STRENGTH[name],
                }
                for name,nr in library_media.LEGACY_NR_STRENGTH.items()
            }
        else:
            self.strength_presets=__import__('engine_bridge').module(
                self.service.config
            ).NR_STRENGTH_PRESETS

        if not self.settings.get('compact_header_chosen'):self.settings['compact_header']=True
        self.strength_names=tuple(self.strength_presets);self.multiplier_values=('auto',0,2,3,4,5,6)
        self.settings['enable_effects']=True;self.settings.setdefault('dark',True);self.hardware_info={'ready':True,'gpu':'Preview GPU','reason':'Preview mode'} if options.demo else None;self.games=[];self.cards={};self.selected_game_ids=set();self.mode='mfg-only';self.filter='available'
        self.busy=False;self.task_kind='';self.pending=None;self.cancel_art=threading.Event();self.log=[];self.dialog=None;self.review=None;self.action_buttons=[]
        self.connect('close-request',self.close_request)
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK if self.settings['dark'] else Adw.ColorScheme.FORCE_LIGHT)
        global THEME_MODE
        THEME_MODE=(self.settings.get('theme') or ('dark' if self.settings['dark'] else 'light'))
        self.settings['dark']=THEME_MODE!='light'
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK if self.settings['dark'] else Adw.ColorScheme.FORCE_LIGHT)
        apply_neutral_palette()
        apply_corner_style(self.settings.get('corner_style','system'))
        self.overlay=Adw.ToastOverlay();self.overlay.add_css_class('forge-toasts');self.set_content(self.overlay)
        stage=Gtk.Overlay();self.overlay.set_child(stage)
        outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.add_css_class('forge-window-surface')
        # Sidebar navigation (Library, Presets, Packages, Extras) beside the
        # page content, as a libadwaita split view.
        self.split=Adw.OverlaySplitView(min_sidebar_width=196,max_sidebar_width=236,sidebar_width_fraction=0.17)
        self.split.add_css_class('forge-split')
        self.split.set_content(outer)
        stage.set_child(self.split)
        header=Adw.HeaderBar()

        # Keep the native headerbar/window controls, but leave the
        # center visually empty. The product identity lives in the hero.
        header.set_title_widget(
            Gtk.Box()
        )

        # Native GNOME-style application menu.
        #
        # Refresh and Add Folder retain their previous busy-state
        # sensitivity through stored Gio.SimpleAction objects.
        self.refresh_action=Gio.SimpleAction.new(
            'refresh-library',
            None,
        )
        self.refresh_action.connect(
            'activate',
            lambda *_:self.scan(),
        )
        self.add_action(
            self.refresh_action
        )

        self.add_folder_action=Gio.SimpleAction.new(
            'add-game-folder',
            None,
        )
        self.add_folder_action.connect(
            'activate',
            lambda *_:self.choose_folder(),
        )
        self.add_action(
            self.add_folder_action
        )

        activity_action=Gio.SimpleAction.new(
            'activity',
            None,
        )
        activity_action.connect(
            'activate',
            lambda *_:self.show_activity(),
        )
        self.add_action(
            activity_action
        )

        settings_action=Gio.SimpleAction.new(
            'settings',
            None,
        )
        settings_action.connect(
            'activate',
            lambda *_:self.show_settings(),
        )
        self.add_action(
            settings_action
        )

        for action_name,callback in [('about',self.show_about),('extras',lambda *_:self.show_page('extras')),('reports',self.show_reports),('packages',lambda *_:self.show_page('packages')),('classic-ui',lambda *_:self.set_ui_mode('classic')),('new-ui',lambda *_:self.set_ui_mode('new')),('compact-header',self.toggle_compact_header),('game-mode',self.enter_game_mode)]:
            action=Gio.SimpleAction.new(action_name,None);action.connect('activate',callback);self.add_action(action)
        # Pages live in the sidebar; the primary menu keeps the rest.
        menu_actions=[
            ('Refresh Library','view-refresh-symbolic','win.refresh-library'),
            ('Add Game Folder','folder-new-symbolic','win.add-game-folder'),
            ('Game Mode','input-gaming-symbolic','win.game-mode'),
        ]
        # Standard primary menu: open-menu icon, F10 opens it.
        main_menu=Gtk.MenuButton(icon_name='open-menu-symbolic',primary=True,valign=Gtk.Align.CENTER)
        main_menu.set_tooltip_text(
            'Main Menu'
        )
        main_menu.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ['Main Menu'],
        )
        menu_model=Gio.Menu()
        main_section=Gio.Menu()
        for caption,icon,action_name in menu_actions:
            # GNOME primary menus are plain text.
            main_section.append_item(Gio.MenuItem.new(caption,action_name))
        menu_model.append_section(None,main_section)
        about_section=Gio.Menu()
        for caption,action_name in (('Preferences','win.settings'),('Activity','win.activity'),('Reports','win.reports'),('About rtxForge','win.about')):
            about_section.append_item(Gio.MenuItem.new(caption,action_name))
        menu_model.append_section(None,about_section)
        menu_popover=Gtk.PopoverMenu.new_from_model(menu_model)
        main_menu.set_popover(menu_popover)
        self.main_menu=main_menu
        if gamescope_session():
            main_menu=button('☰',self.show_controller_menu,'flat')
            main_menu.set_tooltip_text('Main Menu')
            self.main_menu=main_menu


        outer.append(
            header
        )
        self.content_header=header
        self.page_stack=Gtk.Stack(hexpand=True,vexpand=True,transition_type=Gtk.StackTransitionType.CROSSFADE,transition_duration=120)
        outer.append(self.page_stack)
        library_page=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.page_stack.add_named(library_page,'library')
        top=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        top.add_css_class('forge-top-surface')
        self.dashboard_top=top
        margins(top,16)
        top.set_margin_top(0)
        # The Library side owns the shared seam spacing. Do not stack
        # another explicit gap beneath the dark dashboard.
        top.set_margin_bottom(8)
        self.header_revealer=Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN,transition_duration=220,reveal_child=True)
        self.header_revealer.set_child(top)
        library_page.append(self.header_revealer)
        hero=Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=16,
        )
        hero.add_css_class('hero')

        hero_reveal=Gtk.Revealer(
            transition_type=Gtk.RevealerTransitionType.SLIDE_UP,
            reveal_child=True,
            transition_duration=180,
        )
        hero_reveal.set_child(hero)
        top.append(hero_reveal)

        hero_top=Gtk.Box(
            spacing=12,
            hexpand=True,
            valign=Gtk.Align.CENTER,
        )
        hero_top.set_vexpand(False)
        hero.append(hero_top)

        self.dashboard_icon=make_brand_icon(128)
        self.dashboard_icon.set_valign(Gtk.Align.CENTER)
        self.dashboard_icon.set_halign(Gtk.Align.START)
        self.dashboard_icon.add_css_class(
            'dashboard-icon'
        )
        hero_top.append(self.dashboard_icon)

        # Keep the copy/actions assembly centered against the logo, but
        # bottom-align its two children to one another. This puts the
        # bulk-action buttons flush with the last line of hero metadata
        # instead of floating at the top of the hero.
        hero_copy_actions=Gtk.Box(
            spacing=12,
            hexpand=True,
            valign=Gtk.Align.CENTER,
        )
        hero_top.append(
            hero_copy_actions
        )

        title=Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=2,
            hexpand=True,
            valign=Gtk.Align.END,
        )
        hero_copy_actions.append(
            title
        )

        title.append(
            label(
                'GEFORCE / BUILT FOR LINUX',
                'eyebrow',
            )
        )

        title.append(
            label(
                'rtxForge',
                'hero-title',
            )
        )

        self.stats=label(
            'Finding your games…',
            'dim-label',
        )
        self.stats.set_margin_top(3)
        title.append(
            self.stats
        )

        self.hardware_label=label(
            'Preview mode · no game writes'
            if options.demo
            else 'Checking system hardware…',
            'card-meta',
        )
        title.append(
            self.hardware_label
        )

        bulk=Gtk.Box(
            spacing=12,
            valign=Gtk.Align.END,
            halign=Gtk.Align.END,
        )
        bulk.add_css_class(
            'dashboard-actions'
        )
        hero_copy_actions.append(
            bulk
        )

        self.install_all=icon_button(
            'Install Features',
            'document-save-symbolic',
            lambda *_:self.launch_scoped('install'),
            'forge-primary',
        )
        bulk.append(self.install_all)

        self.uninstall_all=icon_button(
            'Restore Original Files',
            'document-revert-symbolic',
            lambda *_:self.launch_scoped('uninstall'),
            'bulk-remove',
        )
        bulk.append(self.uninstall_all)
        update_dlss=button('Update DLSS',lambda *_:self.update_dlss_games(self.selected_or_library()),'dlss-outline')
        self.update_dlss_button=update_dlss
        update_dlss.set_tooltip_text('Update older DLSS files in the selected games, or across the library')
        bulk.append(update_dlss)


        self.reset_all=icon_button(
            'Reset',
            'edit-undo-symbolic',
            self.discard_preset_changes,
        )
        self.apply_presets=icon_button('Apply to All','object-select-symbolic',lambda *_:self.apply_presets_to(self.configured_games(),entire=True),'suggested-action')
        # Reset belongs to Presets, not the file actions.

        tuning,self.tuning_widgets=self.tuning_controls(
            self.settings
        )
        tuning.set_hexpand(True)
        tuning.set_halign(Gtk.Align.FILL)
        tuning.set_margin_top(0)
        tuning.add_css_class('dashboard-tuning')

        self.strength_slider=(
            self.tuning_widgets['nr_strength']
        )

        self.operation_hide_source=0
        self.operation_revealer=Gtk.Revealer(
            transition_type=Gtk.RevealerTransitionType.SLIDE_UP,
            transition_duration=160,
            reveal_child=False,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.END,
        )
        self.operation_revealer.set_margin_bottom(16)
        operation=Gtk.Box(spacing=9,valign=Gtk.Align.CENTER);operation.add_css_class('operation-bubble');self.operation_revealer.set_child(operation)
        self.operation_spinner=Gtk.Spinner();operation.append(self.operation_spinner)
        self.operation_icon=Gtk.Image.new_from_icon_name('object-select-symbolic');self.operation_icon.add_css_class('operation-complete');self.operation_icon.set_visible(False);operation.append(self.operation_icon)
        self.operation_status=label('');self.operation_status.set_max_width_chars(54);self.operation_status.set_ellipsize(Pango.EllipsizeMode.END);operation.append(self.operation_status)
        self.operation_elapsed=label('','dim-label');operation.append(self.operation_elapsed)
        self.operation_dismiss=Gtk.Button(icon_name='window-close-symbolic');self.operation_dismiss.add_css_class('operation-dismiss');self.operation_dismiss.set_tooltip_text('Dismiss');self.operation_dismiss.set_visible(False);self.operation_dismiss.connect('clicked',lambda *_:self.hide_operation_status());operation.append(self.operation_dismiss)
        for key,widget in self.tuning_widgets.items():widget.connect('notify::selected' if key=='mfg_multiplier' else 'value-changed',self.strength_changed)
        self.strength_changed()
        self.reset_all.set_tooltip_text('Discard unsaved preset changes.')
        self.install_all.set_tooltip_text('Review feature installation across every library before applying changes. Incompatible games are skipped.')
        self.uninstall_all.set_tooltip_text('Review restoration of recorded feature installs across every library. Your games remain installed.')
        controls=Gtk.Box(spacing=14)
        controls.add_css_class('control-pod')
        controls.add_css_class('mode-bar')
        controls.set_margin_top(0)

        hero.append(controls)
        profile_text=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=1,hexpand=True,valign=Gtk.Align.CENTER);controls.append(profile_text)
        profile_text.append(label('Features','heading'))
        self.profile_note=label('','dim-label');self.profile_note.add_css_class('mode-description');self.profile_note.set_ellipsize(Pango.EllipsizeMode.END);self.profile_note.set_lines(1);self.profile_note.set_max_width_chars(42);profile_text.append(self.profile_note)
        self.profile_group=Adw.ToggleGroup(homogeneous=True,valign=Gtk.Align.CENTER)
        self.profile_group.add_css_class('mode-selector')
        for mode,title in [('nr-only','NR Only'),('mfg-only','MFG Only'),('nr-mfg','NR + MFG')]:
            toggle=Adw.Toggle(name=mode,label=title,child=profile_label(mode,title));self.profile_group.add(toggle)
            if mode=='nr-only':self.nr_only=toggle;toggle.set_enabled(self.settings.get('runtime_provider','y4my') in ('dlss-unlocked','custom'))
        controls.append(self.profile_group)
        self.profile_group.connect('notify::active-name',self.profile_changed)
        self.profile_group.set_active_name(self.settings.get('default_profile','mfg-only'));self.profile_changed(self.profile_group)

        # ------------------------------------------------------------
        # Compact sticky dashboard.
        #
        # The existing native HeaderBar is intentionally empty while
        # the full dashboard is on screen. Once that dashboard scrolls
        # away, this compact version occupies the same already-reserved
        # titlebar space.
        # ------------------------------------------------------------

        sticky_brand=Gtk.Box(
            spacing=8,
            valign=Gtk.Align.CENTER,
        )
        sticky_brand.set_size_request(-1,64)
        sticky_brand.add_css_class(
            'sticky-dashboard-brand'
        )

        self.sticky_brand_icon=sticky_brand_icon=make_brand_icon(48)
        sticky_brand_icon.set_valign(Gtk.Align.CENTER)
        sticky_brand_icon.add_css_class(
            'sticky-dashboard-app-icon'
        )
        sticky_brand.append(
            sticky_brand_icon
        )

        sticky_brand_title=label(
            'rtxForge',
            'sticky-dashboard-title',
        )
        sticky_brand_title.set_valign(Gtk.Align.CENTER)
        sticky_brand_title.set_wrap(
            False
        )
        sticky_brand_title.set_single_line_mode(
            True
        )
        sticky_brand.append(
            sticky_brand_title
        )

        # Compact mirror of Feature.
        self.sticky_profile_group=Adw.ToggleGroup(
            homogeneous=True,
            valign=Gtk.Align.CENTER,
        )
        self.sticky_profile_group.add_css_class(
            'sticky-mode-selector'
        )

        for mode,title_text in [
            ('nr-only','NR Only'),
            ('mfg-only','MFG Only'),
            ('nr-mfg','NR + MFG'),
        ]:
            compact_toggle=Adw.Toggle(
                name=mode,
                label=title_text,
            )

            if mode=='nr-only':
                compact_toggle.set_enabled(
                    self.settings.get(
                        'runtime_provider',
                        'y4my',
                    )=='dlss-unlocked'
                )

            self.sticky_profile_group.add(
                compact_toggle
            )

        self.sticky_profile_group.set_active_name(
            self.profile_group.get_active_name()
            or 'mfg-only'
        )

        def sticky_profile_changed(
            group,
            *_,
        ):
            active=group.get_active_name()

            if (
                active
                and self.profile_group.get_active_name()!=active
            ):
                self.profile_group.set_active_name(
                    active
                )

        def primary_profile_changed(
            group,
            *_,
        ):
            active=group.get_active_name()

            if (
                active
                and self.sticky_profile_group.get_active_name()!=active
            ):
                self.sticky_profile_group.set_active_name(
                    active
                )

        self.sticky_profile_group.connect(
            'notify::active-name',
            sticky_profile_changed,
        )

        self.profile_group.connect(
            'notify::active-name',
            primary_profile_changed,
        )

        # The compact selector follows the busy/disabled state of the
        # canonical dashboard selector.
        self.sticky_profile_group.set_sensitive(
            self.profile_group.get_sensitive()
        )

        self.profile_group.connect(
            'notify::sensitive',
            lambda source,*_:
                self.sticky_profile_group.set_sensitive(
                    source.get_sensitive()
                ),
        )

        # Compact mirrors of the three library-wide dashboard actions.
        sticky_actions=Gtk.Box(
            spacing=12,
            valign=Gtk.Align.CENTER,
        )
        sticky_actions.add_css_class(
            'sticky-dashboard-actions'
        )

        self.sticky_install_all=icon_button(
            'Install Features',
            'document-save-symbolic',
            lambda *_:self.launch_scoped('install'),
            'forge-primary',
        )

        self.sticky_remove_all=icon_button(
            'Restore Original Files',
            'document-revert-symbolic',
            lambda *_:self.launch_scoped('uninstall'),
            'bulk-remove',
        )

        self.sticky_reset_all=icon_button(
            'Reset',
            'edit-undo-symbolic',
            self.apply_library_settings,
        )

        self.sticky_install_all.set_tooltip_text(
            'Install features across the Library'
        )

        self.sticky_remove_all.set_tooltip_text(
            'Restore original files for the selected games or Library'
        )

        self.sticky_reset_all.set_tooltip_text(
            'Reset managed settings across the Library'
        )

        sticky_actions.append(
            self.sticky_install_all
        )
        sticky_actions.append(
            self.sticky_remove_all
        )


        self.sticky_update_dlss=button('Update DLSS',lambda *_:self.update_dlss_games(self.selected_or_library()),'dlss-outline')
        self.sticky_update_dlss.set_tooltip_text('Update older DLSS files in the selected games, or across the library')
        sticky_actions.append(self.sticky_update_dlss)

        # Mirror sensitivity from the canonical dashboard buttons so
        # this compact presentation never becomes a second source of
        # application state.
        for primary,compact in [
            (self.update_dlss_button,self.sticky_update_dlss),
            (
                self.install_all,
                self.sticky_install_all,
            ),
            (
                self.uninstall_all,
                self.sticky_remove_all,
            ),
            (
                self.reset_all,
                self.sticky_reset_all,
            ),
        ]:
            compact.set_sensitive(
                primary.get_sensitive()
            )

            primary.connect(
                'notify::sensitive',
                lambda source,*args,target=compact:
                    target.set_sensitive(
                        source.get_sensitive()
                    ),
            )

        # Reset All can become Apply Settings when dashboard defaults
        # have changed. Keep the compact button's wording synchronized.
        self.sticky_reset_all.text_label.set_text(
            self.reset_all.text_label.get_text()
        )

        self.reset_all.text_label.connect(
            'notify::label',
            lambda source,*_:
                self.sticky_reset_all.text_label.set_text(
                    source.get_text()
                ),
        )

        def make_sticky_revealer(child):
            revealer=Gtk.Revealer(
                transition_type=Gtk.RevealerTransitionType.CROSSFADE,
                transition_duration=140,
                reveal_child=False,
            )
            revealer.set_child(
                child
            )
            return revealer

        self.sticky_brand_revealer=make_sticky_revealer(
            sticky_brand
        )

        self.sticky_dashboard_revealer=make_sticky_revealer(
            self.sticky_profile_group
        )

        self.sticky_actions_revealer=make_sticky_revealer(
            sticky_actions
        )

        self._sticky_wanted=False
        def set_sticky_dashboard_visible(visible):
            self._sticky_wanted=visible
            self.sync_header_bar()

        # The brand (mark + wordmark) lives in the sidebar's header bar and
        # stays the same size on every page.
        self.sticky_brand_revealer.set_child(None)
        sticky_brand.set_margin_start(4)

        # Presets mode (Presets › Select games to apply presets) replaces the
        # Features selector and install actions with its own options.
        self.preset_summary=label('','dim-label')
        self.preset_summary.set_wrap(False)
        self.preset_summary.set_ellipsize(Pango.EllipsizeMode.NONE)
        self.preset_summary.set_valign(Gtk.Align.CENTER)
        preset_bar=Gtk.Box(spacing=8,valign=Gtk.Align.CENTER)
        preset_bar.add_css_class('sticky-dashboard-actions')
        self.preset_apply_selected=icon_button('Apply to Selected','object-select-symbolic',lambda *_:self.apply_presets_to(self.selected_games()),'suggested-action')
        self.preset_apply_selected.set_tooltip_text('Review the presets for the checked games')
        edit_presets=icon_button('Edit Presets','document-edit-symbolic',lambda *_:self.show_page('presets'))
        edit_presets.set_tooltip_text('Back to the Presets page')
        preset_done=Gtk.Button(label='Done',valign=Gtk.Align.CENTER)
        preset_done.set_tooltip_text('Leave presets mode')
        preset_done.connect('clicked',lambda *_:self.end_preset_selection())
        for widget in (self.preset_apply_selected,edit_presets,preset_done):
            preset_bar.append(widget)
        self.preset_bar_revealer=make_sticky_revealer(preset_bar)

        # Title area: the compact Features selector on the Library, the
        # presets summary in presets mode, and the page name elsewhere.
        # The Library's compact controls sit at the start of the header bar
        # so the bulk actions never squeeze them; other pages get a title.
        self.page_title=Adw.WindowTitle(title='Library',visible=False)
        self.header_title_stack=Gtk.Stack(hhomogeneous=False,vhomogeneous=False,transition_type=Gtk.StackTransitionType.CROSSFADE,transition_duration=140)
        self.header_title_stack.add_named(self.sticky_dashboard_revealer,'dashboard')
        self.header_title_stack.add_named(self.preset_summary,'presets')
        self.header_title_stack.add_named(Gtk.Box(),'page')
        self.header_title_stack.set_margin_start(6)
        # The header bar shrinks start widgets to their minimum when its
        # center is crowded; never let that truncate the mode labels.
        self.sticky_profile_group.set_size_request(self.sticky_profile_group.measure(Gtk.Orientation.HORIZONTAL,-1)[1],-1)

        self.sidebar_button=Gtk.ToggleButton(icon_name='sidebar-show-symbolic',visible=False)
        self.sidebar_button.set_tooltip_text('Show Sidebar')
        self.sidebar_button.update_property([Gtk.AccessibleProperty.LABEL],['Show Sidebar'])
        self.split.bind_property('show-sidebar',self.sidebar_button,'active',GObject.BindingFlags.BIDIRECTIONAL|GObject.BindingFlags.SYNC_CREATE)
        self.split.bind_property('collapsed',self.sidebar_button,'visible',GObject.BindingFlags.SYNC_CREATE)
        header.pack_start(
            self.sidebar_button
        )

        header.pack_start(
            self.header_title_stack
        )
        header.set_title_widget(
            self.page_title
        )

        header.pack_end(
            self.sticky_actions_revealer
        )
        header.pack_end(
            self.preset_bar_revealer
        )
        self.split.set_sidebar(self.build_sidebar(main_menu))
        # Narrower windows: header actions become icon buttons (their
        # tooltips keep the full names), then the sidebar folds away. The
        # labels follow the width directly: a breakpoint would also close
        # any open popover each time it applies.
        self.connect('notify::default-width',self._header_density)
        self._header_density()
        GLib.idle_add(self._header_density)
        narrow=Adw.Breakpoint.new(Adw.BreakpointCondition.parse('max-width: 860sp'))
        narrow.add_setter(self.split,'collapsed',True)
        self.add_breakpoint(narrow)

        # Presets is its own page (sidebar), not part of the dashboard.
        self.page_stack.add_named(self.build_presets_page(tuning),'presets')
        self.settings['presets_hint_seen']=True

        # One Library toolbar row: title, filter, search, view, card size,
        # Select all (Clear while anything is selected), Refresh, Add folder.
        viewbar=Gtk.Box(
            spacing=8,
            valign=Gtk.Align.CENTER,
        )
        viewbar.add_css_class(
            'library-sticky-header'
        )

        # Balanced light-side inset at the dark/light seam.
        viewbar.set_margin_top(
            12
        )

        library_title=label('Library','heading')
        library_title.set_valign(Gtk.Align.CENTER)
        library_title.set_margin_end(4)
        viewbar.append(library_title)

        filterbox=Gtk.Box()
        filterbox.add_css_class(
            'linked'
        )
        filterbox.add_css_class(
            'library-filter-group'
        )
        viewbar.append(
            filterbox
        )

        previous=None
        self.filter_buttons={}
        for name,key in [
            ('Available','available'),
            ('Installed','installed'),
            ('All','all'),
        ]:
            b=Gtk.ToggleButton(
                label=name
            )

            if previous:
                b.set_group(
                    previous
                )
            else:
                previous=b
                b.set_active(
                    True
                )

            b.connect(
                'toggled',
                self.filter_changed,
                key,
            )
            self.filter_buttons[key]=b
            filterbox.append(
                b
            )

        self.search=Gtk.SearchEntry(
            placeholder_text='Search library',
            hexpand=True,
        )
        self.search.connect(
            'search-changed',
            lambda *_:self.filter_games(),
        )
        viewbar.append(
            self.search
        )

        viewbox=Gtk.Box()
        viewbox.add_css_class(
            'linked'
        )
        viewbar.append(
            viewbox
        )

        self.view_buttons={}
        first=None

        for title,key in (
            ('Posters','posters'),
            ('Wide capsules','capsules'),
            ('List','list'),
        ):
            toggle=Gtk.ToggleButton(
                icon_name={
                    'posters':'rtx-posters-symbolic',
                    'capsules':'view-grid-symbolic',
                    'list':'view-list-symbolic',
                }[key]
            )

            toggle.set_tooltip_text(
                title
            )

            toggle.update_property(
                [Gtk.AccessibleProperty.LABEL],
                [title],
            )

            toggle.add_css_class(
                'view-action'
            )

            if first:
                toggle.set_group(
                    first
                )
            else:
                first=toggle

            toggle.set_active(
                self.settings.get(
                    'library_view',
                    'posters',
                )==key
            )

            toggle.connect(
                'toggled',
                self.view_changed,
                key,
            )

            viewbox.append(
                toggle
            )

            self.view_buttons[
                key
            ]=toggle

        self.select_toggle=icon_button(
            'Select all',
            'object-select-symbolic',
            lambda *_:self.select_all(not bool(self.selected_game_ids)),
        )
        self.select_toggle.set_tooltip_text('Select every game in this view')

        refresh=Gtk.Button(icon_name='view-refresh-symbolic',valign=Gtk.Align.CENTER)
        refresh.set_action_name('win.refresh-library')
        refresh.set_tooltip_text('Refresh Library')
        refresh.update_property([Gtk.AccessibleProperty.LABEL],['Refresh Library'])
        add_folder=Gtk.Button(icon_name='folder-new-symbolic',valign=Gtk.Align.CENTER)
        add_folder.set_action_name('win.add-game-folder')
        add_folder.set_tooltip_text('Add Game Folder')
        add_folder.update_property([Gtk.AccessibleProperty.LABEL],['Add Game Folder'])

        controls_surface=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        controls_surface.add_css_class('forge-top-surface')
        controls_surface.set_margin_bottom(0)
        library_page.append(controls_surface)

        library_surface=Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=0,
            hexpand=True,
            vexpand=True,
        )
        library_surface.add_css_class('forge-library-surface')
        library_page.append(library_surface)

        viewbar.set_margin_start(16)
        viewbar.set_margin_end(16)
        self.library_viewbar=viewbar
        # Balance the two-tone panel seam:
        # dark dashboard bottom = 16px
        # light Library top     = 16px
        viewbar.set_margin_bottom(12)
        controls_surface.append(viewbar)

        # List mode uses a real Gtk.ColumnView. Its built-in
        # headers own sorting, resizing and column drag/reordering.

        scroll=Gtk.ScrolledWindow(
            vexpand=True,

            # This Library is horizontally responsive but never exposes
            # a horizontal scrollbar.
            #
            # NEVER is wrong for that contract: GTK lets the child
            # determine the ScrolledWindow's horizontal size, so a large
            # fixed-slot gallery can become the application's new minimum.
            #
            # EXTERNAL keeps the scrollbar hidden without making current
            # gallery content dictate the viewport/window width.
            hscrollbar_policy=Gtk.PolicyType.EXTERNAL,
        )
        self.library_scroll=scroll

        # Native overlay scrolling does not reserve a separate gutter.
        scroll.set_overlay_scrolling(
            True
        )

        # The gallery deliberately recalculates card geometry from the
        # visible viewport. Its current child requests must therefore
        # never become the minimum width of the application itself.
        #
        # This is what allows a window enlarged at 4K/maximized size to
        # shrink again before the next responsive layout pass.
        scroll.set_propagate_natural_width(
            False
        )
        scroll.set_min_content_width(
            1
        )

        self.column_view=self._build_library_column_view()

        self.column_scroll=Gtk.ScrolledWindow(
            vexpand=True,
            hscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
        )
        self.column_scroll.set_margin_start(16)
        self.column_scroll.set_margin_end(16)
        self.column_scroll.set_overlay_scrolling(
            True
        )
        self.column_scroll.set_hexpand(
            True
        )
        self.column_scroll.set_halign(
            Gtk.Align.FILL
        )
        self.column_scroll.set_child(
            self.column_view
        )
        # Narrow lists drop Location, then Features; Game, Status and
        # Actions always stay.
        self.column_scroll.get_hadjustment().connect('notify::page-size',self._column_density_changed)

        self.library_stack=Gtk.Stack(
            hexpand=True,
            vexpand=True,
            transition_type=Gtk.StackTransitionType.NONE,
        )
        self.library_stack.add_named(
            scroll,
            'gallery',
        )
        self.library_stack.add_named(
            self.column_scroll,
            'list',
        )

        library_stage=Gtk.Overlay(
            vexpand=True
        )
        library_stage.set_margin_top(16)
        library_stage.set_margin_bottom(16)
        library_stage.set_child(
            self.library_stack
        )
        library_surface.append(
            library_stage
        )
        bottom_gutter=Gtk.Box(height_request=28,valign=Gtk.Align.END,hexpand=True)
        bottom_gutter.add_css_class('library-bottom-fade')
        bottom_gutter.set_can_target(False)
        library_stage.add_overlay(bottom_gutter)
        self.library_bottom_fade=bottom_gutter
        def update_library_fade(*_):
            active=self.column_scroll if self.library_stack.get_visible_child_name()=='list' else self.library_scroll
            adj=active.get_vadjustment()
            remaining=max(0,adj.get_upper()-adj.get_page_size()-adj.get_value())
            bottom_gutter.set_opacity(1 if remaining>0.5 else 0)
            bottom_gutter.set_size_request(-1,max(1,min(28,__import__('math').ceil(remaining))))
        for viewport in (self.library_scroll,self.column_scroll):
            viewport.get_vadjustment().connect('changed',update_library_fade)
            viewport.get_vadjustment().connect('value-changed',update_library_fade)
        self.library_stack.connect('notify::visible-child-name',update_library_fade)
        update_library_fade()
        self.controller_hud=Gtk.Label(label='',visible=False,margin_top=6,margin_bottom=8)
        self.controller_hud.add_css_class('dim-label')
        library_surface.append(self.controller_hud)
        # Decorative top fade removed. The Library now begins
        # with ordinary physical spacing below its controls.
        def collapse_header(adj):
            if getattr(self,'_switching_library_view',False):return
            value=adj.get_value()
            can_collapse=(
                adj.get_upper()
                - adj.get_page_size()
                > 300
            )

            if (
                self.settings.get('compact_header',True) or getattr(self,'preset_selecting',False) or (value>120
                and can_collapse)
            ):
                hero_reveal.set_reveal_child(
                    False
                )

                # Do not leave the old dashboard surface painted behind
                # the sticky titlebar. This removes the residual hairline
                # between the HeaderBar and Library surface.
                self.header_revealer.set_reveal_child(
                    False
                )

                set_sticky_dashboard_visible(
                    True
                )
                top.set_margin_top(
                    0
                )
                top.set_margin_bottom(8)
                viewbar.add_css_class(
                    'stuck'
                )

            elif value<10:
                # Restore the full dashboard surface before revealing
                # its contents again.
                self.header_revealer.set_reveal_child(
                    True
                )

                hero_reveal.set_reveal_child(
                    True
                )
                set_sticky_dashboard_visible(
                    False
                )
                top.set_margin_top(0)
                top.set_margin_bottom(8)
                viewbar.remove_css_class(
                    'stuck'
                )
        self._collapse_library_header=collapse_header
        self._library_scroll_adjustment=scroll.get_vadjustment()
        scroll.get_vadjustment().connect(
            'value-changed',
            collapse_header,
        )

        self.flow=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,column_spacing=14,row_spacing=16,min_children_per_line=1,max_children_per_line=12,homogeneous=False,valign=Gtk.Align.START);margins(self.flow,18);self.flow.set_margin_top(0);self.flow.set_margin_bottom(0);scroll.set_child(self.flow)
        self.flow.add_css_class(
            'library-flow'
        )
        self.flow.set_hexpand(True)
        self.flow.set_halign(Gtk.Align.START)

        self._library_viewport_width=0
        self._library_resize_source=0

        scroll.get_hadjustment().connect(
            'notify::page-size',
            self._library_viewport_changed,
        )

        # Overlay scrollbar presence is driven by vertical content.
        # Re-solve the gallery when that content extent changes.
        scroll.get_vadjustment().connect(
            'notify::upper',
            self._library_vertical_extent_changed,
        )
        scroll.get_vadjustment().connect(
            'notify::page-size',
            self._library_vertical_extent_changed,
        )

        GLib.idle_add(
            self.update_library_spacing
        )

        # Kept for summaries elsewhere; the count lives in "Install Selected (N)".
        self.selected_label=label('0 selected', 'selection-count')
        # Artwork size, as on Windows: the window width decides how many
        # posters or capsules fit at this size.
        self.art_scale=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,75,150,5)
        self.art_scale.set_draw_value(False)
        self.art_scale.set_size_request(120,-1)
        self.art_scale.set_valign(Gtk.Align.CENTER)
        self.art_scale.set_value(self.library_art_scale())
        self.art_scale.set_tooltip_text('Artwork size')
        self.art_scale.update_property([Gtk.AccessibleProperty.LABEL],['Artwork size'])
        self.art_scale.add_css_class('library-art-scale')
        self.art_scale.connect('value-changed',self.art_scale_changed)
        self.art_scale.set_sensitive(self.settings.get('library_view','posters')!='list')
        self.size_button=self.art_scale
        for widget in (self.size_button,self.select_toggle,refresh,add_folder):
            viewbar.append(widget)


        # Add the floating operation/status layer only after every normal
        # dashboard widget has been constructed. GtkOverlay paints this
        # final overlay above the library and selection footer.
        stage.add_overlay(
            self.operation_revealer
        )

        GLib.timeout_add(180,self.tick)
        if options.demo:
            games=demo_games()

            for game in games:
                path=ROOT/'dist/demo-media'/((game['appid'] or 'forza')+'.json')

                if path.exists():
                    game.update(
                        __import__('json').loads(
                            path.read_text()
                        )
                    )

            if options.library_state_smoke:
                games=library_state_smoke_games(
                    games
                )

                self.settings[
                    'library_view'
                ]='list'

            self.show_games(
                games,
                False,
            )

            if options.library_state_smoke:
                GLib.timeout_add(
                    700,
                    self.library_state_smoke_ready,
                )
            else:
                for key in list(self.cards)[:3]:
                    self.cards[key]['check'].set_active(
                        True
                    )
        else:
            self.scan()
        if options.resize_smoke:
            GLib.timeout_add(
                900,
                self.resize_smoke_startup,
            )
        elif options.smoke_test:
            GLib.timeout_add(
                800,
                self.smoke_library,
            )
        elif options.live_smoke:
            GLib.timeout_add(
                800,
                self.live_smoke_startup,
            )

        import controller_input
        self.controller=controller_input.Controller()
        self.controller_source=GLib.timeout_add(40,self.poll_controller)
        from game_mode import GameMode
        classic_child=self.overlay.get_child();self.overlay.set_child(None)
        self.input_stack=Gtk.Stack(hhomogeneous=False,vhomogeneous=False)
        self.input_stack.add_named(classic_child,'desktop')
        self.couch=GameMode(self,SimpleNamespace(make_brand_icon=make_brand_icon,poster_art_path=poster_art_path,capsule_art_path=capsule_art_path,
                                                 accent_source=accent_source,artwork_pixels=artwork_pixels,app_version=APP_VERSION))
        self.couch_content=ScaledContent(self.couch)
        self.input_stack.add_named(self.couch_content,'couch')
        self.overlay.set_child(self.input_stack)
        self.input_kind='keyboard'
        self.last_controller_input=0.0;self._pointer_origin=None
        self.set_input_surface(gamescope_session())
        if gamescope_session() and not options.demo:
            self.set_resizable(True)
            self.fullscreen()
        keys=Gtk.EventControllerKey();keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed',self.keyboard_input);self.add_controller(keys)
        pointer=Gtk.GestureClick();pointer.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        pointer.connect('pressed',lambda *_:self.set_input_kind('keyboard'));self.add_controller(pointer)
        self._canonical_library=self.overlay
        self._new_shell=None;self._new_stack=None
        initial=(getattr(options,'ui_mode',None) or 'classic') if options.demo else 'classic'
        self.set_ui_mode(initial,persist=False)
        GLib.idle_add(self._collapse_library_header,self._library_scroll_adjustment)

    # ---------------- NAVIGATION ----------------

    PAGES=(
        ('library','Library','applications-games-symbolic'),
        ('presets','Presets','preferences-color-symbolic'),
        ('packages','Packages','package-x-generic-symbolic'),
        ('extras','Extras','applications-utilities-symbolic'),
    )

    def build_sidebar(self,menu):
        """The same sidebar as Settings and Game Details: brand, then the pages."""
        sidebar=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,vexpand=True)
        sidebar.add_css_class('settings-sidebar-surface')
        sidebar.add_css_class('forge-main-sidebar')
        # Brand: the logo mark (no platter) and the wordmark font, left aligned.
        header=Gtk.Box(spacing=10)
        header.add_css_class('settings-sidebar-header')
        header.add_css_class('forge-sidebar-brand')
        mark=make_brand_icon(30)
        mark.set_valign(Gtk.Align.CENTER)
        header.append(mark)
        title=label('rtxForge','forge-brand-title')
        title.set_wrap(False);title.set_valign(Gtk.Align.CENTER);title.set_hexpand(True)
        header.append(title)
        menu.set_valign(Gtk.Align.CENTER)
        menu.add_css_class('flat')
        header.append(menu)
        handle=Gtk.WindowHandle()
        handle.set_child(header)
        sidebar.append(handle)

        self.nav_list=Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE,vexpand=True,valign=Gtk.Align.FILL)
        self.nav_list.add_css_class('settings-navigation')
        self.nav_rows={}
        for key,title_text,icon in self.PAGES:
            row=Gtk.ListBoxRow()
            row.page=key
            content=Gtk.Box(spacing=12)
            content.append(Gtk.Image(icon_name=icon))
            content.append(Gtk.Label(label=title_text,xalign=0,hexpand=True))
            row.set_child(content)
            self.nav_list.append(row)
            self.nav_rows[key]=row
        self.nav_list.select_row(self.nav_rows['library'])
        self.nav_list.connect('row-selected',lambda _list,row:row is not None and self.show_page(row.page))
        sidebar.append(self.nav_list)
        return sidebar

    def _header_density(self,*_):
        width=self.get_width() or self.get_default_size()[0]
        scale=Gtk.Settings.get_default().get_property('gtk-xft-dpi')/(96*1024) if Gtk.Settings.get_default() else 1
        labels=width>=1400*max(1.0,scale)
        for widget in (self.sticky_install_all,self.sticky_remove_all,self.sticky_update_dlss):
            if widget.text_label.get_visible()!=labels:widget.text_label.set_visible(labels)
        return False

    def current_page(self):
        stack=getattr(self,'page_stack',None)
        return stack.get_visible_child_name() if stack is not None else 'library'

    def show_page(self,name):
        if name not in dict((key,title) for key,title,_icon in self.PAGES):return
        # Presets mode belongs to the Library; any other page ends it.
        if name!='library' and getattr(self,'preset_selecting',False):self.end_preset_selection()
        if name=='packages':self.refresh_packages_page()
        elif name=='extras':self.refresh_extras_page()
        elif name=='presets':self.sync_presets_page()
        self.page_stack.set_visible_child_name(name)
        row=self.nav_rows.get(name)
        if row is not None and self.nav_list.get_selected_row() is not row:
            self.nav_list.select_row(row)
        self.page_title.set_title(dict((key,title) for key,title,_icon in self.PAGES)[name])
        if self.split.get_collapsed():self.split.set_show_sidebar(False)
        if name=='library':self._collapse_library_header(self._library_scroll_adjustment)
        self.sync_header_bar()

    def sync_header_bar(self):
        """Compact dashboard on the Library, presets options in presets mode, page title elsewhere."""
        if not hasattr(self,'header_title_stack'):return
        library=self.current_page()=='library'
        presets=library and getattr(self,'preset_selecting',False)
        dashboard=library and not presets and getattr(self,'_sticky_wanted',False)
        for revealer,shown in (
            (self.sticky_dashboard_revealer,dashboard),
            (self.sticky_actions_revealer,dashboard),
            (self.preset_bar_revealer,presets),
        ):
            # A crossfading revealer keeps its size while hidden; take it out
            # of the header layout once it has faded.
            if not getattr(revealer,'_forge_hides',False):
                revealer._forge_hides=True
                revealer.connect('notify::child-revealed',lambda r,*_:r.set_visible(r.get_reveal_child() or r.get_child_revealed()))
            if shown:revealer.set_visible(True)
            revealer.set_reveal_child(shown)
            if not shown and not revealer.get_child_revealed():revealer.set_visible(False)
        self.header_title_stack.set_visible_child_name('presets' if presets else 'dashboard' if library else 'page')
        self.page_title.set_visible(not library)
        # Without a centered title the Library's start and end groups size
        # independently instead of reserving symmetric space.
        self.content_header.set_show_title(not library)

    def enter_game_mode(self,*_):
        if not self.settings.get('big_picture_ui',True):
            self.toast('Turn on Game Mode in Settings to use the controller interface.')
            return
        self.set_input_surface(True)

    # ---------------- PRESETS ----------------

    def page_column(self,content):
        """A page as one centered column, like the Library: 3% side margins, at most 1600 px."""
        scroll=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,vexpand=True)
        clamp=Adw.Clamp(maximum_size=1600,tightening_threshold=1600)
        clamp.set_child(content)
        scroll.set_child(clamp)
        content.set_margin_top(24);content.set_margin_bottom(32)
        def resized(adjustment,*_):
            width=int(adjustment.get_page_size())
            if width<=1:return
            side=self.page_side_margin(width)
            if clamp.get_margin_start()!=side:clamp.set_margin_start(side);clamp.set_margin_end(side)
        scroll.get_hadjustment().connect('notify::page-size',resized)
        return scroll

    def build_presets_page(self,tuning):
        page=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=24)
        page.add_css_class('forge-page')
        group=Adw.PreferencesGroup(
            title='Library Presets',
            description='NR Strength, Sharpening and MFG for new installs. Apply them to games you have already configured.',
        )
        pod=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        pod.add_css_class('card')
        pod.add_css_class('presets-card')
        margins(tuning,18)
        pod.append(tuning)
        group.add(pod)
        self.presets_status=label('','dim-label')
        self.presets_status.set_margin_top(12)
        group.add(self.presets_status)
        page.append(group)

        apply_group=Adw.PreferencesGroup(title='Apply')
        self.presets_apply_row=Adw.ActionRow(title='Apply to all configured games',subtitle='Review the presets for every game with features installed.')
        self.apply_presets.set_valign(Gtk.Align.CENTER)
        self.presets_apply_row.add_suffix(self.apply_presets)
        apply_group.add(self.presets_apply_row)
        choose=Adw.ActionRow(title='Select games to apply presets',subtitle='Return to the Library and choose games. Each one is reviewed first.',activatable=True)
        choose.add_suffix(Gtk.Image(icon_name='go-next-symbolic'))
        choose.connect('activated',lambda *_:self.begin_preset_selection())
        apply_group.add(choose)
        reset=Adw.ActionRow(title='Discard changes',subtitle='Go back to the saved library presets.')
        self.reset_all.set_valign(Gtk.Align.CENTER)
        reset.add_suffix(self.reset_all)
        apply_group.add(reset)
        page.append(apply_group)
        hint=label('Saved settings take effect on the next game launch. They do not verify the rendered effect.','dim-label')
        hint.add_css_class('caption')
        page.append(hint)
        return self.page_column(page)

    def preset_summary_text(self,values=None):
        values=values or self.tuning_values(self.tuning_widgets)
        mfg=values.get('mfg_multiplier','auto')
        mfg='In game' if mfg=='auto' else 'Off' if mfg==0 else f'{mfg}×'
        return f"NR {float(values.get('nr_strength',0)):.1f} · Sharpening {float(values.get('sharpening_strength',0)):.1f} · MFG {mfg}"

    def configured_games(self):
        return [game for game in self.games if game.get('installed') and not game.get('blocked')]

    def selected_games(self):
        return [game for game in self.games if game['game'] in self.selected_game_ids]

    def sync_presets_page(self):
        if not hasattr(self,'presets_status'):return
        count=len(self.configured_games())
        self.presets_apply_row.set_title(f'Apply to all configured games ({count})')
        self.presets_status.set_text(
            'Unsaved changes · applying to all configured games saves them as your library presets.'
            if self.defaults_changed()
            else 'Saved · '+self.preset_summary_text()
        )

    def discard_preset_changes(self,*_):
        for key,widget in self.tuning_widgets.items():
            value=self.settings[key]
            if key=='mfg_multiplier':widget.set_selected(self.multiplier_values.index(value))
            else:widget.set_value(value)
        self.strength_changed()

    def apply_presets_to(self,games,entire=False):
        """The library presets for these games, through the usual review."""
        targets=[game for game in games if game.get('installed') and not game.get('blocked')]
        if not targets:
            self.toast('Presets apply to games with features installed.')
            return
        self.launch_action('reset',entire=entire,targets=targets,visual_settings=self.tuning_values(self.tuning_widgets))

    def begin_preset_selection(self,*_):
        """Presets › Select games: the Library without the Features selector and install actions."""
        self.preset_selecting=True
        self.selected_game_ids.clear()
        self.show_page('library')
        self.refresh_library_mode()

    def end_preset_selection(self,*_):
        if not getattr(self,'preset_selecting',False):return
        self.preset_selecting=False
        self.selected_game_ids.clear()
        self.refresh_library_mode()

    def refresh_library_mode(self):
        self.select_all(False)
        if self.settings.get('library_view','posters')=='list':
            for root in list(getattr(self,'list_action_cells',{}).values()):
                if root._game is not None:self._column_bind_actions_root(root,root._game)
        self._collapse_library_header(self._library_scroll_adjustment)
        self.sync_header_bar()

    def sync_preset_bar(self):
        if not hasattr(self,'preset_summary'):return
        count=len(self.selected_game_ids)
        self.preset_summary.set_text('Applying presets · '+self.preset_summary_text())
        self.preset_apply_selected.set_label(f'Apply to Selected ({count})' if count else 'Apply to Selected')
        self.preset_apply_selected.set_sensitive(bool(count) and not self.busy)

    # ---------------- PACKAGES AND EXTRAS PAGES ----------------

    def refresh_packages_page(self):
        old=self.page_stack.get_child_by_name('packages')
        page=build_packages(self,on_selected=lambda:self.show_page('library'),column=self.page_side_margin)
        if old is not None:self.page_stack.remove(old)
        self.page_stack.add_named(page,'packages')

    def refresh_extras_page(self):
        old=self.page_stack.get_child_by_name('extras')
        column=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=24)
        group=Adw.PreferencesGroup(title='Extras',description='Standalone tools and NR diagnostics for each game.')
        column.append(group)
        page=self.page_column(column)
        if not self.games:
            group.add(label('Your games appear here once the Library has been scanned.','dim-label'))
        for game in self.games:
            item=row(game['name'],game.get('profile',''))
            self.add_game_art_prefix(item,game)
            tools=button('Tools',lambda _,g=game:(self.details(g),self.detail_pages.set_visible_child_name('Tools')))
            tools.set_valign(Gtk.Align.CENTER)
            item.add_suffix(tools)
            group.add(item)
        if old is not None:self.page_stack.remove(old)
        self.page_stack.add_named(page,'extras')

    def show_about(self,*_):
        d,b,f=self.open_panel('About rtxForge',width=420,height=280)
        b.set_spacing(8)
        b.append(label('rtxForge','title-1'))
        b.append(label('Version '+APP_VERSION,'dim-label'))
        b.append(label('new tricks for old cards','title-4'))
        b.append(label('GeForce graphics tools for Linux.','dim-label'))
        f.append(button('GitHub',lambda *_:Gio.AppInfo.launch_default_for_uri('https://github.com/lrnolivia/rtxForge',None)))
        f.append(button('Close',lambda *_:d.close()))

    def show_controller_menu(self,*_):
        if self.busy and self.task_kind!='art':return
        d,b,f=self.open_panel('Menu',width=380,height=420)
        for title,icon,fn in [('Refresh Library','view-refresh-symbolic',self.scan),('Add Game Folder','folder-new-symbolic',self.choose_folder),('Packages','package-x-generic-symbolic',self.show_packages),('Extras','applications-utilities-symbolic',self.show_extras),('Settings','emblem-system-symbolic',self.show_settings)]:
            def invoke(*_,fn=fn):
                d.close();GLib.idle_add(lambda:(fn(),False)[1])
            b.append(icon_button(title,icon,invoke))

    def set_input_surface(self,couch):
        if not hasattr(self,'input_stack'):return
        couch=couch and self.settings.get('big_picture_ui',True)
        self._pointer_origin=None
        self.input_stack.set_visible_child_name('couch' if couch else 'desktop')
        self.apply_display_preferences()
        self.controller_hud.set_visible(False)
        if couch:self.couch.refresh()
        self.add_css_class('controller-active') if couch else self.remove_css_class('controller-active')

    def set_input_kind(self,kind):
        if getattr(self,'input_kind',None)==kind:return
        self.input_kind=kind
        if hasattr(self,'couch'):self.couch.update_prompts()

    def keyboard_input(self,_controller=None,keyval=None,_keycode=None,state=0):
        # Device changes affect prompts, never the selected interface.
        self.set_input_kind('keyboard')
        if keyval is None or self.input_stack.get_visible_child_name()!='couch':return False
        dialog=self.get_visible_dialog()
        if dialog:
            if keyval==Gdk.KEY_Escape:
                if dialog.get_can_close():dialog.close()
                return True
            return False
        focus=self.get_focus()
        editing=isinstance(focus,(Gtk.Entry,Gtk.Text,Gtk.TextView,Gtk.SpinButton))
        if keyval==Gdk.KEY_Escape:self.couch.navigate('back');return True
        if editing:return False
        control=bool(state&Gdk.ModifierType.CONTROL_MASK)
        if control and keyval in (Gdk.KEY_comma,Gdk.KEY_l,Gdk.KEY_L,Gdk.KEY_1,Gdk.KEY_2,Gdk.KEY_3):
            target={Gdk.KEY_comma:'settings',Gdk.KEY_l:'library',Gdk.KEY_L:'library',Gdk.KEY_1:'library',Gdk.KEY_2:'presets',Gdk.KEY_3:'dlss'}[keyval]
            self.couch.open(target);return True
        if keyval==Gdk.KEY_F10:self.couch.open('menu');return True
        if isinstance(focus,(Gtk.Scale,Gtk.DropDown)):return False
        if keyval in (Gdk.KEY_Return,Gdk.KEY_KP_Enter) and isinstance(focus,Gtk.Button):
            # Tab and mouse focus must activate that native control, including Settings.
            focus.emit('clicked');return True
        actions={Gdk.KEY_Up:'up',Gdk.KEY_Down:'down',Gdk.KEY_Left:'left',Gdk.KEY_Right:'right',Gdk.KEY_Return:'accept',Gdk.KEY_KP_Enter:'accept',Gdk.KEY_BackSpace:'back',
                 Gdk.KEY_x:'select',Gdk.KEY_X:'select',Gdk.KEY_Page_Up:'previous',Gdk.KEY_Page_Down:'next'}
        if keyval in actions:self.couch.navigate(actions[keyval]);return True
        return False

    def poll_controller(self):
        actions=self.controller.poll()
        if not hasattr(self,'couch'):return True
        self.apply_display_preferences();self.couch.update_prompts()
        panel=self.dialog if isinstance(self.dialog,ResizablePanelWindow) and self.dialog.get_mapped() else None
        active_panel=panel if panel and panel.is_active() else None
        if not self.is_active() and not active_panel:return True
        if actions:
            self.last_controller_input=time.monotonic();self._pointer_origin=None
            self.set_input_kind('controller')
        for action in actions:
            dialog=active_panel or self.get_visible_dialog()
            if not dialog:
                if not self.settings.get('big_picture_ui',True):
                    direction={'up':Gtk.DirectionType.UP,'down':Gtk.DirectionType.DOWN,'left':Gtk.DirectionType.LEFT,'right':Gtk.DirectionType.RIGHT,'previous':Gtk.DirectionType.TAB_BACKWARD,'next':Gtk.DirectionType.TAB_FORWARD}.get(action)
                    if direction is not None:self.child_focus(direction)
                    elif action=='accept' and self.get_focus():self.get_focus().activate()
                    continue
                if self.input_stack.get_visible_child_name()!='couch':self.set_input_surface(True)
                self.couch.navigate(action)
                continue
            if action in ('up','down','left','right','previous','next'):
                direction={'up':Gtk.DirectionType.UP,'down':Gtk.DirectionType.DOWN,'left':Gtk.DirectionType.LEFT,'right':Gtk.DirectionType.RIGHT,'previous':Gtk.DirectionType.TAB_BACKWARD,'next':Gtk.DirectionType.TAB_FORWARD}[action]
                dialog.child_focus(direction)
            elif action=='accept':
                focus=dialog.get_focus()
                while focus and focus is not dialog:
                    if focus.activate():break
                    focus=focus.get_parent()
            elif action=='back' and dialog.get_can_close():dialog.close()
        return True

    def make_action_button(self,text,callback):return button(text,callback)
    def poster_art_path(self,game):return poster_art_path(game)
    def capsule_art_path(self,game):return capsule_art_path(game)
    def wide_art_path(self,game):return capsule_art_path(game) or str(LIBRARY_GHOST_TEXTURE)
    def make_art_picture(self,width,height):return FixedArtworkPicture(width,height)

    def support_reason(self,game):
        reason=str(game.get('blocked',''))
        return {'No Windows executable found':'This game does not have a Windows launch file that rtxForge can use.',
                'Anti-cheat detected':'This game uses anti-cheat software. rtxForge does not install graphics tools into anti-cheat protected games.',
                'No native DLSS-G detected':'This game does not include the native NVIDIA frame-generation files required by the tools rtxForge currently supports.'}.get(reason,user_messages.friendly_error(reason))

    def decorate_support_artwork(self,artwork,picture,game,path):
        unsupported=bool(game.get('blocked'))
        picture.set_opacity(0.45 if unsupported else 1.0)
        picture.support_desaturated=unsupported
        if unsupported and path and Path(path).is_file():
            cache=getattr(self,'_muted_art_cache',{})
            key=(path,Path(path).stat().st_mtime_ns)
            if key not in cache:
                try:
                    pix=GdkPixbuf.Pixbuf.new_from_file_at_scale(path,1400,1400,True)
                    muted=pix.copy();pix.saturate_and_pixelate(muted,0.1,False)
                    cache[key]=Gdk.Texture.new_for_pixbuf(muted)
                except (GLib.Error,OSError):cache[key]=None
                self._muted_art_cache=cache
            if cache[key]:picture.set_paintable(cache[key])
        info=getattr(artwork,'support_info',None)
        if info is None:
            info=Gtk.Button(child=caution_image(14),halign=Gtk.Align.START,valign=Gtk.Align.START)
            info.add_css_class('support-info');info.set_margin_top(10);info.set_margin_start(10)
            info.connect('clicked',lambda *_:self.show_support_help(info))
            artwork.add_overlay(info);artwork.set_measure_overlay(info,False)
            artwork.support_info=info
        info._support_game=game
        info.set_visible(unsupported)
        if unsupported:
            reason=self.support_reason(game)
            info.set_tooltip_text('Not supported · '+reason)
            info.update_property([Gtk.AccessibleProperty.LABEL,Gtk.AccessibleProperty.DESCRIPTION],['Why this game is not supported',reason])

    def unsupported_notice(self,game):
        listing=Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        listing.add_css_class('boxed-list');listing.add_css_class('unsupported-notice')
        content=Gtk.Box(spacing=12)
        margins(content,16)
        icon=caution_image(24);icon.set_valign(Gtk.Align.START)
        icon.set_margin_top(2);icon.add_css_class('unsupported-caution')
        content.append(icon)
        explanation=label(self.support_reason(game))
        explanation.set_wrap(True);explanation.set_xalign(0)
        explanation.set_hexpand(True);explanation.set_valign(Gtk.Align.START)
        content.append(explanation)
        listing.append(content)
        return listing

    def show_support_help(self,control):
        popover=getattr(control,'support_popover',None)
        if popover is None:
            popover=Gtk.Popover(autohide=True)
            popover.set_parent(control);control.support_popover=popover
        notice=self.unsupported_notice(control._support_game)
        notice.set_size_request(320,-1)
        popover.set_child(notice);popover.popup()

    def review_check_view(self,dialog,body,games):
        body.add_css_class('review-check-body');body.set_spacing(10)
        body.append(label('Preparing your review','title-2'))
        body.append(label('Checking compatibility and the changes each game needs.','dim-label'))
        card=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        card.add_css_class('card');margins(card,2)
        line=Gtk.Box(spacing=12);margins(line,12)
        line.set_margin_bottom(4)
        art=ListArtwork();art.add_css_class('review-bezel');art.set_margin_top(0);art.set_margin_bottom(0);line.append(art)
        card.add_css_class('review-game')
        text=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4,hexpand=True,valign=Gtk.Align.CENTER)
        current=label('Getting files ready','heading');stage=label('Checking the feature package','dim-label')
        text.append(current);text.append(stage);line.append(text)
        spinner=Gtk.Spinner(spinning=True,width_request=24,height_request=24);line.append(spinner)
        card.append(line)
        counter=label(f'0 of {len(games)} checked','dim-label');counter.set_margin_start(16);counter.set_margin_end(16)
        card.append(counter)
        bar=Gtk.ProgressBar();bar.set_margin_start(16);bar.set_margin_end(16);bar.set_margin_bottom(16)
        card.append(bar);body.append(card)
        body.append(label('Your files will only change after you review and confirm.','dim-label'))
        state={'dialog':dialog,'art':art,'game':current,'stage':stage,'counter':counter,'bar':bar,'total':len(games),'determinate':False,'sequence':0,'card':card,'accent':None}
        self.review_check_state=state
        scroll=body.get_parent()
        while scroll and not isinstance(scroll,Gtk.ScrolledWindow):scroll=scroll.get_parent()
        if scroll:
            scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.NEVER)
            scroll.set_vexpand(False)
            scroll.get_vadjustment().set_value(0)
            def fit():
                if self.review_check_state is not state:return False
                width=max(320,dialog.get_content_width()-48)
                natural=body.measure(Gtk.Orientation.VERTICAL,width)[1]
                scroll.set_max_content_height(-1);scroll.set_min_content_height(natural)
                scroll.set_propagate_natural_height(True)
                shell=dialog.get_child();chrome=0;child=shell.get_first_child()
                while child:
                    if child is not scroll:chrome+=child.measure(Gtk.Orientation.VERTICAL,width)[1]
                    child=child.get_next_sibling()
                dialog.set_content_height(natural+chrome)
                return False
            GLib.timeout_add(50,fit)
        def pulse():
            if getattr(self,'review_check_state',None) is not state or self.dialog is not dialog:return False
            if not state['determinate']:bar.pulse()
            return True
        GLib.timeout_add(100,pulse)

    def review_check_event(self,event,state):
        state['stage'].set_text(user_messages.friendly_status(event['label']))
        if event.get('phase')!='review-check':return
        state['determinate']=True
        checked=event['checked'];total=event['total']
        state['counter'].set_text(f'{checked} of {total} checked')
        game=next((g for g in self.operation_games if g['name']==event.get('game')),None)
        if game:
            state['game'].set_text(game['name']);state['art'].set_artwork(capsule_art_path(game))
            if state['accent']:state['card'].remove_css_class(state['accent'])
            state['accent']=self._ensure_game_accent(game)
            if state['accent']:state['card'].add_css_class(state['accent'])
        state['sequence']+=1;sequence=state['sequence']
        start=state['bar'].get_fraction();target=checked/max(1,total);began=time.monotonic()
        settings=Gtk.Settings.get_default()
        if not settings or not settings.get_property('gtk-enable-animations'):
            state['bar'].set_fraction(target);return
        def animate():
            if getattr(self,'review_check_state',None) is not state or state['sequence']!=sequence:return False
            t=min(1,(time.monotonic()-began)/0.18)
            state['bar'].set_fraction(start+(target-start)*(1-(1-t)**3))
            return t<1
        self.add_tick_callback(lambda _widget,_clock:animate())

    def populate_tools(self,body,game):
        body.append(label('Tools','title-2'))
        body.append(label('Check NR or add ReShade to this game. Existing graphics files are kept safe.','dim-label'))
        actions=[button('Diagnose NR',lambda *_:self.show_diagnostics(game))]
        for kind,title in [('reshade','Install ReShade'),('addon','Install Add-on')]:
            control=button(title,lambda _,kind=kind:self.choose_extra(game,kind))
            control.set_sensitive(not self.options.demo);actions.append(control)
        actions.append(button('ReShade Downloads',lambda *_:Gio.AppInfo.launch_default_for_uri('https://reshade.me/',None)))
        body.append(action_tiles(actions))
        body.append(label('Use an extracted x64 ReShade DLL or .addon64 file from a source you trust. Shader packs and presets remain yours to manage. DirectX 10–12 installs use dxgi.dll; Proton may require dxgi=n,b in the existing DLL overrides.','dim-label'))
        if not self.options.demo:
            import extra_tools
            for record in extra_tools.recoveries(self.service.config,game):
                item=row(extra_tools.KINDS[record['kind']],record['date'])
                item.add_suffix(button('Restore',lambda _,r=record:self.review_extra_restore(r)))
                body.append(item)

    def review_list(self):
        listing=Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        listing.add_css_class('boxed-list');listing.add_css_class('review-list')
        GLib.timeout_add(80,self.size_review_panel,listing)
        return listing

    def size_review_panel(self,listing):
        # Measure the finished panel, keeping at most five complete rows visible.
        scroll=listing.get_parent()
        while scroll and not isinstance(scroll,Gtk.ScrolledWindow):scroll=scroll.get_parent()
        if scroll is None:return False
        body=scroll.get_child()
        if isinstance(body,Gtk.Viewport):body=body.get_child()
        dialog=self.dialog
        if dialog is None or not hasattr(dialog,'set_content_height'):return False
        container=scroll.get_parent()
        if isinstance(container,Gtk.Overlay):container=container.get_parent()
        if container is not dialog.get_child():return False
        shell=container
        footer=shell.get_last_child()
        footer.set_margin_top(28)
        footer.remove_css_class('progress-footer')
        if scroll.get_parent() is shell:
            shell.remove(scroll)
            shell.insert_child_after(scroll_bottom_fade(scroll),shell.get_first_child())
        width=max(320,body.get_width() or dialog.get_content_width()-48)
        natural=body.measure(Gtk.Orientation.VERTICAL,width)[1]
        rows=[]
        def collect(widget):
            if widget.has_css_class('review-list'):
                entry=widget.get_first_child()
                while entry:
                    rows.append(entry);entry=entry.get_next_sibling()
                return
            child=widget.get_first_child()
            while child:collect(child);child=child.get_next_sibling()
        collect(body)
        heights=[row.measure(Gtk.Orientation.VERTICAL,width)[1] for row in rows]
        visible=natural
        if len(rows)>5:
            ok,bounds=rows[4].compute_bounds(scroll)
            visible=round(bounds.get_y()+bounds.get_height()+scroll.get_vadjustment().get_value()) if ok else natural-sum(heights[5:])
        scroll_container=scroll.get_parent()
        chrome=0;child=shell.get_first_child()
        while child:
            if child is not scroll_container:chrome+=child.measure(Gtk.Orientation.VERTICAL,width)[1]
            child=child.get_next_sibling()
        available=max(320,self.get_height()-48-chrome)
        if visible>available:
            boundaries=[]
            for row in rows[:5]:
                ok,bounds=row.compute_bounds(scroll)
                if ok:
                    end=round(bounds.get_y()+bounds.get_height()+scroll.get_vadjustment().get_value())
                    if end<=available:boundaries.append(end)
            visible=max(boundaries) if boundaries else available
        scroll.set_max_content_height(-1)
        scroll.set_min_content_height(visible)
        scroll.set_max_content_height(visible)
        scroll.set_propagate_natural_height(True)
        dialog.set_content_height(visible+chrome)
        return False

    def review_entry(self,title,subtitle='',game=None,badge=None,details=None,icon='text-x-generic-symbolic'):
        entry=(Adw.ExpanderRow if details is not None else Adw.ActionRow)(title=str(title),subtitle=str(subtitle))
        entry.set_use_markup(False);entry.set_subtitle_lines(0)
        entry.add_css_class('review-game')
        if details is not None:
            def resized(*_):
                listing=entry.get_parent()
                if isinstance(listing,Gtk.ListBox):GLib.timeout_add(80,self.size_review_panel,listing)
            entry.connect('notify::expanded',resized)
        if game:
            accent=self._ensure_game_accent(game)
            if accent:entry.add_css_class(accent)
        path=capsule_art_path(game) if game else None
        if game:
            # Reuse the actual Library artwork and its approved ghost layer.
            bezel=ListArtwork();bezel.set_artwork(path)
            bezel.picture.set_content_fit(Gtk.ContentFit.CONTAIN)
            bezel.button.set_can_target(False);bezel.button.set_focusable(False)
        else:
            bezel=Gtk.Frame(width_request=100,height_request=49,valign=Gtk.Align.CENTER)
            bezel.set_child(Gtk.Image(icon_name=icon,pixel_size=28))
        bezel.add_css_class('review-bezel');bezel.set_overflow(Gtk.Overflow.HIDDEN)
        entry.add_prefix(bezel)
        if badge:
            pill=label(badge,'review-badge');pill.set_valign(Gtk.Align.CENTER);entry.add_suffix(pill)
        if details is not None:
            if isinstance(details,Gtk.Widget):entry.add_row(details)
            else:
                text=label(str(details));text.set_selectable(True);margins(text,14);entry.add_row(text)
        return entry

    def review_game(self,name,game_id=None):
        return next((g for g in self.games if (game_id and g['game']==game_id) or g['name']==name),None)

    def add_game_art_prefix(self,entry,game):
        if game and poster_art_path(game):
            art=Gtk.Picture.new_for_filename(poster_art_path(game))
            art.set_content_fit(Gtk.ContentFit.COVER)
            art.set_size_request(40,56)
            art.set_can_shrink(True)
            art.set_valign(Gtk.Align.CENTER)
        else:
            art=Gtk.Image(icon_name='applications-games-symbolic',pixel_size=28)
        entry.add_prefix(art)

    make_brand_icon=staticmethod(make_brand_icon)

    def artwork_preferences(self,game):
        """Role-specific local artwork with explicit, reversible selection."""
        group=Adw.PreferencesGroup(
            title='Custom Artwork',
            description='Artwork changes also sync to your local Steam library. Reset restores your original Steam artwork.',
        )
        group.add(button('Sync artwork to Steam',lambda *_:self.sync_steam_artwork(game=game)))
        group.artwork_controls={}
        accent_path=accent_source(game)
        try:
            editor_accent=artwork_accent(accent_path,self.settings.get('game_accents',{}).get(game['game'])) if accent_path else None
        except Exception:editor_accent=None
        cards=Gtk.Box(spacing=16,homogeneous=True)
        group.add(cards)
        for role,title,hint,width,height in (
            ('poster','Poster','600 × 900',72,108),
            ('capsule','Wide Capsule','920 × 430',132,62),
            ('hero','Hero','1920 × 620',156,50),
        ):
            path=poster_art_path(game) if role=='poster' else capsule_art_path(game) if role=='capsule' else game.get('hero')
            item=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12,hexpand=True)
            item.add_css_class('artwork-editor')
            if editor_accent:item.add_css_class(editor_accent)
            heading=label(title,'heading');heading.set_halign(Gtk.Align.CENTER)
            item.append(heading)
            canvas=Gtk.CenterBox(height_request=120)
            frame=Gtk.Frame(valign=Gtk.Align.CENTER,halign=Gtk.Align.CENTER)
            frame.add_css_class('artwork-preview')
            frame.set_overflow(Gtk.Overflow.HIDDEN)
            preview=FixedArtworkPicture(width,height)
            if path and Path(path).is_file():
                try:preview.set_paintable(Gdk.Texture.new_from_filename(str(path)))
                except Exception:pass
            if preview.get_paintable() is None:
                placeholder=Gtk.CenterBox(width_request=width,height_request=height)
                placeholder.set_center_widget(Gtk.Image(icon_name='applications-games-symbolic',pixel_size=24))
                frame.set_child(placeholder)
            else:frame.set_child(preview)
            canvas.set_center_widget(frame)
            item.append(canvas)
            dimensions=label(hint,'dim-label');dimensions.set_halign(Gtk.Align.CENTER)
            item.append(dimensions)
            actions=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
            controls={}
            for key,text,icon in (
                ('choose','Choose Image','image-x-generic-symbolic'),
                ('search','Browse artwork','system-search-symbolic'),
                ('reset','Reset','edit-undo-symbolic'),
            ):
                callbacks={'choose':self.choose_game_artwork,'search':self.search_game_artwork,'reset':self.reset_game_artwork}
                control=icon_button(text,icon,lambda *_,r=role,fn=callbacks[key]:fn(game,r))
                control.set_sensitive(not self.options.demo)
                control.set_tooltip_text('Preview mode' if self.options.demo else text)
                actions.append(control);controls[key]=control
            item.append(actions)
            cards.append(item)
            group.artwork_controls[role]={'row':item,'preview':preview,'canvas':canvas,**controls}
        return group

    def steam_shortcut_added(self):
        if self.options.demo:return False
        import steam_self_install
        try:return steam_self_install.shortcut_status(self.service.config,self.settings)['added']
        except Exception:return False

    def toggle_rtxforge_in_steam(self,*_):
        if self.options.demo:self.toast('Steam integration is disabled in preview mode.');return
        import steam_self_install,copy
        settings=copy.deepcopy(self.settings)
        try:status=steam_self_install.shortcut_status(self.service.config,settings)
        except Exception as error:self.error(str(error));return
        if not status['added']:self.add_rtxforge_to_steam();return
        d,b,f=self.open_panel('Remove rtxForge from Steam',width=560,height=240)
        b.append(label('Remove this app’s shortcut from Steam?','title-2'))
        b.append(label('Close Steam first. Your games, saved artwork and installed rtxForge app will be kept.','dim-label'))
        def remove(*_):
            d.close()
            def ready(result):
                self.toast('rtxForge was removed from Steam. Your saved artwork was kept.')
                self.refresh_steam_shortcut_action()
            self.start('Removing rtxForge from Steam',lambda:steam_self_install.remove(self.service.config,settings,reviewed=status),ready)
        f.append(button('Cancel',lambda *_:d.close()))
        f.append(button('Remove from Steam',remove,'destructive-action'))

    def refresh_steam_shortcut_action(self):
        added=self.steam_shortcut_added()
        if getattr(self,'steam_shortcut_row',None):
            self.steam_shortcut_row.set_title('rtxForge is in Steam' if added else 'Add rtxForge to Steam')
            self.steam_shortcut_button.set_label('Remove from Steam' if added else 'Add to Steam')
        if self.couch.page=='settings':self.couch.render()

    def add_rtxforge_to_steam(self,*_):
        if self.options.demo:self.toast('Steam integration is disabled in preview mode.');return
        import steam_self_install,copy
        settings=copy.deepcopy(self.settings)
        self.start('Checking rtxForge in Steam',lambda:steam_self_install.review(self.service.config,settings),
                   lambda review:self.review_rtxforge_steam(review,settings))

    def review_rtxforge_steam(self,review,settings):
        import steam_self_install
        titles={'poster':'Poster','capsule':'Wide capsule','hero':'Hero background','logo':'Transparent logo'}
        messages={'add':'Add the bundled artwork.','replace':'Replace existing custom artwork. Your current image will be backed up.','unchanged':'The bundled artwork is already in place.'}
        badges={'add':'New','replace':'Replace','unchanged':'Unchanged'}
        art={'game':'rtxforge:self','name':'rtxForge','capsule':str(ROOT/'packaging/steam-artwork/exports/rtxforge-steam-wide.png')}
        rows=[{'name':titles[slot['role']],'detail':messages[slot['status']],'badge':badges[slot['status']],'art':art} for slot in review['roles']]
        def run(_review):
            return steam_self_install.install(self.service.config,settings,reviewed=review)
        def done(result):
            self.refresh_steam_shortcut_action()
            if result['errors']:raise RuntimeError('The Steam shortcut is available, but some artwork still needs syncing: '+'; '.join(result['errors']))
            if result.get('preserved'):return 'rtxForge is in Steam. Your existing custom artwork was kept.'
            return 'rtxForge and its artwork are ready in Steam. Restart Steam to refresh its library.'
        profile=Gtk.Button(label='Choose Steam Profile',halign=Gtk.Align.START)
        profile.connect('clicked',lambda *_:(self.dialog.force_close() if self.dialog else None,self.choose_steam_artwork_profile()))
        flow=self.review_write('steam-shortcut',{'operation':'steam-shortcut','rows':rows,'blocked':[]},run=run,
            details=['Add rtxForge to Steam' if review['created'] else 'Refresh rtxForge artwork','Steam account '+review['profile']],
            note='Only this app’s shortcut artwork will change. Replaced images are backed up. Restart Steam afterward to refresh its library.',
            done=done,extra=profile)
        if flow is not None:flow.primary.set_label('Add & Apply Artwork' if review['created'] else 'Apply Artwork')

    def show_game_artwork(self,game):
        d,b,f=self.open_panel('Artwork · '+game.get('name','Game'),width=800,height=600)
        b.append(self.artwork_preferences(game))

    def choose_steam_artwork_profile(self,*_):
        import steam_artwork
        try:accounts=steam_artwork.profiles(self.service.config)
        except Exception as error:self.error(str(error));return
        d,b,f=self.open_panel('Steam artwork profile',width=580,height=420)
        b.append(label('Choose the local Steam account whose artwork rtxForge should update.','dim-label'))
        if not accounts:b.append(label('No Steam profile found. Open Steam once, then try again.'))
        for account in accounts:
            def choose(*_,account=account):
                self.settings['steam_artwork_profile']={'root':account['root'],'userid':account['userid']}
                library_media.save_settings(self.service.config,self.settings)
                d.close();self.toast('Steam artwork profile selected')
            b.append(button('Steam account '+account['userid']+' · '+account['root'],choose))

    def sync_steam_artwork(self,*_,game=None,refresh=False):
        import steam_artwork,copy
        if self.options.demo:self.toast('Steam artwork sync is disabled in preview mode.');return
        if self.busy and self.task_kind!='art':return
        settings=copy.deepcopy(self.settings)
        if game and refresh:
            import artwork_overrides
            game.update(artwork_overrides.apply(settings,game,game))
        targets=[game] if game else [g for g in self.games if settings.get('game_artwork',{}).get(g['game']) or settings.get('steam_artwork_pending',{}).get(g['game']) or any(g.get(role) for role in steam_artwork.SUFFIX)]
        if not targets:self.toast('No custom artwork to sync yet.');return
        def work():
            result={'images':0,'success':[],'errors':[]}
            for item in targets:
                try:
                    pending=settings.get('steam_artwork_pending',{}).get(item['game'],{})
                    changes=steam_artwork.sync_game(self.service.config,settings,item,reset_roles=[role for role,value in pending.items() if value=='reset'],include_displayed=not refresh)
                    result['images']+=sum(bool(change.get('changed')) for change in changes)
                    result['success'].append(item['game'])
                except Exception as error:result['errors'].append(item.get('name','Game')+': '+str(error))
            return result
        def ready(result):
            for key in result['success']:self.settings.setdefault('steam_artwork_pending',{}).pop(key,None)
            library_media.save_settings(self.service.config,self.settings)
            if result['errors']:
                d,b,f=self.open_panel('Artwork saved locally',width=650,height=460)
                b.append(label(str(result['images'])+' Steam images updated. Some artwork still needs syncing.','dim-label'))
                for error in result['errors']:b.append(label(error,'dim-label'))
                f.append(button('Choose Steam profile',lambda *_:(d.close(),self.choose_steam_artwork_profile())))
            else:self.toast('Artwork synced to Steam. Restart Steam if its cached images have not refreshed.')
            if refresh and not result['errors']:self.refresh_game_artwork(game)
            elif refresh:
                if getattr(self,'couch',None):self.couch.artwork_updated(game)
                self.show_games(self.games,art=False)
        if game is None:
            # Library-wide sync is reviewed first, like every other write.
            def reviewed_done(result):
                for key in result['success']:self.settings.setdefault('steam_artwork_pending',{}).pop(key,None)
                library_media.save_settings(self.service.config,self.settings)
                if result['errors']:raise RuntimeError(str(result['images'])+' Steam images updated. Some artwork still needs syncing: '+'; '.join(result['errors']))
                return str(result['images'])+' Steam images updated. Restart Steam if its cached images have not refreshed.'
            review={'operation':'artwork','rows':[{'name':item['name'],'game':item['game'],'detail':'Send your chosen artwork to Steam'} for item in targets],'blocked':[]}
            self.review_write('artwork',review,run=lambda _review:work(),details=['Sync','Replaced Steam images are backed up'],done=reviewed_done)
            return
        self.start('Syncing artwork to Steam',work,ready)

    def refresh_game_artwork(self,game):
        def ready(result):
            game.update(result)
            self._ensure_game_accent(game)
            if getattr(self,'couch',None):self.couch.artwork_updated(game)
            self.show_games(self.games,art=False)
            self.details(game)
        self.start('Updating artwork',lambda:library_media.LibraryMedia(self.service.config,self.settings).enrich(game),ready)

    def choose_game_artwork(self,game,role):
        import artwork_overrides
        if getattr(self,'_artwork_file_chooser',None) is not None:return
        # Desktop Game Details is a separate movable window, not the library.
        panel=getattr(self,'dialog',None)
        parent=panel if isinstance(panel,Gtk.Window) and panel.get_visible() else self
        chooser=Gtk.FileDialog(title='Choose '+role+' artwork')
        chooser.set_modal(True)
        self._artwork_file_chooser=chooser
        formats=Gtk.FileFilter();formats.set_name('Images (PNG, JPEG, WebP)')
        for mime in ('image/png','image/jpeg','image/webp'):formats.add_mime_type(mime)
        filters=Gio.ListStore.new(Gtk.FileFilter);filters.append(formats);chooser.set_filters(filters)
        def chosen(dialog,result):
            if getattr(self,'_artwork_file_chooser',None) is dialog:
                self._artwork_file_chooser=None
            try:path=dialog.open_finish(result).get_path()
            except GLib.Error:
                if parent.get_visible():parent.present()
                return
            if not path:return
            try:
                with open(path,'rb') as stream:data=stream.read(artwork_overrides.MAX_BYTES+1)
                artwork_overrides.store(self.service.config,self.settings,game,role,data)
            except Exception as error:self.error(str(error));return
            self.sync_steam_artwork(game=game,refresh=True)
        try:chooser.open(parent,None,chosen)
        except Exception as error:
            self._artwork_file_chooser=None
            self.error(str(error))

    def reset_game_artwork(self,game,role):
        import artwork_overrides
        try:artwork_overrides.reset(self.service.config,self.settings,game,role)
        except Exception as error:self.error(str(error));return
        game.pop(role,None)
        self.sync_steam_artwork(game=game,refresh=True)

    def show_steamgrid_connection(self,*_,on_connected=None):
        import steamgrid_client,steamgrid_credentials
        dialog,body,footer=self.open_panel('Connect SteamGridDB',width=560,height=430)
        body.append(label('Choose artwork from SteamGridDB in Desktop or Game Mode. Connect once with your own API key.','dim-label'))
        body.append(button('Get my key',lambda *_:Gio.AppInfo.launch_default_for_uri('https://www.steamgriddb.com/profile/preferences/api',None)))
        entry=Gtk.PasswordEntry(show_peek_icon=True,hexpand=True)
        entry.set_property('placeholder-text','Paste your SteamGridDB API key')
        entry.update_property([Gtk.AccessibleProperty.LABEL],['SteamGridDB API key'])
        entry.set_tooltip_text('Stored only in your system password wallet')
        body.append(entry)
        status=label('Checking your saved connection…','dim-label');status.set_wrap(True);body.append(status)
        body.append(label('Your key is saved in the system password wallet, never in app settings or your game files.','dim-label'))
        state={'closed':False,'busy':False,'saved':False,'generation':0,'token':None}
        connect=button('Connect',lambda *_:connect_key(),'suggested-action')
        disconnect=button('Disconnect',lambda *_:disconnect_key())
        footer.append(disconnect);footer.append(connect)
        def controls():
            connect.set_sensitive(not state['busy'] and not self.options.demo)
            disconnect.set_sensitive(not state['busy'] and state['saved'] and not self.options.demo)
            entry.set_sensitive(not state['busy'])
        def close(*_):
            state['closed']=True;state['generation']+=1;entry.set_text('')
            if state['token']:state['token'].cancel()
        dialog.connect('closed',close)
        def run(work,ready):
            if state['busy']:return
            state['busy']=True;state['generation']+=1
            generation=state['generation'];token=Gio.Cancellable();state['token']=token;controls()
            def finish(value,error):
                if state['closed'] or generation!=state['generation']:return False
                state['busy']=False;state['token']=None
                if error:status.set_text(error)
                else:ready(value)
                controls();return False
            def worker():
                try:value=work(token);error=None
                except (steamgrid_credentials.CredentialError,ValueError) as problem:
                    value=None;error=str(problem)
                except Exception:
                    value=None;error='Could not connect. Check your internet connection and system password wallet, then try again.'
                GLib.idle_add(finish,value,error)
            threading.Thread(target=worker,daemon=True).start()
        def connect_key():
            try:key=steamgrid_credentials.normalize_key(entry.get_text())
            except ValueError as error:status.set_text(str(error));return
            status.set_text('Checking key and saving securely…')
            def work(token):
                client=steamgrid_client.Client(key);client.validate()
                if token.is_cancelled():raise steamgrid_credentials.CredentialError('Connection cancelled.')
                steamgrid_credentials.save_key(key,cancel=token)
                return client
            def ready(client):
                entry.set_text('');state['saved']=True
                status.set_text('Connected. Desktop and Game Mode share this connection.')
                connect.set_label('Replace key')
                if on_connected:
                    dialog.close();on_connected(client)
            run(work,ready)
        def disconnect_key():
            status.set_text('Removing saved connection…')
            def ready(external):
                state['saved']=False;entry.set_text('');connect.set_label('Connect')
                status.set_text('Saved key removed. An external environment key is still configured.' if external else 'Disconnected. Your downloaded artwork stays in place.')
            run(lambda token:steamgrid_credentials.clear_key(cancel=token),ready)
        def loaded(key):
            state['saved']=bool(key);connect.set_label('Replace key' if key else 'Connect')
            status.set_text('Connected. Desktop and Game Mode share this connection.' if key else 'Get your key, paste it above, then choose Connect.')
            if not key:entry.grab_focus()
        self._steamgrid_connection_review={'dialog':dialog,'entry':entry,'status':status,'connect':connect,'disconnect':disconnect,'state':state}
        if self.options.demo:
            status.set_text('Preview only. No credentials are read or saved.');controls()
        else:run(lambda token:steamgrid_credentials.load_key(cancel=token),loaded)

    def search_game_artwork(self,game,role):
        import steamgrid_client
        if self.options.demo:
            self.open_steamgrid_search(game,role)
            return
        if getattr(self,'_steamgrid_loading',False):return
        self._steamgrid_loading=True
        def ready(client):
            self._steamgrid_loading=False
            if client:self.open_steamgrid_search(game,role,client=client)
            else:self.show_steamgrid_connection(on_connected=lambda client:self.open_steamgrid_search(game,role,client=client))
            return False
        def work():
            try:client=steamgrid_client.Client()
            except Exception:client=None
            GLib.idle_add(ready,client)
        threading.Thread(target=work,daemon=True).start()

    def open_steamgrid_search(self,game,role,client=None):
        import steamgrid_client,artwork_overrides
        from concurrent.futures import ThreadPoolExecutor
        client=client or steamgrid_client.Client()
        title={'poster':'Posters','capsule':'Wide capsules','hero':'Heroes','logo':'Logos'}[role]
        dialog,body,footer=self.open_panel(title+' for '+game['name'],width=800,height=700)
        state={'generation':0,'match':None,'page':0,'assets':[],'picked':None,'closed':False,'loading':False}
        pool=ThreadPoolExecutor(max_workers=4,thread_name_prefix='artwork-preview')
        def close(*_):
            state['closed']=True;state['generation']+=1;pool.shutdown(wait=False,cancel_futures=True)
        dialog.connect('closed',close)
        def current(token):return not state['closed'] and self.dialog is dialog and state['generation']==token
        status=label('Community artwork from SteamGridDB · static images','dim-label');status.set_wrap(True)
        stack=Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,vexpand=True)
        browse=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
        searchline=Gtk.Box(spacing=8)
        query=Gtk.SearchEntry(placeholder_text='Search for a different game',hexpand=True);query.set_text(game['name'])
        searchline.append(query);search_button=button('Search',lambda *_:search());searchline.append(search_button);browse.append(searchline)
        filters=Gtk.Box(spacing=8)
        def choice(title,values):
            box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4,hexpand=True);box.append(label(title,'caption'))
            control=Gtk.DropDown.new_from_strings(['All '+title.lower()]+[v.replace('_',' ').replace('material','Minimal').replace('image/','').replace('x',' × ') for v in values])
            control.set_hexpand(True);box.append(control);filters.append(box)
            return control,values
        style=choice('Styles',steamgrid_client.STYLES[role]);size=choice('Sizes',steamgrid_client.DIMENSIONS[role]);mime=choice('Formats',steamgrid_client.MIMES)
        browse.append(filters)
        humor=Gtk.CheckButton(label='Include humorous artwork');browse.append(humor)
        listing=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
        grid=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,min_children_per_line=2,max_children_per_line=4,column_spacing=12,row_spacing=12,homogeneous=True)
        results=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10);results.append(listing);results.append(grid)
        scroll=Gtk.ScrolledWindow(vexpand=True,min_content_height=220,hscrollbar_policy=Gtk.PolicyType.NEVER);scroll.set_child(results);browse.append(scroll)
        preview=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
        picture=Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN,can_shrink=True,vexpand=True,height_request=310)
        credit=label('','dim-label');credit.set_wrap(True);preview.append(picture);preview.append(credit)
        stack.add_named(browse,'browse');stack.add_named(preview,'preview');body.append(status);body.append(stack)
        back=button('Back to results',lambda *_:back_to_results());back.set_visible(False)
        more=button('Load more',lambda *_:load_artwork(True));more.set_visible(False)
        apply=button('Use artwork',lambda *_:save(),'suggested-action');apply.set_visible(False)
        footer.append(back);footer.append(more);footer.append(apply)
        def choice_value(pair):
            control,values=pair;index=control.get_selected();return values[index-1] if 0<index<=len(values) else ''
        def request(work,done,token):
            if not current(token):return
            def execute():
                try:result=work();error=None
                except Exception as ex:result=None;error=str(ex)
                def deliver():
                    if not current(token):return False
                    state['loading']=False;search_button.set_sensitive(True)
                    if error:status.set_text(error);more.set_sensitive(True)
                    else:
                        try:done(result)
                        except Exception as ex:status.set_text(str(ex))
                    return False
                GLib.idle_add(deliver)
            pool.submit(execute)
        def clear_results():
            clear(listing)
            while grid.get_first_child():grid.remove(grid.get_first_child())
        def back_to_results():
            state['generation']+=1;state['picked']=None;stack.set_visible_child_name('browse');back.set_visible(False);apply.set_visible(False);more.set_visible(bool(state['assets']))
            status.set_text(title+' · choose an image to preview and apply')
        def select_asset(asset):
            state['generation']+=1;token=state['generation'];status.set_text('Loading full-size preview…');state['picked']=None;more.set_visible(False);apply.set_sensitive(False)
            def ready(data):
                artwork_overrides.dimensions(data)
                picture.set_paintable(Gdk.Texture.new_from_bytes(GLib.Bytes.new(data)))
                state['picked']=(asset,data);credit.set_text(str(asset.get('width','?'))+' × '+str(asset.get('height','?'))+' · '+str((asset.get('author') or {}).get('name','Community artist')))
                stack.set_visible_child_name('preview');back.set_visible(True);apply.set_visible(True);apply.set_sensitive(True);status.set_text('Apply this '+role+' to rtxForge and your selected Steam library.');apply.grab_focus()
            request(lambda:client.download(asset),ready,token)
        def thumbnail(asset,pic,token):
            try:
                data=client.thumbnail(asset);loader=GdkPixbuf.PixbufLoader.new();invalid=[]
                def prepared(loader,w,h):
                    if w*h>40_000_000:invalid.append(True)
                    loader.set_size(192,288 if role=='poster' else 100)
                loader.connect('size-prepared',prepared);loader.write(data);loader.close();pixbuf=loader.get_pixbuf()
                if invalid or pixbuf is None:return
                def paint():
                    if not state['closed'] and self.dialog is dialog and asset in state['assets']:pic.set_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
                    return False
                GLib.idle_add(paint)
            except Exception:pass
        def render_assets(assets,append,token,page):
            state['page']=page
            if not append:clear_results();state['assets']=[]
            seen={x.get('id') for x in state['assets']}
            for asset in assets:
                if not isinstance(asset,dict) or not asset.get('url') or asset.get('id') in seen:continue
                state['assets'].append(asset);seen.add(asset.get('id'))
                card=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6)
                pic=FixedArtworkPicture(144,216 if role=='poster' else 82);card.append(pic)
                author=label(str((asset.get('author') or {}).get('name','Community artist')),'caption');author.set_ellipsize(Pango.EllipsizeMode.END);card.append(author)
                control=Gtk.Button();control.set_child(card);control.add_css_class('artwork-preview');control.set_tooltip_text(str(asset.get('width','?'))+' × '+str(asset.get('height','?'))+' · '+author.get_text());control.connect('clicked',lambda _,a=asset:select_asset(a));grid.append(control)
                pool.submit(thumbnail,asset,pic,token)
            status.set_text(str(len(state['assets']))+' '+title.lower()+' · '+state['match']['name'] if state['assets'] else 'No artwork matches these filters. Try another style or size.')
            more.set_visible(bool(assets) and state['page']<100);more.set_sensitive(True)
        def load_artwork(append=False):
            if not state['match']:return
            state['generation']+=1;token=state['generation'];page=state['page']+1 if append else 0
            if not append:clear_results();state['assets']=[];more.set_visible(False)
            status.set_text('Finding '+title.lower()+'…');more.set_sensitive(False);stack.set_visible_child_name('browse');back.set_visible(False);apply.set_visible(False)
            args={'page':page,'style':choice_value(style),'dimensions':choice_value(size),'mime':choice_value(mime),'humor':humor.get_active()};match=state['match']['id']
            request(lambda:client.artwork(match,role,**args),lambda assets:render_assets(assets,append,token,page),token)
        def choose_match(match):state['match']=match;load_artwork()
        def games_ready(matches):
            clear_results();state['assets']=[];state['match']=None;more.set_visible(False)
            exact=[m for m in matches if str(m.get('name','')).casefold()==query.get_text().strip().casefold()]
            if len(exact)==1:choose_match(exact[0]);return
            status.set_text('Choose the matching game.' if matches else 'No matching games. Try another title or upload an image.')
            for match in matches:listing.append(button(str(match.get('name','Unknown game')),lambda *_,m=match:choose_match(m)))
        def search():
            state['generation']+=1;token=state['generation'];term=query.get_text().strip();search_button.set_sensitive(False);status.set_text('Searching games…')
            request(lambda:client.search(term),games_ready,token)
        def save():
            if not state['picked']:return
            asset,data=state['picked']
            try:artwork_overrides.store(self.service.config,self.settings,game,role,data,credit='SteamGridDB · '+str((asset.get('author') or {}).get('name','Community artist')))
            except Exception as ex:status.set_text(str(ex));return
            dialog.close();self.sync_steam_artwork(game=game,refresh=True)
        query.connect('activate',lambda *_:search())
        for control,_ in (style,size,mime):control.connect('notify::selected',lambda *_:load_artwork())
        humor.connect('toggled',lambda *_:load_artwork())
        self._steamgrid_review={'dialog':dialog,'stack':stack,'grid':grid,'state':state,'status':status,'select':select_asset,'back':back_to_results,'search':search,'style':style[0],'more':more}
        search()

    def preview_steamgrid_artwork(self,asset,selected):
        import steamgrid_client
        # Keep the browser dialog open; preview is a child window.
        def ready(data):
            try:
                raw=GLib.Bytes.new(data);texture=Gdk.Texture.new_from_bytes(raw)
            except Exception as error:self.error(str(error));return
            preview=Gtk.Window(title='Artwork preview',transient_for=self,modal=True,default_width=640,default_height=480)
            body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12);margins(body,16)
            picture=Gtk.Picture.new_for_paintable(texture);picture.set_content_fit(Gtk.ContentFit.CONTAIN);picture.set_vexpand(True);body.append(picture)
            body.append(button('Use Artwork',lambda *_:(preview.close(),selected(asset,data)),'suggested-action'))
            body.append(button('Cancel',lambda *_:preview.close()))
            preview.set_child(body);preview.present()
        self.start('Loading artwork preview',lambda:steamgrid_client.Client.download(asset),ready)

    def show_extras(self,*_):
        self.show_page('extras')

    def show_diagnostics(self,game):
        import runtime_diagnostics,json
        def ready(report):
            d,b,f=self.open_panel(game['name']+' · NR Diagnosis')
            for observation in report['observations']:b.append(label(observation))
            b.append(label('Visible result: '+report['visual_result'],'heading'))
            view=Gtk.TextView(editable=False,monospace=True,wrap_mode=Gtk.WrapMode.WORD_CHAR)
            view.get_buffer().set_text(json.dumps(report,indent=2))
            scroller=Gtk.ScrolledWindow(min_content_height=240,vexpand=True,hscrollbar_policy=Gtk.PolicyType.NEVER)
            scroller.set_child(view);b.append(scroller)
            f.append(button('Refresh',lambda *_:self.show_diagnostics(game)))
        if self.options.demo:
            ready({'observations':['Demo: diagnosis reads the selected game’s settings, exact runtime hashes, and bounded log tail.'],'visual_result':'Not tested'})
        else:self.start('Reading NR evidence',lambda:runtime_diagnostics.inspect(game),ready)

    def choose_extra(self,game,kind):
        import extra_tools
        chooser=Gtk.FileDialog(title='Choose x64 ReShade DLL' if kind=='reshade' else 'Choose .addon64 file')
        def chosen(dialog,result):
            try:path=dialog.open_finish(result).get_path()
            except GLib.Error:return
            if not path:return
            self.start('Preparing tool review',lambda:extra_tools.prepare(self.service.config,game,path,kind),self.review_extra)
        chooser.open(self,None,chosen)

    def review_extra(self,plan):
        import extra_tools
        changes='\n'.join('Add '+change['path']+'\nSHA-256: '+change['after'] for change in plan['changes'])
        review={'operation':'tool','rows':[{'name':plan['name'],'game':plan.get('game'),'detail':changes}],'blocked':[]}
        self.review_write('tool',review,
            run=lambda _review:extra_tools.apply(self.service.config,plan),
            details=['Install','Add '+extra_tools.KINDS[plan['kind']]],
            note='This native code will run inside the game. The hash identifies the selected file; it does not establish its publisher or safety.',
            trust='I trust the source of this exact file',
            done=lambda _:'Tool installed. Recovery is available in Tools.')

    def review_extra_restore(self,record):
        import extra_tools
        review={'operation':'tool-restore','rows':[{'name':record['name'],'game':record.get('game'),'detail':'Changed files will be refused. Game saves and other tools are preserved.'}],'blocked':[]}
        self.review_write('tool-restore',review,
            run=lambda _review:extra_tools.restore(self.service.config,record['path']),
            details=['Restore','This tool’s original files'],
            done=lambda _:'Tool restored.')

    def show_packages(self,*_):
        return show_packages(self)

    def select_package(self,provider,values):
        if self.busy:raise ValueError('Wait for the current operation to finish.')
        self.settings.update(values);self.settings['runtime_provider']=provider
        self.nr_only.set_enabled(provider in ('dlss-unlocked','custom'))
        def ready(*_):
            if self.selected_game_ids:self.launch_action('install',visual_settings=dict(self.settings))
            else:self.toast('Package selected. Select games, then choose Install Features.')
        if self.options.demo:ready()
        else:self.start('Saving package choice',lambda:library_media.save_settings(self.service.config,self.settings),ready)

    def set_start_page(self,page):
        self.settings['start_page']=page
        if not self.options.demo:library_media.save_settings(self.service.config,self.settings)

    def set_ui_mode(self,mode,persist=True):
        if mode not in ('classic','new'):mode='classic'
        if self.busy and persist:self.toast('Finish the current operation before switching interfaces.');return
        width,height=self.get_default_size()
        if self._new_stack is not None:
            self._new_stack.remove(self._canonical_library)
            self._new_stack=None
        self.set_content(None)
        if mode=='new':
            self._new_shell,self._new_stack=new_shell(self,self._canonical_library)
            self.set_content(self._new_shell)
        else:self.set_content(self._canonical_library);self._new_shell=None
        self.set_default_size(width if width>1 else 1280,height if height>1 else 820)
        self.settings['ui_mode']=mode
        if persist and not self.options.demo:library_media.save_settings(self.service.config,self.settings)
        GLib.idle_add(self.update_library_spacing)

    def toggle_compact_header(self,*_):
        self.settings['compact_header']=not self.settings.get('compact_header',True)
        self.settings['compact_header_chosen']=True
        self._collapse_library_header(self._library_scroll_adjustment)
        if not self.options.demo:library_media.save_settings(self.service.config,self.settings)

    def title_button(self,icon,title,callback):
        b=Gtk.Button(icon_name=icon);b.set_tooltip_text(title);b.update_property([Gtk.AccessibleProperty.LABEL],[title]);b.add_css_class('title-action');b.connect('clicked',callback);return b

    def _clear_library_ghost_slots(self):
        flow=getattr(
            self,
            'flow',
            None,
        )

        ghosts=list(
            getattr(
                self,
                'ghost_slots',
                [],
            )
        )

        if flow is not None:
            for entry in ghosts:
                wrapper=entry.get(
                    'wrapper'
                )

                if (
                    wrapper is not None
                    and wrapper.get_parent() is flow
                ):
                    flow.remove(
                        wrapper
                    )

        self.ghost_slots=[]


    def _sync_library_ghost_slots(
        self,
        slot_count,
        visible_count,
        view,
    ):
        """Keep the final gallery row structurally full without fake games."""

        if (
            view=='list'
            or slot_count<=0
            or visible_count<=0
        ):
            desired=0
        else:
            desired=(
                slot_count
                - (
                    visible_count
                    % slot_count
                )
            ) % slot_count

        current=list(
            getattr(
                self,
                'ghost_slots',
                [],
            )
        )

        reusable=(
            len(current)==desired
            and all(
                entry.get(
                    'view'
                )==view
                and entry.get(
                    'wrapper'
                ) is not None
                and entry[
                    'wrapper'
                ].get_parent() is self.flow
                for entry in current
            )
        )

        if reusable:
            return current

        self._clear_library_ghost_slots()

        for _index in range(
            desired
        ):
            ghost=FixedLibraryCard(
                orientation=Gtk.Orientation.VERTICAL,
            )

            ghost.add_css_class(
                'library-ghost-card'
            )
            ghost.set_sensitive(
                False
            )
            ghost.set_overflow(
                Gtk.Overflow.HIDDEN
            )

            center=Gtk.CenterBox()
            center.set_hexpand(
                True
            )
            center.set_vexpand(
                True
            )

            icon=Gtk.Image.new_from_icon_name(
                'applications-games-symbolic'
            )
            icon.set_pixel_size(
                22
            )
            icon.add_css_class(
                'library-ghost-icon'
            )

            center.set_center_widget(
                icon
            )
            ghost.append(
                center
            )

            self.flow.insert(
                ghost,
                -1,
            )

            wrapper=ghost.get_parent()
            wrapper.set_halign(
                Gtk.Align.START
            )
            wrapper.set_valign(
                Gtk.Align.START
            )
            wrapper.set_hexpand(
                False
            )
            wrapper.set_vexpand(
                False
            )

            self.ghost_slots.append(
                {
                    'view':view,
                    'widget':ghost,
                    'wrapper':wrapper,
                }
            )

        return list(
            self.ghost_slots
        )


    def _library_viewport_changed(
        self,
        adjustment,
        *_,
    ):
        """Schedule gallery geometry when the visible viewport changes."""

        width=int(
            round(
                adjustment.get_page_size()
            )
        )

        if width<=1:
            return

        if width==getattr(
            self,
            '_library_viewport_width',
            0,
        ):
            return

        self._library_viewport_width=width

        # Coalesce resize bursts. The eventual layout reads page_size
        # again, so it always solves against the newest allocation.
        if getattr(
            self,
            '_library_resize_source',
            0,
        ):
            return

        self._library_resize_source=GLib.idle_add(
            self._apply_library_viewport_resize
        )

    def _apply_library_viewport_resize(self):
        self._library_resize_source=0

        self.update_library_spacing()

        return False

    def _library_vertical_extent_changed(
        self,
        *_,
    ):
        """Re-solve gallery width when overlay scrollbar state changes."""

        if getattr(
            self,
            '_library_resize_source',
            0,
        ):
            return

        self._library_resize_source=GLib.idle_add(
            self._apply_library_viewport_resize
        )


    def update_library_spacing(self,*_):
        """Fit the preferred 3–9 columns to a readable live viewport."""

        flow=getattr(
            self,
            'flow',
            None,
        )

        if flow is None:
            return False

        view=self.settings.get(
            'library_view',
            'posters',
        )

        entries=[
            entry
            for entry in getattr(
                self,
                'cards',
                {},
            ).values()
            if entry.get(
                'wrapper'
            ) is not None
        ]

        # Always clear old per-row remainder corrections first.
        for entry in entries:
            wrapper=entry[
                'wrapper'
            ]
            wrapper.set_margin_start(
                0
            )
            wrapper.set_margin_end(
                0
            )

        # --------------------------------------------------------
        # LIST VIEW
        # --------------------------------------------------------

        if view=='list':
            self._clear_library_ghost_slots()
            return False

        scroll=getattr(
            self,
            'library_scroll',
            None,
        )

        if scroll is None:
            return False

        # --------------------------------------------------------
        # REAL VIEWPORT AUTHORITY
        # --------------------------------------------------------

        hadj=scroll.get_hadjustment()

        viewport_width=(
            int(
                round(
                    hadj.get_page_size()
                )
            )
            if hadj is not None
            else 0
        )

        if viewport_width<=1:
            viewport_width=int(
                scroll.get_width()
            )

            vscroll=scroll.get_vscrollbar()

            if (
                vscroll is not None
                and vscroll.get_visible()
                and vscroll.get_width()>0
            ):
                viewport_width=max(
                    1,
                    viewport_width
                    - vscroll.get_width(),
                )

        if viewport_width<=1:
            return False

        # The adjustment is the full content viewport. Overlay scrollbars do
        # not consume layout width; reserve equal insets on both sides only.
        OUTER_INSET=self.page_side_margin(viewport_width)
        self.apply_page_margins(OUTER_INSET)
        usable_width=max(1,viewport_width-OUTER_INSET*2)

        # As many columns as fit at the slider's size; the solver below then
        # widens them so the row ends flush with the edge (Windows
        # ApplyGridMetrics: 212 px posters / 300 px capsules at 100%).
        preferred_gap=16
        preferred_width=(300 if view=='capsules' else 212)*self.library_art_scale()/100
        slot_count=max(1,int((usable_width+preferred_gap)//(preferred_width+preferred_gap)))
        visible_entries=[
            entry
            for entry in entries
            if entry[
                'wrapper'
            ].get_visible()
        ]
        # Never ask cards to be narrower than their own content allows (title,
        # source and test pills): fewer columns rather than a clipped row.
        content_minimum=0
        for entry in visible_entries[:12]:
            text=entry.get('text')
            if text is not None:content_minimum=max(content_minimum,text.measure(Gtk.Orientation.HORIZONTAL,-1)[0])
        content_minimum+=12
        while slot_count>1 and (usable_width-preferred_gap*(slot_count-1))//slot_count<content_minimum:
            slot_count-=1

        for entry in entries:
            entry[
                'widget'
            ].remove_css_class(
                'library-stripe-a'
            )
            entry[
                'widget'
            ].remove_css_class(
                'library-stripe-b'
            )

        for index,entry in enumerate(
            visible_entries
        ):
            entry[
                'widget'
            ].add_css_class(
                'library-stripe-a'
                if index%2==0
                else 'library-stripe-b'
            )

        visible_count=len(
            visible_entries
        )

        ghosts=self._sync_library_ghost_slots(
            slot_count,
            visible_count,
            view,
        )

        # Every Poster/Wide slot has exactly the same allocation.
        # Card dimensions remain dynamically calculated from the viewport.
        flow.set_homogeneous(
            False
        )
        flow.set_min_children_per_line(
            slot_count
        )
        flow.set_max_children_per_line(
            slot_count
        )
        flow.set_row_spacing(
            16
        )
        flow.set_margin_start(
            OUTER_INSET
        )
        flow.set_margin_end(
            OUTER_INSET
        )
        flow.set_hexpand(
            False
        )
        flow.set_halign(
            Gtk.Align.START
        )

        # --------------------------------------------------------
        # VIEWPORT-SCALED CARD SIZE
        # --------------------------------------------------------

        (
            _art_value,
            _preferred_art_width,
            _preferred_art_height,
            info_height,
            _preferred_total_height,
            ratio,
        )=self.library_card_geometry(
            100,
            view,
        )

        # Fixed slot count is authoritative. Cards simply consume the
        # available viewport width evenly.
        #
        # Prefer the normal visual gap when there is room. At unusually
        # narrow widths the gap compresses before the slot count changes.
        minimum_workable_card=24

        if slot_count>1:
            maximum_gap_that_fits=max(
                0,
                (
                    usable_width
                    - (
                        minimum_workable_card
                        * slot_count
                    )
                )
                // (
                    slot_count-1
                ),
            )

            base_gap=min(
                preferred_gap,
                maximum_gap_that_fits,
            )
        else:
            base_gap=0

        card_width=max(
            5,
            (
                usable_width
                - (
                    base_gap
                    * (
                        slot_count-1
                    )
                )
            )
            // slot_count,
        )

        actual_art_width=max(
            1,
            card_width-10,
        )

        actual_art_height=max(
            1,
            int(
                round(
                    actual_art_width
                    / ratio
                )
            ),
        )

        # The row always spans exactly between the two 16px insets.
        spare_width=max(
            0,
            usable_width
            - (
                card_width
                * slot_count
            ),
        )

        if slot_count>1:
            dynamic_gap=(
                spare_width
                // (
                    slot_count-1
                )
            )

            remainder=(
                spare_width
                - (
                    dynamic_gap
                    * (
                        slot_count-1
                    )
                )
            )
        else:
            dynamic_gap=0
            remainder=0

        flow.set_column_spacing(
            dynamic_gap
        )

        # Compact physical cards must retain the wrapped-title behavior
        # regardless of the saved slider value.
        compact_titles=(
            actual_art_width
            < 112
        )

        if compact_titles:
            info_height=max(
                info_height,
                62,
            )

        if actual_art_width < 92:
            title_class='art-title-xs'
        elif actual_art_width < 120:
            title_class='art-title-sm'
        elif actual_art_width < 152:
            title_class='art-title-md'
        else:
            title_class='art-title-lg'

        title_classes=(
            'art-title-xs',
            'art-title-sm',
            'art-title-md',
            'art-title-lg',
        )

        provisional_height=(
            actual_art_height
            + info_height
            + 7
        )

        # --------------------------------------------------------
        # APPLY ONE REAL-CARD TEMPLATE
        # --------------------------------------------------------

        for entry in entries:
            wrapper=entry[
                'wrapper'
            ]
            card=entry[
                'widget'
            ]
            overlay=entry.get(
                'overlay'
            )
            click=entry.get(
                'click'
            )
            picture=entry[
                'picture'
            ]
            text_box=entry.get(
                'text'
            )
            title=entry.get(
                'title'
            )

            wrapper.set_size_request(
                card_width,
                provisional_height,
            )
            wrapper.set_halign(
                Gtk.Align.START
            )
            wrapper.set_valign(
                Gtk.Align.START
            )
            wrapper.set_hexpand(
                False
            )
            wrapper.set_vexpand(
                False
            )

            if isinstance(
                card,
                FixedLibraryCard,
            ):
                card.fixed_width=(
                    card_width
                )
                card.fixed_height=(
                    provisional_height
                )

            card.set_size_request(
                card_width,
                provisional_height,
            )
            card.set_halign(
                Gtk.Align.FILL
            )
            card.set_valign(
                Gtk.Align.START
            )
            card.set_hexpand(
                True
            )
            card.set_vexpand(
                False
            )

            if overlay is not None:
                overlay.set_size_request(
                    actual_art_width,
                    actual_art_height,
                )
                overlay.set_halign(
                    Gtk.Align.FILL
                )
                overlay.set_hexpand(
                    True
                )

            if click is not None:
                click.set_size_request(
                    actual_art_width,
                    actual_art_height,
                )
                click.set_halign(
                    Gtk.Align.FILL
                )
                click.set_hexpand(
                    True
                )

            picture.cover_width=(
                actual_art_width
            )
            picture.cover_ratio=ratio
            picture.set_size_request(
                actual_art_width,
                actual_art_height,
            )
            picture.set_halign(
                Gtk.Align.FILL
            )
            picture.set_hexpand(
                True
            )

            card_for_scale=entry.get(
                'widget'
            )

            card_scale_class={
                'art-title-xs':'art-card-xs',
                'art-title-sm':'art-card-sm',
                'art-title-md':'art-card-md',
                'art-title-lg':'art-card-lg',
            }.get(
                title_class,
                'art-card-lg',
            )

            if card_for_scale is not None:
                for css_class in (
                    'art-card-xs',
                    'art-card-sm',
                    'art-card-md',
                    'art-card-lg',
                ):
                    card_for_scale.remove_css_class(
                        css_class
                    )

                card_for_scale.add_css_class(
                    card_scale_class
                )

            if title is not None:
                for css_class in title_classes:
                    title.remove_css_class(
                        css_class
                    )

                title.add_css_class(
                    title_class
                )

                # Keep title space compact even when one name is unusually long.
                title.set_wrap(True)
                title.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
                title.set_lines(2)
                title.set_vexpand(True)
                title.set_valign(Gtk.Align.FILL)
                title.set_yalign(0.5)
                title.set_single_line_mode(
                    False
                )
                title.set_width_chars(
                    1
                )
                title.set_max_width_chars(
                    1
                )
                title.set_ellipsize(
                    Pango.EllipsizeMode.END
                )
                title.set_size_request(
                    -1,
                    -1,
                )
                title.set_hexpand(
                    True
                )
                title.queue_resize()

            meta_row=entry.get('meta_row')
            if meta_row is not None:
                meta_row.set_orientation(Gtk.Orientation.HORIZONTAL)
                meta_row.set_homogeneous(False)
                test=entry['test_meta']
                tested=test.get_visible()
                test.set_halign(Gtk.Align.START)
                test.set_fixed_width(28)
                test._label.set_visible(False)
                test._content.set_margin_start(7);test._content.set_margin_end(7)
                status=entry['meta']
                status.set_halign(Gtk.Align.START)
                status_width=max(28,min(132,card_width-28-(34 if tested else 0)))
                status.set_fixed_width(status_width)
                status._label.set_visible(status_width>=86)
                status.set_tooltip_text(status._label.get_text().title())
                status._content.set_margin_start(7 if status_width<86 else 9)
                status._content.set_margin_end(7 if status_width<86 else 8)

            if text_box is not None:
                text_box.set_size_request(
                    -1,
                    -1,
                )
                text_box.set_halign(
                    Gtk.Align.FILL
                )
                text_box.set_hexpand(
                    True
                )
                text_box.queue_resize()

            entry[
                'size'
            ]=(
                actual_art_width,
                actual_art_height,
            )

        # --------------------------------------------------------
        # PRESERVE "TALLEST CARD WINS"
        # --------------------------------------------------------

        for offset in range(0,len(visible_entries),slot_count):
            group=visible_entries[offset:offset+slot_count]
            measured=[]
            for entry in group:
                title=entry.get('title')
                if title is None:continue
                title.set_attributes(None)
                layout=title.create_pango_layout(title.get_text())
                layout.set_width(-1)
                measured.append((title,layout.get_pixel_size()[0]))
            available=max(1,card_width-36)
            if any(width>available for _,width in measured):
                for title,width in measured:
                    if width*1.15<=available:
                        attrs=Pango.AttrList();attrs.insert(Pango.attr_scale_new(1.15));title.set_attributes(attrs)
        tallest_footer=info_height

        for entry in visible_entries:
            text_box=entry.get(
                'text'
            )

            if text_box is None:
                continue

            (
                _minimum,
                natural,
                _minimum_baseline,
                _natural_baseline,
            )=text_box.measure(
                Gtk.Orientation.VERTICAL,
                card_width-4,
            )

            tallest_footer=max(
                tallest_footer,
                natural,
            )

        uniform_height=(
            actual_art_height
            + tallest_footer
            + 7
        )

        for entry in entries:
            wrapper=entry[
                'wrapper'
            ]
            card=entry[
                'widget'
            ]
            text_box=entry.get(
                'text'
            )

            if text_box is not None:
                text_box.set_size_request(
                    -1,
                    tallest_footer,
                )
                text_box.set_vexpand(
                    False
                )

            if isinstance(
                card,
                FixedLibraryCard,
            ):
                card.fixed_width=(
                    card_width
                )
                card.fixed_height=(
                    uniform_height
                )

            card.set_size_request(
                card_width,
                uniform_height,
            )

            wrapper.set_size_request(
                card_width,
                uniform_height,
            )

        # Ghosts occupy exactly the same complete card slot.
        for ghost in ghosts:
            wrapper=ghost[
                'wrapper'
            ]
            card=ghost[
                'widget'
            ]

            wrapper.set_margin_start(
                0
            )
            wrapper.set_margin_end(
                0
            )
            wrapper.set_size_request(
                card_width,
                uniform_height,
            )
            wrapper.set_halign(
                Gtk.Align.START
            )
            wrapper.set_valign(
                Gtk.Align.START
            )
            wrapper.set_hexpand(
                False
            )
            wrapper.set_vexpand(
                False
            )

            card.fixed_width=(
                card_width
            )
            card.fixed_height=(
                uniform_height
            )
            card.set_size_request(
                card_width,
                uniform_height,
            )
            card.set_halign(
                Gtk.Align.FILL
            )
            card.set_hexpand(
                True
            )

        # --------------------------------------------------------
        # INTEGER REMAINDER
        #
        # FlowBox owns the uniform gap. At most slot_count-2 pixels
        # remain after integer division. Add those one at a time to
        # inter-card gaps, repeating identically on every row.
        # --------------------------------------------------------

        layout_entries=(
            visible_entries
            + ghosts
        )

        for index,entry in enumerate(
            layout_entries
        ):
            position=(
                index
                % slot_count
            )

            entry[
                'wrapper'
            ].set_margin_start(
                1
                if (
                    1 <= position <= remainder
                )
                else 0
            )
            entry[
                'wrapper'
            ].set_margin_end(
                0
            )

        # Hidden real cards must never retain a correction from an older
        # visible/filter state.
        for entry in entries:
            if not entry[
                'wrapper'
            ].get_visible():
                entry[
                    'wrapper'
                ].set_margin_start(
                    0
                )
                entry[
                    'wrapper'
                ].set_margin_end(
                    0
                )

        flow.set_size_request(
            usable_width,
            -1,
        )
        flow.set_hexpand(
            False
        )
        flow.set_halign(
            Gtk.Align.START
        )

        for entry in entries:
            entry[
                'picture'
            ].queue_resize()

            overlay=entry.get(
                'overlay'
            )
            if overlay is not None:
                overlay.queue_resize()

            click=entry.get(
                'click'
            )
            if click is not None:
                click.queue_resize()

            entry[
                'widget'
            ].queue_resize()
            entry[
                'wrapper'
            ].queue_resize()

        for ghost in ghosts:
            ghost[
                'widget'
            ].queue_resize()
            ghost[
                'wrapper'
            ].queue_resize()

        flow.queue_resize()
        flow.queue_allocate()

        return False


    def hide_operation_status(self,*_):
        if self.operation_hide_source:
            try:GLib.source_remove(self.operation_hide_source)
            except Exception:pass
            self.operation_hide_source=0
        self.operation_spinner.stop();self.operation_revealer.set_reveal_child(False)
        return False
    def show_operation_status(self,text,complete=False,icon='object-select-symbolic'):
        if self.operation_hide_source:
            try:GLib.source_remove(self.operation_hide_source)
            except Exception:pass
            self.operation_hide_source=0
        self.operation_status.set_text(user_messages.friendly_status(text))
        self.operation_revealer.set_reveal_child(True)
        if complete:
            self.operation_spinner.stop();self.operation_spinner.set_visible(False)
            self.operation_icon.set_from_icon_name(icon);self.operation_icon.set_visible(True)
            self.operation_icon.remove_css_class('operation-error')
            if icon=='dialog-warning-symbolic':self.operation_icon.add_css_class('operation-error')
            self.operation_elapsed.set_text('')
            self.operation_dismiss.set_visible(True)
            self.operation_hide_source=GLib.timeout_add(4000,self.hide_operation_status)
        else:
            self.operation_icon.set_visible(False);self.operation_dismiss.set_visible(False)
            self.operation_spinner.set_visible(True);self.operation_spinner.start()
        return False
    # ========================================================
    # GTK COLUMN VIEW — STRUCTURED LIST MODE
    # ========================================================

    def _column_factory(
        self,
        setup,
        bind,
        unbind=None,
    ):
        factory=Gtk.SignalListItemFactory()

        factory.connect(
            'setup',
            setup,
        )

        factory.connect(
            'bind',
            bind,
        )
        factory.connect('bind',lambda *_:GLib.idle_add(lambda:(self._column_sync_selection_widgets(),False)[1]))

        if unbind is not None:
            factory.connect(
                'unbind',
                unbind,
            )

        return factory


    def _column_sorter(self,property_name):
        expression=Gtk.PropertyExpression.new(
            LibraryGameItem,
            None,
            property_name,
        )

        return Gtk.StringSorter.new(
            expression
        )


    def _build_library_column_view(self):
        self.list_name_cells={}
        self.list_action_cells={}

        self.list_store=Gio.ListStore.new(
            LibraryGameItem
        )

        self.list_filter=Gtk.CustomFilter.new(
            self._column_filter_match
        )

        self.list_filter_model=Gtk.FilterListModel.new(
            self.list_store,
            self.list_filter,
        )

        view=Gtk.ColumnView(
            hexpand=True,
            vexpand=True,
        )

        view.add_css_class(
            'library-column-view'
        )
        view.set_halign(
            Gtk.Align.FILL
        )


        view.set_show_column_separators(
            False
        )

        view.set_show_row_separators(
            False
        )

        view.set_single_click_activate(
            False
        )

        # GTK exposes reordering at the whole-view level. We enable it,
        # then enforce Game/Name at index zero after any drag operation.
        view.set_reorderable(
            True
        )

        name_factory=self._column_factory(
            self._column_name_setup,
            self._column_name_bind,
            self._column_name_unbind,
        )

        location_factory=self._column_factory(
            self._column_location_setup,
            self._column_location_bind,
        )

        status_factory=self._column_factory(
            self._column_status_setup,
            self._column_status_bind,
        )

        features_factory=self._column_factory(
            self._column_features_setup,
            self._column_features_bind,
        )

        actions_factory=self._column_factory(
            self._column_actions_setup,
            self._column_actions_bind,
            self._column_actions_unbind,
        )

        specs=(
            # Game owns spare viewport width.
            # Game and Location may be resized.
            # Utility columns use natural content width.
            (
                'Game',
                'name',
                name_factory,
                -1,
                True,
                True,
            ),
            (
                'Location',
                'location',
                location_factory,
                240,
                True,
                False,
            ),
            (
                'Status',
                'status',
                status_factory,
                124,
                False,
                False,
            ),
            (
                'Features',
                'features',
                features_factory,
                132,
                False,
                False,
            ),
            (
                'Actions',
                None,
                actions_factory,
                -1,
                False,
                False,
            ),
        )

        self.list_columns={}

        for (
            title,
            sort_property,
            factory,
            width,
            resizable,
            expand,
        ) in specs:
            column=Gtk.ColumnViewColumn.new(
                title,
                factory,
            )

            column.set_fixed_width(
                width
            )

            column.set_resizable(
                False
            )

            # Game retains its explicit user-controlled width.
            # Fixed right-side columns keep their base width but may
            # absorb spare viewport space instead of bunching left.
            column.set_expand(
                expand
            )

            try:
                column.set_id(
                    title.casefold()
                )
            except Exception:
                pass

            if sort_property is not None:
                column.set_sorter(
                    self._column_sorter(
                        sort_property
                    )
                )

            view.append_column(
                column
            )

            self.list_columns[
                title
            ]=column

        self.list_name_column=self.list_columns[
            'Game'
        ]

        self.list_name_column.connect(
            'notify::fixed-width',
            self._column_name_width_changed,
        )

        self.list_location_column=self.list_columns[
            'Location'
        ]

        self.list_location_column.connect(
            'notify::fixed-width',
            self._column_location_width_changed,
        )

        self._column_width_guard=False
        self._column_location_width_guard=False
        self._column_order_guard=False
        self._column_height_refresh_source=0
        self._column_rows_tall=False

        columns_model=view.get_columns()

        columns_model.connect(
            'items-changed',
            self._column_order_changed,
        )

        self.list_sort_model=Gtk.SortListModel.new(
            self.list_filter_model,
            view.get_sorter(),
        )

        self.list_sort_model.connect('items-changed',lambda *_:GLib.idle_add(self._column_sync_selection_widgets))
        self.list_selection_model=Gtk.NoSelection.new(
            self.list_sort_model
        )

        view.set_model(
            self.list_selection_model
        )

        view.connect(
            'activate',
            self._column_activate,
        )

        return view


    def _column_density_changed(self,*_):
        stage=self.library_stack.get_width()
        if stage>1:self.apply_page_margins(self.page_side_margin(stage))
        width=self.column_scroll.get_hadjustment().get_page_size()
        if width<=1:return
        for title,minimum in (('Location',1060),('Features',860)):
            column=self.list_columns.get(title)
            if column is not None and column.get_visible()!=(width>=minimum):
                column.set_visible(width>=minimum)

    def _column_name_width_changed(self,column,*_):
        width=column.get_fixed_width()
        if 0<=width<420:
            column.set_fixed_width(420)
        # Keep spare viewport space filled while individual columns resize.
        column.set_expand(True)


    def _column_location_width_changed(
        self,
        column,
        *_,
    ):
        if getattr(
            self,
            '_column_location_width_guard',
            False,
        ):
            return

        width=column.get_fixed_width()

        if width<0:
            return

        width=max(160,width)

        if width==column.get_fixed_width():
            return

        self._column_location_width_guard=True

        try:
            column.set_fixed_width(
                width
            )
        finally:
            self._column_location_width_guard=False


    def _column_schedule_height_refresh(self):
        if getattr(
            self,
            '_column_height_refresh_source',
            0,
        ):
            return

        self._column_height_refresh_source=GLib.idle_add(
            self._column_refresh_name_heights
        )


    def _column_refresh_name_heights(self):
        self._column_height_refresh_source=0
        for root in list(self.list_name_cells.values()):
            self._column_update_name_height(root)
        return False


    def _column_name_wraps(
        self,
        root,
        name=None,
    ):
        game=getattr(
            root,
            '_game',
            None,
        )

        if (
            game is None
            and name is None
        ):
            return False

        if name is None:
            name=str(
                game.get(
                    'name',
                    '',
                )
            )

        title_width=root._title.get_width()

        # No real title allocation yet. Wait for the existing
        # notify::width callback instead of guessing.
        if title_width<=1:
            return False

        layout=root._title.create_pango_layout(
            name
        )

        layout.set_width(
            -1
        )

        (
            natural_width,
            _natural_height,
        )=layout.get_pixel_size()

        return (
            natural_width
            > max(
                1,
                title_width,
            )
        )


    def _column_update_name_height(self,root,row_height=None):
        root._title.set_wrap(False)
        root._title.set_single_line_mode(True)
        root._title.set_ellipsize(Pango.EllipsizeMode.END)
        root._title.set_width_chars(18)
        root._title.set_max_width_chars(40)
        root._title.set_size_request(-1,-1)
        root.set_size_request(420,64)


    def _column_order_changed(
        self,
        *_,
    ):
        if getattr(
            self,
            '_column_order_guard',
            False,
        ):
            return

        model=self.column_view.get_columns()

        name_index=None

        for index in range(
            model.get_n_items()
        ):
            if (
                model.get_item(index)
                is self.list_name_column
            ):
                name_index=index
                break

        if (
            name_index is None
            or name_index==0
        ):
            return

        # Right-side columns may move among themselves.
        # Game/Name is permanently pinned at the left edge.
        self._column_order_guard=True

        try:
            self.column_view.remove_column(
                self.list_name_column
            )

            self.column_view.insert_column(
                0,
                self.list_name_column,
            )
        finally:
            self._column_order_guard=False


    def game_matches_view(self,game):
        """The Library's current filter and search, shared by every view."""
        query=self.search.get_text().casefold() if hasattr(self,'search') else ''
        if query and query not in str(game.get('name','')).casefold():return False
        if self.filter=='installed':return bool(game.get('installed'))
        if self.filter=='available':return not bool(game.get('blocked'))
        return True

    def _column_filter_match(
        self,
        item,
        *_,
    ):
        game=item.game

        query=(
            self.search.get_text().casefold()
            if hasattr(
                self,
                'search'
            )
            else ''
        )

        if (
            query
            and query
            not in str(
                game.get(
                    'name',
                    '',
                )
            ).casefold()
        ):
            return False

        if self.filter=='installed':
            return bool(
                game.get(
                    'installed'
                )
            )

        if self.filter=='available':
            return not bool(
                game.get(
                    'blocked'
                )
            )

        return True


    def _column_reload_store(self):
        while self.list_store.get_n_items():
            self.list_store.remove(
                self.list_store.get_n_items()-1
            )

        for game in self.games:
            self.list_store.append(
                LibraryGameItem(
                    game
                )
            )

        self.list_filter.changed(
            Gtk.FilterChange.DIFFERENT
        )


    def _ensure_game_accent(self,game):
        accent=game.get(
            'accent_class'
        )

        if accent and game.get('_accent_blocked')==bool(game.get('blocked')):
            return accent

        path=accent_source(game)

        if not path:
            return None

        try:
            accent=artwork_accent(
                path,
                self.settings.get(
                    'game_accents',
                    {},
                ).get(
                    game['game']
                ),
                muted=bool(game.get('blocked')),
            )
            game['_accent_blocked']=bool(game.get('blocked'))

            game[
                'accent_class'
            ]=accent

            return accent

        except Exception:
            return None


    def _column_remove_accent(
        self,
        widget,
    ):
        old=getattr(
            widget,
            '_accent_class',
            None,
        )

        if old:
            widget.remove_css_class(
                old
            )

        widget._accent_class=None


    def _column_apply_accent(
        self,
        widget,
        game,
    ):
        self._column_remove_accent(
            widget
        )

        accent=self._ensure_game_accent(
            game
        )

        if accent:
            widget.add_css_class(
                accent
            )

            widget._accent_class=accent


    # ---------------- GAME / NAME ----------------

    def _column_name_setup(
        self,
        _factory,
        list_item,
    ):
        root=Gtk.Box(
            spacing=10,
            valign=Gtk.Align.CENTER,
            hexpand=True,
        )
        root.add_css_class(
            'library-column-cell'
        )
        root.add_css_class(
            'library-column-game'
        )
        root.set_size_request(
            340,
            -1,
        )
        root.set_vexpand(
            False
        )

        check=Gtk.CheckButton(
            valign=Gtk.Align.CENTER,
            halign=Gtk.Align.CENTER,
        )
        check.set_margin_start(
            0
        )
        check.set_margin_end(
            0
        )

        artwork=ListArtwork()

        text=Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=4,
            hexpand=True,
            valign=Gtk.Align.CENTER,
        )
        text.set_vexpand(
            False
        )

        title=label(
            '',
            'card-title',
        )
        title.add_css_class(
            'library-column-title'
        )
        title.set_wrap(
            True
        )
        title.set_wrap_mode(
            Pango.WrapMode.WORD_CHAR
        )
        title.set_lines(
            2
        )
        title.set_single_line_mode(
            False
        )
        title.set_ellipsize(
            Pango.EllipsizeMode.END
        )
        title.set_width_chars(
            8
        )
        title.set_max_width_chars(
            20
        )
        title.set_hexpand(
            True
        )

        meta=LibraryPill(
            kind='source',
        )
        meta.add_css_class(
            'library-source-pill'
        )
        meta.set_wrap(
            False
        )
        meta.set_lines(
            1
        )
        meta.set_single_line_mode(
            True
        )
        meta.set_ellipsize(
            Pango.EllipsizeMode.NONE
        )
        meta.set_width_chars(
            9
        )
        meta.set_max_width_chars(
            9
        )
        meta.set_hexpand(
            False
        )
        meta.set_halign(
            Gtk.Align.START
        )
        meta.set_xalign(
            0.5
        )

        text.append(
            title
        )
        text.append(
            meta
        )

        root.append(
            check
        )
        root.append(
            artwork
        )
        root.append(
            text
        )

        root._check=check
        root._artwork=artwork
        root._title=title
        root._meta=meta
        root._game=None
        root._game_id=None
        root._binding=False
        root._accent_class=None
        root._hovered=False
        motion=Gtk.EventControllerMotion()
        def hover(value):
            root._hovered=value;self.sync_row_check(root)
        motion.connect('enter',lambda *_:hover(True))
        motion.connect('leave',lambda *_:hover(False))
        root.add_controller(motion)

        root.connect(
            'notify::width',
            lambda *_:self._column_schedule_height_refresh(),
        )

        title.connect(
            'notify::width',
            lambda *_:self._column_schedule_height_refresh(),
        )

        check.connect(
            'toggled',
            self._column_check_toggled,
            root,
        )

        artwork.button.connect(
            'clicked',
            self._column_art_clicked,
            root,
        )

        self.attach_game_context(root,lambda: list_item.get_item().game if list_item.get_item() is not None else None)
        list_item.set_child(
            root
        )


    def _column_bind_name_root(
        self,
        root,
        game,
    ):
        root._game=game
        root._game_id=game[
            'game'
        ]

        root._title.set_text(
            game.get(
                'name',
                '',
            )
        )

        root._meta.set_text(
            str(
                game.get(
                    'source',
                    '',
                )
            ).upper()
        )

        self._column_update_name_height(
            root
        )

        root._check.set_tooltip_text(
            'Select '+game.get(
                'name',
                '',
            )
        )

        path=capsule_art_path(game)

        root._artwork.set_artwork(path)
        root._check.set_sensitive(not bool(game.get('blocked')))
        self.decorate_support_artwork(root._artwork,root._artwork.picture,game,path)

        self._column_apply_accent(
            root,
            game,
        )

        selected=(
            game['game']
            in self.selected_game_ids
        )

        root._binding=True

        try:
            root._check.set_active(
                selected
            )
        finally:
            root._binding=False

        root._artwork.set_selected(
            selected
        )
        self.sync_row_check(root)

    def sync_row_check(self,root):
        """List rows keep the check's space so they never shift on hover."""
        game=root._game or {}
        shown=not game.get('blocked') and bool(
            getattr(root,'_hovered',False)
            or root._check.get_active()
            or self.selected_game_ids
        )
        root._check.set_opacity(1 if shown else 0)
        root._check.set_can_target(shown)
        root._check.set_focusable(shown)


    def _column_name_bind(
        self,
        _factory,
        list_item,
    ):
        root=list_item.get_child()
        item=list_item.get_item()

        old_id=getattr(
            root,
            '_game_id',
            None,
        )

        if (
            old_id
            and self.list_name_cells.get(
                old_id
            )
            is root
        ):
            self.list_name_cells.pop(
                old_id,
                None,
            )

        game=item.game

        self._column_bind_name_root(
            root,
            game,
        )

        self.list_name_cells[
            game['game']
        ]=root

        self._column_schedule_height_refresh()


    def _column_name_unbind(
        self,
        _factory,
        list_item,
    ):
        root=list_item.get_child()

        game_id=getattr(
            root,
            '_game_id',
            None,
        )

        if (
            game_id
            and self.list_name_cells.get(
                game_id
            )
            is root
        ):
            self.list_name_cells.pop(
                game_id,
                None,
            )

        self._column_remove_accent(
            root
        )

        root._game=None
        root._game_id=None


    def _column_check_toggled(
        self,
        check,
        root,
    ):
        if root._binding:
            return

        game_id=root._game_id

        if not game_id:
            return

        if check.get_active() and root._game and root._game.get('blocked'):
            root._binding=True;check.set_active(False);root._binding=False
            return
        if check.get_active():
            self.selected_game_ids.add(
                game_id
            )
        else:
            self.selected_game_ids.discard(
                game_id
            )

        self._column_sync_selection_widgets()
        self._update_selection_summary()


    def _column_art_clicked(
        self,
        _button,
        root,
    ):
        if root._game is not None:
            self.details(
                root._game
            )


    # ---------------- LOCATION ----------------

    def _column_location_setup(
        self,
        _factory,
        list_item,
    ):
        root=Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=1,
            valign=Gtk.Align.CENTER,
            halign=Gtk.Align.FILL,
            hexpand=True,
        )
        root.add_css_class(
            'library-column-cell'
        )
        root.set_size_request(
            160,
            -1,
        )
        root.set_vexpand(
            False
        )


        source=label(
            '',
            'library-column-primary',
        )

        path=label(
            '',
            'library-list-location',
        )
        path.set_single_line_mode(
            False
        )
        path.set_ellipsize(
            Pango.EllipsizeMode.NONE
        )
        path.set_width_chars(
            1
        )
        path.set_max_width_chars(
            -1
        )

        path.set_wrap(True)
        path.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        root.append(
            source
        )
        root.append(
            path
        )

        root._source=source
        root._path=path

        self.attach_game_context(root,lambda: list_item.get_item().game if list_item.get_item() is not None else None)
        list_item.set_child(
            root
        )


    def _column_location_bind(
        self,
        _factory,
        list_item,
    ):
        root=list_item.get_child()
        game=list_item.get_item().game

        root._source.set_text(
            game.get(
                'source',
                '',
            )
        )

        root._path.set_text(
            game.get(
                'game',
                '',
            )
        )


    # ---------------- STATUS ----------------

    def _column_status_setup(
        self,
        _factory,
        list_item,
    ):
        root=Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=3,
            valign=Gtk.Align.CENTER,
            halign=Gtk.Align.START,
        )
        root.add_css_class(
            'library-column-cell'
        )
        root.add_css_class(
            'library-status-stack'
        )
        root.set_size_request(
            -1,
            -1,
        )
        root.set_vexpand(
            False
        )

        primary=Gtk.Box(
            spacing=LIBRARY_PILL_GAP,
            valign=Gtk.Align.CENTER,
            halign=Gtk.Align.START,
            hexpand=False,
        )
        primary.add_css_class(
            'library-status-line'
        )
        primary.add_css_class(
            'library-status-primary'
        )
        primary.set_size_request(
            LIBRARY_LIST_STATUS_WIDTH,
            LIBRARY_PILL_HEIGHT,
        )

        dot=label(
            '●',
            'library-list-status-dot',
        )
        dot.set_size_request(
            LIBRARY_PILL_ICON_SIZE,
            -1,
        )
        dot.set_margin_start(
            LIBRARY_PILL_HPAD_START
        )
        dot.set_xalign(
            0.5
        )

        state=label(
            '',
            'library-list-status-text',
        )
        state.set_margin_end(
            LIBRARY_PILL_HPAD_END
        )

        primary.append(
            dot
        )
        primary.append(
            state
        )

        test=LibraryPill(
            kind='status',
        )
        test.add_css_class(
            'library-test-pill'
        )
        test.set_halign(
            Gtk.Align.START
        )
        test.set_xalign(
            0.5
        )
        test.set_wrap(
            False
        )
        test.set_lines(
            1
        )
        test.set_single_line_mode(
            True
        )
        test.set_ellipsize(
            Pango.EllipsizeMode.NONE
        )
        test.set_width_chars(
            9
        )
        test.set_max_width_chars(
            9
        )

        test.set_fixed_width(
            LIBRARY_LIST_STATUS_WIDTH
        )
        test.set_size_request(
            LIBRARY_LIST_STATUS_WIDTH,
            -1,
        )

        root.append(
            primary
        )
        root.append(
            test
        )

        root._dot=dot
        root._state=state
        root._test=test
        # Tiny OS mark beside "Installed".
        root._os=Gtk.Image(pixel_size=10,visible=False,valign=Gtk.Align.CENTER)
        root._os.add_css_class('library-pill-os')
        primary.append(root._os)

        self.attach_game_context(root,lambda: list_item.get_item().game if list_item.get_item() is not None else None)
        list_item.set_child(
            root
        )


    def _column_status_bind(
        self,
        _factory,
        list_item,
    ):
        root=list_item.get_child()
        game=list_item.get_item().game

        for css_class in (
            'installed',
            'available',
            'unavailable',
        ):
            root._dot.remove_css_class(
                css_class
            )

        if game.get('blocked'):
            text='Unsupported'
            css='unavailable'
        elif game.get('installed'):
            text='Installed'
            css='installed'
        else:
            text='Available'
            css='available'

        root._dot.add_css_class(
            css
        )

        root._state.set_text(
            text
        )
        installed_on=game.get('installed_on') if game.get('installed') else None
        root._os.set_visible(installed_on in ('linux','windows'))
        if installed_on in ('linux','windows'):
            root._os.set_from_icon_name('rtx-os-'+installed_on+'-symbolic')
            root._os.set_tooltip_text('Installed with rtxForge on '+installed_on.title())

        test_status=library_display_test_status(
            game
        )

        root._test.set_text(
            test_status.upper()
        )
        root._test.set_visible(test_status.casefold() not in ('untested','n/a',''))

        for css_class in (
            'test-untested',
            'test-tested',
        ):
            root._test.remove_css_class(
                css_class
            )

        root._test.add_css_class(
            'test-untested'
            if test_status.casefold()=='untested'
            else 'test-tested'
        )


    # ---------------- FEATURES ----------------

    def _column_features_setup(
        self,
        _factory,
        list_item,
    ):
        root=Gtk.Box(
            spacing=6,
            valign=Gtk.Align.CENTER,
            halign=Gtk.Align.START,
        )
        root.add_css_class(
            'library-column-cell'
        )
        root.set_size_request(
            -1,
            -1,
        )
        root.set_vexpand(
            False
        )


        nr=label(
            '',
            'library-list-chip',
        )

        mfg=label(
            '',
            'library-list-chip',
        )

        for chip in (nr,mfg):
            chip.set_wrap(False);chip.set_single_line_mode(True)
            chip.set_ellipsize(Pango.EllipsizeMode.NONE)
            chip.set_valign(Gtk.Align.CENTER)

        root.append(
            nr
        )
        root.append(
            mfg
        )

        root._nr=nr
        root._mfg=mfg

        self.attach_game_context(root,lambda: list_item.get_item().game if list_item.get_item() is not None else None)
        list_item.set_child(
            root
        )


    def _column_features_bind(
        self,
        _factory,
        list_item,
    ):
        root=list_item.get_child()
        game=list_item.get_item().game

        nr_value=(
            game.get(
                'nr_strength'
            )
            if game.get(
                'nr_strength'
            )
            is not None
            else '—'
        )

        mfg_value=(
            game.get(
                'mfg_multiplier'
            )
            if game.get(
                'mfg_multiplier'
            )
            is not None
            else '—'
        )

        root._nr.set_markup(
            '<span weight="800">NR</span> '
            '<span weight="500">'
            +GLib.markup_escape_text(
                str(nr_value)
            )
            +'</span>'
        )

        root._mfg.set_markup(
            '<span weight="800">MFG</span> '
            '<span weight="500">'
            +GLib.markup_escape_text(
                'In game' if mfg_value == 'auto' else 'Off' if mfg_value == 0 else str(mfg_value) + ('×' if isinstance(mfg_value,int) else '')
            )
            +'</span>'
        )

        root._nr.remove_css_class(
            'active'
        )
        root._mfg.remove_css_class(
            'active'
        )

        profile=game.get(
            'profile',
            '',
        )

        if profile in (
            'NR Only',
            'NR + MFG',
        ):
            root._nr.add_css_class(
                'active'
            )

        if profile in (
            'MFG Only',
            'NR + MFG',
        ):
            root._mfg.add_css_class(
                'active'
            )


    # ---------------- ACTIONS ----------------

    def _column_actions_setup(
        self,
        _factory,
        list_item,
    ):
        root=Gtk.Box(
            spacing=6,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
        )
        root.add_css_class(
            'library-column-cell'
        )
        root.add_css_class(
            'library-column-actions'
        )
        root.set_size_request(
            -1,
            -1,
        )
        root.set_vexpand(
            False
        )

        primary=Gtk.Button(
            label='Install'
        )
        primary.set_size_request(
            88,
            -1,
        )
        primary.set_halign(
            Gtk.Align.START
        )
        primary.set_hexpand(
            False
        )

        more=Gtk.Button(
            icon_name='view-more-symbolic',
        )
        more.set_size_request(
            36,
            -1,
        )
        more.set_halign(
            Gtk.Align.START
        )
        more.set_hexpand(
            False
        )
        more.set_tooltip_text(
            'Game actions'
        )

        root.append(
            primary
        )
        root.append(
            more
        )

        root.set_margin_start(8)
        root.set_margin_end(16)
        root._primary=primary
        root._more=more
        root._game=None
        root._game_id=None
        root._accent_class=None

        primary.connect(
            'clicked',
            self._column_primary_clicked,
            root,
        )

        more.connect(
            'clicked',
            self._column_more_clicked,
            root,
        )

        self.attach_game_context(root,lambda: list_item.get_item().game if list_item.get_item() is not None else None)
        list_item.set_child(
            root
        )


    def _column_bind_actions_root(
        self,
        root,
        game,
    ):
        root._game=game
        root._game_id=game[
            'game'
        ]

        blocked=bool(
            game.get(
                'blocked'
            )
        )

        # Geometry stays constant between Install / Restore / Apply.
        root._primary.set_size_request(
            88,
            -1,
        )
        root._primary.set_halign(
            Gtk.Align.START
        )
        root._primary.set_hexpand(
            False
        )

        caption=self.list_primary_caption(game)
        content=Gtk.Box(spacing=10,halign=Gtk.Align.CENTER,valign=Gtk.Align.CENTER)
        image=Gtk.Image.new_from_icon_name(action_icon(caption))
        image.set_visible(BUTTON_GLYPHS);BUTTON_IMAGES.add(image)
        content.append(image);content.append(label(caption))
        root._primary.set_child(content)
        root._primary.set_tooltip_text(None)
        root._primary.set_size_request(108,-1)

        enabled=(
            not self.busy
            or self.task_kind=='art'
        )

        compatible=bool(
            self.hardware_info
            and self.hardware_info[
                'ready'
            ]
        )

        root._primary.set_sensitive(
            enabled and self.list_primary_enabled(game,compatible)
        )

        root._more.set_sensitive(
            enabled
        )

        self._column_apply_accent(
            root,
            game,
        )

        if (
            game['game']
            in self.selected_game_ids
        ):
            root.add_css_class(
                'selected-actions'
            )
        else:
            root.remove_css_class(
                'selected-actions'
            )


    def _column_actions_bind(
        self,
        _factory,
        list_item,
    ):
        root=list_item.get_child()

        old_id=getattr(
            root,
            '_game_id',
            None,
        )

        if (
            old_id
            and self.list_action_cells.get(
                old_id
            )
            is root
        ):
            self.list_action_cells.pop(
                old_id,
                None,
            )

        game=list_item.get_item().game

        self._column_bind_actions_root(
            root,
            game,
        )

        self.list_action_cells[
            game['game']
        ]=root


    def _column_actions_unbind(
        self,
        _factory,
        list_item,
    ):
        root=list_item.get_child()

        game_id=getattr(
            root,
            '_game_id',
            None,
        )

        if (
            game_id
            and self.list_action_cells.get(
                game_id
            )
            is root
        ):
            self.list_action_cells.pop(
                game_id,
                None,
            )

        self._column_remove_accent(
            root
        )

        root._game=None
        root._game_id=None


    def _column_primary_clicked(
        self,
        _button,
        root,
    ):
        game=root._game

        if game is None or game.get('blocked'):return
        if getattr(self,'preset_selecting',False):
            self.apply_presets_to([game])
        elif game.get('installed') and not self.needs_linux_setup(game):
            self.launch_action('uninstall',targets=[game])
        else:
            self.launch_action('install',targets=[game])

    def needs_linux_setup(self,game):
        """Installed with rtxForge on Windows, not yet set up (adapted) to run under Proton."""
        return game.get('installed_on')=='windows' and bool(game.get('adaptable') or not game.get('linux_ready'))

    def list_primary_caption(self,game):
        if getattr(self,'preset_selecting',False):return 'Apply'
        if self.needs_linux_setup(game):return 'Set Up'
        return 'Restore' if game.get('installed') else 'Install'

    def list_primary_enabled(self,game,compatible):
        if game.get('blocked'):return False
        if getattr(self,'preset_selecting',False):return bool(game.get('installed'))
        return bool(game.get('installed') or compatible)

    def attach_game_context(self,widget,get_game):
        gesture=Gtk.GestureClick(button=3)
        def pressed(controller,_count,x,y):
            game=get_game()
            if game is not None:
                controller.set_state(Gtk.EventSequenceState.CLAIMED)
                self.game_context_menu(widget,game,x,y)
        gesture.connect('pressed',pressed)
        widget.add_controller(gesture)

    def game_context_menu(self,widget,game,x=None,y=None):
        pop=Gtk.Popover()
        pop.set_parent(widget)
        if x is not None:
            rect=Gdk.Rectangle();rect.x=int(x);rect.y=int(y);rect.width=1;rect.height=1
            pop.set_pointing_to(rect)
        content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4)
        margins(content,6)
        def add(caption,callback,enabled=True):
            action=button(caption,lambda *_:(pop.popdown(),callback()))
            action.add_css_class('flat');action.set_sensitive(enabled)
            action.get_child().set_halign(Gtk.Align.START)
            content.append(action)
        add('Game Details',lambda:self.details(game))
        def files():
            self.details(game);self.detail_pages.set_visible_child_name('DLSS Files')
        add('DLSS Files',files)
        if game.get('installed_on')=='windows' and not game.get('adaptable'):
            # Older Windows record without shared state: Linux only adds or removes its Proton setting.
            if self.needs_linux_setup(game):add('Set Up for Linux',lambda:self.launch_action('install',targets=[game]),not self.busy)
            else:add('Remove Linux Setup',lambda:self.launch_action('uninstall',targets=[game]),not self.busy)
        else:
            # A Windows install with shared state is adapted for Linux (Set Up) or restored right here.
            add('Set Up for Linux' if self.needs_linux_setup(game) else 'Install Features',lambda:self.launch_action('install',targets=[game]),not game.get('blocked') and not self.busy)
            add('Restore Original Files',lambda:self.launch_action('uninstall',targets=[game]),bool(game.get('installed')) and not self.busy)
        add('Open Folder',lambda:Gio.AppInfo.launch_default_for_uri(Path(game['game']).as_uri(),None),not self.options.demo)
        pop.set_child(content)
        pop.connect('closed',lambda *_:GLib.idle_add(lambda:(pop.unparent(),False)[1]))
        pop.popup()
        return pop

    def _column_more_clicked(self,button,root):
        if root._game is not None:
            self.game_context_menu(button,root._game)


    def _column_activate(
        self,
        _view,
        position,
    ):
        item=self.list_selection_model.get_item(
            position
        )

        if item is not None:
            self.details(
                item.game
            )


    # ---------------- SHARED SELECTION ----------------

    def _style_column_row(self,root,selected):
        widget=root.get_parent()
        while widget is not None and widget.get_css_name()!='row':
            widget=widget.get_parent()
        if widget is None:return
        for name in widget.get_css_classes():
            if name.startswith('art-'):widget.remove_css_class(name)
        for name in root.get_css_classes():
            if name.startswith('art-'):widget.add_css_class(name)
        (widget.add_css_class if selected else widget.remove_css_class)('game-selected')
        count=self.list_sort_model.get_n_items()
        game_id=getattr(root,'_game_id',None)
        for css,index in (('joined-first',0),('joined-last',count-1)):
            edge=count>0 and game_id==self.list_sort_model.get_item(index).game['game']
            (widget.add_css_class if edge else widget.remove_css_class)(css)

    def _column_sync_selection_widgets(self):
        for game_id,root in list(
            self.list_name_cells.items()
        ):
            selected=(
                game_id
                in self.selected_game_ids
            )

            self._style_column_row(root,selected)
            root._binding=True

            try:
                if (
                    root._check.get_active()
                    != selected
                ):
                    root._check.set_active(
                        selected
                    )
            finally:
                root._binding=False

            root._artwork.set_selected(
                selected
            )
            self.sync_row_check(root)

        for game_id,root in list(
            self.list_action_cells.items()
        ):
            if (
                game_id
                in self.selected_game_ids
            ):
                root.add_css_class(
                    'selected-actions'
                )
            else:
                root.remove_css_class(
                    'selected-actions'
                )


    def library_art_scale(self):
        """Artwork size in percent (75–150), 100 until the person changes it."""
        if not self.settings.get('art_scale_chosen'):return 100
        try:value=int(self.settings.get('art_scale',100))
        except (TypeError,ValueError):value=100
        return max(75,min(150,value))

    def art_scale_changed(self,scale):
        value=int(round(scale.get_value()/5)*5)
        if value==self.library_art_scale() and self.settings.get('art_scale_chosen'):return
        self.settings['art_scale']=value;self.settings['art_scale_chosen']=True
        self.update_library_spacing()
        if not self.options.demo:
            if getattr(self,'_art_scale_save',0):GLib.source_remove(self._art_scale_save)
            def save():
                self._art_scale_save=0
                library_media.save_settings(self.service.config,self.settings)
                return False
            self._art_scale_save=GLib.timeout_add(400,save)

    def library_columns_changed(self,widget):
        self.settings['library_columns']=widget.get_value_as_int()
        if not self.options.demo:
            library_media.save_settings(self.service.config,self.settings)
        self.update_library_spacing()

    def _update_selection_summary(self):
        count=len(
            self.selected_game_ids
        )
        if hasattr(self,'reset_all') and not self.defaults_changed():
            self.reset_all.text_label.set_text('Reset')
        for name in ('install_all','sticky_install_all'):
            widget=getattr(self,name,None)
            if widget:widget.set_label(f'Install Selected ({count})' if count else 'Install Features')
        for name in ('uninstall_all','sticky_remove_all'):
            widget=getattr(self,name,None)
            if widget:widget.set_label(f'Restore Selected ({count})' if count else 'Restore Original Files')
        # Icon-only at narrow widths: the tooltip names the action and its scope.
        if hasattr(self,'sticky_install_all'):
            self.sticky_install_all.set_tooltip_text(self.sticky_install_all.get_label()+(' · selected games' if count else ' · whole library'))
            self.sticky_remove_all.set_tooltip_text(self.sticky_remove_all.get_label()+(' · selected games' if count else ' · whole library'))
        toggle=getattr(self,'select_toggle',None)
        if toggle:
            toggle.set_label('Clear' if count else 'Select all')
            toggle.set_tooltip_text('Clear selection' if count else 'Select every game in this view')
        self.sync_preset_bar()


        if hasattr(
            self,
            'selected_label'
        ):
            self.selected_label.set_text(
                f'{count} selected'
                +(
                    ' · across the whole library'
                    if count
                    else ''
                )
            )

        if hasattr(
            self,
            'install_all'
        ):
            self.controls()


    def _column_refresh_game(self,game):
        game_id=game.get(
            'game'
        )

        root=self.list_name_cells.get(
            game_id
        )

        if root is not None:
            self._column_bind_name_root(
                root,
                game,
            )

        action_root=self.list_action_cells.get(
            game_id
        )

        if action_root is not None:
            self._column_bind_actions_root(
                action_root,
                game,
            )


    def view_changed(self,toggle,key):
        if (
            not toggle.get_active()
            or self.settings.get(
                'library_view'
            )==key
        ):
            return

        self._switching_library_view=True
        self.library_scroll.get_vadjustment().set_value(0)
        self.column_scroll.get_vadjustment().set_value(0)
        self.settings['library_view']=key
        # Artwork size applies to posters and capsules, not the list.
        if hasattr(self,'art_scale'):self.art_scale.set_sensitive(key!='list')

        if key=='list':
            self._column_reload_store()
            self.library_stack.set_visible_child_name('list')
        elif self.cards:
            for entry in self.cards.values():self.paint_card(entry)
            self.library_stack.set_visible_child_name('gallery')
            self.update_library_spacing()
            self.filter_games()
        else:
            self.show_games(self.games,False)

        def settle_view():
            self.library_scroll.get_vadjustment().set_value(0)
            self.column_scroll.get_vadjustment().set_value(0)
            self._switching_library_view=False
            self._collapse_library_header(self.library_scroll.get_vadjustment())
            return False
        GLib.idle_add(settle_view)

        if not self.options.demo:
            library_media.save_settings(self.service.config,self.settings)

    def update_library_dlss(self,*_,games=None):
        self.update_dlss_games(list(self.games if games is None else games))

    def selected_or_library(self):
        """Library-wide actions act on the selection, else the current view."""
        try:return operation_targets(self.games,self.selected_game_ids,self.game_matches_view)
        except ScopeError as error:
            self.toast(str(error));return []

    def launch_scoped(self,operation,**kwargs):
        """Toolbar actions: never widen past the selection or current view."""
        targets=self.selected_or_library()
        if not targets:return
        self.launch_action(operation,not bool(self.selected_game_ids),targets=targets,**kwargs)

    def update_dlss_games(self,games):
        """Review DLSS Update → Updating → Done, in one dialog."""
        if self.busy and self.task_kind!='art':return
        targets=list({game['game']:game for game in games if not game.get('blocked')}.values())
        if not targets:
            self.toast('No games selected.');return
        self.operation_games=targets
        self.operation_cancel=None
        flow=self.new_operation_flow('update-dlss',targets)
        review={'operation':'update-dlss','rows':[{'name':game['name'],'game':game['game'],'detail':'Check for newer DLSS files'} for game in targets],'blocked':[]}
        details=['Update','Only older supported native DLSS files are updated','Previous copies are backed up']
        def run(_review):
            if self.options.demo:return
            import runtime_updates
            flow.show_progress(len(targets));flow.rescan=True
            flow.cancel_button.set_sensitive(False)
            def finished(result):
                message=str(result['updated_games'])+' games updated.'
                if result['skipped']:message+=' '+str(len(result['skipped']))+' games skipped; see Activity.'
                self.log.extend(result['skipped'])
                self.finish_progress(True,message)
            self.start('Update DLSS Files',lambda:runtime_updates.manage(self.service.config,targets),finished)
        flow.show_review(review,run,details,enabled=not self.options.demo)

    def manage_dlss_files(self,game,restore=False,replace_same=False,_reviewed=False):
        if restore and not _reviewed:
            review={'operation':'restore-dlss','rows':[{'name':game['name'],'game':game['game'],'detail':'Put back the DLSS files this game shipped with. rtxForge’s backups are used.'}],'blocked':[]}
            def run(_review):
                import runtime_updates
                return runtime_updates.restore_game(self.service.config,game['game'])
            self.review_write('restore-dlss',review,run=run,details=['Restore','Original DLSS files'],done=lambda _:'Original DLSS files restored.')
            return
        if self.options.demo:
            self.toast('Preview mode · game writes disabled')
            return
        import runtime_updates
        work=(lambda:runtime_updates.restore_game(self.service.config,game['game'])) if restore else (lambda:runtime_updates.manage(self.service.config,[game],replace_same=replace_same))
        def finished(result):
            if restore:
                self.toast('Original DLSS files restored')
            elif result['skipped']:
                self.toast(result['skipped'][0])
            else:
                self.toast('DLSS files updated' if result['updated_games'] else 'No DLSS updates needed')
            if self.detail_game==game['game'] and self.dialog is self.detail_dialog:
                self.details(game)
                self.detail_pages.set_visible_child_name('DLSS Files')
        self.start('DLSS Files',work,finished)

    def toast(self,text):self.overlay.add_toast(Adw.Toast.new(str(text)))
    def profile_changed(self,group,*_):
        self.mode=group.get_active_name() or 'mfg-only'
        self.profile_note.set_text({'nr-only':'Neural Rendering','nr-mfg':'Neural Rendering and frame generation','mfg-only':'Native frame generation'}[self.mode])
    def tuning_controls(self,initial):
        box=Gtk.Box(spacing=16)
        widgets={}

        for key,title,upper in [
            ('nr_strength','NR Strength',2.0),
            ('sharpening_strength','Sharpening',1.0),
        ]:
            pod=Gtk.Box(hexpand=True)
            pod.add_css_class('control-pod')
            box.append(pod)

            group=Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=3,
                hexpand=True,
                valign=Gtk.Align.CENTER,
            )
            pod.append(group)

            raw=initial.get(key)
            if raw is None:
                raw=self.settings.get(
                    key,
                    2.0 if key=='nr_strength' else 0.5,
                )

            # Backward-compatible display for old preset-shaped rows.
            if isinstance(raw,str):
                if raw=='off':
                    value=0.0
                else:
                    preset=self.strength_presets.get(raw,{})
                    field='nr' if key=='nr_strength' else 'sharpness'
                    try:value=float(preset[field])
                    except (KeyError,TypeError,ValueError):
                        value=2.0 if key=='nr_strength' else 0.5
            else:
                try:value=float(raw)
                except (TypeError,ValueError):
                    value=2.0 if key=='nr_strength' else 0.5

            value=max(0.0,min(upper,round(value,1)))

            adjustment=Gtk.Adjustment(
                value=value,
                lower=0.0,
                upper=upper,
                step_increment=0.1,
                page_increment=0.1,
            )

            header=Gtk.Box(spacing=8)
            heading=label(title,'heading')
            heading.set_wrap(False)
            heading.set_hexpand(True)
            header.append(heading)

            spin=Gtk.SpinButton.new(
                adjustment,
                0.1,
                1,
            )
            spin.set_numeric(True)
            spin.add_css_class(
                'tuning-number-input'
            )
            spin.set_width_chars(4)
            spin.set_valign(Gtk.Align.CENTER)
            spin.update_property(
                [Gtk.AccessibleProperty.LABEL],
                [title+' exact value'],
            )
            header.append(spin)

            group.append(header)

            slider=Gtk.Scale(
                orientation=Gtk.Orientation.HORIZONTAL,
                adjustment=adjustment,
            )
            slider.set_digits(1)
            slider.set_draw_value(False)
            slider.set_hexpand(True)
            slider.set_size_request(125,-1)
            slider.update_property(
                [Gtk.AccessibleProperty.LABEL],
                [title],
            )

            slider.set_tooltip_text(
                '0.0 - 2.0 · 0.1 increments'
                if key=='nr_strength'
                else '0.0 - 1.0 · 0.1 increments'
            )

            # Existing code changes slider sensitivity. Keep the numeric
            # entry synchronized with that state too.
            slider.connect(
                'notify::sensitive',
                lambda w,*_,sp=spin:
                    sp.set_sensitive(w.get_sensitive()),
            )

            group.append(slider)

            detail=label('','dim-label')
            group.append(detail)

            def update(w,d=detail,k=key):
                number=round(w.get_value(),1)
                if number==0.0:
                    d.set_text('Disabled')
                elif k=='nr_strength':
                    d.set_text(
                        f'Intensity / skin · {number:.1f}'
                    )
                else:
                    d.set_text(
                        f'Sharpness · {number:.1f}'
                    )

            slider.connect('value-changed',update)
            update(slider)

            widgets[key]=slider

        pod=Gtk.Box()
        pod.add_css_class('control-pod')
        box.append(pod)

        group=Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6,
            valign=Gtk.Align.CENTER,
        )
        pod.append(group)
        group.append(label('MFG','heading'))

        multiplier=safe_dropdown(
            ['In game','Off']+[str(x)+'×' for x in range(2,7)]
        )
        multiplier.set_selected(
            self.multiplier_values.index(
                initial['mfg_multiplier']
                if initial.get('mfg_multiplier') is not None
                else self.settings.get('mfg_multiplier','auto')
            )
        )
        multiplier.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ['MFG Multiplier'],
        )

        group.append(multiplier)
        group.append(label('Requested ratio','dim-label'))
        widgets['mfg_multiplier']=multiplier

        return box,widgets

    def tuning_values(self,widgets):
        return {
            key:
                self.multiplier_values[int(w.get_selected())]
                if key=='mfg_multiplier'
                else round(float(w.get_value()),1)
            for key,w in widgets.items()
        }

    def chosen_strength(self):return self.tuning_values(self.tuning_widgets)['nr_strength']
    def defaults_changed(self):return any(self.settings.get(k)!=v for k,v in self.tuning_values(self.tuning_widgets).items())
    def strength_changed(self,*_):
        self.reset_all.text_label.set_text('Reset')
        if hasattr(self,'profile_group'):self.controls()
        self.sync_preset_bar()
    def defaults_applied(self,values):
        self.settings.update(values);self.strength_changed()
    def reset_library_settings(self,*_):
        for key,widget in self.tuning_widgets.items():
            value=self.settings[key]
            if key=='mfg_multiplier':widget.set_selected(self.multiplier_values.index(value))
            else:widget.set_value(value)
        self.apply_library_settings()
    def apply_library_settings(self,*_):
        if self.games and any(g.get('installed') for g in self.games):self.launch_scoped('reset',visual_settings=self.tuning_values(self.tuning_widgets));return
        values=self.tuning_values(self.tuning_widgets)
        if self.options.demo:self.defaults_applied(values);return
        self.start('Saving defaults',lambda:self.service.save_visual_defaults(values),lambda _:(self.defaults_applied(values),self.toast('Defaults saved for new installs.')))
    def filter_changed(self,toggle,key):
        if toggle.get_active():self.filter=key;self.filter_games()
    def close_request(self,*_):
        if self.busy and self.task_kind!='art':self.toast('Please wait for the current file operation to finish.');return True
        if self.busy:self.cancel_art.set()
        if getattr(getattr(self,'couch',None),'hint_timer',0):
            GLib.source_remove(self.couch.hint_timer);self.couch.hint_timer=0
        if getattr(self,'controller_source',0):
            GLib.source_remove(self.controller_source);self.controller_source=0
            self.controller.close()
        return False
    def tick(self):
        if self.busy:self.operation_elapsed.set_text(f'{int(time.monotonic()-self.started)}s')
        return True
    def controls(self):
        enabled=not self.busy or self.task_kind=='art'
        compatible=bool(self.hardware_info and self.hardware_info['ready'])
        self.install_all.set_sensitive(enabled and bool(self.games) and compatible);self.uninstall_all.set_sensitive(enabled and bool(self.games))
        self.reset_all.set_sensitive(enabled and self.defaults_changed())
        self.apply_presets.set_sensitive(enabled and bool(self.configured_games()))
        self.sync_presets_page()
        for widget in self.tuning_widgets.values():widget.set_sensitive(enabled)
        for entry in self.cards.values():
            primary=entry.get(
                'primary'
            )

            if primary is not None:
                primary.set_sensitive(
                    enabled
                    and compatible
                    and not entry['data'].get(
                        'blocked'
                    )
                )
        for root in list(
            getattr(
                self,
                'list_action_cells',
                {},
            ).values()
        ):
            game=getattr(
                root,
                '_game',
                None,
            )

            if game is None:
                continue

            root._primary.set_sensitive(
                enabled and self.list_primary_enabled(game,compatible)
            )

            root._more.set_sensitive(
                enabled
            )

        selected_any=bool(
            self.selected_game_ids
        )

        for i,b in enumerate(
            self.action_buttons
        ):
            b.set_sensitive(
                enabled
                and (
                    compatible
                    or i in (
                        2,
                        3,
                    )
                )
                and selected_any
            )
        self.refresh_action.set_enabled(
            enabled
        )
        self.add_folder_action.set_enabled(
            enabled
        )

        for b in (
            self.profile_group,
            self.update_dlss_button,
            *self.view_buttons.values(),
        ):
            b.set_sensitive(
                enabled
            )
    def event(self,event):
        if event['kind']=='progress':
            flow=getattr(self,'operation_flow',None)
            if flow is not None and not flow.closed and flow.stage in ('checking','progress'):
                (flow.checking_event if flow.stage=='checking' else flow.progress_event)(event)
                self.show_operation_status(event['label'])
                return False
            state=getattr(self,'review_check_state',None)
            if state and self.dialog is state['dialog']:
                self.review_check_event(event,state)
                self.show_operation_status(event['label'])
                return False
            self.show_operation_status(event['label']);self.update_progress_art(event.get('game',''))
            if getattr(self,'job_label',None):
                self.job_caption.set_text(user_messages.friendly_status(event['label']))
                if 'fraction' in event:
                    self.job_bar.set_fraction(event['fraction'])
                    self.job_counter.set_text(str(event['current'])+' of '+str(event['total'])+' games')
        elif event['kind']=='art':
            game=next(
                (
                    candidate
                    for candidate in self.games
                    if candidate.get(
                        'game'
                    )==event[
                        'game'
                    ]
                ),
                None,
            )

            if game is not None:
                game.update(
                    event[
                        'data'
                    ]
                )

            card=self.cards.get(
                event['game']
            )

            if card:
                card[
                    'data'
                ].update(
                    event[
                        'data'
                    ]
                )
                self.paint_card(
                    card
                )

            if (
                game is not None
                and self.settings.get(
                    'library_view',
                    'posters',
                )=='list'
            ):
                self._column_refresh_game(
                    game
                )
            if game is not None and hasattr(self,'couch'):
                self.couch.artwork_updated(game)
            if getattr(self,'detail_game',None)==event['game'] and self.dialog==getattr(self,'detail_dialog',None) and event['data'].get('hero'):
                try:self.detail_banner.set_paintable(Gdk.Texture.new_from_filename(event['data']['hero']))
                except Exception:pass
        else:self.log.append(event['text']);self.log=self.log[-400:]
        return False
    def start(self,title,action,done,kind='work'):
        if self.busy:
            if self.task_kind=='art':self.pending=(title,action,done,kind);self.cancel_art.set();self.show_operation_status('Finishing current artwork request…')
            return
        self.busy=True;self.task_kind=kind;self.started=time.monotonic();self.operation_elapsed.set_text('');self.show_operation_status(title);self.controls()
        # Results arrive at default priority: a running animation (spinner,
        # pulsing bar) must never hold back progress or completion.
        def deliver(callback,*args):
            GLib.idle_add(callback,*args,priority=GLib.PRIORITY_DEFAULT)
        def run_task():
            try:
                with ui.report_to(lambda e:deliver(self.event,e)):result=action()
            except Exception as ex:deliver(self.finished,None,done,(str(ex),traceback.format_exc()))
            else:deliver(self.finished,result,done,None)
        threading.Thread(target=run_task,daemon=False).start()
    def finished(self,result,done,error):
        self.busy=False;self.task_kind='';self.controls()
        if getattr(self,'operation_cancel',None) is not None and self.operation_cancel.is_set() and (not getattr(self,'operation_executing',False) or (error and 'operation_session.Cancelled' in error[1])):
            self.operation_cancel=None
            flow=getattr(self,'operation_flow',None)
            if flow is not None and not flow.closed and flow.stage=='progress':
                self.show_operation_status('Cancelled · changes undone',True,'process-stop-symbolic')
                self.finish_progress(False,'Changes to the games in progress were undone.',title='Cancelled')
                return
            if self.dialog:self.dialog.force_close()
            self.dialog=None;self.job_label=None;self.show_operation_status('Cancelled · changes undone',True,'process-stop-symbolic')
            previous=getattr(self,'operation_previous',None)
            if previous:self.details(previous)
            return
        if error:
            self.log.append(error[1]);self.show_operation_status('Stopped · details available in Activity',True,'dialog-warning-symbolic');self.error(error[0])
        else:
            try:done(result)
            except Exception as ex:
                self.log.append(traceback.format_exc());self.show_operation_status('Stopped · details available in Activity',True,'dialog-warning-symbolic');self.error(str(ex))
            else:self.show_operation_status('Completed',True)
        if self.pending:
            task=self.pending;self.pending=None;self.start(*task)
        return False
    def snapshot_library_texture(self):
        """Freeze the main library content for result-screen blur."""
        widget=self.overlay

        width=max(1,widget.get_width())
        height=max(1,widget.get_height())

        paint=Gtk.WidgetPaintable.new(widget)
        snapshot=Gtk.Snapshot()
        paint.snapshot(snapshot,width,height)

        node=snapshot.to_node()
        if node is None:
            return None

        rect=Graphene.Rect()
        rect.init(0,0,width,height)

        return self.get_renderer().render_texture(node,rect)

    def enable_dialog_resize(
        self,
        dialog,
        min_width=640,
        min_height=480,
    ):
        """Allow pointer resizing from the dialog's bottom-right edge."""

        try:
            dialog.set_presentation_mode(
                Adw.DialogPresentationMode.FLOATING
            )
        except Exception:
            pass

        EDGE=24

        state={
            'active':False,
            'width':0,
            'height':0,
        }

        def near_corner(x,y):
            return (
                x>=max(
                    0,
                    dialog.get_width()-EDGE,
                )
                and
                y>=max(
                    0,
                    dialog.get_height()-EDGE,
                )
            )

        motion=Gtk.EventControllerMotion()

        def motion_cb(_controller,x,y):
            try:
                dialog.set_cursor_from_name(
                    'se-resize'
                    if near_corner(x,y)
                    else 'default'
                )
            except Exception:
                pass

        motion.connect(
            'motion',
            motion_cb,
        )

        dialog.add_controller(
            motion
        )

        drag=Gtk.GestureDrag()

        def drag_begin(_gesture,x,y):
            state['active']=near_corner(
                x,
                y,
            )

            if not state['active']:
                return

            state['width']=max(
                min_width,
                dialog.get_content_width(),
            )

            state['height']=max(
                min_height,
                dialog.get_content_height(),
            )

        def drag_update(_gesture,dx,dy):
            if not state['active']:
                return

            max_width=max(
                min_width,
                self.get_width()-24,
            )

            max_height=max(
                min_height,
                self.get_height()-24,
            )

            width=max(
                min_width,
                min(
                    max_width,
                    round(
                        state['width']+dx
                    ),
                ),
            )

            height=max(
                min_height,
                min(
                    max_height,
                    round(
                        state['height']+dy
                    ),
                ),
            )

            dialog.set_content_width(
                width
            )
            dialog.set_content_height(
                height
            )

        def drag_end(*_):
            state['active']=False

        drag.connect(
            'drag-begin',
            drag_begin,
        )
        drag.connect(
            'drag-update',
            drag_update,
        )
        drag.connect(
            'drag-end',
            drag_end,
        )

        dialog.add_controller(
            drag
        )


    def open_panel(
        self,
        title,
        width=730,
        height=620,
        show_close=True,
        resizable=False,
    ):
        if self.dialog:
            self.dialog.force_close()

        resizable=resizable and not gamescope_session() and not (hasattr(self,'input_stack') and self.input_stack.get_visible_child_name()=='couch')
        if resizable:
            dialog=ResizablePanelWindow(
                self,
                title,
                width,
                height,
            )
        else:
            dialog=PresentationDialog(
                self,
                title=title,
                content_width=width,
                content_height=height,
            )

        self.dialog=dialog
        dialog.add_css_class('modal-panel')
        self.job_label=None

        box=Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
        )
        dialog.set_child(box)
        box.add_css_class('panel-shell')

        header=Adw.HeaderBar()
        header.set_show_end_title_buttons(
            show_close
        )
        header.set_show_start_title_buttons(
            False
        )
        header.set_title_widget(
            Adw.WindowTitle(
                title=title
            )
        )
        box.append(header)

        scroll=Gtk.ScrolledWindow(
            vexpand=True,
            hscrollbar_policy=Gtk.PolicyType.NEVER,
        )
        box.append(scroll)

        body=Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=16,
        )
        body.add_css_class(
            'panel-body'
        )
        scroll.set_child(body)

        foot=Gtk.Box(
            spacing=10,
            halign=Gtk.Align.END,
        )
        margins(
            foot,
            24,
        )
        box.append(foot)

        if resizable:
            dialog.present()
        else:
            dialog.present(self)

        return dialog,body,foot

    def organize_pages(self,body,sections):
        dialog=self.dialog
        shell=dialog.get_child()

        # open_panel() initially creates:
        #
        #   header
        #   scroll -> body
        #   footer
        #
        # Settings replaces that generic dialog composition with a
        # GNOME Settings-style split layout whose sidebar owns the full
        # left edge from top to bottom.
        old_header=shell.get_first_child()
        old_scroll=old_header.get_next_sibling()
        footer=old_scroll.get_next_sibling()

        old_scroll.set_child(None)
        shell.remove(footer)
        dialog.set_child(None)

        root=Gtk.Box(
            hexpand=True,
            vexpand=True,
        )

        sidebar=Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            width_request=236,
            vexpand=True,
        )
        sidebar.add_css_class(
            'settings-sidebar-surface'
        )

        sidebar_header=Gtk.Box()
        sidebar_header.add_css_class(
            'settings-sidebar-header'
        )

        sidebar_title=label(
            'Settings',
            'title-2',
        )
        sidebar_header.append(
            sidebar_title
        )
        sidebar.append(
            sidebar_header
        )

        nav=Gtk.ListBox(
            selection_mode=Gtk.SelectionMode.SINGLE,
            valign=Gtk.Align.FILL,
            vexpand=True,
        )
        nav.add_css_class(
            'settings-navigation'
        )
        sidebar.append(
            nav
        )

        main=Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            hexpand=True,
            vexpand=True,
        )
        main.add_css_class(
            'settings-main-surface'
        )

        page_title=Adw.WindowTitle(
            title=sections[0][0] if sections else 'Settings',
        )

        header=Adw.HeaderBar()
        header.set_show_start_title_buttons(False)
        header.set_show_end_title_buttons(True)
        header.set_title_widget(
            page_title
        )
        settings_window_handle=Gtk.WindowHandle()
        settings_window_handle.set_hexpand(
            True
        )
        settings_window_handle.set_child(
            header
        )

        main.append(
            settings_window_handle
        )

        stack=Gtk.Stack(
            transition_type=Gtk.StackTransitionType.CROSSFADE,
            hexpand=True,
            vexpand=True,
        )
        main.append(
            stack
        )

        # Reuse the existing footer object so show_settings() can append
        # Save Settings normally after this layout has been created.
        footer.add_css_class(
            'settings-footer'
        )
        main.append(
            footer
        )

        root.append(
            sidebar
        )
        root.append(
            main
        )

        dialog.set_child(
            root
        )

        icons={
            'Graphics':'video-display-symbolic',
            'Library':'applications-games-symbolic',
            'Gaming Mode':'input-gaming-symbolic',
            'Appearance':'applications-graphics-symbolic',
            'System':'computer-symbolic',
            'Recovery':'document-revert-symbolic',
        }

        for title,items in sections:
            page=Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=28,
            )
            page.add_css_class(
                'settings-content'
            )

            for item in items:
                page.append(
                    item
                )

            scroll=Gtk.ScrolledWindow(
                hscrollbar_policy=Gtk.PolicyType.NEVER,
                vexpand=True,
            )
            clamp=Adw.Clamp(child=page,maximum_size=800,tightening_threshold=600)
            scroll.set_child(clamp)

            stack.add_titled(
                scroll_bottom_fade(scroll),
                title,
                title,
            )

            nav_row=Gtk.ListBoxRow()

            line=Gtk.Box(
                spacing=12,
                valign=Gtk.Align.CENTER,
            )

            line.append(
                Gtk.Image.new_from_icon_name(
                    icons.get(
                        title,
                        'preferences-system-symbolic',
                    )
                )
            )

            line.append(
                label(title)
            )

            nav_row.set_child(
                line
            )
            nav_row.page_name=title

            nav.append(
                nav_row
            )

        def selected(_nav,row):
            if row is None:
                return

            stack.set_visible_child_name(
                row.page_name
            )

            page_title.set_title(
                row.page_name
            )

        nav.connect(
            'row-selected',
            selected,
        )

        first=nav.get_row_at_index(0)

        if first is not None:
            nav.select_row(
                first
            )

        return stack

    def technical_details(self,message):
        group=Adw.PreferencesGroup()
        detail=Adw.ExpanderRow(title='Technical details')
        raw=label(str(message));raw.set_selectable(True);margins(raw,12)
        detail.add_row(raw);group.add(detail)
        return group

    def error(self,message):
        flow=getattr(self,'operation_flow',None)
        if flow is not None and not flow.closed and flow.stage in ('checking','progress','working'):
            self.finish_progress(False,str(message));return
        if self.dialog==getattr(self,'progress_dialog',None) and getattr(self,'job_label',None):
            box=self.progress_shell.get_last_child();self.finish_progress(False,str(message),box.get_last_child());return
        d,b,f=self.open_panel('Could Not Finish',width=580,height=360,show_close=False)
        b.append(label(user_messages.friendly_error(message)))
        b.append(self.technical_details(message))
        f.append(button('Close',lambda *_:d.close()))
    def scan(self):
        if self.options.demo:return
        extra=list(self.settings['extra_folders']);self.start('Checking hardware and scanning libraries',lambda:{'hardware':self.service.hardware(),'games':self.service.scan_all(extra)},self.scanned)
    def scanned(self,result):
        self.hardware_info=result['hardware'];self.hardware_label.set_text(self.hardware_info['gpu']+' · '+('Hardware check passed' if self.hardware_info['ready'] else 'Install unavailable — see Settings'));self.show_games(result['games'])
    def choose_folder(self,*_):
        if gamescope_session():
            dialog=Adw.Dialog(
                title='Add Game Folder',
                content_width=520,
                content_height=190,
            )

            try:
                dialog.set_presentation_mode(
                    Adw.DialogPresentationMode.FLOATING
                )
            except Exception:
                pass

            shell=Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=14,
            )
            margins(
                shell,
                18,
            )

            shell.append(
                label(
                    'Enter the full path to the folder containing your games.',
                    'dim-label',
                )
            )

            path_entry=Gtk.Entry(
                placeholder_text='/var/mnt/Games',
            )
            path_entry.set_hexpand(
                True
            )
            shell.append(
                path_entry
            )

            actions=Gtk.Box(
                spacing=8,
                halign=Gtk.Align.END,
            )

            actions.append(
                button(
                    'Cancel',
                    lambda *_:dialog.close(),
                )
            )

            def add_path(*_):
                path=path_entry.get_text().strip()

                if not path:
                    return

                folder=Path(path).expanduser()

                if not folder.is_dir():
                    self.toast(
                        'That folder does not exist.'
                    )
                    return

                value=str(
                    folder.resolve()
                )

                if value not in self.settings['extra_folders']:
                    self.settings['extra_folders'].append(
                        value
                    )

                dialog.close()

                if self.options.demo:
                    return

                self.start(
                    'Saving game folder',
                    lambda:library_media.save_settings(
                        self.service.config,
                        self.settings,
                    ),
                    lambda _:self.scan(),
                )

            actions.append(
                button(
                    'Add Folder',
                    add_path,
                    'suggested-action',
                )
            )

            shell.append(
                actions
            )

            dialog.set_child(
                shell
            )
            dialog.present(
                self
            )
            return

        d=Gtk.FileChooserNative(title='Add a game folder',transient_for=self,action=Gtk.FileChooserAction.SELECT_FOLDER,accept_label='Add game')
        def selected(dialog,response):
            if response==Gtk.ResponseType.ACCEPT:
                path=dialog.get_file().get_path()
                if path and path not in self.settings['extra_folders']:
                    self.settings['extra_folders'].append(path)
                    self.start('Saving game folder',lambda:library_media.save_settings(self.service.config,self.settings),lambda _:self.scan())
            dialog.destroy()
        d.connect('response',selected);d.show()
    def show_games(self,games,art=True):
        # Capture gallery checkbox state before replacing widgets.
        for game_id,entry in self.cards.items():
            check=entry.get(
                'check'
            )

            if (
                check is not None
                and check.get_active()
            ):
                self.selected_game_ids.add(
                    game_id
                )

        previous={
            g['game']:g
            for g in self.games
        }

        clear(
            self.flow
        )

        self.ghost_slots=[]
        self.games=games
        if hasattr(self,'couch'):GLib.idle_add(lambda:(self.couch.refresh(),False)[1])
        self.cards={}

        valid_ids={
            g['game']
            for g in games
        }

        self.selected_game_ids.intersection_update(
            valid_ids
        )

        view=self.settings.get(
            'library_view',
            'posters',
        )

        self.library_stack.set_visible_child_name(
            'list'
            if view=='list'
            else 'gallery'
        )

        self.flow.set_max_children_per_line(
            12
        )
        self.flow.set_min_children_per_line(
            1
        )
        self.flow.set_homogeneous(
            True
        )

        media=library_media.LibraryMedia(
            self.service.config,
            {
                **self.settings,
                'online_art':False,
            },
        )

        for game in games:
            for key in (
                'poster',
                'hero',
                'capsule',
                'art_credit',
                'art_link',
                'hero_credit',
                'hero_link',
                'accent_class',
            ):
                if (
                    key
                    in previous.get(
                        game['game'],
                        {},
                    )
                ):
                    game.setdefault(
                        key,
                        previous[
                            game['game']
                        ][key],
                    )

            if self.options.demo:
                try:
                    local_art=media.steam_art(
                        game
                    )

                    for art_key,art_value in local_art.items():
                        if (
                            art_value
                            and not game.get(
                                art_key
                            )
                        ):
                            game[
                                art_key
                            ]=art_value
                except Exception:
                    pass

            else:
                game.update(
                    media.enrich(
                        game
                    )
                )

            game[
                'test_record'
            ]=(
                game_notes.load(
                    self.service.config,
                    game['game'],
                )
                if not self.options.demo
                else game.get(
                    'test_record',
                    {
                        'status':'Untested',
                        'notes':'',
                    },
                )
            )

        if view=='list':
            self._column_reload_store()

        else:
            for game in games:
                self.make_card(
                    game
                )

                entry=self.cards[
                    game['game']
                ]

                if (
                    game['game']
                    in self.selected_game_ids
                ):
                    entry[
                        'check'
                    ].set_active(
                        True
                    )

            self.resize_library_art(
                self.settings.get(
                    'art_scale',
                    100,
                )
            )

        count=sum(
            g.get(
                'installed',
                False,
            )
            for g in games
        )

        libs=len(
            set(
                g.get(
                    'library',
                    '',
                )
                for g in games
            )
        )

        self.stats.set_text(
            f'{len(games)} games · '
            f'{libs} locations · '
            f'{count} OptiScaler installs detected'
        )

        self.filter_games()

        if (
            art
            and self.settings[
                'online_art'
            ]
            and games
        ):
            self.fetch_media()


    def library_card_geometry(
        self,
        value=None,
        view=None,
    ):
        """Return one canonical geometry for every card in a view."""

        if value is None:
            value=self.settings.get(
                'art_scale',
                100,
            )

        try:
            value=int(
                round(
                    float(value)
                )
            )
        except (TypeError,ValueError):
            value=100

        value=max(
            50,
            min(
                150,
                value,
            ),
        )

        if view is None:
            view=self.settings.get(
                'library_view',
                'posters',
            )

        position=(
            value-50
        )/100.0

        # Small cards may allow a two-line title.
        # Every card in the view gets the same footer height;
        # unused title space becomes flexible space above Details.
        info_height=(
            62
            if value < 75
            else 52
        )

        if view=='capsules':
            # Wide Capsule never gets microscopic.
            width=int(
                round(
                    220
                    + (
                        340-220
                    )*position
                )
            )
            ratio=290/136

        elif view=='posters':
            # Posters retain a larger visual footprint because
            # their 2:3 frame is substantially taller.
            width=int(
                round(
                    140
                    + (
                        220-140
                    )*position
                )
            )
            ratio=2/3

        else:
            width=54
            ratio=2/3
            info_height=0

        height=max(
            1,
            int(
                round(
                    width/ratio
                )
            ),
        )

        total_height=(
            height
            + info_height
            + (
                4
                if view!='list'
                else 0
            )
        )

        return (
            value,
            width,
            height,
            info_height,
            total_height,
            ratio,
        )


    def page_side_margin(self,width):
        """One centered column: 3% side margins (16–56 px), at most 1600 px wide."""
        side=max(16,min(56,round(width*0.03)))
        if width-side*2>1600:side=(width-1600)//2
        return side

    def apply_page_margins(self,side):
        for widget in (getattr(self,'library_viewbar',None),getattr(self,'dashboard_top',None),getattr(self,'column_scroll',None)):
            if widget is not None and widget.get_margin_start()!=side:
                widget.set_margin_start(side);widget.set_margin_end(side)

    def resize_library_art(self,value=None):
        """Use the viewport solver for initial cards and subsequent resizes."""
        self.update_library_spacing()


    def make_card(self,game):
        view=self.settings.get(
            'library_view',
            'posters',
        )

        (
            _art_value,
            width,
            height,
            info_height,
            total_height,
            ratio,
        )=self.library_card_geometry(
            self.settings.get(
                'art_scale',
                100,
            ),
            view,
        )

        # List mode is rendered by Gtk.ColumnView and never reaches
        # this FlowBox card builder.

        card=FixedLibraryCard(
            orientation=Gtk.Orientation.VERTICAL,
        )
        card.fixed_width=width+4
        card.fixed_height=total_height
        card.set_overflow(
            Gtk.Overflow.HIDDEN
        )

        card.add_css_class('game-card')
        card.set_size_request(
            width+4,
            total_height,
        )

        if view!='list':
            card.set_halign(
                Gtk.Align.FILL
            )
            card.set_hexpand(
                True
            )
            card.set_overflow(
                Gtk.Overflow.HIDDEN
            )

        overlay=Gtk.Overlay(
            valign=Gtk.Align.START,
        )
        overlay.add_css_class(
            'gallery-artwork-frame'
        )
        overlay.set_margin_start(3)
        overlay.set_margin_end(3)
        overlay.set_margin_top(3)
        overlay.set_overflow(
            Gtk.Overflow.HIDDEN
        )
        overlay.set_size_request(
            width,
            height,
        )
        overlay.set_halign(
            Gtk.Align.FILL
        )
        overlay.set_hexpand(
            True
        )
        card.append(
            overlay
        )

        pic=CoverPicture(
            content_fit=Gtk.ContentFit.COVER,
            can_shrink=True,
        )
        pic.add_css_class('poster')
        pic.cover_width=width
        pic.cover_ratio=ratio
        pic.set_size_request(
            width,
            height,
        )
        pic.set_halign(
            Gtk.Align.FILL
        )
        pic.set_hexpand(
            True
        )

        click=ArtworkButton(
            child=pic
        )
        click.add_css_class(
            'poster-button'
        )
        click.set_size_request(
            width,
            height,
        )
        click.set_halign(
            Gtk.Align.FILL
        )
        click.set_hexpand(
            True
        )
        click.set_overflow(
            Gtk.Overflow.HIDDEN
        )
        pic.set_overflow(
            Gtk.Overflow.HIDDEN
        )
        click.connect(
            'clicked',
            lambda *_:self.library_game_activated(game),
        )

        overlay.set_child(
            click
        )
        # Paint the ring AFTER the picture; parent CSS shadows sit beneath children.
        ring=Gtk.Box(can_target=False, hexpand=True, vexpand=True)
        ring.add_css_class('gallery-artwork-ring')
        overlay.add_overlay(ring)
        overlay.set_measure_overlay(ring,False)
        fallback=label(
            game['name'],
            'poster-fallback',
        )
        fallback.set_halign(
            Gtk.Align.CENTER
        )
        fallback.set_valign(
            Gtk.Align.CENTER
        )

        # Missing-art text must never establish the artwork/card size.
        fallback.set_wrap(
            False
        )
        fallback.set_lines(
            1
        )
        fallback.set_single_line_mode(
            True
        )
        fallback.set_width_chars(
            1
        )
        fallback.set_max_width_chars(
            1
        )
        fallback.set_ellipsize(
            Pango.EllipsizeMode.END
        )

        overlay.add_overlay(
            fallback
        )
        overlay.set_measure_overlay(
            fallback,
            False,
        )
        check=Gtk.CheckButton(halign=Gtk.Align.END,valign=Gtk.Align.START);margins(check,7);check.set_tooltip_text('Select '+game['name']);check.connect('toggled',lambda *_:self.selection_changed())
        if view=='list':
            card.prepend(
                check
            )
            fallback.set_visible(
                False
            )
        else:
            overlay.add_overlay(
                check
            )
            overlay.set_measure_overlay(
                check,
                False,
            )
        # Installed-OS mark on the art, top-left: 22 px translucent square.
        os_badge=Gtk.Box(halign=Gtk.Align.START,valign=Gtk.Align.START,can_target=True,visible=False)
        os_badge.add_css_class('poster-os-badge');margins(os_badge,8)
        os_badge._icon=Gtk.Image(pixel_size=12,halign=Gtk.Align.CENTER,valign=Gtk.Align.CENTER,hexpand=True)
        os_badge.append(os_badge._icon)
        if view!='list':
            overlay.add_overlay(os_badge);overlay.set_measure_overlay(os_badge,False)
        badge=label('Unsupported' if game.get('blocked') else game.get('profile','Ready') if game.get('installed') else 'Ready','cover-badge');badge.set_halign(Gtk.Align.START);badge.set_valign(Gtk.Align.END);margins(badge,7)
        badge_mode={'NR Only':'nr-only','MFG Only':'mfg-only','NR + MFG':'nr-mfg'}.get(game.get('profile'))
        if badge_mode:
            badge=profile_label(badge_mode,badge.get_text());badge.add_css_class('cover-badge');badge.set_halign(Gtk.Align.START);badge.set_valign(Gtk.Align.END);margins(badge,7)
        badge.add_css_class('state-unavailable' if game.get('blocked') else 'state-nr' if game.get('profile')=='NR + MFG' else 'state-mfg' if game.get('installed') else 'state-ready')
        # The artwork stays clean: the feature profile lives in Details.
        text=Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=1,
            hexpand=True,
            vexpand=False if view!='list' else True,
            valign=Gtk.Align.START,
        );text.add_css_class('card-info');card.append(text)
        title=label(
            game['name'],
            'card-title',
        )

        # Center text vertically within the shared title area, never horizontally.
        title.set_wrap(True)
        title.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        title.set_lines(2)
        title.set_vexpand(True)
        title.set_valign(Gtk.Align.FILL)
        title.set_yalign(0.5)
        title.set_tooltip_text(game['name'])
        title.set_single_line_mode(
            False
        )
        title.set_width_chars(
            1
        )
        title.set_max_width_chars(
            1
        )
        title.set_ellipsize(
            Pango.EllipsizeMode.END
        )
        title.set_size_request(
            -1,
            -1,
        )
        title.set_hexpand(
            True
        )

        text.append(
            title
        )

        meta_row=Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=4,
            halign=Gtk.Align.FILL,
            valign=Gtk.Align.CENTER,
            hexpand=True,
        )
        meta_row.set_homogeneous(
            False
        )
        meta_row.add_css_class(
            'library-meta-row'
        )

        # One status pill (with the tiny OS mark) and a tested icon, as on Windows.
        meta=LibraryPill(
            kind='state',
        )
        meta.add_css_class(
            'library-status-pill'
        )
        meta.add_css_class(
            'library-source-pill'
        )
        meta.set_wrap(
            False
        )
        meta.set_lines(
            1
        )
        meta.set_single_line_mode(
            True
        )
        meta.set_ellipsize(
            Pango.EllipsizeMode.END
        )
        meta.set_width_chars(
            1
        )
        meta.set_max_width_chars(
            1
        )
        meta.set_hexpand(
            False
        )

        meta.set_halign(
            Gtk.Align.FILL
        )
        meta.set_xalign(
            0.5
        )

        test_meta=LibraryPill(
            kind='status',
        )
        test_meta.add_css_class(
            'library-test-pill'
        )
        test_meta.set_wrap(
            False
        )
        test_meta.set_lines(
            1
        )
        test_meta.set_single_line_mode(
            True
        )
        test_meta.set_ellipsize(
            Pango.EllipsizeMode.END
        )
        test_meta.set_width_chars(
            1
        )
        test_meta.set_max_width_chars(
            1
        )
        test_meta.set_hexpand(
            False
        )

        test_meta.set_halign(
            Gtk.Align.FILL
        )
        test_meta.set_xalign(
            0.5
        )

        meta_row.append(
            meta
        )
        meta_row.append(
            test_meta
        )

        footer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8,vexpand=False)
        footer.add_css_class('card-footer')
        footer.append(meta_row)
        text.append(footer)

        self.flow.insert(
            card,
            -1,
        )
        wrapper=card.get_parent()

        if view!='list':
            wrapper.set_size_request(
                width+4,
                total_height,
            )
            wrapper.set_halign(
                Gtk.Align.START
            )
            wrapper.set_valign(
                Gtk.Align.START
            )
            wrapper.set_hexpand(
                False
            )
            wrapper.set_vexpand(
                False
            )
        entry={
            'widget':card,
            'wrapper':wrapper,
            'overlay':overlay,
            'click':click,
            'text':text,
            'title':title,
            'badge':badge,
            'check':check,
            'picture':pic,
            'fallback':fallback,
            'meta':meta,
            'os_badge':os_badge,
            'test_meta':test_meta,
            'meta_row':meta_row,
            'data':game,
            'size':(width,height),
            'hovered':False,
        };self.cards[game['game']]=entry;self.paint_card(entry)
        self.attach_game_context(card,lambda:entry['data'])
        self.attach_card_selection(entry)
    def paint_card(self,entry):
        game=entry['data']
        entry['check'].set_sensitive(not bool(game.get('blocked')))

        view=self.settings.get(
            'library_view',
            'posters',
        )

        if view in (
            'capsules',
            'list',
        ):
            path=self.wide_art_path(game)
        else:
            path=poster_art_path(game)
        if path:
            try:
                texture=Gdk.Texture.new_from_filename(path)
                entry['picture'].set_paintable(texture)
                entry['picture'].queue_resize()
                entry['fallback'].set_visible(False)
                if game.get('accent_class'):entry['widget'].remove_css_class(game['accent_class'])
                accent_path=accent_source(game) or path
                game['accent_class']=artwork_accent(accent_path,self.settings.get('game_accents',{}).get(game['game']),muted=bool(game.get('blocked')));entry['widget'].add_css_class(game['accent_class'])
            except Exception:entry['fallback'].set_visible(True)
        else:
            entry['picture'].set_paintable(None);entry['fallback'].set_visible(True)
        self.decorate_support_artwork(entry['overlay'],entry['picture'],game,path)
        state='Unsupported' if game.get('blocked') else 'Installed' if game.get('installed') else 'Available'
        entry['meta'].set_text(state.upper())
        installed_on=game.get('installed_on') if game.get('installed') else None
        on_art=installed_on in ('linux','windows') and self.settings.get('library_view','posters')!='list'
        # Posters and capsules carry the mark on the art; List keeps it beside the status.
        entry['meta'].set_os(None if on_art else installed_on)
        badge=entry.get('os_badge')
        if badge is not None:
            badge.set_visible(on_art)
            if on_art:
                badge._icon.set_from_icon_name('rtx-os-'+installed_on+'-symbolic')
                badge.set_tooltip_text('Installed with rtxForge on '+installed_on.title())
        for css in ('state-installed','state-available','state-unsupported'):entry['meta'].remove_css_class(css)
        entry['meta'].add_css_class('state-'+state.lower())

        test_meta=entry.get(
            'test_meta'
        )

        if test_meta is not None:
            test_status=library_display_test_status(
                game
            )

            test_meta.set_text(
                test_status.upper()
            )

            for css_class in (
                'test-untested',
                'test-tested',
            ):
                test_meta.remove_css_class(
                    css_class
                )

            test_meta.add_css_class(
                'test-untested'
                if test_status.casefold()=='untested'
                else 'test-tested'
            )
            # Only a tested game carries the (icon-only) test badge.
            test_meta.set_visible(test_status.casefold() not in ('untested','n/a',''))
            test_meta.set_tooltip_text(test_status)
        entry['widget'].set_tooltip_text(game['name']+'\n'+(game.get('art_credit') or 'Artwork pending'))
    def filter_games(self):
        if not hasattr(
            self,
            'search'
        ):
            return

        if self.settings.get(
            'library_view',
            'posters',
        )=='list':
            self.list_filter.changed(
                Gtk.FilterChange.DIFFERENT
            )
            self._column_schedule_height_refresh()
            self._column_sync_selection_widgets()
            self._update_selection_summary()
            return

        text=self.search.get_text().casefold()

        for entry in self.cards.values():
            game=entry['data']

            visible=(
                text
                in game[
                    'name'
                ].casefold()
                and (
                    self.filter=='all'
                    or (
                        self.filter=='installed'
                        and game.get(
                            'installed'
                        )
                    )
                    or (
                        self.filter=='available'
                        and not game.get(
                            'blocked'
                        )
                    )
                )
            )

            entry[
                'wrapper'
            ].set_visible(
                bool(
                    visible
                )
            )

        self.update_library_spacing()
        self.selection_changed()


    def select_all(self,active):
        # Select all takes every supported game in the current view
        # (filter + search); Clear empties the whole selection.
        if active:
            self.selected_game_ids={
                game['game']
                for game in self.games
                if not game.get('blocked') and self.game_matches_view(game)
            }
        else:
            self.selected_game_ids.clear()

        self._selection_syncing=True

        try:
            for game_id,entry in self.cards.items():
                check=entry.get(
                    'check'
                )

                if check is not None:
                    check.set_active(
                        game_id
                        in self.selected_game_ids
                    )
        finally:
            self._selection_syncing=False

        for game_id,entry in self.cards.items():
            method=entry['widget'].add_css_class if game_id in self.selected_game_ids else entry['widget'].remove_css_class
            method('selected')
            self.sync_card_check(entry)
        self._column_sync_selection_widgets()
        self._update_selection_summary()

    def attach_card_selection(self,entry):
        """Photos-style selection on a poster or capsule card.

        The check appears on hover and stays on every card while anything
        is selected; unsupported games never show one. Clicking the check
        toggles selection, clicking anywhere else opens the game.
        """
        card=entry['widget'];check=entry['check']
        motion=Gtk.EventControllerMotion()
        def hover(value):
            entry['hovered']=value;self.sync_card_check(entry)
        motion.connect('enter',lambda *_:hover(True))
        motion.connect('leave',lambda *_:hover(False))
        card.add_controller(motion)
        click=Gtk.GestureClick(button=Gdk.BUTTON_PRIMARY)
        def released(_gesture,_count,x,y):
            target=card.pick(x,y,Gtk.PickFlags.DEFAULT)
            # The check and the artwork button handle their own clicks.
            while target is not None and target is not card:
                if target is check or isinstance(target,Gtk.Button):return
                target=target.get_parent()
            self.library_game_activated(entry['data'])
        click.connect('released',released)
        card.add_controller(click)
        self.sync_card_check(entry)

    def sync_card_check(self,entry):
        check=entry.get('check')
        if check is None:return
        check.set_visible(
            not entry['data'].get('blocked')
            and bool(entry.get('hovered') or check.get_active() or self.selected_game_ids)
        )

    def library_game_activated(self,game):
        """A click on a game: its Details, or in presets mode, its presets review."""
        if getattr(self,'preset_selecting',False):
            self.apply_presets_to([game])
            return
        self.details(game)


    def selection_changed(self,*_):
        if getattr(
            self,
            '_selection_syncing',
            False,
        ):
            return

        if self.settings.get(
            'library_view',
            'posters',
        )!='list':
            self.selected_game_ids={
                game_id
                for game_id,entry in self.cards.items()
                if (
                    entry.get(
                        'check'
                    )
                    is not None
                    and not entry['data'].get('blocked')
                    and entry[
                        'check'
                    ].get_active()
                )
            }

            for game_id,entry in self.cards.items():
                if (
                    game_id
                    in self.selected_game_ids
                ):
                    entry[
                        'widget'
                    ].add_css_class(
                        'selected'
                    )
                else:
                    entry[
                        'widget'
                    ].remove_css_class(
                        'selected'
                    )

            for entry in self.cards.values():
                self.sync_card_check(entry)

        self._column_sync_selection_widgets()
        self._update_selection_summary()


    def fetch_media(self,refresh=False):
        if getattr(self,'art_loading',False):self.art_pending=True;return
        self.art_loading=True;self.cancel_art.clear();games=list(self.games);settings=dict(self.settings)
        def finished_art():
            self.art_loading=False
            if getattr(self,'art_pending',False):self.art_pending=False;self.fetch_media()
            return False
        def load():
            try:
                media=library_media.LibraryMedia(self.service.config,settings)
                for game in games:
                    if self.cancel_art.is_set():break
                    try:data=media.enrich(game,refresh)
                    except Exception:continue
                    GLib.idle_add(self.event,{'kind':'art','game':game['game'],'data':data})
            finally:GLib.idle_add(finished_art)
        threading.Thread(target=load,daemon=True).start()
    def details(self,game):
        d,b,f=self.open_panel(
            game['name'],
            width=920,
            height=700,
            resizable=True,
        )
        self.detail_resize_source=0

        # Replace the generic dialog shell with a Settings-style
        # full-height sidebar and a cinematic main pane.
        detail_shell=d.get_child()
        detail_header=detail_shell.get_first_child()
        old_scroll=detail_header.get_next_sibling()
        detail_footer=old_scroll.get_next_sibling()

        old_scroll.set_child(None)
        detail_shell.remove(detail_footer)
        d.set_child(None)

        detail_root=Gtk.Box(
            hexpand=True,
            vexpand=True,
        )
        detail_root.add_css_class(
            'game-detail-root'
        )

        sidebar=Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            width_request=210,
            vexpand=True,
        )
        sidebar.add_css_class(
            'game-detail-sidebar'
        )

        sidebar_header=Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=2,
        )
        sidebar_header.add_css_class(
            'game-detail-sidebar-header'
        )
        sidebar_header.append(
            label(
                'Game Details',
                'title-2',
            )
        )

        sidebar.append(
            sidebar_header
        )

        nav=Gtk.ListBox(
            selection_mode=Gtk.SelectionMode.SINGLE,
            valign=Gtk.Align.START,
        )
        nav.add_css_class(
            'game-detail-nav'
        )
        sidebar.append(
            nav
        )

        main=Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            hexpand=True,
            vexpand=True,
        )
        main.add_css_class(
            'game-detail-main'
        )

        detail_root.append(
            sidebar
        )
        detail_root.append(
            main
        )

        d.set_child(
            detail_root
        )

        f=detail_footer
        f.add_css_class(
            'detail-footer'
        )

        if game.get('accent_class'):
            d.add_css_class(game['accent_class'])

        DETAIL_HERO_HEIGHT=280

        banner=Gtk.Overlay(
            height_request=DETAIL_HERO_HEIGHT,
            vexpand=False,
        )
        banner.add_css_class('game-banner')
        banner.set_vexpand(False)
        banner.set_valign(Gtk.Align.START)
        banner.set_overflow(Gtk.Overflow.HIDDEN)
        banner.set_size_request(
            -1,
            DETAIL_HERO_HEIGHT,
        )
        detail_window_handle=Gtk.WindowHandle()
        detail_window_handle.set_hexpand(
            True
        )
        detail_window_handle.set_child(
            banner
        )

        main.append(
            detail_window_handle
        )

        image=HeroPicture(
            content_fit=Gtk.ContentFit.COVER,
            can_shrink=True,
            height_request=DETAIL_HERO_HEIGHT,
        )
        image.hero_height=DETAIL_HERO_HEIGHT
        image.set_vexpand(False)
        image.set_valign(Gtk.Align.START)
        image.set_size_request(
            -1,
            DETAIL_HERO_HEIGHT,
        )
        image.set_vexpand(
            False
        )
        if game.get('hero'):
            try:image.set_paintable(Gdk.Texture.new_from_filename(game['hero']))
            except Exception:pass
        banner.set_child(image);shade=Gtk.Box();shade.add_css_class('banner-shade');banner.add_overlay(shade)
        self.detail_game=game['game'];self.detail_dialog=d;self.detail_banner=image

        def detail_closed(*_):
            if getattr(self,'detail_dialog',None) is d:
                self.detail_dialog=None
                self.detail_game=None

            if getattr(self,'dialog',None) is d:
                self.dialog=None

        if isinstance(d,ResizablePanelWindow):
            d.connect(
                'destroy',
                detail_closed,
            )
        else:
            d.connect(
                'closed',
                detail_closed,
            )
        close=Gtk.Button(
            icon_name='window-close-symbolic',
            valign=Gtk.Align.CENTER,
            halign=Gtk.Align.END,
        )
        close.add_css_class(
            'game-detail-close'
        )
        close.set_tooltip_text(
            'Close'
        )

        close_state={
            'done':False,
        }

        def close_game_details(*_):
            if close_state['done']:
                return

            close_state['done']=True

            if getattr(
                self,
                'dialog',
                None,
            ) is d:
                self.dialog=None

            if getattr(
                self,
                'detail_dialog',
                None,
            ) is d:
                self.detail_dialog=None
                self.detail_game=None

            try:
                d.force_close()
            except Exception:
                try:
                    d.destroy()
                except Exception:
                    pass
        close.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ['Close game details'],
        )

        close.connect(
            'clicked',
            close_game_details,
        )

        close_gesture=Gtk.GestureClick()
        close_gesture.set_button(
            1
        )
        close_gesture.set_propagation_phase(
            Gtk.PropagationPhase.CAPTURE
        )
        close_gesture.connect(
            'pressed',
            close_game_details,
        )
        close.add_controller(
            close_gesture
        )

        close_holder=Gtk.Box(
            halign=Gtk.Align.END,
            valign=Gtk.Align.START,
        )
        margins(
            close_holder,
            16,
        )
        close_holder.append(
            close
        )


        hero_light=False

        if game.get('hero'):
            hero_light=hero_title_background_is_light(
                game['hero']
            )

        banner.add_css_class(
            'hero-light'
            if hero_light
            else 'hero-dark'
        )

        if hero_light:
            close.add_css_class('light')
        # Anchor the poster and left-aligned text to the hero’s lower edge.
        identity=Gtk.Box(
            spacing=16,
            valign=Gtk.Align.END,
            halign=Gtk.Align.FILL,
            hexpand=True,
        )
        identity.set_margin_start(16)
        identity.set_margin_end(16)

        identity.set_margin_top(16)
        identity.set_margin_bottom(16)

        detail_poster_source=poster_art_path(game)

        if detail_poster_source:
            DETAIL_POSTER_WIDTH=104
            DETAIL_POSTER_HEIGHT=156
            DETAIL_POSTER_FRAME_WIDTH=110
            DETAIL_POSTER_FRAME_HEIGHT=162

            detail_poster=CoverPicture(
                content_fit=Gtk.ContentFit.COVER,
                can_shrink=True,
            )
            detail_poster.cover_width=DETAIL_POSTER_WIDTH
            detail_poster.cover_ratio=2/3
            detail_poster.set_size_request(
                DETAIL_POSTER_WIDTH,
                DETAIL_POSTER_HEIGHT,
            )
            detail_poster.add_css_class(
                'progress-poster'
            )
            detail_poster.set_overflow(
                Gtk.Overflow.HIDDEN
            )

            try:
                detail_poster.set_paintable(
                    Gdk.Texture.new_from_filename(
                        str(detail_poster_source)
                    )
                )
            except Exception:
                pass

            detail_poster_frame=Gtk.Frame(
                width_request=DETAIL_POSTER_FRAME_WIDTH,
                height_request=DETAIL_POSTER_FRAME_HEIGHT,
                halign=Gtk.Align.START,
                valign=Gtk.Align.END,
            )
            detail_poster_frame.add_css_class(
                'progress-poster-frame'
            )
            detail_poster_frame.set_overflow(
                Gtk.Overflow.VISIBLE
            )
            detail_poster_frame.set_child(
                detail_poster
            )

            identity.append(
                detail_poster_frame
            )

        heading=Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=4,
            valign=Gtk.Align.END,
            hexpand=True,
        )

        # Feature/status tag ABOVE the game name.
        mode_name=(
            'Unsupported' if game.get('blocked') else
            game.get('profile') if game.get('installed')
            else 'Ready for Features'
        )

        status=label(
            mode_name or 'Ready for Features',
            'cover-badge',
        )
        if game.get('blocked'):status.add_css_class('unsupported-badge')
        status.set_halign(
            Gtk.Align.START
        )
        heading.append(
            status
        )

        detail_title_text=str(
            game['name']
        ).strip()

        detail_title=label(
            detail_title_text,
            'game-banner-title',
        )

        # Game Details titles are never ellipsized.
        # Longer names wrap naturally and step down in font size.
        detail_title.set_wrap(
            True
        )
        detail_title.set_wrap_mode(
            Pango.WrapMode.WORD_CHAR
        )
        detail_title.set_single_line_mode(
            False
        )
        detail_title.set_lines(
            -1
        )
        detail_title.set_ellipsize(
            Pango.EllipsizeMode.NONE
        )
        detail_title.set_width_chars(
            1
        )
        detail_title.set_max_width_chars(
            42
        )
        detail_title.set_hexpand(
            True
        )
        detail_title.set_halign(
            Gtk.Align.FILL
        )

        title_length=len(
            detail_title_text
        )

        longest_word=max(
            (
                len(word)
                for word in detail_title_text.split()
            ),
            default=0,
        )

        if (
            title_length >= 52
            or longest_word >= 24
        ):
            detail_title.add_css_class(
                'detail-title-xs'
            )

        elif (
            title_length >= 40
            or longest_word >= 20
        ):
            detail_title.add_css_class(
                'detail-title-sm'
            )

        elif (
            title_length >= 28
            or longest_word >= 16
        ):
            detail_title.add_css_class(
                'detail-title-md'
            )

        heading.append(
            detail_title
        )

        meta_parts=[
            str(value)
            for value in (
                game.get('developers'),
                game.get('release'),
            )
            if value
        ]

        metadata_line=Gtk.Box(spacing=8,halign=Gtk.Align.FILL)
        heading.append(metadata_line)
        if meta_parts:
            meta=label(
                ' · '.join(meta_parts),
                'game-detail-meta',
            )
            meta.set_max_width_chars(32)
            meta.set_width_chars(1)
            meta.set_wrap(False)
            meta.set_single_line_mode(True)
            meta.set_tooltip_text(' · '.join(meta_parts))
            meta.set_ellipsize(
                Pango.EllipsizeMode.END
            )
            metadata_line.append(meta)

        source_badge=LibraryPill(kind='source')
        source_badge.add_css_class('library-source-pill')
        source_badge.set_fixed_width(108)
        source_badge.set_text('STEAM' if game.get('source')=='Steam' else 'NON-STEAM')
        test_badge=LibraryPill(kind='status')
        test_badge.add_css_class('library-test-pill')
        test_badge.set_fixed_width(108)
        test_status=library_display_test_status(game)
        test_badge.set_text(test_status.upper())
        test_badge.add_css_class('test-untested' if test_status.casefold()=='untested' else 'test-tested')
        metadata_line.append(source_badge)
        installed_on=game.get('installed_on') if game.get('installed') else None
        if installed_on in ('linux','windows'):
            # Windows GamePage OsBadge: between the source and tested pills.
            os_badge=LibraryPill(kind='source')
            os_badge.add_css_class('library-source-pill')
            os_badge.set_fixed_width(108)
            os_badge.set_text(installed_on.upper())
            os_badge.set_tooltip_text('Installed with rtxForge on '+installed_on.title())
            metadata_line.append(os_badge)
        metadata_line.append(test_badge)


        summary=label(game.get('description') or '', 'game-detail-summary')
        summary.set_tooltip_text(game.get('description') or '')
        summary.set_lines(2)
        summary.set_max_width_chars(54)
        summary.set_ellipsize(Pango.EllipsizeMode.END)
        summary.set_size_request(-1,34)
        heading.append(summary)

        identity.append(
            heading
        )

        banner.add_overlay(
            identity
        )


        # Add close control last so no hero overlay can intercept it.
        banner.add_overlay(
            close_holder
        )
        pages=Gtk.Stack(
            transition_type=Gtk.StackTransitionType.CROSSFADE,
            transition_duration=220,
            hexpand=True,
        )
        pages.set_vhomogeneous(
            False
        )

        detail_content_scroll=Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vscrollbar_policy=Gtk.PolicyType.NEVER,
            hexpand=True,
            vexpand=True,
        )
        detail_content_scroll.set_child(
            pages
        )

        main.append(
            detail_content_scroll
        )

        content={}

        # One stable Settings-style footer. Only its actions change.
        clear(f)

        f.set_halign(
            Gtk.Align.FILL
        )
        f.set_margin_top(0)
        f.set_margin_bottom(0)
        f.set_margin_start(0)
        f.set_margin_end(0)

        detail_action_stack=Gtk.Stack(
            hexpand=True,
            transition_type=Gtk.StackTransitionType.CROSSFADE,
            transition_duration=120,
        )

        detail_action_rows={}

        for action_page in (
            'Overview',
            'Features',
            'DLSS Files',
            'Tools',
            'Appearance',
            'Notes',
        ):
            action_row=Gtk.Box(
                spacing=7,
                hexpand=True,
                halign=Gtk.Align.END,
                valign=Gtk.Align.CENTER,
            )

            action_row.add_css_class(
                'detail-footer-actions'
            )

            detail_action_rows[action_page]=action_row

            detail_action_stack.add_named(
                action_row,
                action_page,
            )

        f.append(
            detail_action_stack
        )

        detail_icons={
            'Overview':'dialog-information-symbolic',
            'Features':'applications-system-symbolic',
            'DLSS Files':'folder-symbolic',
            'Tools':'applications-utilities-symbolic',
            'Notes':'document-edit-symbolic',
            'Appearance':'applications-graphics-symbolic',
        }

        for name in (
            'Overview',
            'Features',
            'DLSS Files',
            'Tools',
            'Appearance',
            'Notes',
        ):
            page=Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=16,
            )
            margins(
                page,
                16,
            )
            page.set_vexpand(
                False
            )

            content[name]=page

            pages.add_titled(
                page,
                name,
                name,
            )

            nav_row=Gtk.ListBoxRow()
            nav_row.page_name=name

            nav_line=Gtk.Box(
                spacing=11,
                valign=Gtk.Align.CENTER,
            )
            nav_line.append(
                Gtk.Image.new_from_icon_name(
                    detail_icons[name]
                )
            )
            nav_line.append(
                label(name)
            )

            nav_row.set_child(
                nav_line
            )
            nav.append(
                nav_row
            )

        def detail_nav_selected(_nav,row):
            if row is None:
                return

            pages.set_visible_child_name(
                row.page_name
            )

            detail_action_stack.set_visible_child_name(
                row.page_name
            )

        nav.connect(
            'row-selected',
            detail_nav_selected,
        )

        self.detail_nav=nav
        def sync_detail_page(*_):
            name=pages.get_visible_child_name()
            for index in range(len(content)):
                candidate=nav.get_row_at_index(index)
                if candidate.page_name==name and nav.get_selected_row() is not candidate:
                    nav.select_row(candidate)
                    break
            detail_action_stack.set_visible_child_name(name)
            detail_content_scroll.get_vadjustment().set_value(0)
        pages.connect('notify::visible-child-name',sync_detail_page)

        first_detail_row=nav.get_row_at_index(
            0
        )

        if first_detail_row is not None:
            nav.select_row(
                first_detail_row
            )

        # Footer belongs to the cinematic/main side, not the sidebar.
        main.append(
            f
        )

        detail_scroll=detail_content_scroll
        self.detail_scroll=detail_content_scroll
        detail_scroll.set_policy(
            Gtk.PolicyType.NEVER,
            Gtk.PolicyType.AUTOMATIC,
        )

        def fit_detail_page(*_):
            # Sidebar navigation must not reshape the dialog or hero.
            return False

        self.detail_pages=pages
        self.detail_fit_page=fit_detail_page
        self.populate_tools(content['Tools'],game)
        overview=content['Overview']
        if game.get('blocked'):overview.append(self.unsupported_notice(game))
        info=Adw.PreferencesGroup(title='Game Information');overview.append(info)
        for title,value in [('Library',game.get('library')),('Location',game['game']),('Compatibility',None if game.get('blocked') else 'Supported'),('Metadata Source',game.get('metadata_source')),('Developer',game.get('developers')),('Release',game.get('release'))]:
            if value:info.add(row(title,value))
        features=content['Features'];installed=game.get('installed',False)
        if installed:
            features.append(label('Saved NR: '+('enabled' if game.get('nr_enabled') else 'disabled')+' · runtime and visual results require diagnosis.','dim-label'))
        tuning,widgets=self.tuning_controls(game)
        presets=Gtk.Expander(label='Presets',expanded=False)
        presets.add_css_class('presets-header')
        presets_body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16)
        presets_body.set_margin_top(16)
        presets.set_child(presets_body)
        features.append(presets)
        presets_body.append(label('Tuning values for this game. Reset restores your library presets. Apply saves them for this game.','dim-label'))
        presets_body.append(tuning)
        preset_reset=button('Reset',lambda *_:self.launch_action('reset',targets=[game]))
        preset_reset.set_halign(Gtk.Align.END)
        preset_actions=Gtk.Box(spacing=8,halign=Gtk.Align.END)
        preset_actions.append(preset_reset)
        mode=game.get('feature_mode') or {'NR Only':'nr-only','MFG Only':'mfg-only'}.get(game.get('profile'),'nr-mfg')
        for key,w in widgets.items():w.set_sensitive(installed and not (key=='nr_strength' and mode=='mfg-only') and not (key=='mfg_multiplier' and mode=='nr-only'))
        apply=button(
            'Apply',
            lambda *_:self.launch_action(
                'reset',
                targets=[game],
                visual_settings=self.tuning_values(widgets),
            ),
            'suggested-action',
        )
        apply.set_valign(
            Gtk.Align.CENTER
        )
        unknown_presets=[key for key in widgets if game.get(key) is None and widgets[key].get_sensitive()]
        if installed and unknown_presets:
            presets_body.append(label('Custom or unreadable preset values found. Reset explicitly to library defaults before editing; existing values are preserved.','dim-label'))
        preset_actions.append(apply)
        presets_body.append(preset_actions)
        def changed(*_):apply.set_sensitive(installed and not unknown_presets and any(v!=game.get(k) for k,v in self.tuning_values(widgets).items() if widgets[k].get_sensitive()))
        for key,w in widgets.items():w.connect('notify::selected' if key=='mfg_multiplier' else 'value-changed',changed)
        changed();self.detail_tuning_widgets=widgets;self.detail_apply_settings=apply
        maintenance=Adw.PreferencesGroup(
            title='Installation'
        )
        features.append(
            maintenance
        )

        for title,subtitle,op in [
            (
                'Install Features',
                'Add or update the selected feature mode.',
                'install',
            ),
            (
                'Repair Feature Files',
                'Replace missing or damaged feature files while preserving your presets.',
                'repair',
            ),
            (
                'Restore Original Files',
                'Restore the original files.',
                'uninstall',
            ),
        ]:
            maintenance_row=row(title,subtitle)
            maintenance.add(maintenance_row)

            action=button(
                'Install'
                if op=='install'
                else 'Repair'
                if op=='repair'
                else 'Reset'
                if op=='reset'
                else 'Restore',
                lambda _,o=op:self.launch_action(
                    o,
                    targets=[game],
                ),
            )

            action.set_valign(
                Gtk.Align.CENTER
            )

            action.set_sensitive(
                installed
                if op in (
                    'reset',
                    'uninstall',
                )
                else (
                    not game.get('blocked')
                    and bool(
                        self.hardware_info
                        and self.hardware_info['ready']
                    )
                )
            )

            if op=='uninstall':
                action.add_css_class(
                    'destructive-action'
                )

            maintenance_row.add_suffix(action)
        file_page=content['DLSS Files']
        inventory=Adw.PreferencesGroup(title='Installed DLSS Files',description='Updater backups are previous copies, not proof of the version currently shipped by the game.')
        inventory_status=row('Checking files…','No files are changed by opening this tab.')
        inventory.add(inventory_status)
        file_page.append(inventory)
        files=Adw.PreferencesGroup(title='File Management')
        file_page.append(files)
        file_buttons={}
        for title,subtitle,caption,restore in (
            ('Update files','Update older supported files, keeping backups.','Update Files',False),
            ('Restore original files','Restore the latest DLSS backup for this game.','Restore Files',True),
        ):
            item=row(title,subtitle)
            action=button(caption,lambda _,restore=restore:self.manage_dlss_files(game,restore))
            action.set_valign(Gtk.Align.CENTER)
            action.set_sensitive(False)
            if restore:
                item.add_suffix(action)
                files.add(item)
            else:
                action.set_label('Update All')
                action.set_tooltip_text('Update all older DLSS files for this game')
                action.add_css_class('suggested-action')
                detail_action_rows['DLSS Files'].append(action)
            file_buttons[restore]=action
        replace_row=row('Replace with verified copies','Also checks same-version files. Identical files are skipped; changed files are backed up.')
        replace_button=button('Replace Files',lambda *_:self.manage_dlss_files(game,replace_same=True))
        replace_button.set_valign(Gtk.Align.CENTER)
        replace_button.set_sensitive(False)
        replace_row.add_suffix(replace_button)
        files.add(replace_row)
        loaded={'value':False}
        def show_inventory(result):
            if self.detail_dialog is not d:return
            import runtime_updates
            found,backups=result
            inventory.remove(inventory_status)
            if found['blocked']:
                inventory.add(row('File management unavailable',user_messages.friendly_error(found['blocked'])))
                inventory.add(self.technical_details(found['blocked']))
            elif not found['files']:
                inventory.add(row('No supported DLSS files','No separate DLSS files were found outside the installed feature stack.'))
            for item in found['files']:
                inventory.add(row(runtime_updates.COMPONENTS[item['component']],item['path']+' · '+item['current']+' · '+item['provenance']))
            file_buttons[False].set_sensitive(bool(found['files']) and not found['blocked'])
            replace_button.set_sensitive(bool(found['files']) and not found['blocked'])
            file_buttons[True].set_sensitive(bool(backups))
            if backups:
                files.add(row('Latest backup',backups[0]['date']))
        def load_inventory(*_):
            if self.detail_dialog is not d:return False
            if pages.get_visible_child_name()!='DLSS Files' or loaded['value']:return False
            if self.options.demo:
                inventory_status.set_title('Preview mode')
                inventory_status.set_subtitle('File versions appear here for your installed games. Game writes are disabled.')
                loaded['value']=True
                return False
            if self.busy:
                GLib.timeout_add(200,load_inventory)
                return False
            import runtime_updates
            loaded['value']=True
            self.start('Checking native DLSS files',lambda:(
                runtime_updates.inspect(self.service.config,[game])[0],
                runtime_updates.game_recoveries(self.service.config,game['game'])),show_inventory)
            return False
        pages.connect('notify::visible-child-name',load_inventory)

        notes_page=content['Notes'];record=game.get('test_record',{'status':'Untested','notes':''});choice=safe_dropdown(list(game_notes.STATES));choice.set_selected(list(game_notes.STATES).index(record.get('status','Untested')));choice.set_valign(Gtk.Align.CENTER)
        group=Adw.PreferencesGroup(title='Your Notes');notes_page.append(group);item=row('Test Result','Bench excludes this game from bulk installation and repair.');item.add_suffix(choice);group.add(item)
        notes=Gtk.TextView(
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            height_request=82,
        )
        notes.add_css_class('game-notes')
        notes.get_buffer().set_text(
            record.get('notes','')
        )
        notes_page.append(
            notes
        )
        def save_notes(*_):
            buf=notes.get_buffer();current=dict(record);current.update(status=list(game_notes.STATES)[choice.get_selected()],notes=buf.get_text(buf.get_start_iter(),buf.get_end_iter(),True))
            if not self.options.demo:game_notes.save(self.service.config,game['game'],current)
            game['test_record']=current;self.toast('Notes saved')
        save_notes_button=button(
            'Save Notes',
            save_notes,
            'suggested-action',
        )
        detail_action_rows['Notes'].append(
            save_notes_button
        )

        active=bool(
            record.get('active')
        )

        test=button(
            'Finish Test'
            if active
            else 'Start Test',
            lambda *_:self.record_test(
                game,
                active,
            ),
        )
        test.set_sensitive(
            not self.options.demo
        )

        detail_action_rows['Notes'].append(
            test
        )
        appearance=content['Appearance']
        appearance.append(self.artwork_preferences(game))

        accent_group=Adw.PreferencesGroup(
            title='Accent Color',
            description='Pick any color directly from this game’s poster.',
        )
        appearance.append(accent_group)

        current_accent=(
            self.settings
            .get('game_accents',{})
            .get(game['game'])
        )

        accent_row=row(
            'Game Accent',
            (
                'Custom · '+current_accent.upper()
                if current_accent
                else 'Artwork-derived'
            ),
        )

        swatch=Gtk.DrawingArea(width_request=32,height_request=32,valign=Gtk.Align.CENTER)
        def draw_swatch(_area,cr,width,height):
            color=self.settings.get('game_accents',{}).get(game['game']) or ('#'+game.get('accent_class','art-76b900').removeprefix('art-'))
            rgba=Gdk.RGBA()
            if not rgba.parse(color):rgba.parse('#76b900')
            cr.set_source_rgba(rgba.red,rgba.green,rgba.blue,1)
            cr.arc(width/2,height/2,min(width,height)/2-2,0,6.283185)
            cr.fill()
        swatch.set_draw_func(draw_swatch)
        accent_row.add_suffix(swatch)
        accent_group.add(accent_row)

        def set_color(color):
            self.settings.setdefault(
                'game_accents',
                {},
            )[game['game']]=color

            if not self.options.demo:
                library_media.save_settings(
                    self.service.config,
                    self.settings,
                )

            old=game.get('accent_class')

            if old:
                d.remove_css_class(old)

                entry=self.cards.get(
                    game['game']
                )

                if entry:
                    entry['widget'].remove_css_class(
                        old
                    )

            source=(
                game.get('poster')
                or game.get('capsule')
                or game.get('hero')
            )

            if not source:
                self.toast(
                    'No artwork is available for this game.'
                )
                return

            game['accent_class']=artwork_accent(
                source,
                color,
            )

            d.add_css_class(
                game['accent_class']
            )

            accent_row.set_subtitle(
                'Custom · '+color.upper()
            )
            swatch.queue_draw()

            entry=self.cards.get(
                game['game']
            )

            if entry:
                self.paint_card(entry)

            if hasattr(
                self,
                '_column_refresh_game'
            ):
                self._column_refresh_game(
                    game
                )

        def pick_accent_from_poster(*_):
            source=(
                game.get('poster')
                or game.get('capsule')
                or game.get('hero')
            )

            if not source:
                self.toast(
                    'No poster artwork is available.'
                )
                return

            try:
                pix=GdkPixbuf.Pixbuf.new_from_file(
                    str(source)
                )

                texture=Gdk.Texture.new_from_filename(
                    str(source)
                )

            except Exception as ex:
                self.toast(
                    'Could not open this game’s artwork.'
                )
                self.log.append(
                    str(ex)
                )
                return

            old_picker=getattr(
                self,
                'accent_picker_window',
                None,
            )

            if old_picker is not None:
                try:
                    old_picker.close()
                except Exception:
                    pass

            sw=max(1,pix.get_width())
            sh=max(1,pix.get_height())

            max_w=380
            max_h=560

            scale=min(
                max_w/sw,
                max_h/sh,
            )

            display_w=max(
                220,
                round(sw*scale),
            )

            display_h=max(
                300,
                round(sh*scale),
            )

            # Real top-level modal window owned by Game Details.
            # It stays above Game Details and is movable by its HeaderBar.
            picker=Adw.Window(
                application=self.get_application(),
                transient_for=d,
                modal=True,
                title='Pick Accent Color',
                default_width=display_w+52,
                default_height=display_h+300,
                resizable=False,
            )

            picker.set_destroy_with_parent(
                True
            )

            self.accent_picker_window=picker

            root=Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
            )

            picker.set_content(
                root
            )

            header=Adw.HeaderBar()

            header.set_title_widget(
                Adw.WindowTitle(
                    title='Pick Accent Color',
                )
            )

            root.append(
                header
            )

            shell=Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=12,
            )

            margins(
                shell,
                18,
            )

            root.append(
                shell
            )

            instructions=label(
                'Choose a pixel to preview it as this game’s accent.',
                'dim-label',
            )

            instructions.set_halign(
                Gtk.Align.CENTER
            )

            instructions.set_xalign(
                0.5
            )

            shell.append(
                instructions
            )

            current_class=str(
                game.get(
                    'accent_class',
                    '',
                )
            )

            initial_color=current_accent

            if (
                not initial_color
                and current_class.startswith('art-')
                and len(current_class)==10
            ):
                initial_color=(
                    '#'
                    + current_class[4:]
                )

            if not initial_color:
                initial_color='#76b900'

            pending={
                'color':initial_color,
            }

            preview_label=label(
                initial_color.upper(),
                'dim-label',
            )

            preview_label.set_halign(
                Gtk.Align.CENTER
            )

            preview_label.set_xalign(
                0.5
            )

            frame=Gtk.Box(
                halign=Gtk.Align.CENTER,
                valign=Gtk.Align.CENTER,
            )

            frame.add_css_class(
                'accent-picker-art-frame'
            )

            clip=Gtk.Box()

            clip.add_css_class(
                'accent-picker-art-clip'
            )

            clip.set_overflow(
                Gtk.Overflow.HIDDEN
            )

            frame.append(
                clip
            )

            poster=Gtk.Picture(
                paintable=texture,
                content_fit=Gtk.ContentFit.FILL,
                can_shrink=True,
                width_request=display_w,
                height_request=display_h,
            )

            poster.set_halign(
                Gtk.Align.CENTER
            )

            poster.set_valign(
                Gtk.Align.CENTER
            )

            # The poster sits under a loupe that magnifies the pixels around
            # the pointer, so a single pixel can be picked precisely.
            stage=Gtk.Overlay()
            stage.set_child(poster)
            clip.append(
                stage
            )
            LOUPE_PIXELS=11
            LOUPE_CELL=9
            loupe=Gtk.DrawingArea(
                width_request=LOUPE_PIXELS*LOUPE_CELL,
                height_request=LOUPE_PIXELS*LOUPE_CELL,
                halign=Gtk.Align.START,
                valign=Gtk.Align.START,
                can_target=False,
                visible=False,
            )
            loupe.add_css_class('accent-loupe')
            stage.add_overlay(loupe)
            stage.set_measure_overlay(loupe,False)
            pointer={'x':0,'y':0}

            def source_pixel(x,y):
                width=max(1,poster.get_width());height=max(1,poster.get_height())
                return (min(sw-1,max(0,int(x/width*sw))),min(sh-1,max(0,int(y/height*sh))))

            def pixel_color(px,py):
                channels=pix.get_n_channels();stride=pix.get_rowstride();data=pix.get_pixels()
                off=py*stride+px*channels
                return int(data[off]),int(data[off+1]),int(data[off+2])

            def draw_loupe(_area,cr,width,height):
                cx,cy=source_pixel(pointer['x'],pointer['y'])
                half=LOUPE_PIXELS//2
                cr.arc(width/2,height/2,width/2-1,0,6.283185)
                cr.clip()
                for row in range(LOUPE_PIXELS):
                    for column in range(LOUPE_PIXELS):
                        px=min(sw-1,max(0,cx+column-half));py=min(sh-1,max(0,cy+row-half))
                        r,g,b=pixel_color(px,py)
                        cr.set_source_rgb(r/255,g/255,b/255)
                        cr.rectangle(column*LOUPE_CELL,row*LOUPE_CELL,LOUPE_CELL,LOUPE_CELL)
                        cr.fill()
                # The picked pixel, outlined in both light and dark.
                cr.set_line_width(2)
                cr.set_source_rgba(0,0,0,0.75)
                cr.rectangle(half*LOUPE_CELL,half*LOUPE_CELL,LOUPE_CELL,LOUPE_CELL);cr.stroke()
                cr.set_line_width(1)
                cr.set_source_rgba(1,1,1,0.95)
                cr.rectangle(half*LOUPE_CELL+1.5,half*LOUPE_CELL+1.5,LOUPE_CELL-3,LOUPE_CELL-3);cr.stroke()
                cr.reset_clip()
                cr.set_line_width(2)
                cr.set_source_rgba(1,1,1,0.9)
                cr.arc(width/2,height/2,width/2-1,0,6.283185);cr.stroke()
            loupe.set_draw_func(draw_loupe)

            motion=Gtk.EventControllerMotion()
            def moved(_motion,x,y):
                pointer.update(x=x,y=y)
                size=LOUPE_PIXELS*LOUPE_CELL
                # Keep the loupe beside the pointer and inside the poster.
                left=x+18 if x+18+size<=poster.get_width() else x-18-size
                top=y+18 if y+18+size<=poster.get_height() else y-18-size
                loupe.set_margin_start(max(0,int(left)));loupe.set_margin_top(max(0,int(top)))
                loupe.set_visible(True);loupe.queue_draw()
                r,g,b=pixel_color(*source_pixel(x,y))
                preview_label.set_text(f'#{r:02x}{g:02x}{b:02x}'.upper()+' · click to use')
            motion.connect('motion',moved)
            motion.connect('leave',lambda *_:(loupe.set_visible(False),preview_label.set_text(pending['color'].upper())))
            poster.add_controller(motion)

            try:
                poster.set_cursor_from_name(
                    'crosshair'
                )
            except Exception:
                pass

            shell.append(
                frame
            )

            shell.append(
                preview_label
            )

            preview_provider=Gtk.CssProvider()

            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                preview_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+2,
            )

            def show_preview(color):
                pending[
                    'color'
                ]=color

                preview_label.set_text(
                    color.upper()
                )

                preview_provider.load_from_data(
                    (
                        '.accent-picker-art-frame { '
                        f'border-color: {color}; '
                        '}'
                    ).encode()
                )

            show_preview(
                initial_color
            )

            gesture=Gtk.GestureClick()

            def picked(
                _gesture,
                _press,
                x,
                y,
            ):
                width=max(
                    1,
                    poster.get_width(),
                )

                height=max(
                    1,
                    poster.get_height(),
                )

                r,g,b=pixel_color(*source_pixel(x,y))
                show_preview(
                    f'#{r:02x}{g:02x}{b:02x}'
                )

            gesture.connect(
                'released',
                picked,
            )

            poster.add_controller(
                gesture
            )

            # Suggestions from the artwork, most characteristic first.
            try:suggestions=ui_colors.accent_suggestions(artwork_pixels(source))
            except Exception:suggestions=[]
            if suggestions:
                shell.append(label('Suggestions','heading'))
                swatches=Gtk.Box(spacing=12,halign=Gtk.Align.CENTER)
                swatches.add_css_class('accent-suggestions')
                for name,color in suggestions:
                    choice=Gtk.Button(tooltip_text=name+' · '+color.upper())
                    choice.add_css_class('flat')
                    choice.update_property([Gtk.AccessibleProperty.LABEL],[name+' accent'])
                    stack=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4)
                    dot=Gtk.DrawingArea(width_request=28,height_request=28,halign=Gtk.Align.CENTER)
                    def draw_dot(_area,cr,width,height,color=color):
                        rgba=Gdk.RGBA();rgba.parse(color)
                        cr.set_source_rgba(rgba.red,rgba.green,rgba.blue,1)
                        cr.arc(width/2,height/2,min(width,height)/2-1,0,6.283185);cr.fill()
                    dot.set_draw_func(draw_dot)
                    stack.append(dot)
                    caption=label(name,'caption');caption.set_halign(Gtk.Align.CENTER)
                    stack.append(caption)
                    choice.set_child(stack)
                    choice.connect('clicked',lambda _b,color=color:show_preview(color))
                    swatches.append(choice)
                shell.append(swatches)

            cancel=Gtk.Button(label='Cancel')
            cancel.connect('clicked',lambda *_:picker.close())

            def commit_accent(*_):
                set_color(
                    pending['color']
                )
                picker.close()

            done=Gtk.Button(label='Done')
            done.add_css_class('suggested-action')
            done.connect('clicked',commit_accent)

            # GNOME dialog layout: Cancel at the start of the header bar,
            # the confirming action at the end.
            header.set_show_end_title_buttons(False)
            header.pack_start(cancel)
            header.pack_end(done)

            def picker_closed(*_):
                if (
                    getattr(
                        self,
                        'accent_picker_window',
                        None,
                    )
                    is picker
                ):
                    self.accent_picker_window=None

                try:
                    Gtk.StyleContext.remove_provider_for_display(
                        Gdk.Display.get_default(),
                        preview_provider,
                    )
                except Exception:
                    pass

                return False

            picker.connect(
                'close-request',
                picker_closed,
            )

            picker.present()

        pick_button=button(
            'Edit',
            pick_accent_from_poster,
        )
        pick_button.set_valign(
            Gtk.Align.CENTER
        )
        accent_row.add_suffix(pick_button)

        artwork_title=label(
            'Artwork Credits',
            'heading',
        )
        appearance.append(
            artwork_title
        )

        credits=Gtk.Box(
            spacing=16,
            homogeneous=True,
            hexpand=True,
        )
        credits.add_css_class(
            'art-credit-pods'
        )
        appearance.append(
            credits
        )

        credit_specs=(
            (
                'Poster',
                'art_credit',
                'art_link',
            ),
            (
                'Wide Capsule',
                'capsule_credit',
                None,
            ),
            (
                'Hero',
                'hero_credit',
                'hero_link',
            ),
        )

        for credit_title,credit_key,link_key in credit_specs:
            pod=Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=5,
                hexpand=True,
            )
            pod.add_css_class(
                'art-credit-pod'
            )

            pod.append(
                label(
                    credit_title,
                    'heading',
                )
            )

            credit_text=label(
                game.get(credit_key)
                or 'Source information unavailable',
                'dim-label',
            )
            credit_text.set_wrap(
                True
            )
            credit_text.set_lines(
                2
            )
            credit_text.set_ellipsize(
                Pango.EllipsizeMode.END
            )
            pod.append(
                credit_text
            )

            if (
                link_key
                and game.get(link_key)
            ):
                source_uri=game[link_key]

                source_button=button(
                    'View Source',
                    lambda *_,
                    uri=source_uri:
                        Gio.AppInfo.launch_default_for_uri(
                            uri,
                            None,
                        ),
                )
                source_button.set_halign(
                    Gtk.Align.START
                )

                pod.append(
                    source_button
                )

            credits.append(
                pod
            )
        open_folder=button(
            'Open Folder',
            lambda *_:Gio.AppInfo.launch_default_for_uri(
                Path(game['game']).as_uri(),
                None,
            ),
        )
        detail_action_rows['Overview'].append(
            open_folder
        )

        play=button('Play', lambda *_:self.play_game(game), 'suggested-action')
        play.set_sensitive(not self.options.demo)
        detail_action_rows['Overview'].prepend(play)

    def play_game(self,game):
        if self.options.demo:return
        self.start('Preparing game launch',
                   lambda:game_launch.prepare_launch(self.service.config,game),
                   lambda request:game_launch.dispatch_launch(self.service.config,request,lambda uri:Gio.AppInfo.launch_default_for_uri(uri,None)))

    def record_test(self,game,finish=False):
        def done(record):
            game['test_record']=record;self.details(game)
            if not finish and game.get('source')=='Steam' and str(game.get('appid','')).isdigit():
                Gio.AppInfo.launch_default_for_uri('steam://rungameid/'+str(game['appid']),None)
            self.toast('Logs captured. Record your result and save notes.' if finish else 'Test started. Launch your game normally, then return here to finish.')
        self.start('Collecting test logs' if finish else 'Starting test record',lambda:(game_notes.finish if finish else game_notes.start)(self.service.config,game),done)
    def show_reports(self,*_):
        d,b,f=self.open_panel('Library status & reports')
        totals=Counter(g.get('test_record',{}).get('status','Untested') for g in self.games)
        b.append(label(' · '.join(f'{totals[state]} {state.lower()}' for state in game_notes.STATES),'heading'))
        b.append(label('Diagnostics separate saved settings from captured runtime evidence. Nothing is uploaded.','dim-label'))
        for game in self.games:
            record=game.get('test_record',{});item=row(game['name'],record.get('status','Untested')+(' · test in progress' if record.get('active') else ''))
            item.add_suffix(button('Diagnose',lambda _,g=game:self.show_diagnostics(g)));b.append(item)
        logs=Gtk.CheckButton(label='Include redacted logs from the latest captured test',active=False)
        notes=Gtk.CheckButton(label='Include my notes',active=False)
        b.append(logs);b.append(notes)
        export=button('Preview Support Report',lambda *_:self.start('Preparing redacted preview',lambda:game_notes.preview(self.service.config,self.games,logs.get_active(),notes.get_active()),self.preview_report),'forge-primary')
        export.set_sensitive(not self.options.demo);f.append(export)

    def preview_report(self,files):
        """The exact redacted text, reviewed before it is saved locally."""
        flow=OperationFlow(self,'report',[])
        body=flow._body()
        body.append(label('Review the exact text below. Redaction is best effort. Export saves this preview locally; nothing is submitted.','dim-label'))
        listing=Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        listing.add_css_class('boxed-list');listing.add_css_class('review-list')
        for name,text in files.items():
            view=Gtk.TextView(editable=False,monospace=True,wrap_mode=Gtk.WrapMode.WORD_CHAR)
            view.get_buffer().set_text(text)
            scroller=Gtk.ScrolledWindow(min_content_height=240,vexpand=True,hscrollbar_policy=Gtk.PolicyType.NEVER)
            scroller.set_child(view);listing.append(self.review_entry(name,'Review the exact report contents',badge='Report',details=scroller))
        body.append(listing)
        issue=Gtk.Button(label='Open Issue Form',halign=Gtk.Align.START)
        issue.connect('clicked',lambda *_:Gio.AppInfo.launch_default_for_uri('https://github.com/lrnolivia/rtxForge/issues/new',None))
        body.append(issue)
        scroll=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,vexpand=True)
        scroll.set_child(body)
        def export(_review):
            flow.show_working('Exporting…')
            self.start('Exporting report',lambda:game_notes.export_preview(self.service.config,files),lambda path:self.finish_progress(True,'Saved '+str(path)))
        flow.review={'operation':'report','rows':[{'name':name} for name in files],'blocked':[]}
        flow.on_confirm=export
        flow._title(flow.review_title)
        flow.primary.set_label('Export')
        flow.primary.set_sensitive(not self.options.demo)
        flow._page('review',scroll,width=760)

    def new_operation_flow(self,operation,games,title=None):
        """The operation dialog for the visible interface: Game Mode draws its own."""
        if getattr(self,'input_stack',None) is not None and self.input_stack.get_visible_child_name()=='couch':
            from game_mode import GameModeFlow
            words=OPERATION_WORDS.get(operation,OPERATION_WORDS['reset'])
            return GameModeFlow(self.couch,self,operation,games,(title or words[0],words[1],words[2]))
        return OperationFlow(self,operation,games,title)

    def launch_action(self,operation,entire=False,targets=None,visual_settings=None,_presets_confirmed=False,_flow=None):
        if self.busy and self.task_kind!='art':return
        rows=(
            targets
            if targets is not None
            else (
                list(
                    self.games
                )
                if entire
                else [
                    game
                    for game in self.games
                    if game.get(
                        'game'
                    )
                    in self.selected_game_ids
                ]
            )
        )
        rows=[g for g in rows if not g.get('blocked')]
        if entire and operation in ('install','repair'):rows=[g for g in rows if g.get('test_record',{}).get('status')!='Bench']
        if operation=='reset':rows=[g for g in rows if g.get('installed')]
        if not rows:self.toast('No eligible games selected.');return
        # Windows installs only need their Proton setting here: no presets step.
        if operation=='install' and rows and all(self.needs_linux_setup(g) for g in rows):_presets_confirmed=True
        if operation=='install' and not _presets_confirmed:
            # Stage 1 (install only): presets, in the same dialog as the rest.
            flow=self.new_operation_flow(operation,rows)
            tuning,widgets=self.tuning_controls(visual_settings if visual_settings is not None else rows[0] if len(rows)==1 else self.tuning_values(self.tuning_widgets))
            flow.show_presets(tuning,lambda:self.launch_action(operation,entire,targets,self.tuning_values(widgets),True,_flow=flow))
            return
        applying_strength=operation=='reset' and entire and self.defaults_changed()
        title={'install':'Install Features','repair':'Repair Feature Files','uninstall':'Restore Original Files','reset':'Reset Presets'}[operation]
        if applying_strength:title='Apply Settings to Library'
        elif operation=='reset' and visual_settings is not None:title='Apply Presets'
        self.operation_previous=targets[0] if targets and len(targets)==1 else None

        self.operation_cancel=threading.Event();self.operation_executing=False
        self.operation_games=rows
        flow=_flow if _flow is not None and not _flow.closed else self.new_operation_flow(operation,rows)
        flow.games=rows
        flow.show_checking()

        if self.options.demo:
            preview={'kind':'batch','operation':operation,'title':title,'plans':[],'rows':[{'name':r['name'],'detail':'2 file changes'} for r in rows[:4]],'blocked':[{'name':'Example protected game','reason':'Another graphics tool is installed.'}]}
            if getattr(self,'flow_hold_checking',False):
                self.flow_release_checking=lambda:self.action_ready(preview)
                return
            self.action_ready(preview);return
        mode=self.mode;adopt=self.settings['recognize_previous'];values=self.tuning_values(self.tuning_widgets) if entire and operation=='reset' else visual_settings
        self.start('Preparing '+title.lower(),lambda:self.service.prepare(rows,mode,operation,adopt,visual_settings=values,save_defaults=entire and operation=='reset'),self.action_ready)
    def live_smoke_begin(self,footer):
        """Interactive, write-disabled preview of Progress -> Done."""
        self.live_smoke_footer=footer
        self.live_smoke_rows=list(
            getattr(self,'operation_games',[])
        )
        self.live_smoke_index=0

        if not self.live_smoke_rows:
            return

        targets=[]

        poster_target=(
            getattr(self,'job_poster_frame',None)
            or getattr(self,'job_poster',None)
        )

        if poster_target is not None:
            targets.append(poster_target)

        if getattr(self,'job_bar',None) is not None:
            targets.append(self.job_bar)

        for target in targets:
            target.set_tooltip_text(
                'Live Smoke · click to advance preview'
            )

            gesture=Gtk.GestureClick()

            gesture.connect(
                'released',
                lambda *_:self.live_smoke_next(),
            )

            target.add_controller(gesture)

        # Populate the first visual state immediately.
        self.live_smoke_next()

    def live_smoke_next(self):
        """Advance one fake operation step; final click shows Done."""
        rows=getattr(
            self,
            'live_smoke_rows',
            [],
        )

        if not rows:
            return

        index=getattr(
            self,
            'live_smoke_index',
            0,
        )

        # One click after the final game transitions to Done.
        if index>=len(rows):
            self.operation_cancel=None

            self.finish_progress(
                True,
                f"{len(rows)} game"
                f"{'s' if len(rows)!=1 else ''} updated.",
                self.live_smoke_footer,
            )

            return

        game=rows[index]

        self.update_progress_art(
            game['name']
        )

        if getattr(self,'job_counter',None):
            self.job_counter.set_text(
                f"{index+1} / {len(rows)}"
            )

        if getattr(self,'job_caption',None):
            self.job_caption.set_text(
                'Applying preview changes…'
            )

        if getattr(self,'job_bar',None):
            self.job_bar.set_fraction(
                (index+1)/(len(rows)+1)
            )

        self.live_smoke_index=index+1

    def progress_view(self,body,message):
        clear(body)

        body.remove_css_class('panel-body')
        body.add_css_class('progress-content')

        body.set_vexpand(True)
        body.set_valign(Gtk.Align.FILL)

        body.set_margin_top(0)
        body.set_margin_bottom(0)
        body.set_margin_start(0)
        body.set_margin_end(0)

        # Compact operation poster.
        # Compact 140x210 operation poster.
        POSTER_WIDTH=140
        POSTER_HEIGHT=210

        # Allowance for the poster frame/padding.
        POSTER_FRAME_WIDTH=146
        POSTER_FRAME_HEIGHT=216

        # The active-operation modal follows the poster's height instead
        # of using an unrelated fixed height.
        #
        # progress-content currently contributes:
        #   30px top padding
        #   26px bottom padding
        PANEL_VERTICAL_PADDING=48

        self.dialog.set_content_width(640)
        self.dialog.set_content_height(
            POSTER_FRAME_HEIGHT + PANEL_VERTICAL_PADDING
        )

        if getattr(self,'progress_dialog',None)!=self.dialog:
            box=self.dialog.get_child()

            # open_panel() gives every ordinary dialog a HeaderBar and
            # Gtk.ScrolledWindow. Progress / Done replaces that generic
            # composition completely, so do not leave either widget
            # lurking underneath the cinematic presentation.
            #
            # In particular, merely hiding the scrollbar is not enough:
            # GTK overlay scrollbars can reveal themselves again on
            # pointer hover. Remove the ScrolledWindow itself.
            header=box.get_first_child()
            scroll=(
                header.get_next_sibling()
                if header is not None
                else None
            )

            if isinstance(
                scroll,
                Gtk.ScrolledWindow,
            ):
                scroll.set_child(
                    None
                )
                box.remove(
                    scroll
                )

            if header is not None:
                box.remove(
                    header
                )

            if body.get_parent() is None:
                box.prepend(
                    body
                )

            self.dialog.set_child(None)

            self.progress_shell=Gtk.Overlay()
            self.progress_shell.set_overflow(Gtk.Overflow.HIDDEN)
            self.dialog.set_child(self.progress_shell)

            self.dialog.add_css_class('art-progress')

            # ACTIVE operation only: current game's hero backdrop.
            self.job_art=Gtk.Stack(
                transition_type=Gtk.StackTransitionType.CROSSFADE,
                transition_duration=500,
            )

            self.job_pictures=[
                SoftBackdropPicture(
                    content_fit=Gtk.ContentFit.COVER,
                    can_shrink=True,
                )
                for _ in range(2)
            ]

            for i,picture in enumerate(self.job_pictures):
                self.job_art.add_named(picture,str(i))

            self.job_art.set_visible(False)
            self.progress_shell.set_child(self.job_art)

            self.progress_shade=Gtk.Box()
            self.progress_shade.add_css_class('progress-shade')
            self.progress_shell.add_overlay(self.progress_shade)

            box.add_css_class('progress-panel')
            box.set_overflow(Gtk.Overflow.HIDDEN)

            self.progress_shell.add_overlay(box)
            self.progress_shell.set_measure_overlay(box,True)

            self.progress_dialog=self.dialog
            self.progress_panel=box

            self.job_picture_index=0
            self.job_current_game=None
            self.job_accent=None

        center=Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            valign=Gtk.Align.FILL,
            vexpand=True,
        )

        body.append(center)

        line=Gtk.Box(
            spacing=22,
            halign=Gtk.Align.FILL,
            valign=Gtk.Align.CENTER,
            vexpand=True,
        )

        center.append(line)

        # ----------------------------------------------------
        # POSTER
        # ----------------------------------------------------

        self.job_poster=Gtk.Stack(
            transition_type=Gtk.StackTransitionType.CROSSFADE,
            transition_duration=400,
            width_request=POSTER_WIDTH,
            height_request=POSTER_HEIGHT,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
        )

        self.job_poster.add_css_class('progress-poster')

        # THIS is the clipping surface for the image.
        self.job_poster.set_overflow(Gtk.Overflow.HIDDEN)

        self.poster_images=[
            CoverPicture(
                content_fit=Gtk.ContentFit.COVER,
                can_shrink=True,
            )
            for _ in range(2)
        ]

        for picture in self.poster_images:
            picture.cover_width=POSTER_WIDTH
            picture.cover_ratio=2/3

        for i,picture in enumerate(self.poster_images):
            self.job_poster.add_named(picture,str(i))

        self.job_poster_frame=Gtk.Frame(
            width_request=POSTER_FRAME_WIDTH,
            height_request=POSTER_FRAME_HEIGHT,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
        )

        self.job_poster_frame.add_css_class(
            'progress-poster-frame'
        )

        # Important: do NOT clip the outer accent frame.
        self.job_poster_frame.set_overflow(
            Gtk.Overflow.VISIBLE
        )

        self.job_poster_frame.set_child(
            self.job_poster
        )

        line.append(self.job_poster_frame)

        # ----------------------------------------------------
        # RIGHT COLUMN
        #
        # Exactly the same height as the poster frame.
        # Center content stays centered; Cancel occupies the end slot.
        # ----------------------------------------------------

        # The entire right-side coordinate space is exactly as tall
        # as the poster frame. Nothing here centers against the modal.
        right=Gtk.Overlay(
            hexpand=True,
            height_request=POSTER_FRAME_HEIGHT,
            valign=Gtk.Align.CENTER,
        )

        right.set_size_request(
            -1,
            POSTER_FRAME_HEIGHT,
        )

        right.set_vexpand(False)

        line.append(right)

        # Full-poster-height slot. The actual information cluster is
        # centered inside THIS, not inside the dialog.
        # Dedicated poster-height centering plane.
        #
        # This is intentionally independent of the modal's own height.
        # The visible status/progress cluster is geometrically centered
        # against the poster frame itself.
        center_slot=Gtk.CenterBox(
            orientation=Gtk.Orientation.VERTICAL,
            hexpand=True,
            height_request=POSTER_FRAME_HEIGHT,
            valign=Gtk.Align.CENTER,
        )

        center_slot.set_vexpand(False)

        right.set_child(center_slot)

        inner=Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=5,
            halign=Gtk.Align.FILL,
            valign=Gtk.Align.CENTER,
            hexpand=True,
        )

        center_slot.set_center_widget(
            inner
        )

        self.job_counter=label(
            'Preparing…',
            'dim-label',
        )
        inner.append(self.job_counter)

        self.job_label=label(
            '',
            'job-title',
        )
        self.job_label.set_max_width_chars(28)
        inner.append(self.job_label)

        self.job_caption=label(message)
        self.job_caption.set_max_width_chars(38)
        inner.append(self.job_caption)

        self.job_bar=Gtk.ProgressBar()
        self.job_bar.set_hexpand(True)
        inner.append(self.job_bar)

        # Cancel now lives INSIDE the same vertical envelope as the poster.
        # Its bottom edge therefore aligns with the poster frame.
        self.progress_cancel_box=Gtk.Box(
            halign=Gtk.Align.END,
            valign=Gtk.Align.END,
        )

        # Cancel occupies the same poster-height space, but because it is
        # an overlay it NEVER participates in the centered content's
        # measurement or positioning.
        right.add_overlay(
            self.progress_cancel_box
        )

        right.set_measure_overlay(
            self.progress_cancel_box,
            False,
        )

        # The old footer is not part of the active-operation composition.
        footer=self.progress_panel.get_last_child()
        clear(footer)
        footer.set_visible(False)

        self.progress_body=body
        self.progress_footer=footer

        self.job_current_game=None

        # Recreate Cancel in its new inline location.
        self.add_cancel(footer)

        self.update_progress_art('')

    def update_progress_art(self,name):
        if not getattr(self,'job_label',None) or not hasattr(self,'job_art'):
            return

        games=getattr(self,'operation_games',[])

        game=next(
            (g for g in games if g['name']==name),
            games[0] if games else None,
        )

        if not game or game['game']==getattr(
            self,
            'job_current_game',
            None,
        ):
            return

        self.job_current_game=game['game']
        self.job_picture_index=1-self.job_picture_index

        # Progress keeps a solid neutral surface; only the compact poster changes.
        self.job_art.set_visible(False)

        if poster_art_path(game):
            try:
                self.poster_images[
                    self.job_picture_index
                ].set_paintable(
                    Gdk.Texture.new_from_filename(
                        poster_art_path(game)
                    )
                )

                self.job_poster.set_visible_child_name(
                    str(self.job_picture_index)
                )
            except Exception:
                pass

        else:
            self.poster_images[self.job_picture_index].set_paintable(None)
            self.job_poster.set_visible_child_name(str(self.job_picture_index))

        # Accent still drives title/progress treatment.
        # It no longer touches either border.
        if self.job_accent:
            self.dialog.remove_css_class(self.job_accent)

        self.job_accent=game.get('accent_class')

        if self.job_accent:
            self.dialog.add_css_class(self.job_accent)

        self.job_label.set_text(game['name'])

    def animate_dialog_width(self,target,duration=280):
        """Smoothly resize the active Adw.Dialog horizontally."""

        dialog=self.dialog

        if dialog is None:
            return

        try:
            start=int(dialog.get_content_width())
        except Exception:
            start=640

        target=int(target)

        if start==target or not Gtk.Settings.get_default().get_property('gtk-enable-animations'):
            dialog.set_content_width(target)
            return

        started=time.monotonic()

        def tick():
            if self.dialog is not dialog:
                return False

            if not Gtk.Settings.get_default().get_property('gtk-enable-animations'):
                dialog.set_content_width(target)
                return False
            elapsed=(time.monotonic()-started)*1000.0
            t=min(1.0,elapsed/max(1,duration))

            # Cubic ease-out: quick initial motion with a soft landing.
            eased=1.0-(1.0-t)**3

            width=round(
                start+(target-start)*eased
            )

            dialog.set_content_width(width)

            return t<1.0

        self.add_tick_callback(lambda _widget,_clock:tick())

    def animate_dialog_height(self,dialog,target,duration=240):
        if dialog is None or self.dialog is not dialog:return
        source=getattr(self,'detail_resize_source',0)
        if source:
            try:self.remove_tick_callback(source)
            except Exception:pass
            self.detail_resize_source=0
        try:start=int(dialog.get_content_height())
        except Exception:start=int(target)
        target=max(1,int(target))
        if start==target or not Gtk.Settings.get_default().get_property('gtk-enable-animations'):
            dialog.set_content_height(target);return
        started=time.monotonic()
        def tick():
            if self.dialog is not dialog:
                self.detail_resize_source=0
                return False
            if not Gtk.Settings.get_default().get_property('gtk-enable-animations'):
                dialog.set_content_height(target)
                self.detail_resize_source=0
                return False
            t=min(1.0,(time.monotonic()-started)*1000.0/max(1,duration))
            eased=1.0-(1.0-t)**3
            dialog.set_content_height(round(start+(target-start)*eased))
            if t>=1.0:self.detail_resize_source=0
            return t<1.0
        self.detail_resize_source=self.add_tick_callback(lambda _widget,_clock:tick())


    def finish_progress(self,success,message,footer=None,title=None):
        """Stage 5: Done, Could not finish or Cancelled."""
        flow=getattr(self,'operation_flow',None)
        if flow is None or flow.closed:
            flow=self.new_operation_flow(getattr(self,'review',None) and self.review.get('operation') or 'install',getattr(self,'operation_games',[]))
        friendly=message if success else user_messages.friendly_error(message)
        flow.show_done(success,friendly,title,technical=None if success or title else message)
        self.job_label=None

    def add_cancel(self,footer):
        target=getattr(
            self,
            'progress_cancel_box',
            None,
        )

        if target is None:
            footer.set_visible(True)
            footer.add_css_class('progress-footer')
            footer.set_spacing(6)

            footer.set_margin_top(2)
            footer.set_margin_bottom(20)
            footer.set_margin_start(28)
            footer.set_margin_end(28)

            target=footer

        # progress_view() and execute() can both request Cancel.
        # Never create two buttons in the same target.
        if target.get_first_child() is not None:
            return

        def cancel(w):
            self.operation_cancel.set()

            w.set_sensitive(False)
            w.set_label('Undoing…')

            if self.job_label:
                self.job_caption.set_text(
                    'Finishing safely, then undoing changes…'
                )

            if not self.busy:
                self.dialog.force_close()
                self.dialog=None

                if self.operation_previous:
                    self.details(
                        self.operation_previous
                    )

        cancel_button=button(
            'Cancel',
            cancel,
        )

        if target is not footer:
            cancel_button.add_css_class(
                'progress-inline-cancel'
            )

        target.append(
            cancel_button
        )

    def review_write(self,operation,review=None,run=None,prepare=None,details=None,trust=None,note=None,done=None,extra=None):
        """Checking → Review → Working → Done for every other reviewed write.

        prepare() builds the review off the main thread (Checking); run(review)
        performs exactly what was shown and returns the Done message.
        """
        if self.busy and self.task_kind!='art':return None
        flow=self.new_operation_flow(operation,[])
        def show(result):
            if flow.closed:return
            flow.show_review(result,confirm,details,enabled=not self.options.demo,trust=trust,note=note,extra=extra)
        def confirm(result):
            if self.options.demo:return
            flow.show_working(flow.progress_verb+'…')
            def finished(value):
                message=done(value) if done else value
                if not flow.closed:self.finish_progress(True,str(message))
            self.start(flow.progress_verb,lambda:run(result),finished)
        if prepare is not None:
            flow.show_working('Checking…',cancellable=True)
            self.start('Checking',prepare,show)
        else:
            show(review)
        return flow

    def review_details(self,review):
        """The "Install · DLSS-Unlocked · MFG 4×" line under the review summary."""
        operation=review.get('operation','install')
        details=[OPERATION_WORDS.get(operation,OPERATION_WORDS['reset'])[1]]
        if operation in ('install','repair','reset'):
            provider=self.settings.get('runtime_provider','dlss-unlocked')
            details.append({'dlss-unlocked':'DLSS-Unlocked','y4my':'y4my','custom':'Custom package'}.get(provider,provider))
            mfg=review.get('mfg_multiplier')
            if mfg is not None:details.append('MFG '+('In game' if mfg=='auto' else 'Off' if mfg==0 else str(mfg)+'×'))
        return details

    def action_ready(self,review,*_legacy):
        """Stage 3: the review, in the operation's dialog."""
        self.review=review
        operation=review.get('operation') or {'rollback':'recovery','restore-cleanup':'recovery','operation':'recovery','cleanup':'cleanup'}.get(review.get('kind'),'install')
        review.setdefault('operation',operation)
        flow=getattr(self,'operation_flow',None)
        if flow is None or flow.closed or flow.operation!=operation:
            flow=self.new_operation_flow(operation,getattr(self,'operation_games',[]) or self.games)
        flow.show_review(review,self.execute,self.review_details(review),enabled=not self.options.demo)

    def execute(self,review,*_legacy):
        """Stage 4: progress, then Done or Could not finish."""
        if self.options.demo:return
        flow=self.operation_flow
        if review.get('kind') in ('rollback','restore-cleanup','operation','cleanup'):flow.show_working(flow.progress_verb+'…')
        else:flow.show_progress(len(review.get('rows',[])) or len(self.operation_games))
        flow.rescan=True
        if review.get('kind')=='engine':
            self.operation_executing=True;review['cancel_event']=self.operation_cancel
            # Close the cancellation window on the GTK thread before the engine's
            # final cancellation check. A late click must never promise an undo
            # after the feature transaction has already committed.
            def finalizing():
                ready=threading.Event()
                def finish_ui():
                    try:flow.finalizing()
                    finally:ready.set()
                    return False
                GLib.idle_add(finish_ui)
                ready.wait()
            review['on_finalizing']=finalizing
        def apply_with_files():
            path=self.service.execute(review)
            if review.get('operation')=='install' and self.settings.get('manage_dlss_files',True) and not self.operation_cancel.is_set():
                try:
                    import runtime_updates
                    successful={str(plan['game'].root) for plan in review.get('plans',[]) if hasattr(plan.get('game'),'root')}
                    games=[game for game in self.operation_games if game['game'] in successful]
                    result=runtime_updates.manage(self.service.config,games) if games else {'updated_games':0,'skipped':[]}
                    ui.line('DLSS Files',f"{result['updated_games']} games updated")
                    for reason in result['skipped']:ui.line('DLSS skipped',reason)
                except Exception as exc:
                    # Feature installation succeeded; a failed optional network/file
                    # update must not masquerade as a failed feature installation.
                    ui.line('DLSS Files',f'No further file updates: {exc}')
            return path
        self.start('Applying changes',apply_with_files,self.completed)

    def completed(self,path,*_legacy):
        self.operation_cancel=None
        if self.review and self.review.get('save_defaults'):self.defaults_applied(self.review['save_defaults'])
        count=len(self.review.get('rows',[])) if self.review else 0
        self.log.append('Saved report: '+str(path))
        self.finish_progress(True,f'{count} game'+('s' if count!=1 else '')+' updated.')

    def show_activity(self,*_):
        d,b,f=self.open_panel('Activity');text=Gtk.TextView(editable=False,monospace=True,wrap_mode=Gtk.WrapMode.WORD_CHAR);text.get_buffer().set_text('\n'.join(self.log) or 'No activity yet.');b.append(text);f.append(button('Close',lambda *_:d.close()))
    def show_settings(self,*_):
        d,b,f=self.open_panel(
            'Settings',
            width=940,
            height=660,
            resizable=True,
        )
        graphics=Adw.PreferencesGroup(title='Graphics Provider',description='Restore original files before switching providers.')
        provider_keys=['y4my','dlss-unlocked','custom'];provider=safe_combo_row(title='Provider',model=Gtk.StringList.new(['y4my Multipass','DLSS-Unlocked','Custom package']),selected=provider_keys.index(self.settings.get('runtime_provider','y4my')));graphics.add(provider)
        nr_path=Adw.EntryRow(title='Local NR DLL for y4my');nr_path.set_text(self.settings.get('nr_runtime',''));graphics.add(nr_path)
        # Adopting only: the Windows install's own files load through a Proton DLL override. Not yet runtime-verified.
        skynizz_proton=Adw.SwitchRow(title='Skynizz on Proton (experimental)',subtitle='Set up Skynizz + Universal MFG installs made on Windows to run here. Unverified under Proton.',active=self.settings.get('skynizz_proton',False) is True)
        graphics.add(skynizz_proton)
        defaults=Adw.PreferencesGroup(title='Installation')
        manage_files=Adw.SwitchRow(title='DLSS Files',subtitle='Update older DLSS files when installing features. Backups are kept for restoration.',active=self.settings.get('manage_dlss_files',True))
        defaults.add(manage_files)
        modes=['nr-only','mfg-only','nr-mfg'];profile=safe_combo_row(title='Default Mode',model=Gtk.StringList.new(['NR Only','MFG Only','NR + MFG']),selected=modes.index(self.settings.get('default_profile','mfg-only')));defaults.add(profile)
        adopt=Adw.SwitchRow(title='Recognize Existing Features',subtitle='Allow updates to compatible installations from other tools.',active=self.settings['recognize_previous']);defaults.add(adopt)
        appearance=Adw.PreferencesGroup(title='Theme',description='Choose the look of rtxForge.')
        window_style=Adw.PreferencesGroup(title='Window',description='Shape and spacing for the desktop interface.')
        library_layout=Adw.PreferencesGroup(title='Library Layout',description='Choose how your desktop game collection is displayed.')
        compact=Adw.SwitchRow(title='Compact Header',subtitle='Keep more room for your games.',active=self.settings.get('compact_header',True))
        compact.connect('notify::active',lambda widget,*_: self.toggle_compact_header() if widget.get_active()!=self.settings.get('compact_header',True) else None)
        views=[
            'posters',
            'capsules',
            'list',
        ]

        original_library_view=self.settings.get(
            'library_view',
            'posters',
        )

        pending_library_view={
            'value':original_library_view,
        }

        layout_row=row(
            'Layout',
            'Preview updates live',
        )

        layout_selector=Adw.ToggleGroup(
            homogeneous=True,
            valign=Gtk.Align.CENTER,
        )
        layout_selector.add_css_class(
            'mode-selector'
        )

        for key,caption in (
            ('posters','Poster'),
            ('capsules','Wide Capsule'),
            ('list','List'),
        ):
            layout_selector.add(
                Adw.Toggle(
                    name=key,
                    label=caption,
                )
            )

        layout_selector.set_active_name(
            original_library_view
        )

        def preview_library_view(
            group,
            *_,
        ):
            key=group.get_active_name()

            if not key:
                return

            if pending_library_view['value']==key:
                return

            pending_library_view['value']=key
            control=self.view_buttons[key]
            control.set_active(True)
            self.view_changed(control,key)

            self.show_games(
                self.games,
                False,
            )

            if key!='list':
                self.resize_library_art(
                    self.settings.get(
                        'art_scale',
                        100,
                    )
                )

        layout_selector.connect(
            'notify::active-name',
            preview_library_view,
        )

        layout_row.add_suffix(
            layout_selector
        )

        library_layout.add(
            layout_row
        )

        steam_launcher=Adw.PreferencesGroup(title='Steam Library')
        added=self.steam_shortcut_added()
        steam_shortcut=row('rtxForge is in Steam' if added else 'Add rtxForge to Steam','Manage this app’s shortcut in your selected Steam profile.')
        steam_action=button('Remove from Steam' if added else 'Add to Steam',self.toggle_rtxforge_in_steam)
        steam_action.set_sensitive(not self.options.demo);steam_action.set_valign(Gtk.Align.CENTER)
        steam_shortcut.add_suffix(steam_action);steam_launcher.add(steam_shortcut)
        self.steam_shortcut_row=steam_shortcut;self.steam_shortcut_button=steam_action
        controls=Adw.PreferencesGroup(title='Interface',description='Choose the experience for Gaming Mode.')
        controller_options=Adw.PreferencesGroup(title='Controller',description='Button labels and navigation prompts.')
        big_picture=safe_combo_row(title='Interface',subtitle='Choose Desktop or Big Picture UI. Keyboard, mouse and controller input keep your choice.',model=Gtk.StringList.new(['Desktop','Big Picture UI']),selected=1 if self.input_stack.get_visible_child_name()=='couch' else 0)
        big_picture.connect('notify::selected',lambda widget,*_:self.set_big_picture_ui(widget.get_selected()==1))
        controls.add(big_picture)
        for key,title,keys,captions in [
            ('controller_glyphs','Controller Labels',['auto','xbox','playstation','nintendo','generic'],['Automatic','Xbox','PlayStation','Nintendo','Generic'])]:
            choice=safe_combo_row(title=title,model=Gtk.StringList.new(captions),selected=keys.index(self.settings.get(key,'auto')))
            def change_input(widget,*_,key=key,keys=keys):
                global COUCH_MODE
                self.settings[key]=keys[widget.get_selected()]
                COUCH_MODE=self.settings.get('input_mode','auto') if self.settings.get('big_picture_ui',True) else 'desktop'
                if not self.options.demo:library_media.save_settings(self.service.config,self.settings)
                if key=='input_mode':self.toast('Input mode saved. Restart to rebuild all menu controls.')
            choice.connect('notify::selected',change_input);(controller_options if key=='controller_glyphs' else controls).add(choice)
        for key,title,keys,captions in [
            ('ui_scale','UI Scale',list(SCALES),['Automatic (150% at 4K)','100%','125%','150%','175%','200%']),
            ('navigation_position','Navigation Position',['top','bottom'],['Top','Bottom']),
            ('controller_hints','Controller Hints',['always','auto'],['Always visible','Hide when idle'])]:
            choice=safe_combo_row(title=title,model=Gtk.StringList.new(captions),selected=keys.index(self.settings.get(key,library_media.DEFAULTS[key])))
            choice.connect('notify::selected',lambda widget,*_,key=key,keys=keys:self.set_display_preference(key,keys[widget.get_selected()]))
            target=controller_options if key=='controller_hints' else controls
            target.add(choice)
        controller_options.add(row('Controller Navigation','D-pad / stick: focus · South: activate · East: back · North: library · Start: menu · View/Select: settings · Bumpers: tab'))
        settings_saved={'value':False}

        def restore_library_preview(*_):
            if settings_saved['value']:
                return

            current_view=self.settings.get(
                'library_view',
                'posters',
            )

            if current_view!=original_library_view:
                control=self.view_buttons[original_library_view]
                control.set_active(True)
                self.view_changed(control,original_library_view)

                self.show_games(
                    self.games,
                    False,
                )

        d.connect(
            'close-request' if isinstance(d,ResizablePanelWindow) else 'closed',
            lambda *_:(
                restore_library_preview(),
                False,
            )[1],
        )

        corner_keys=['system','rounded','square']
        corners=Adw.ComboRow(title='Corners',subtitle='System uses native window decoration. Square also flattens custom cards and controls.',model=Gtk.StringList.new(['System','Rounded','Square']),selected=corner_keys.index(self.settings.get('corner_style','system')))
        def change_corners(widget,*_):
            value=corner_keys[widget.get_selected()]
            self.settings['corner_style']=value
            apply_corner_style(value)
            self.queue_draw()
            if not self.options.demo:library_media.save_settings(self.service.config,self.settings)
        corners.connect('notify::selected',change_corners);window_style.add(corners);window_style.add(compact)

        theme_row=row('App Theme','Changes only rtxForge. Saved immediately.')
        theme_selector=Adw.ToggleGroup(valign=Gtk.Align.CENTER)
        for key,caption in [('light','Light'),('dark','Dark'),('night','Night')]:
            theme_selector.add(Adw.Toggle(name=key,label=caption))
        theme_selector.set_active_name((self.settings.get('theme') or ('dark' if self.settings['dark'] else 'light')))
        def change_theme(group,*_):
            global THEME_MODE
            THEME_MODE=group.get_active_name()
            self.settings['theme']=THEME_MODE
            dark=THEME_MODE!='light'
            self.settings['dark']=dark
            Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK if dark else Adw.ColorScheme.FORCE_LIGHT)
            apply_neutral_palette()
            if not self.options.demo:
                saved=library_media.load_settings(self.service.config)
                saved['dark']=dark
                saved['theme']=THEME_MODE
                library_media.save_settings(self.service.config,saved)
        theme_selector.connect('notify::active-name',change_theme)
        theme_row.add_suffix(theme_selector)
        appearance.add(theme_row)
        glyphs=Adw.SwitchRow(title='Button Icons',subtitle='Show action icons beside button labels.',active=self.settings.get('button_glyphs',True))
        def change_glyphs(widget,*_):
            value=widget.get_active();self.settings['button_glyphs']=value;set_button_glyphs(value)
            if not self.options.demo:
                saved=library_media.load_settings(self.service.config);saved['button_glyphs']=value
                library_media.save_settings(self.service.config,saved)
            if hasattr(self,'couch'):self.couch.apply_navigation_preferences()
        glyphs.connect('notify::active',change_glyphs);appearance.add(glyphs)
        artwork=Adw.PreferencesGroup(title='Artwork',description='Your Steam poster, capsule, and hero images take priority.')
        art=Adw.SwitchRow(title='Download Missing Artwork',subtitle='Use SteamGridDB and Steam when local images are unavailable.',active=self.settings['online_art']);artwork.add(art)
        metadata=Adw.SwitchRow(title='Download Game Information',subtitle='Descriptions, developers, and release dates from Steam.',active=self.settings['steam_metadata']);artwork.add(metadata)
        refresh=row('Refresh Artwork','Cached images remain available offline.');refresh_button=button('Refresh',lambda *_:self.fetch_media(True));refresh_button.set_valign(Gtk.Align.CENTER);refresh.add_suffix(refresh_button);artwork.add(refresh)
        timeout=Gtk.SpinButton.new_with_range(5,30,1);timeout.set_value(self.settings.get('network_timeout',10));timeout.set_valign(Gtk.Align.CENTER);item=row('Download Timeout','Seconds per request');item.add_suffix(timeout);artwork.add(item)
        steam_artwork=Adw.PreferencesGroup(title='Steam Artwork',description='Choose the Steam account and manage artwork for your game library.')
        for title,subtitle,caption,fn in [
            ('Steam Artwork Profile','Choose which local Steam account receives artwork.','Choose',self.choose_steam_artwork_profile),
            ('Sync Artwork to Steam','Review and sync artwork for your library.','Sync',self.sync_steam_artwork),
            ('SteamGridDB','Connect your account to browse custom artwork.','Connect',self.show_steamgrid_connection)]:
            item=row(title,subtitle);action=button(caption,fn);action.set_valign(Gtk.Align.CENTER);item.add_suffix(action);steam_artwork.add(item)
        system=Adw.PreferencesGroup(title='System');host=self.hardware_info or {}
        for title,key in [('Graphics Card','gpu'),('Driver','driver'),('Video Memory','vram'),('Processor','cpu'),('Architecture','architecture')]:
            if host.get(key):system.add(row(title,host[key]))
        system.add(row('Compatibility',host.get('reason','Not checked')))
        app=Adw.PreferencesGroup(title='Application');app.add(row('rtxForge',f'Version {APP_VERSION}'))

        if os.environ.get('APPIMAGE'):
            item=row(
                'Application Update',
                'Download, verify, and install the newest rtxForge build.'
            )
            action=button(
                'Check for Updates',
                self.check_app_update
            )
            action.set_valign(Gtk.Align.CENTER)
            item.add_suffix(action)
            app.add(item)

            item=row(
                'Desktop Installation',
                'Re-register this AppImage in the application menu.'
            )
            action=button(
                'Reinstall App Menu',
                self.install_desktop
            )
            action.set_valign(Gtk.Align.CENTER)
            item.add_suffix(action)
            app.add(item)
        recovery=Adw.PreferencesGroup(title='Recovery')
        for title,subtitle,caption,fn in [('Previous Changes','Browse available recovery records.','Browse',lambda *_:self.show_undo()),('Old NR Files','Review legacy files before removal.','Review',lambda *_:self.show_cleanup()),('Library Reports','View test notes and export a support report.','Open',self.show_reports)]:
            item=row(title,subtitle);action=button(caption,fn);action.set_valign(Gtk.Align.CENTER);item.add_suffix(action);recovery.add(item)
        self.organize_pages(b,[('Graphics',[graphics,defaults]),('Appearance',[appearance,window_style,library_layout]),('Library',[artwork,steam_artwork]),('Gaming Mode',[steam_launcher,controls,controller_options]),('System',[system,app]),('Recovery',[recovery])])
        def save(*_):
            selected_provider=provider_keys[provider.get_selected()];selected_mode=modes[profile.get_selected()]
            if selected_provider=='y4my' and selected_mode=='nr-only':self.toast('NR Only requires DLSS-Unlocked.');return
            settings_saved['value']=True
            self.settings.update(manage_dlss_files=manage_files.get_active(),runtime_provider=selected_provider,nr_runtime=nr_path.get_text().strip(),default_profile=selected_mode,library_view=pending_library_view['value'],dark=theme_selector.get_active_name()!='light',online_art=art.get_active(),steam_metadata=metadata.get_active(),network_timeout=timeout.get_value_as_int(),recognize_previous=adopt.get_active(),skynizz_proton=skynizz_proton.get_active())
            self.nr_only.set_enabled(selected_provider in ('dlss-unlocked','custom'))
            self.profile_group.set_active_name(selected_mode)
            Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK if self.settings['dark'] else Adw.ColorScheme.FORCE_LIGHT)
            apply_neutral_palette()
            self.view_buttons[self.settings['library_view']].set_active(True)
            if self.options.demo:d.close();self.show_games(self.games,False);return
            self.start('Saving settings',lambda:library_media.save_settings(self.service.config,self.settings),lambda _:(d.close(),self.show_games(self.games,False),self.fetch_media()))
        save_button=button(
            'Save Settings',
            save,
            'suggested-action',
        )

        # Settings now has a true full-height sidebar, so the footer
        # belongs entirely to the right content pane.
        f.set_halign(Gtk.Align.FILL)
        f.set_spacing(10)

        f.set_margin_top(0)
        f.set_margin_bottom(0)
        f.set_margin_start(0)
        f.set_margin_end(0)

        footer_spacer=Gtk.Box(
            hexpand=True,
        )
        f.append(
            footer_spacer
        )
        f.append(
            save_button
        )
    def check_app_update(self,*_):
        import app_update
        self.start(
            'Checking for application updates',
            app_update.check,
            self.update_checked,
        )

    def update_checked(self,info):
        if not info['available']:
            self.toast(
                f"rtxForge {APP_VERSION} is up to date."
            )
            return

        d,b,f=self.open_panel(
            'rtxForge Update',
            width=620,
            height=390,
        )

        group=Adw.PreferencesGroup(
            title=f"rtxForge {info['version']}",
            description='A newer application build is ready.'
        )
        b.append(group)

        group.add(
            row(
                'Installed',
                f"{info['current_version']} · "
                f"{info['current_commit'][:8]}"
            )
        )
        group.add(
            row(
                'Available',
                f"{info['version']} · "
                f"{info['commit'][:8]}"
            )
        )

        size=float(info['size'])
        units=['B','KB','MB','GB']
        index=0
        while size>=1024 and index<len(units)-1:
            size/=1024
            index+=1

        group.add(
            row(
                'Download',
                f"{size:.1f} {units[index]} · SHA256 verified"
            )
        )

        f.append(
            button(
                'Later',
                lambda *_:d.close()
            )
        )
        f.append(
            button(
                'Install Update',
                lambda *_:self.install_app_update(
                    info,d,b,f
                ),
                'suggested-action',
            )
        )

    def install_app_update(self,info,d,b,f):
        import app_update

        clear(b)
        clear(f)

        d.set_can_close(False)

        content=Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=14,
            valign=Gtk.Align.CENTER,
            vexpand=True,
        )
        content.add_css_class('panel-body')
        b.append(content)

        content.append(
            label(
                f"Updating to rtxForge {info['version']}",
                'title-2',
            )
        )

        caption=label(
            'Downloading application…',
            'dim-label',
        )
        content.append(caption)

        bar=Gtk.ProgressBar(
            width_request=360,
        )
        content.append(bar)

        def progress(fraction,received,total):
            GLib.idle_add(
                bar.set_fraction,
                fraction,
            )

            mb_received=received/(1024*1024)
            mb_total=total/(1024*1024)

            GLib.idle_add(
                caption.set_text,
                f"Downloading · "
                f"{mb_received:.1f} / {mb_total:.1f} MB",
            )

        self.start(
            'Downloading and verifying application update',
            lambda:app_update.install(
                info,
                progress=progress,
            ),
            lambda target:self.app_update_installed(
                info,target,d,b,f
            ),
        )

    def app_update_installed(self,info,target,d,b,f):
        import app_update

        d.set_can_close(True)
        clear(b)
        clear(f)

        box=Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=14,
            valign=Gtk.Align.CENTER,
            vexpand=True,
        )
        box.add_css_class('panel-body')
        b.append(box)

        icon=Gtk.Image.new_from_icon_name(
            'object-select-symbolic'
        )
        icon.set_pixel_size(40)
        icon.add_css_class('result-success')
        box.append(icon)

        box.append(
            label(
                f"rtxForge {info['version']} installed",
                'title-2',
            )
        )

        box.append(
            label(
                'The verified AppImage replaced the installed '
                'copy. Your previous build was preserved.',
                'dim-label',
            )
        )

        f.append(
            button(
                'Later',
                lambda *_:d.close()
            )
        )

        def restart(*_):
            app_update.restart()
            self.get_application().quit()

        f.append(
            button(
                'Restart Now',
                restart,
                'suggested-action',
            )
        )

    def install_desktop(self,*_):
        import desktop_install
        self.start(
            'Installing desktop app',
            desktop_install.install,
            lambda _:self.toast(
                'rtxForge installed in your app menu. '
                'This build is now the default.'
            ),
        )

    def show_undo(self):
        if self.options.demo:
            d,b,f=self.open_panel('Undo previous changes');b.append(label('Your install and uninstall backups will appear here.'));return
        self.start('Finding previous changes',self.service.recoveries,self.undo_loaded)
    def undo_loaded(self,records):
        d,b,f=self.open_panel('Undo previous changes');g=self.review_list();b.append(g)
        for record in records:
            item=self.review_entry(record['name'],record['detail'],self.review_game(record['name'],record.get('game')),'Backup');item.add_suffix(button('Review',lambda _,r=record:self.review_recovery(r)));g.append(item)
        if not records:b.append(label('No recorded changes yet.'))
    def review_recovery(self,record):
        flow=self.new_operation_flow('recovery',[])
        flow.show_working('Checking the recorded changes…',cancellable=True)
        self.start('Checking restore',lambda:self.service.review_recovery(record),lambda review:None if flow.closed else self.action_ready(review))

    def show_cleanup(self):
        if self.options.demo:return
        flow=self.new_operation_flow('cleanup',[])
        flow.show_working('Checking global cleanup candidates…',cancellable=True)
        self.start('Scanning old NR files',self.service.review_cleanup,lambda review:None if flow.closed else self.action_ready(review))
    def capture(self,name):
        """Capture a rendered GTK widget without assuming a node exists."""

        widget=self

        if isinstance(self.dialog,ResizablePanelWindow) and self.dialog.get_mapped():
            widget=self.dialog

        width=max(
            1,
            widget.get_width(),
        )

        height=max(
            1,
            widget.get_height(),
        )

        if (
            not widget.get_mapped()
            or width<=1
            or height<=1
        ):
            return None

        # WidgetPaintable is GTK4's observation mechanism for widget
        # contents. Freeze its current image before building our snapshot;
        # this is considerably safer than assuming the live paintable has
        # already emitted render nodes during the current frame.
        paint=Gtk.WidgetPaintable.new(
            widget
        )

        image=paint.get_current_image()

        if image is None:
            return None

        snapshot=Gtk.Snapshot()

        image.snapshot(
            snapshot,
            float(width),
            float(height),
        )

        node=snapshot.to_node()

        # GTK explicitly allows a snapshot to contain no render node.
        # Treat that as "frame not ready" rather than a fatal TypeError.
        if node is None:
            return None

        native=widget.get_native()

        if native is None:
            return None

        renderer=native.get_renderer()

        if renderer is None:
            return None

        rect=Graphene.Rect()
        rect.init(
            0,
            0,
            width,
            height,
        )

        texture=renderer.render_texture(
            node,
            rect,
        )

        output=ROOT/'dist'/name

        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        texture.save_to_png(
            str(output)
        )

        return output


    def capture_when_ready(
        self,
        name,
        continuation,
        attempt=0,
    ):
        """Retry screenshot capture across frames instead of crashing."""

        try:
            output=self.capture(
                name
            )

            if output is not None:
                print(
                    f'SCREENSHOT: {output}',
                    flush=True,
                )

                GLib.timeout_add(
                    180,
                    continuation,
                )

                return False

            if attempt>=30:
                raise RuntimeError(
                    'GTK did not produce a renderable screenshot '
                    f'after 30 attempts: {name}'
                )

            self.queue_draw()

            GLib.timeout_add(
                120,
                lambda:self.capture_when_ready(
                    name,
                    continuation,
                    attempt+1,
                ),
            )

        except Exception:
            traceback.print_exc()
            self.get_application().exit_code=1
            self.get_application().quit()

        return False


    def resize_smoke_startup(self):
        """Visual regression test for adaptive Library resizing."""

        try:
            self._resize_smoke_results={}
            self._resize_smoke_target_width=1160
            self._resize_smoke_target_height=820

            output_dir=ROOT/'dist'/'resize-smoke'
            output_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            # Do not let stale screenshots masquerade as a successful run.
            for old in output_dir.glob(
                '*.png'
            ):
                old.unlink()

            print(
                'RESIZE-SMOKE: starting six-state visual test',
                flush=True,
            )

            self.unmaximize()

            self.set_default_size(
                self._resize_smoke_target_width,
                self._resize_smoke_target_height,
            )

            self.view_buttons[
                'posters'
            ].set_active(
                True
            )

            self.update_library_spacing()

            GLib.timeout_add(
                900,
                self._resize_smoke_poster_normal,
            )

        except Exception:
            traceback.print_exc()
            self.get_application().exit_code=1
            self.get_application().quit()

        return False


    def _resize_smoke_state(
        self,
        label,
        expected_slots,
        continuation,
    ):
        """Validate geometry and capture the current allocation."""

        self.update_library_spacing()

        window_width=self.get_width()
        window_height=self.get_height()

        hadj=self.library_scroll.get_hadjustment()

        viewport_width=(
            int(
                round(
                    hadj.get_page_size()
                )
            )
            if hadj is not None
            else 0
        )

        min_slots=(
            self.flow.get_min_children_per_line()
        )

        max_slots=(
            self.flow.get_max_children_per_line()
        )

        expected_slots=max_slots
        if not 3<=min_slots<=9:
            raise AssertionError(
                f'{label}: min slots {min_slots}, '
                f'expected {expected_slots}'
            )

        if max_slots!=expected_slots:
            raise AssertionError(
                f'{label}: max slots {max_slots}, '
                f'expected {expected_slots}'
            )

        visible=[
            entry
            for entry in self.cards.values()
            if (
                entry.get(
                    'wrapper'
                ) is not None
                and entry[
                    'wrapper'
                ].get_visible()
            )
        ]

        if not visible:
            raise AssertionError(
                f'{label}: no visible Library cards'
            )

        card_width=visible[
            0
        ][
            'widget'
        ].get_size_request()[0]

        dimensions={(entry['widget'].get_width(), entry['widget'].get_height())
                    for entry in visible}
        if len(dimensions)!=1:
            raise AssertionError(f'{label}: unequal allocated cards: {dimensions}')
        # get_width excludes CSS borders; wrapper allocation includes them.
        for entry in visible + list(getattr(self, 'ghost_slots', [])):
            allocated=entry['wrapper'].get_width()
            if allocated != card_width:
                raise AssertionError(
                    f'{label}: allocated slot {allocated}px != requested {card_width}px')
        last=visible[min(expected_slots,len(visible))-1]['wrapper']
        ok,bounds=last.compute_bounds(self.library_scroll)
        if not ok or abs(bounds.get_x()+bounds.get_width()-(viewport_width-16))>1:
            raise AssertionError(f'{label}: final slot does not meet the viewport inset: slots={max_slots}, viewport={viewport_width}, x={bounds.get_x()}, width={bounds.get_width()}')

        self._resize_smoke_results[
            label
        ]={
            'window_width':window_width,
            'window_height':window_height,
            'viewport_width':viewport_width,
            'card_width':card_width,
            'slots':max_slots,
        }

        print(
            (
                f'RESIZE-SMOKE: {label}: '
                f'window={window_width}x{window_height}, '
                f'viewport={viewport_width}, '
                f'slots={max_slots}, '
                f'card={card_width}px'
            ),
            flush=True,
        )

        filename=(
            f'resize-smoke/'
            f'{label}-'
            f'w{window_width}-'
            f'viewport{viewport_width}-'
            f'card{card_width}.png'
        )

        self.capture_when_ready(
            filename,
            continuation,
        )

        return False


    # --------------------------------------------------------
    # POSTER:
    # normal -> maximize -> restored
    # --------------------------------------------------------

    def _resize_smoke_poster_normal(self):
        try:
            return self._resize_smoke_state(
                '01-poster-normal',
                7,
                self._resize_smoke_poster_maximize,
            )
        except Exception:
            traceback.print_exc()
            self.get_application().exit_code=1
            self.get_application().quit()

        return False


    def _resize_smoke_poster_maximize(self):
        normal=self._resize_smoke_results.get(
            '01-poster-normal',
            {},
        )

        normal_width=int(
            normal.get(
                'window_width',
                0,
            )
        )

        sanity_limit=(
            self._resize_smoke_target_width
            + 500
        )

        if normal_width>sanity_limit:
            print(
                (
                    'FAIL-SAFE: initial Library window is already '
                    f'{normal_width}px wide; expected roughly '
                    f'{self._resize_smoke_target_width}px. '
                    'Keeping the first screenshot and refusing to '
                    'maximize a known-bad layout.'
                ),
                flush=True,
            )

            self.get_application().exit_code=1
            self.get_application().quit()

            return False

        self.maximize()

        GLib.timeout_add(
            1100,
            self._resize_smoke_poster_maximized,
        )

        return False


    def _resize_smoke_poster_maximized(self):
        try:
            return self._resize_smoke_state(
                '02-poster-maximized',
                7,
                self._resize_smoke_poster_restore,
            )
        except Exception:
            traceback.print_exc()
            self.get_application().exit_code=1
            self.get_application().quit()

        return False


    def _resize_smoke_poster_restore(self):
        self.unmaximize()

        self.set_default_size(
            self._resize_smoke_target_width,
            self._resize_smoke_target_height,
        )

        GLib.timeout_add(
            1100,
            self._resize_smoke_poster_restored,
        )

        return False


    def _resize_smoke_poster_restored(self):
        try:
            current=self.get_width()

            maximized=self._resize_smoke_results[
                '02-poster-maximized'
            ][
                'window_width'
            ]

            if (
                maximized-current
                < 32
            ):
                raise AssertionError(
                    'Poster window failed to shrink after maximize: '
                    f'max={maximized}px restored={current}px'
                )

            return self._resize_smoke_state(
                '03-poster-restored',
                7,
                self._resize_smoke_capsule_normal,
            )

        except Exception:
            traceback.print_exc()
            self.get_application().exit_code=1
            self.get_application().quit()

        return False


    # --------------------------------------------------------
    # WIDE CAPSULE:
    # normal -> maximize -> restored
    # --------------------------------------------------------

    def _resize_smoke_capsule_normal(self):
        try:
            self.view_buttons[
                'capsules'
            ].set_active(
                True
            )

            self.update_library_spacing()

            GLib.timeout_add(
                700,
                self._resize_smoke_capsule_normal_capture,
            )

        except Exception:
            traceback.print_exc()
            self.get_application().exit_code=1
            self.get_application().quit()

        return False


    def _resize_smoke_capsule_normal_capture(self):
        try:
            return self._resize_smoke_state(
                '04-capsule-normal',
                6,
                self._resize_smoke_capsule_maximize,
            )
        except Exception:
            traceback.print_exc()
            self.get_application().exit_code=1
            self.get_application().quit()

        return False


    def _resize_smoke_capsule_maximize(self):
        self.maximize()

        GLib.timeout_add(
            1100,
            self._resize_smoke_capsule_maximized,
        )

        return False


    def _resize_smoke_capsule_maximized(self):
        try:
            return self._resize_smoke_state(
                '05-capsule-maximized',
                6,
                self._resize_smoke_capsule_restore,
            )
        except Exception:
            traceback.print_exc()
            self.get_application().exit_code=1
            self.get_application().quit()

        return False


    def _resize_smoke_capsule_restore(self):
        self.unmaximize()

        self.set_default_size(
            self._resize_smoke_target_width,
            self._resize_smoke_target_height,
        )

        GLib.timeout_add(
            1100,
            self._resize_smoke_capsule_restored,
        )

        return False


    def _resize_smoke_capsule_restored(self):
        try:
            current=self.get_width()

            maximized=self._resize_smoke_results[
                '05-capsule-maximized'
            ][
                'window_width'
            ]

            if (
                maximized-current
                < 32
            ):
                raise AssertionError(
                    'Wide Capsule window failed to shrink after maximize: '
                    f'max={maximized}px restored={current}px'
                )

            return self._resize_smoke_state(
                '06-capsule-restored',
                6,
                self._resize_smoke_complete,
            )

        except Exception:
            traceback.print_exc()
            self.get_application().exit_code=1
            self.get_application().quit()

        return False


    def _resize_smoke_complete(self):
        try:
            results=self._resize_smoke_results

            # In addition to window shrinkability, prove the actual cards
            # responded in both directions.
            for prefix in (
                'poster',
                'capsule',
            ):
                normal=results[
                    (
                        '01-poster-normal'
                        if prefix=='poster'
                        else '04-capsule-normal'
                    )
                ]

                maximum=results[
                    (
                        '02-poster-maximized'
                        if prefix=='poster'
                        else '05-capsule-maximized'
                    )
                ]

                restored=results[
                    (
                        '03-poster-restored'
                        if prefix=='poster'
                        else '06-capsule-restored'
                    )
                ]

                if maximum['slots']<normal['slots']:
                    raise AssertionError(f'{prefix}: density decreased in a wider viewport')
                if (restored['slots'],restored['card_width']) != (normal['slots'],normal['card_width']):
                    raise AssertionError(f'{prefix}: restored geometry differs from normal')

            print(
                '',
                flush=True,
            )

            print(
                'PASS: live resize expanded and contracted both galleries.',
                flush=True,
            )

            print(
                'SCREENSHOTS: dist/resize-smoke/',
                flush=True,
            )

            print(
                '',
                flush=True,
            )

            for key,value in results.items():
                print(
                    (
                        f'  {key}: '
                        f'window={value["window_width"]}, '
                        f'viewport={value["viewport_width"]}, '
                        f'card={value["card_width"]}, '
                        f'slots={value["slots"]}'
                    ),
                    flush=True,
                )

        except Exception:
            traceback.print_exc()
            self.get_application().exit_code=1

        self.get_application().quit()

        return False


    def library_state_smoke_ready(self):
        print(
            '',
            flush=True,
        )
        print(
            'LIBRARY STATE SMOKE READY',
            flush=True,
        )
        print(
            '  Each title has: Installed / Available / '
            'Blocked / Installed+Blocked',
            flush=True,
        )
        print(
            '  Report pills exercise: WORKING / UNTESTED / '
            'PROBLEM / BENCH',
            flush=True,
        )
        print(
            '  This mode is write-disabled.',
            flush=True,
        )
        print(
            '',
            flush=True,
        )

        self.toast(
            'Library state smoke · write-disabled'
        )

        return False


    def live_smoke_startup(self):
        """Open the real write-disabled Progress -> Done path."""
        try:
            rows=list(self.games[:3])

            if not rows:
                raise RuntimeError(
                    'Live Smoke has no demo games available.'
                )

            self.launch_action(
                'install',
                targets=rows,
            )

        except Exception:
            traceback.print_exc()
            self.get_application().exit_code=1
            self.get_application().quit()

        return False

    def smoke_library(self):
        try:
            assert (
                self.reset_all.text_label.get_text()
                == 'Reset'
            )

            assert hasattr(
                self,
                'dashboard_icon',
            )

            assert hasattr(
                self,
                'operation_revealer',
            )

            # Manual Library artwork sizing has been removed.
            assert not hasattr(
                self,
                'library_size_scale',
            )

            def viewport_width():
                hadj=self.library_scroll.get_hadjustment()

                width=(
                    int(
                        round(
                            hadj.get_page_size()
                        )
                    )
                    if hadj is not None
                    else 0
                )

                if width<=1:
                    width=self.library_scroll.get_width()

                    vscroll=self.library_scroll.get_vscrollbar()

                    if (
                        vscroll is not None
                        and vscroll.get_visible()
                        and vscroll.get_width()>0
                    ):
                        width=max(
                            1,
                            width-vscroll.get_width(),
                        )

                return width

            def assert_gallery_contract(
                view,
                slots,
            ):
                assert (
                    self.settings.get(
                        'library_view'
                    )
                    == view
                )

                # This smoke helper switches views synchronously. Let GTK allocate
                # the new gallery before asserting its responsive geometry.
                settle=GLib.MainLoop()
                GLib.timeout_add(120,lambda:(settle.quit(),False)[1])
                settle.run()
                assert viewport_width()>1, 'Smoke gallery was not allocated'
                self.update_library_spacing()
                slots=self.flow.get_max_children_per_line()

                assert (
                    self.flow.get_min_children_per_line()
                    == slots
                )

                assert (
                    self.flow.get_max_children_per_line()
                    == slots
                )

                # Pages keep one centered column: 3% side margins, at least 16 px.
                assert (
                    self.flow.get_margin_start()
                    >= 16
                )

                assert (
                    self.flow.get_margin_end()
                    == self.flow.get_margin_start()
                )

                assert (
                    self.flow.get_column_spacing()
                    >= 0
                )

                assert (
                    self.flow.get_row_spacing()
                    == 16
                )

                assert not self.flow.get_hexpand()

                assert (
                    self.flow.get_halign()
                    == Gtk.Align.START
                )

                visible=[
                    entry
                    for entry in self.cards.values()
                    if (
                        entry.get(
                            'wrapper'
                        ) is not None
                        and entry[
                            'wrapper'
                        ].get_visible()
                    )
                ]

                expected_ghosts=(
                    (
                        slots
                        - (
                            len(visible)
                            % slots
                        )
                    )
                    % slots
                    if visible
                    else 0
                )

                ghosts=list(
                    getattr(
                        self,
                        'ghost_slots',
                        [],
                    )
                )

                assert (
                    len(ghosts)
                    == expected_ghosts
                )

                for ghost in ghosts:
                    assert 'data' not in ghost
                    assert 'check' not in ghost
                    assert 'click' not in ghost

                layout_entries=(
                    visible
                    + ghosts
                )

                if layout_entries:
                    assert (
                        len(layout_entries)
                        % slots
                        == 0
                    )

                    widths=[
                        entry[
                            'widget'
                        ].get_size_request()[0]
                        for entry in layout_entries
                    ]

                    assert len(set(widths))==1

                    first_row=layout_entries[
                        :slots
                    ]

                    card_width=widths[0]

                    occupied=(
                        card_width
                        * slots
                        + (
                            self.flow.get_column_spacing()
                            * (
                                slots-1
                            )
                        )
                        + sum(
                            entry[
                                'wrapper'
                            ].get_margin_start()
                            for entry in first_row
                        )
                    )

                    flow_width=(
                        self.flow.get_size_request()[0]
                    )

                    assert (
                        occupied
                        == flow_width
                    )

                    assert (
                        flow_width
                        <= max(
                            1,
                            viewport_width()-32,
                        )
                    )

            # Poster is permanently seven visual slots.
            self.settings[
                'library_view'
            ]='posters'

            self.show_games(
                list(
                    self.games
                ),
                False,
            )

            assert_gallery_contract(
                'posters',
                7,
            )

            # Wide Capsule is permanently six visual slots.
            self.settings[
                'library_view'
            ]='capsules'

            self.show_games(
                list(
                    self.games
                ),
                False,
            )

            assert_gallery_contract(
                'capsules',
                6,
            )

            # Return screenshot smoke to Poster.
            self.settings[
                'library_view'
            ]='posters'

            self.show_games(
                list(
                    self.games
                ),
                False,
            )

            assert_gallery_contract(
                'posters',
                7,
            )

            for key,widget in self.tuning_widgets.items():
                original=(
                    widget.get_selected()
                    if key=='mfg_multiplier'
                    else widget.get_value()
                )

                if key=='mfg_multiplier':
                    widget.set_selected(1 if original == 0 else 0)
                else:
                    widget.set_value(0)

                assert (
                    self.apply_presets.get_sensitive()
                )

                if key=='mfg_multiplier':
                    widget.set_selected(
                        original
                    )
                else:
                    widget.set_value(
                        original
                    )

                assert (
                    self.reset_all.text_label.get_text()
                    == 'Reset'
                )

            GLib.timeout_add(
                250,
                self.smoke_library_ready,
            )

        except Exception:
            traceback.print_exc()
            self.get_application().exit_code=1
            self.get_application().quit()

        return False

    def smoke_capture_ready(self,name,continuation):
        if getattr(self,'_smoke_captured',None)==name:
            self._smoke_captured=None
            return True
        def resume():
            self._smoke_captured=name
            return continuation()
        self.capture_when_ready(name,resume)
        return False

    def smoke_library_ready(self):
        try:
            if not self.smoke_capture_ready('gnome-library.png',self.smoke_library_ready):return False
            self.search.set_text('Cyberpunk');self.select_all(True)
            # Select all takes the supported games the search shows, and only those.
            chosen=[g for g in self.games if g['game'] in self.selected_game_ids]
            assert chosen and all('cyberpunk' in g['name'].casefold() and not g.get('blocked') for g in chosen)
            assert all(self.cards[g['game']]['check'].get_active() for g in chosen if g['game'] in self.cards)
            self.profile_group.set_active_name('nr-mfg');assert self.mode=='nr-mfg'
            game={**self.games[0],'feature_mode':'nr-mfg','profile':'NR + MFG','nr_strength':2.0,'sharpening_strength':0.5,'mfg_multiplier':2}
            self.details(game)
            assert not self.detail_apply_settings.get_sensitive()
            assert hasattr(self,'detail_fit_page')
            self.detail_tuning_widgets['sharpening_strength'].set_value(0)
            assert self.detail_apply_settings.get_sensitive()
            assert self.tuning_values(self.tuning_widgets)['sharpening_strength']==0.5
            GLib.timeout_add(700,self.smoke_action)
        except Exception:traceback.print_exc();self.get_application().exit_code=1;self.get_application().quit()
        return False
    def smoke_action(self):
        try:
            # Switch directly to the Features page.
            self.detail_pages.set_visible_child_name(
                'Features'
            )

            if hasattr(
                self,
                'detail_scroll',
            ):
                self.detail_scroll.get_vadjustment().set_value(
                    0
                )
            GLib.timeout_add(300,self.smoke_game_settings)
        except Exception:traceback.print_exc();self.get_application().exit_code=1;self.get_application().quit()
        return False
    def smoke_game_settings(self):
        try:
            if not self.smoke_capture_ready('gnome-game-settings.png',self.smoke_game_settings):return False
            self.show_settings();GLib.timeout_add(700,self.smoke_settings)
        except Exception:traceback.print_exc();self.get_application().exit_code=1;self.get_application().quit()
        return False
    def smoke_settings(self):
        try:
            if not self.smoke_capture_ready('gnome-settings.png',self.smoke_settings):return False

            try:self.done_backdrop=self.snapshot_library_texture()
            except Exception:self.done_backdrop=None

            d,b,f=self.open_panel('Apply Settings',width=580,height=310,show_close=False)
            self.operation_games=self.games;self.operation_cancel=threading.Event();self.add_cancel(f);self.progress_view(b,'Applying Settings')

            progress_child=self.progress_panel.get_first_child()

            while progress_child is not None:
                assert not isinstance(
                    progress_child,
                    Gtk.ScrolledWindow,
                )

                progress_child=progress_child.get_next_sibling()

            GLib.timeout_add(500,self.smoke_progress)
        except Exception:traceback.print_exc();self.get_application().exit_code=1;self.get_application().quit()
        return False
    def smoke_progress(self):
        try:
            if not self.smoke_capture_ready('gnome-progress.png',self.smoke_progress):return False
            self.finish_progress(True,'3 games updated.',self.progress_shell.get_last_child().get_last_child());GLib.timeout_add(300,self.smoke_complete);return False
        except Exception:traceback.print_exc();self.get_application().exit_code=1
        self.get_application().quit();return False
    def smoke_complete(self):
        try:
            if not self.smoke_capture_ready('gnome-complete.png',self.smoke_complete):return False
            print('PASS: controls, tabs, settings, progress and completion; demo writes disabled',flush=True)
        except Exception:traceback.print_exc();self.get_application().exit_code=1
        self.get_application().quit();return False


class Application(Adw.Application):
    def __init__(self,options):super().__init__(application_id='io.github.lrnolivia.RTXForge',flags=Gio.ApplicationFlags.NON_UNIQUE);self.options=options;self.exit_code=0
    def do_activate(self):
        try:
            Gtk.IconTheme.get_for_display(
                Gdk.Display.get_default()
            ).add_search_path(
                str(ROOT/'gui/icons')
            )
            Gtk.Window.set_default_icon_name(
                'io.github.lrnolivia.RTXForge'
            )

            provider=Gtk.CssProvider()
            provider.load_from_data(CSS)
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )

            self.window=Window(
                self,
                self.options,
            )
            self.window.present()

        except Exception:
            # In automated smoke mode a startup exception must terminate
            # the process promptly instead of leaving an empty GTK loop
            # alive until the CI timeout.
            traceback.print_exc()
            self.exit_code=1
            self.quit()
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--provider',type=Path)
    parser.add_argument('--ui-mode',choices=['classic','new'],default=None)
    parser.add_argument(
        '--demo',
        action='store_true',
        help='Interactive write-disabled demo mode.',
    )
    parser.add_argument(
        '--resize-smoke',
        action='store_true',
        help=(
            'Automated six-screenshot Library resize regression test.'
        ),
    )
    parser.add_argument(
        '--smoke-test',
        action='store_true',
        help='Automated screenshot and regression smoke test.',
    )
    parser.add_argument(
        '--live-smoke',
        action='store_true',
        help=(
            'Interactive write-disabled UI smoke test with '
            'manual Progress and Done states.'
        ),
    )
    parser.add_argument(
        '--library-state-smoke',
        action='store_true',
        help=(
            'Interactive write-disabled Library matrix showing '
            'every status/action state.'
        ),
    )
    options=parser.parse_args()

    if (
        options.resize_smoke
        or options.smoke_test
        or options.live_smoke
        or options.library_state_smoke
    ):
        options.demo=True
    app=Application(options);result=app.run([sys.argv[0]]);return app.exit_code or result
if __name__=='__main__':sys.exit(main())
