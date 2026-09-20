#!/usr/bin/env python3
"""Native GNOME poster library. All engine work is serialized off the GTK thread."""
from pathlib import Path
import sys,threading,time,traceback,argparse,datetime,colorsys
from collections import Counter
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
APP_VERSION=(ROOT/'VERSION').read_text(encoding='utf-8').strip() if (ROOT/'VERSION').exists() else 'dev'
import gi
gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
from gi.repository import Gtk,Adw,GLib,Gio,Gdk,Graphene,Pango,GdkPixbuf,GObject
import ui,library_media,os,game_notes
from desktop_service import DesktopService

ACCENT_PROVIDERS={}


def gamescope_session():
    """Return True for Steam Gaming Mode / gamescope-session."""

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

    def get_selected(self):
        return self.choice.get_selected()

    def set_selected(self,index):
        self.choice.set_selected(index)


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
def artwork_accent(path,color=None):
    pix=GdkPixbuf.Pixbuf.new_from_file_at_scale(
        path,
        32,
        32,
        True,
    )

    data=pix.get_pixels()
    stride=pix.get_rowstride()
    channels=pix.get_n_channels()
    colors=Counter()

    for y in range(pix.get_height()):
        for x in range(pix.get_width()):
            off=y*stride+x*channels

            if (
                channels==4
                and data[off+3]<128
            ):
                continue

            rgb=tuple(
                data[off+k]/255
                for k in range(3)
            )

            h,s,v=colorsys.rgb_to_hsv(
                *rgb
            )

            if (
                s>.25
                and .2<v<.98
            ):
                colors[
                    int(h*24)
                ]+=s*v

    hue=(
        (
            colors.most_common(1)[0][0]
            + .5
        )
        /24
        if colors
        else .23
    )

    rgb=tuple(
        round(v*255)
        for v in colorsys.hsv_to_rgb(
            hue,
            .62,
            .90,
        )
    )

    color=(
        color
        or '#%02x%02x%02x'%rgb
    )

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

        accent_dark='#%02x%02x%02x'%(
            round(dr*255),
            round(dg*255),
            round(db*255),
        )

    except Exception:
        accent_fg='#ffffff'
        accent_dark='#18181b'

    name='art-'+color[1:]

    if name not in ACCENT_PROVIDERS:
        provider=Gtk.CssProvider()

        provider.load_from_data((
            # Poster / Wide Capsule selection border.
            f'.game-card.{name}.selected {{ '
            f'background: {color}; '
            f'border-color: {color}; '
            f'box-shadow: 0 2px 12px alpha({color},0.28); '
            f'}} '

            f'.game-card.{name}.selected .gallery-artwork-frame {{ '
            f'background: {color}; '
            f'border-color: transparent; '
            f'box-shadow: inset 0 0 0 3.5px {color}; '
            f'}} '

            f'.game-card.{name}.selected .library-meta-pill {{ '
            f'background: alpha({accent_dark},0.94); '
            f'border-color: transparent; '
            f'box-shadow: none; '
            f'color: white; '
            f'}} '

            f'.game-card.{name}.selected .library-pill-text, '
            f'.game-card.{name}.selected .library-pill-icon {{ '
            f'color: white; '
            f'}} '

            f'.game-card.{name}:hover {{ '
            f'border-color: transparent; '
            f'box-shadow: none; '
            f'}} '

            f'.game-card.{name}:hover .gallery-artwork-frame {{ '
            f'background: {color}; '
            f'border-color: transparent; '
            f'box-shadow: '
            f'inset 0 0 0 3.5px {color}, '
            f'0 0 9px alpha({color},0.34); '
            f'}} '

            # Gtk.ColumnView: accent stays inside the Game and
            # Actions cells. The row itself never gets an accent border.
            f'.library-column-game.{name} '
            f'.library-column-art.selected-art {{ '
            f'border-color: {color}; '
            f'box-shadow: 0 2px 10px alpha({color},0.28); '
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
            f'.game-card.{name}.selected .game-details {{ '
            f'background: alpha(white,0.44); '
            f'color: {accent_dark}; '
            f'border-color: transparent; '
            f'box-shadow: none; '
            f'}} '

            f'.game-card.{name}.selected .game-details label {{ '
            f'color: {accent_dark}; '
            f'font-weight: 700; '
            f'}} '

            f'.game-card.{name}:hover .card-title {{ '
            f'color: {color}; '
            f'}} '

            f'.game-card.{name}.selected .card-title, '
            f'.game-card.{name}.selected:hover .card-title {{ '
            f'color: {accent_dark}; '
            f'}} '

            f'.library-column-game.{name}:hover .library-column-title, '
            f'columnview.library-column-view row:hover '
            f'.library-column-game.{name} .library-column-title {{ '
            f'color: {color}; '
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
            f'color: {color}; '
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
            f'.{name} .game-banner-title, '
            f'.{name} .job-title, '
            f'.{name} .eyebrow {{ '
            f'color: {color}; '
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


class CoverPicture(Gtk.Picture):
    # Ask the layout for height at the actual allocated width, not the original minimum.
    cover_width=158
    cover_ratio=2/3
    def do_get_request_mode(self):return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH
    def do_measure(self, orientation, for_size):
        if orientation==Gtk.Orientation.HORIZONTAL:return (self.cover_width,self.cover_width,-1,-1)
        height=__import__('math').ceil((for_size if for_size>0 else self.cover_width)/self.cover_ratio)
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
LIBRARY_BOTTOM_CLEARANCE=0
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


    def _update_icon(self,text):
        value=str(
            text or ''
        ).strip().casefold()

        if self.kind=='source':
            if (
                value=='steam'
                and LIBRARY_STEAM_ICON.exists()
            ):
                try:
                    self._icon.set_from_gicon(Gio.FileIcon.new(Gio.File.new_for_path(str(LIBRARY_STEAM_ICON))))

                    return

                except Exception:
                    pass

            if value=='steam':
                icon=_library_icon_name(
                    'steam-symbolic',
                    'com.valvesoftware.Steam-symbolic',
                    'applications-games-symbolic',
                )
            else:
                icon=_library_icon_name(
                    'input-gaming-symbolic',
                    'applications-games-symbolic',
                )

        else:
            if value=='working':
                icon=_library_icon_name(
                    'emblem-ok-symbolic',
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


class HeroPicture(Gtk.Picture):
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
@define-color window_bg_color #242424;
@define-color window_fg_color #f2f2f2;
@define-color view_bg_color #1e1e1e;
@define-color view_fg_color #f2f2f2;
@define-color sidebar_bg_color #2d2d2d;
@define-color sidebar_fg_color #f2f2f2;
@define-color card_bg_color #383838;
@define-color card_fg_color #f2f2f2;
@define-color dialog_bg_color #242424;
@define-color popover_bg_color #303030;
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
@define-color forge_lower_bg @sidebar_bg_color;
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
    padding: 3px 8px;
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
    background: transparent;
    background-image: none;
    box-shadow: none;
}

.settings-navigation row:selected label {
    font-weight: 700;
}

.settings-main-surface {
    background: @view_bg_color;
}

.settings-content {
    padding: 16px;
}

.settings-footer {
    padding: 14px 18px;
    background: @view_bg_color;
    border-top: 1px solid alpha(@window_fg_color,0.10);
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
    color: #212121;
}

button.game-detail-close:hover {
    background: alpha(#161616,0.88);
}

button.game-detail-close.light:hover {
    background: alpha(white,0.90);
}

.game-banner { background: #262626; }

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
    color: alpha(white,0.84);
    font-size: 13px;
    text-shadow: 0 1px 5px alpha(black,0.90);
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
    color: alpha(white,0.78);
    font-size: 12px;
    text-shadow: 0 1px 5px alpha(black,0.92);
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
        alpha(black,0.28) 0%,
        alpha(black,0.12) 28%,
        alpha(@window_bg_color,0.26) 52%,
        alpha(@window_bg_color,0.72) 76%,
        @window_bg_color 100%
    );
}

/*
 * Hero typography separation.
 * Apply the treatment to title, metadata, summary and status badge text.
 */
.game-banner.hero-light .game-banner-title,
.game-banner.hero-light .game-detail-meta,
.game-banner.hero-light .game-detail-summary {
    padding: 6px 9px 7px;
}

/* Compact, stable Library card labels. */
.game-card .card-info {
    padding: 8px;
}


.game-card .card-title {
    font-size: 15px;
    font-weight: 700;
    min-height: 0;
    margin: 0;
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
    background: #c9c9c9;
    color: #212121;
    border-color: transparent;
}

.game-card .game-details:hover label {
    color: #212121;
}


.game-card .card-title.art-title-xs {
    font-size: 12px;
}

.game-card .card-title.art-title-sm {
    font-size: 13px;
}

.game-card .card-title.art-title-md {
    font-size: 14px;
}

.game-card .card-title.art-title-lg {
    font-size: 15px;
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
    padding: 0 16px;
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
    padding-right: 18px;
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
    background: @view_bg_color;
    border: none;
    border-color: transparent;
    box-shadow: none;
    color: #d2d2d2;
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
    color: #d2d2d2;
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
    min-height: 24px;
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
    background: #c9c9c9;
    color: #212121;
    border-color: transparent;
}

.library-column-actions button:hover label,
.library-column-actions button:hover image {
    color: #212121;
}


.game-card .poster-fallback {
    font-size: 14px;
    padding: 10px;
}

.game-banner.hero-dark .game-detail-meta,
.game-banner.hero-dark .game-detail-summary,
.game-banner.hero-dark .cover-badge {
    text-shadow:
        0 2px 7px alpha(black,0.82),
        0 0 10px alpha(white,0.10);
}

.game-banner-title {
    color: @window_fg_color;
    font-size: 42px;
    font-weight: 600;
    letter-spacing: -0.8px;
    text-shadow: 0 0 8px alpha(black,0.78), 0 0 20px alpha(black,0.42);
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
    padding: 30px 34px 26px;
    color: white;
}

.progress-shade {
    background:
        linear-gradient(
            to right,
            alpha(black,0.88),
            alpha(black,0.48)
        );
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
    border-radius: 22px;

    /* 70% thinner than the old 2px treatment. */
    border: 0.6px solid alpha(black,0.60);

    background: alpha(#0e0e0e,0.54);
}

.progress-panel.done {
    background: @window_bg_color;
}
.progress-panel.done .progress-content { padding: 20px 24px; }

.progress-poster-frame {
    border-radius: 20px;

    /*
     * Neutral fallback only.
     * artwork_accent() overrides the border color per game.
     *
     * Keep the frame itself outside the clipping surface so the
     * rounded accent edge stays clean instead of being cut off.
     */
    border: 1px solid alpha(white,0.18);

    background: alpha(black,0.16);
    padding: 2px;
}

.progress-poster {
    border-radius: 16px;
    background: black;
}

.job-title {
    font-size: 28px;
    font-weight: 600;
}

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

    background: alpha(#333333,0.96);
    color: white;

    border: 1px solid alpha(white,0.10);
}

.progress-inline-cancel:hover {
    background: alpha(#3e3e3e,1.0);
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
    color: white;
}


.control-pod {
    padding: 16px;
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
    padding: 6px 13px;
    min-height: 20px;
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
.dashboard-tuning .control-pod scale { padding: 2px; }

/* rtxForge dashboard tuning typography */
.dashboard-tuning .control-pod {
    padding: 16px;
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

.hamburger-glyph {
    font-size: 18px;
    font-weight: 600;
}

.hero-title { font-size: 25px; font-weight: 800; letter-spacing: -0.6px; }
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


.game-card.selected { border-color: #76b900; box-shadow: 0 2px 12px alpha(#76b900,0.22); }

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

.panel-body { padding: 18px 24px; }
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


.library-sticky-header entry {
    min-height: 36px;
}

.library-sticky-header button, .library-sticky-header toggle {
    min-height: 34px;
    padding: 5px 10px;
}


/* Column header gets matching vertical room. */
columnview.library-column-view header {
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
 * Artwork occupies the FULL container.
 * The 3.5px ring is an INSET shadow painted over the artwork,
 * so it consumes zero layout space and cannot expose dark gaps.
 * ---------------------------------------------------------- */

.game-card .gallery-artwork-frame {
    border: none;
    border-radius: 14px;
    background: @forge_library_card_a;
    box-shadow: inset 0 0 0 3.5px @forge_library_card_a;
}

.game-card.library-stripe-a .gallery-artwork-frame {
    border-color: @forge_library_card_a;
    background: @forge_library_card_a;
    box-shadow: inset 0 0 0 3.5px @forge_library_card_a;
}

.game-card.library-stripe-b .gallery-artwork-frame {
    border-color: @forge_library_card_b;
    background: @forge_library_card_b;
    box-shadow: inset 0 0 0 3.5px @forge_library_card_b;
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
    min-height: 42px;
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
    font-size: 13px;
    font-weight: 700;
}

/* Two neighboring rows create an 8px visual gap total. */
columnview.library-column-view listview row {
    min-height: 0;
    margin: 2px 0;
    padding: 0;
    border: 2px solid transparent;
    border-radius: 12px;
    background: @forge_library_card_a;
    margin-top: 4px;
    margin-bottom: 4px;
}


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



columnview.library-column-view header button:first-child { padding-left: 68px; }
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
    box=Gtk.Box(spacing=6);box.append(Gtk.Image.new_from_icon_name(profile_icon(mode)));box.append(label(text));return box

def label(text,css=None):
    w=Gtk.Label(label=str(text),xalign=0,wrap=True)
    if css:w.add_css_class(css)
    return w
def button(text,fn,css=None):
    w=Gtk.Button(label=text);w.connect('clicked',fn)
    if css:w.add_css_class(css)
    return w
def icon_button(text,icon,fn,css=None):
    content=Gtk.Box(spacing=6)
    content.append(Gtk.Image.new_from_icon_name(icon))
    text_label=label(text);text_label.set_wrap(False);text_label.set_single_line_mode(True)
    content.append(text_label)
    w=Gtk.Button(child=content)
    w.text_label=text_label
    w.connect('clicked',fn)
    if css:w.add_css_class(css)
    return w
def margins(w,n=16):
    for edge in ('start','end','top','bottom'):getattr(w,'set_margin_'+edge)(n)
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
            default_width=width,
            default_height=height,
            resizable=True,
        )

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
        self.set_content(child)

    def get_child(self):
        return self.get_content()

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
    def __init__(self,application,options):
        super().__init__(application=application,title='rtxForge',default_width=1160,default_height=820)
        self.options=options;self.service=DesktopService(options.provider)
        self.settings=dict(library_media.DEFAULTS) if options.demo else library_media.load_settings(self.service.config)

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

        self.strength_names=tuple(self.strength_presets);self.multiplier_values=(0,2,3,4,5,6)
        self.settings['enable_effects']=True;self.settings.setdefault('dark',True);self.hardware_info={'ready':True,'gpu':'Preview GPU','reason':'Preview mode'} if options.demo else None;self.games=[];self.cards={};self.selected_game_ids=set();self.mode='mfg-only';self.filter='all'
        self.busy=False;self.task_kind='';self.pending=None;self.cancel_art=threading.Event();self.log=[];self.dialog=None;self.review=None;self.action_buttons=[]
        self.connect('close-request',self.close_request)
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK if self.settings['dark'] else Adw.ColorScheme.FORCE_LIGHT)
        self.overlay=Adw.ToastOverlay();self.overlay.add_css_class('forge-toasts');self.set_content(self.overlay)
        stage=Gtk.Overlay();self.overlay.set_child(stage)
        outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.add_css_class('forge-window-surface')
        stage.set_child(outer)
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

        menu=Gio.Menu()

        library_menu=Gio.Menu()
        library_menu.append(
            'Refresh Library',
            'win.refresh-library',
        )
        library_menu.append(
            'Add Game Folder…',
            'win.add-game-folder',
        )
        menu.append_section(
            None,
            library_menu,
        )

        app_menu=Gio.Menu()
        app_menu.append(
            'Activity',
            'win.activity',
        )
        app_menu.append(
            'Settings',
            'win.settings',
        )
        menu.append_section(
            None,
            app_menu,
        )

        menu_glyph=Gtk.Label(
            label='☰',
        )
        menu_glyph.add_css_class(
            'hamburger-glyph'
        )

        main_menu=Gtk.MenuButton()
        main_menu.set_child(
            menu_glyph
        )
        main_menu.add_css_class(
            'flat'
        )
        main_menu.set_tooltip_text(
            'Main Menu'
        )
        main_menu.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ['Main Menu'],
        )
        main_menu.set_menu_model(
            menu
        )
        if gamescope_session():
            # Gtk.MenuButton/GMenu uses a GtkPopover. Gamescope has
            # compositor/input problems with popup surfaces, so keep
            # this menu inside the existing application surface.
            main_menu.set_menu_model(
                None
            )

            def show_gamemode_menu(*_):
                menu_dialog=Adw.Dialog(
                    title='Menu',
                    content_width=340,
                    content_height=300,
                )

                try:
                    menu_dialog.set_presentation_mode(
                        Adw.DialogPresentationMode.FLOATING
                    )
                except Exception:
                    pass

                shell=Gtk.Box(
                    orientation=Gtk.Orientation.VERTICAL,
                    spacing=6,
                )
                margins(
                    shell,
                    14,
                )

                def menu_button(
                    title,
                    icon_name,
                    callback,
                ):
                    content=Gtk.Box(
                        spacing=10,
                    )
                    content.append(
                        Gtk.Image.new_from_icon_name(
                            icon_name
                        )
                    )
                    content.append(
                        label(title)
                    )

                    control=Gtk.Button(
                        child=content,
                    )

                    def activate(*_):
                        menu_dialog.close()
                        GLib.idle_add(
                            lambda:(
                                callback(),
                                False,
                            )[1]
                        )

                    control.connect(
                        'clicked',
                        activate,
                    )

                    return control

                shell.append(
                    menu_button(
                        'Refresh Library',
                        'view-refresh-symbolic',
                        self.scan,
                    )
                )

                shell.append(
                    menu_button(
                        'Add Game Folder',
                        'list-add-symbolic',
                        self.choose_folder,
                    )
                )

                shell.append(
                    menu_button(
                        'Activity',
                        'document-open-recent-symbolic',
                        self.show_activity,
                    )
                )

                shell.append(
                    menu_button(
                        'Settings',
                        'emblem-system-symbolic',
                        self.show_settings,
                    )
                )

                menu_dialog.set_child(
                    shell
                )
                menu_dialog.present(
                    self
                )

            click=Gtk.GestureClick()
            click.set_propagation_phase(
                Gtk.PropagationPhase.CAPTURE
            )
            click.connect(
                'released',
                lambda *_:show_gamemode_menu(),
            )
            main_menu.add_controller(
                click
            )


        outer.append(
            header
        )
        top=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        top.add_css_class('forge-top-surface')
        margins(top,16)
        top.set_margin_top(0)
        # The Library side owns the shared seam spacing. Do not stack
        # another explicit gap beneath the dark dashboard.
        top.set_margin_bottom(8)
        outer.append(top)
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

        dashboard_art_path=(
            ROOT
            / 'gui'
            / 'icons'
            / 'hicolor'
            / '512x512'
            / 'apps'
            / 'io.github.lrnolivia.RTXForge.png'
        )

        self.dashboard_icon=Gtk.Image.new_from_file(
            str(dashboard_art_path)
        )
        self.dashboard_icon.set_pixel_size(128)
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
            lambda *_:self.launch_action(
                'install',
                not bool(self.selected_game_ids),
            ),
            'forge-primary',
        )
        bulk.append(self.install_all)

        self.uninstall_all=icon_button(
            'Restore Original Files',
            'document-revert-symbolic',
            lambda *_:self.launch_action(
                'uninstall',
                not bool(self.selected_game_ids),
            ),
            'bulk-remove',
        )
        bulk.append(self.uninstall_all)

        self.reset_all=icon_button(
            'Reset Presets',
            'edit-undo-symbolic',
            self.apply_library_settings,
        )
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
        self.operation_icon=Gtk.Image.new_from_icon_name('emblem-ok-symbolic');self.operation_icon.add_css_class('operation-complete');self.operation_icon.set_visible(False);operation.append(self.operation_icon)
        self.operation_status=label('');self.operation_status.set_max_width_chars(54);self.operation_status.set_ellipsize(Pango.EllipsizeMode.END);operation.append(self.operation_status)
        self.operation_elapsed=label('','dim-label');operation.append(self.operation_elapsed)
        self.operation_dismiss=Gtk.Button(icon_name='window-close-symbolic');self.operation_dismiss.add_css_class('operation-dismiss');self.operation_dismiss.set_tooltip_text('Dismiss');self.operation_dismiss.set_visible(False);self.operation_dismiss.connect('clicked',lambda *_:self.hide_operation_status());operation.append(self.operation_dismiss)
        for key,widget in self.tuning_widgets.items():widget.connect('notify::selected' if key=='mfg_multiplier' else 'value-changed',self.strength_changed)
        self.strength_changed()
        self.reset_all.set_tooltip_text('Restore current sharpening, NR and menu-font defaults for managed games. Each configuration is backed up. Close running games first.')
        self.install_all.set_tooltip_text('One click: prepare, back up and install wherever possible across every library. Incompatible games are skipped.')
        self.uninstall_all.set_tooltip_text('One click: remove recorded OptiScaler installs across every library, with backups. Your games remain installed.')
        controls=Gtk.Box(spacing=14)
        controls.add_css_class('control-pod')
        controls.add_css_class('mode-bar')
        controls.set_margin_top(0)

        hero.append(controls)
        profile_text=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=1,hexpand=True,valign=Gtk.Align.CENTER);controls.append(profile_text)
        profile_text.append(label('Feature Mode','heading'))
        self.profile_note=label('','dim-label');self.profile_note.add_css_class('mode-description');self.profile_note.set_ellipsize(Pango.EllipsizeMode.END);self.profile_note.set_lines(1);self.profile_note.set_max_width_chars(42);profile_text.append(self.profile_note)
        self.profile_group=Adw.ToggleGroup(homogeneous=True,valign=Gtk.Align.CENTER)
        self.profile_group.add_css_class('mode-selector')
        for mode,title in [('nr-only','NR Only'),('mfg-only','MFG Only'),('nr-mfg','NR + MFG')]:
            toggle=Adw.Toggle(name=mode,label=title,child=profile_label(mode,title));self.profile_group.add(toggle)
            if mode=='nr-only':self.nr_only=toggle;toggle.set_enabled(self.settings.get('runtime_provider','y4my')=='dlss-unlocked')
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
            spacing=6,
            valign=Gtk.Align.CENTER,
        )
        sticky_brand.add_css_class(
            'sticky-dashboard-brand'
        )

        sticky_brand_icon=Gtk.Image.new_from_file(
            str(dashboard_art_path)
        )
        sticky_brand_icon.set_pixel_size(
            22
        )
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
        sticky_brand_title.set_wrap(
            False
        )
        sticky_brand_title.set_single_line_mode(
            True
        )
        sticky_brand.append(
            sticky_brand_title
        )

        # Compact mirror of Feature Mode.
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
            spacing=4,
            valign=Gtk.Align.CENTER,
        )
        sticky_actions.add_css_class(
            'sticky-dashboard-actions'
        )

        self.sticky_install_all=icon_button(
            'Install Features',
            'document-save-symbolic',
            lambda *_:self.launch_action(
                'install',
                not bool(self.selected_game_ids),
            ),
            'forge-primary',
        )

        self.sticky_remove_all=icon_button(
            'Restore Original Files',
            'document-revert-symbolic',
            lambda *_:self.launch_action(
                'uninstall',
                not bool(self.selected_game_ids),
            ),
            'bulk-remove',
        )

        self.sticky_reset_all=icon_button(
            'Reset Presets',
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


        # Mirror sensitivity from the canonical dashboard buttons so
        # this compact presentation never becomes a second source of
        # application state.
        for primary,compact in [
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

        def set_sticky_dashboard_visible(visible):
            for revealer in (
                self.sticky_brand_revealer,
                self.sticky_dashboard_revealer,
                self.sticky_actions_revealer,
            ):
                revealer.set_reveal_child(
                    visible
                )

        # Let HeaderBar perform the alignment instead of putting all
        # three groups inside one centered title widget.
        # Give the compact product identity a little breathing room
        # from the physical left edge of the window.
        self.sticky_brand_revealer.set_margin_start(
            10
        )

        # The selector remains the title widget, but a right-side margin
        # biases it slightly left and creates more breathing room before
        # the bulk action cluster.
        self.sticky_dashboard_revealer.set_margin_end(
            48
        )

        header.pack_start(
            self.sticky_brand_revealer
        )

        header.set_title_widget(
            self.sticky_dashboard_revealer
        )

        # pack_end() order matters: the first packed item is nearest the
        # native window controls. Put the hamburger there, then actions.
        header.pack_end(
            main_menu
        )

        header.pack_end(
            self.sticky_actions_revealer
        )

        # Feature Mode sits directly above the tuning controls.
        self.presets_expander=Gtk.Expander(label='Presets', expanded=False)
        self.presets_expander.add_css_class('presets-header')
        preset_label=Gtk.Box(spacing=8,valign=Gtk.Align.CENTER)
        preset_label.append(label('Presets'))
        preset_light=Gtk.Box(valign=Gtk.Align.CENTER,visible=False)
        preset_light.add_css_class('presets-hint-light')
        preset_label.append(preset_light)
        self.presets_expander.set_label_widget(preset_label)
        preset_body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16)
        preset_body.set_margin_top(16)
        preset_body.append(tuning)
        self.reset_all.set_halign(Gtk.Align.END)
        preset_body.append(self.reset_all)
        self.presets_expander.set_child(preset_body)
        self.presets_expander.connect('notify::expanded',lambda widget,*_:top.set_margin_bottom(16 if widget.get_expanded() else 8))
        hero.append(self.presets_expander)
        if not self.settings.get('presets_hint_seen',False):
            preset_light.set_visible(True)
            GLib.timeout_add(4000,lambda:(preset_light.set_visible(False),False)[1])
            self.settings['presets_hint_seen']=True
            if not self.options.demo:
                library_media.save_settings(self.service.config,self.settings)

        viewbar=Gtk.Box(
            spacing=8,
            valign=Gtk.Align.CENTER,
        )
        viewbar.add_css_class(
            'library-sticky-header'
        )

        # Balanced light-side inset at the dark/light seam.
        viewbar.set_margin_top(
            16
        )

        # Search/filter/selection controls begin the Library toolbar
        # directly. The expanded dashboard already identifies the app at
        # the top of the Library, while the compact titlebar provides the
        # rtxForge identity after that dashboard scrolls away.
        library_tools=Gtk.Box(
            spacing=8,
            hexpand=True,
            valign=Gtk.Align.CENTER,
        )
        viewbar.append(
            library_tools
        )

        # Gallery artwork geometry is automatic and follows the
        # current Library viewport. There is intentionally no
        # manual artwork-size control.

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
                    'posters':'view-grid-symbolic',
                    'capsules':'view-dual-symbolic',
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
        self.search=Gtk.SearchEntry(
            placeholder_text='Search library',
            hexpand=True,
        )
        self.search.connect(
            'search-changed',
            lambda *_:self.filter_games(),
        )
        library_tools.append(
            self.search
        )

        filterbox=Gtk.Box()
        filterbox.add_css_class(
            'linked'
        )
        filterbox.add_css_class(
            'library-filter-group'
        )
        library_tools.append(
            filterbox
        )

        previous=None
        for name,key in [
            ('All','all'),
            ('Installed','installed'),
            ('Available','available'),
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
            filterbox.append(
                b
            )

        select_all=button(
            'Select all',
            lambda *_:self.select_all(True),
        )
        select_all.add_css_class(
            'flat'
        )
        library_tools.append(
            select_all
        )

        clear_selection=button(
            'Clear',
            lambda *_:self.select_all(False),
        )
        clear_selection.add_css_class(
            'flat'
        )
        library_tools.append(
            clear_selection
        )

        library_surface=Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=0,
            hexpand=True,
            vexpand=True,
        )
        library_surface.add_css_class('forge-library-surface')
        outer.append(library_surface)

        viewbar.set_margin_start(16)
        viewbar.set_margin_end(16)
        # Balance the two-tone panel seam:
        # dark dashboard bottom = 16px
        # light Library top     = 16px
        viewbar.set_margin_bottom(16)
        library_surface.append(viewbar)

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
        library_stage.set_child(
            self.library_stack
        )
        library_surface.append(
            library_stage
        )
        # Decorative top fade removed. The Library now begins
        # with ordinary physical spacing below its controls.
        def collapse_header(adj):
            value=adj.get_value()
            can_collapse=(
                adj.get_upper()
                - adj.get_page_size()
                > 300
            )

            if (
                value>120
                and can_collapse
            ):
                hero_reveal.set_reveal_child(
                    False
                )

                # Do not leave the old dashboard surface painted behind
                # the sticky titlebar. This removes the residual hairline
                # between the HeaderBar and Library surface.
                top.set_visible(
                    False
                )

                set_sticky_dashboard_visible(
                    True
                )
                top.set_margin_top(
                    0
                )
                top.set_margin_bottom(16 if self.presets_expander.get_expanded() else 8)
                viewbar.add_css_class(
                    'stuck'
                )

            elif value<10:
                # Restore the full dashboard surface before revealing
                # its contents again.
                top.set_visible(
                    True
                )

                hero_reveal.set_reveal_child(
                    True
                )
                set_sticky_dashboard_visible(
                    False
                )
                top.set_margin_top(0)
                top.set_margin_bottom(16 if self.presets_expander.get_expanded() else 8)
                viewbar.remove_css_class(
                    'stuck'
                )
        scroll.get_vadjustment().connect(
            'value-changed',
            collapse_header,
        )

        self.flow=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,column_spacing=14,row_spacing=16,min_children_per_line=1,max_children_per_line=12,homogeneous=False,valign=Gtk.Align.START);margins(self.flow,18);self.flow.set_margin_top(0);self.flow.set_margin_bottom(LIBRARY_BOTTOM_CLEARANCE);scroll.set_child(self.flow)
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

        self.selected_label=label('0 selected', 'selection-count')
        self.selected_label.set_wrap(False)
        self.selected_label.set_hexpand(True)
        selection_tools=Gtk.Box(spacing=12)
        margins(selection_tools,16)
        selection_tools.set_margin_top(0)
        selection_tools.set_margin_bottom(8)
        selection_tools.append(self.selected_label)
        for widget in (select_all, clear_selection):
            library_tools.remove(widget)
            widget.remove_css_class('flat')
            selection_tools.append(widget)
        self.columns_control=Gtk.SpinButton.new_with_range(3,9,1)
        self.columns_control.set_value(self.settings.get('library_columns',7))
        self.columns_control.set_tooltip_text('Preferred games per row; adapts when cards become too small or large')
        size_content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
        margins(size_content,16)
        size_content.append(label('Games per row','heading'))
        size_content.append(self.columns_control)
        hint=label('Adapts to the window to keep cards readable.','dim-label')
        hint.set_max_width_chars(28)
        size_content.append(hint)
        size_popover=Gtk.Popover()
        size_popover.set_child(size_content)
        self.size_button=Gtk.MenuButton(icon_name='view-fullscreen-symbolic')
        self.size_button.set_tooltip_text('Card size')
        self.size_button.update_property([Gtk.AccessibleProperty.LABEL],['Card size'])
        self.size_button.set_popover(size_popover)
        selection_tools.append(self.size_button)
        self.columns_control.connect('value-changed', self.library_columns_changed)
        library_surface.insert_child_after(selection_tools,viewbar)


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
        OUTER_INSET=16
        usable_width=max(1,viewport_width-OUTER_INSET*2)

        # Preferred density adapts only when cards become cramped or oversized.
        preferred=max(3,min(9,int(self.settings.get('library_columns',7))))
        preferred_gap=16
        minimum_width=180 if view=='posters' else 220
        maximum_width=300 if view=='posters' else 380
        slot_count=preferred
        while slot_count>3 and (usable_width-preferred_gap*(slot_count-1))/slot_count<minimum_width:
            slot_count-=1
        while slot_count<9 and (usable_width-preferred_gap*(slot_count-1))/slot_count>maximum_width:
            slot_count+=1
        if slot_count!=preferred and slot_count%2==0:
            if slot_count>preferred and slot_count<9:
                slot_count+=1
            elif slot_count>3:
                slot_count-=1

        visible_entries=[
            entry
            for entry in entries
            if entry[
                'wrapper'
            ].get_visible()
        ]

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
            card_width-4,
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
                94,
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
            + 4
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

                # Maximum three lines. Font size already scales down with
                # card width through art-title-xs/sm/md/lg.
                title.set_wrap(
                    True
                )
                title.set_wrap_mode(
                    Pango.WrapMode.WORD_CHAR
                )
                title.set_lines(
                    3
                )
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

            # Preserve full pill labels without letting their combined minimum
            # width overrule the golden viewport/slot geometry.
            meta_row=entry.get('meta_row')
            if meta_row is not None:
                pills=(entry['meta'], entry['test_meta'])
                pill_width=max(pill.measure(Gtk.Orientation.HORIZONTAL, -1)[0]
                               for pill in pills)
                stacked=actual_art_width-16 < pill_width*2+4
                meta_row.set_orientation(Gtk.Orientation.VERTICAL if stacked
                                         else Gtk.Orientation.HORIZONTAL)
                meta_row.set_homogeneous(not stacked)
                for pill in pills:
                    pill.set_halign(Gtk.Align.START if stacked else Gtk.Align.FILL)

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

        tallest_footer=info_height

        for entry in entries:
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
                actual_art_width,
            )

            tallest_footer=max(
                tallest_footer,
                natural,
            )

        uniform_height=(
            actual_art_height
            + tallest_footer
            + 4
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
    def show_operation_status(self,text,complete=False,icon='emblem-ok-symbolic'):
        if self.operation_hide_source:
            try:GLib.source_remove(self.operation_hide_source)
            except Exception:pass
            self.operation_hide_source=0
        self.operation_status.set_text(str(text))
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
                180,
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
                170,
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
                resizable
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


    def _column_name_width_changed(self,column,*_):
        width=column.get_fixed_width()
        if 0<=width<420:
            column.set_fixed_width(420)
        if width>=0:
            column.set_expand(False)


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

        width=max(
            160,
            min(
                360,
                width,
            ),
        )

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

        if accent:
            return accent

        path=(
            game.get('capsule')
            or game.get('poster')
            or game.get('hero')
        )

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
            )

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

        path=(
            game.get('capsule')
            or game.get('poster')
        )

        root._artwork.set_artwork(
            path
        )

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
            halign=Gtk.Align.START,
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
            True
        )
        path.set_ellipsize(
            Pango.EllipsizeMode.END
        )
        path.set_width_chars(
            1
        )
        path.set_max_width_chars(
            1
        )

        root.append(
            source
        )
        root.append(
            path
        )

        root._source=source
        root._path=path

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
            text='Not Installed'
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

        test_status=library_display_test_status(
            game
        )

        root._test.set_text(
            test_status.upper()
        )

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

        root.append(
            nr
        )
        root.append(
            mfg
        )

        root._nr=nr
        root._mfg=mfg

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
                str(mfg_value)
            )
            +'×</span>'
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
            'Open game details'
        )

        root.append(
            primary
        )
        root.append(
            more
        )

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

        # Geometry stays constant between Install / Details / unavailable.
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

        if blocked:
            child=Gtk.Image.new_from_icon_name(
                'action-unavailable-symbolic'
            )
            child.set_pixel_size(
                16
            )

            root._primary.set_child(
                child
            )
            root._primary.set_tooltip_text(
                'Not Installed'
            )

        else:
            child=Gtk.Label(
                label=(
                    'Details'
                    if game.get('installed')
                    else 'Install'
                )
            )

            root._primary.set_child(
                child
            )
            root._primary.set_tooltip_text(
                None
            )

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
            enabled
            and compatible
            and not blocked
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

        if (
            game is None
            or game.get(
                'blocked'
            )
        ):
            return

        if game.get('installed'):
            self.details(game)
            return
        self.launch_action('install', targets=[game])

    def _column_more_clicked(
        self,
        _button,
        root,
    ):
        if root._game is not None:
            self.details(
                root._game
            )


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

    def _column_sync_selection_widgets(self):
        for game_id,root in list(
            self.list_name_cells.items()
        ):
            selected=(
                game_id
                in self.selected_game_ids
            )

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
            self.reset_all.text_label.set_text('Reset Selected Presets' if count else 'Reset Presets')
        for name in ('install_all','sticky_install_all'):
            widget=getattr(self,name,None)
            if widget:widget.text_label.set_text('Install Selected' if count else 'Install Features')
        for name in ('uninstall_all','sticky_remove_all'):
            widget=getattr(self,name,None)
            if widget:widget.text_label.set_text('Restore Selected' if count else 'Restore Original Files')


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

        self.settings['library_view']=key

        self.show_games(
            self.games,
            False,
        )

        if not self.options.demo:
            self.start(
                'Saving library view',
                lambda:library_media.save_settings(
                    self.service.config,
                    self.settings,
                ),
                lambda _:(
                    self.fetch_media()
                    if self.settings['online_art']
                    else None
                ),
            )

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
            ['Off']+[str(x)+'×' for x in range(2,7)]
        )
        multiplier.set_selected(
            self.multiplier_values.index(
                initial['mfg_multiplier']
                if initial.get('mfg_multiplier') is not None
                else self.settings.get('mfg_multiplier',2)
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
        self.reset_all.text_label.set_text('Apply Presets' if self.defaults_changed() else 'Reset Presets')
        if hasattr(self,'profile_group'):self.controls()
    def defaults_applied(self,values):
        self.settings.update(values);self.strength_changed()
    def apply_library_settings(self,*_):
        if self.games and any(g.get('installed') for g in self.games):self.launch_action('reset',not bool(self.selected_game_ids),visual_settings=self.tuning_values(self.tuning_widgets));return
        values=self.tuning_values(self.tuning_widgets)
        if self.options.demo:self.defaults_applied(values);return
        self.start('Saving defaults',lambda:self.service.save_visual_defaults(values),lambda _:(self.defaults_applied(values),self.toast('Defaults saved for new installs.')))
    def filter_changed(self,toggle,key):
        if toggle.get_active():self.filter=key;self.filter_games()
    def close_request(self,*_):
        if self.busy and self.task_kind!='art':self.toast('Please wait for the current file operation to finish.');return True
        if self.busy:self.cancel_art.set()
        return False
    def tick(self):
        if self.busy:self.operation_elapsed.set_text(f'{int(time.monotonic()-self.started)}s')
        return True
    def controls(self):
        enabled=not self.busy or self.task_kind=='art'
        compatible=bool(self.hardware_info and self.hardware_info['ready'])
        self.install_all.set_sensitive(enabled and bool(self.games) and compatible);self.uninstall_all.set_sensitive(enabled and bool(self.games))
        self.reset_all.set_sensitive(enabled and (any(g.get('installed') for g in self.games) or self.defaults_changed()))
        for widget in self.tuning_widgets.values():widget.set_sensitive(enabled)
        for entry in self.cards.values():
            entry['reset'].set_sensitive(enabled)

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
                enabled
                and compatible
                and not bool(
                    game.get(
                        'blocked'
                    )
                )
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
            *self.view_buttons.values(),
        ):
            b.set_sensitive(
                enabled
            )
    def event(self,event):
        if event['kind']=='progress':
            self.show_operation_status(event['label']);self.update_progress_art(event.get('game',''))
            if getattr(self,'job_label',None):
                self.job_caption.set_text(event['label'])
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
        def run_task():
            try:
                with ui.report_to(lambda e:GLib.idle_add(self.event,e)):result=action()
            except Exception as ex:GLib.idle_add(self.finished,None,done,(str(ex),traceback.format_exc()))
            else:GLib.idle_add(self.finished,result,done,None)
        threading.Thread(target=run_task,daemon=False).start()
    def finished(self,result,done,error):
        self.busy=False;self.task_kind='';self.controls()
        if getattr(self,'operation_cancel',None) is not None and self.operation_cancel.is_set() and (not getattr(self,'operation_executing',False) or (error and 'operation_session.Cancelled' in error[1])):
            self.operation_cancel=None
            if self.dialog:self.dialog.force_close()
            self.dialog=None;self.job_label=None;self.show_operation_status('Cancelled · changes undone',True,'process-stop-symbolic')
            previous=getattr(self,'operation_previous',None)
            if previous:self.details(previous)
            return
        if error:
            self.log.append(error[1]);self.show_operation_status('Stopped · details available in Activity',True,'dialog-warning-symbolic');self.error(error[0])
        else:
            done(result);self.show_operation_status('Completed',True)
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

        if resizable:
            dialog=ResizablePanelWindow(
                self,
                title,
                width,
                height,
            )
        else:
            dialog=Adw.Dialog(
                title=title,
                content_width=width,
                content_height=height,
            )

        self.dialog=dialog
        self.job_label=None

        box=Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
        )
        dialog.set_child(box)

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
            16,
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
            'System':'computer-symbolic',
            'Recovery':'document-revert-symbolic',
        }

        for title,items in sections:
            page=Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=16,
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
            scroll.set_child(
                page
            )

            stack.add_titled(
                scroll,
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

    def error(self,message):
        if self.dialog==getattr(self,'progress_dialog',None) and getattr(self,'job_label',None):
            box=self.progress_shell.get_last_child();self.finish_progress(False,str(message),box.get_last_child());return
        d,b,f=self.open_panel('Could Not Finish',width=580,height=300,show_close=False);b.append(label(str(message)));f.append(button('Close',lambda *_:d.close()))
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
            94
            if value < 75
            else 84
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

        click=Gtk.Button(
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
            lambda *_:self.details(game),
        )

        overlay.set_child(
            click
        )
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
        badge=label('Not Installed' if game.get('blocked') else game.get('profile','Ready') if game.get('installed') else 'Ready','cover-badge');badge.set_halign(Gtk.Align.START);badge.set_valign(Gtk.Align.END);margins(badge,7)
        badge_mode={'NR Only':'nr-only','MFG Only':'mfg-only','NR + MFG':'nr-mfg'}.get(game.get('profile'))
        if badge_mode:
            badge=profile_label(badge_mode,badge.get_text());badge.add_css_class('cover-badge');badge.set_halign(Gtk.Align.START);badge.set_valign(Gtk.Align.END);margins(badge,7)
        badge.add_css_class('state-unavailable' if game.get('blocked') else 'state-nr' if game.get('profile')=='NR + MFG' else 'state-mfg' if game.get('installed') else 'state-ready')
        if view!='list':
            overlay.add_overlay(
                badge
            )
            overlay.set_measure_overlay(
                badge,
                False,
            )
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

        # Initial gallery state mirrors the live responsive contract.
        title.set_wrap(
            True
        )
        title.set_wrap_mode(
            Pango.WrapMode.WORD_CHAR
        )
        title.set_lines(
            3
        )
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
            orientation=Gtk.Orientation.VERTICAL,
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

        text.append(Gtk.Box(vexpand=True))
        text.append(
            meta_row
        )

        reset=button('Details',lambda *_:self.details(game));reset.add_css_class('game-details');reset.set_size_request(-1,28)
        reset.set_tooltip_text('Open game details and settings')
        reset.set_sensitive(True);spacer=Gtk.Box(vexpand=False,height_request=8);text.append(spacer);text.append(reset)
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
            'reset':reset,
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
            'test_meta':test_meta,
            'meta_row':meta_row,
            'data':game,
            'size':(width,height),
        };self.cards[game['game']]=entry;self.paint_card(entry)
    def paint_card(self,entry):
        game=entry['data']

        view=self.settings.get(
            'library_view',
            'posters',
        )

        if view in (
            'capsules',
            'list',
        ):
            path=(
                game.get('capsule')
                or game.get('poster')
            )
        else:
            path=(
                game.get('poster')
                or game.get('capsule')
            )
        if path:
            try:
                texture=Gdk.Texture.new_from_filename(path)
                entry['picture'].set_paintable(texture)
                entry['picture'].queue_resize()
                entry['fallback'].set_visible(False)
                if game.get('accent_class'):entry['widget'].remove_css_class(game['accent_class'])
                game['accent_class']=artwork_accent(path,self.settings.get('game_accents',{}).get(game['game']));entry['widget'].add_css_class(game['accent_class'])
            except Exception:entry['fallback'].set_visible(True)
        else:
            entry['picture'].set_paintable(None);entry['fallback'].set_visible(True)
        entry['meta'].set_text(
            str(
                game.get(
                    'source',
                    '',
                )
            ).upper()
        )

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
        # Select All continues to mean the complete unified Library,
        # regardless of filtering, sorting or current view.
        if active:
            self.selected_game_ids={
                game['game']
                for game in self.games
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

        self._column_sync_selection_widgets()
        self._update_selection_summary()


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
        identity.set_margin_start(20)
        identity.set_margin_end(20)

        identity.set_margin_top(16)
        identity.set_margin_bottom(16)

        detail_poster_source=(
            game.get('poster')
            or game.get('capsule')
            or game.get('hero')
        )

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
            game.get('profile')
            if game.get('installed')
            else 'Ready for Features'
        )

        status=label(
            mode_name or 'Ready for Features',
            'cover-badge',
        )
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
        metadata_line.append(test_badge)


        if game.get('description'):
            summary=label(
                game['description'],
                'game-detail-summary',
            )
            summary.set_lines(
                2
            )
            summary.set_max_width_chars(
                54
            )
            summary.set_ellipsize(
                Pango.EllipsizeMode.END
            )
            heading.append(
                summary
            )

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
            'Notes',
            'Appearance',
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
            'Notes':'document-edit-symbolic',
            'Appearance':'applications-graphics-symbolic',
        }

        for name in (
            'Overview',
            'Features',
            'Notes',
            'Appearance',
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
            for index in range(4):
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
        overview=content['Overview']
        info=Adw.PreferencesGroup(title='Game Information');overview.append(info)
        for title,value in [('Library',game.get('library')),('Location',game['game']),('Compatibility',game.get('blocked') or 'Available'),('Developer',game.get('developers')),('Release',game.get('release'))]:
            if value:info.add(row(title,value))
        features=content['Features'];installed=game.get('installed',False)
        tuning,widgets=self.tuning_controls(game)
        presets=Gtk.Expander(label='Presets',expanded=False)
        presets.add_css_class('presets-header')
        presets_body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16)
        presets_body.set_margin_top(16)
        presets.set_child(presets_body)
        features.append(presets)
        presets_body.append(label('Tuning values for this game. Reset Presets applies your library defaults without replacing files.','dim-label'))
        presets_body.append(tuning)
        preset_reset=button('Reset Presets',lambda *_:self.launch_action('reset',targets=[game]))
        preset_reset.set_halign(Gtk.Align.END)
        presets_body.append(preset_reset)
        mode=game.get('feature_mode') or {'NR Only':'nr-only','MFG Only':'mfg-only'}.get(game.get('profile'),'nr-mfg')
        for key,w in widgets.items():w.set_sensitive(installed and not (key=='nr_strength' and mode=='mfg-only') and not (key=='mfg_multiplier' and mode=='nr-only'))
        apply=button(
            'Apply Presets',
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
        presets_body.append(apply)
        def changed(*_):apply.set_sensitive(installed and any(v!=game.get(k) for k,v in self.tuning_values(widgets).items() if widgets[k].get_sensitive()))
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
        notes_page=content['Notes'];record=game.get('test_record',{'status':'Untested','notes':''});choice=safe_dropdown(list(game_notes.STATES));choice.set_selected(list(game_notes.STATES).index(record.get('status','Untested')));choice.set_valign(Gtk.Align.CENTER)
        group=Adw.PreferencesGroup(title='Your Notes');notes_page.append(group);item=row('Test Result','Bench excludes this game from bulk installation and repair.');item.add_suffix(choice);group.add(item)
        notes=Gtk.TextView(
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            height_request=82,
        )
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
                default_height=display_h+190,
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

            clip.append(
                poster
            )

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

                px=min(
                    sw-1,
                    max(
                        0,
                        int(x/width*sw),
                    ),
                )

                py=min(
                    sh-1,
                    max(
                        0,
                        int(y/height*sh),
                    ),
                )

                channels=pix.get_n_channels()
                stride=pix.get_rowstride()
                data=pix.get_pixels()

                off=(
                    py*stride
                    + px*channels
                )

                r=int(data[off])
                g=int(data[off+1])
                b=int(data[off+2])

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

            actions=Gtk.Box(
                spacing=8,
                halign=Gtk.Align.END,
            )

            actions.add_css_class(
                'accent-picker-actions'
            )

            shell.append(
                actions
            )

            cancel=button(
                'Cancel',
                lambda *_:picker.close(),
            )

            def commit_accent(*_):
                set_color(
                    pending['color']
                )
                picker.close()

            done=button(
                'Done',
                commit_accent,
                'suggested-action',
            )

            actions.append(
                cancel
            )

            actions.append(
                done
            )

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

        if (
            game.get('appid')
            and game.get('source')=='Steam'
        ):
            play=button(
                'Play',
                lambda *_:Gio.AppInfo.launch_default_for_uri(
                    'steam://rungameid/'+str(game['appid']),
                    None,
                ),
                'suggested-action',
            )
            play.set_sensitive(
                not self.options.demo
            )
            detail_action_rows['Overview'].append(
                play
            )
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
        b.append(label('Export includes your notes, game paths, package identity and captured logs. Review the ZIP before sharing. Nothing is uploaded.','dim-label'))
        for game in self.games:
            record=game.get('test_record',{});item=row(game['name'],record.get('status','Untested')+(' · test in progress' if record.get('active') else ''))
            item.add_suffix(button('Open',lambda _,g=game:self.details(g)));b.append(item)
        export=button('Export support ZIP',lambda *_:self.start('Exporting report',lambda:game_notes.export(self.service.config,self.games),lambda p:(self.toast('Saved '+str(p)),Gio.AppInfo.launch_default_for_uri(p.parent.as_uri(),None))),'forge-primary');export.set_sensitive(not self.options.demo);f.append(export)
    def launch_action(self,operation,entire=False,targets=None,visual_settings=None,_presets_confirmed=False):
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
        if entire and operation in ('install','repair'):rows=[g for g in rows if g.get('test_record',{}).get('status')!='Bench']
        if operation=='reset':rows=[g for g in rows if g.get('installed')]
        if not rows:self.toast('No eligible games selected.');return
        if operation=='install' and not _presets_confirmed:
            d,b,f=self.open_panel('Install Features',width=760,height=340)
            b.append(label('Presets','title-2'))
            b.append(label('Adjust your presets, or continue with the current values.'))
            tuning,widgets=self.tuning_controls(visual_settings if visual_settings is not None else rows[0] if len(rows)==1 else self.tuning_values(self.tuning_widgets))
            b.append(tuning)
            f.append(button('Cancel',lambda *_:d.close()))
            f.append(button('Continue',lambda *_:self.launch_action(
                operation,entire,targets,self.tuning_values(widgets),True),'suggested-action'))
            return
        applying_strength=operation=='reset' and entire and self.defaults_changed()
        title={'install':'Install Features','repair':'Repair Feature Files','uninstall':'Restore Original Files','reset':'Reset Presets'}[operation]
        if applying_strength:title='Apply Settings to Library'
        elif operation=='reset' and visual_settings is not None:title='Apply Presets'
        self.operation_previous=targets[0] if targets and len(targets)==1 else None

        self.operation_cancel=threading.Event();self.operation_executing=False
        d,b,f=self.open_panel(title,width=580,height=310,show_close=False);d.set_can_close(False)

        self.operation_games=rows
        self.progress_view(b,f'Checking {len(rows)} games…')
        self.add_cancel(f)

        if self.options.live_smoke:
            self.live_smoke_begin(f)
            return

        if self.options.demo:
            preview={'kind':'batch','operation':operation,'title':title,'plans':[],'rows':[{'name':r['name'],'detail':'2 file changes'} for r in rows[:4]],'blocked':[{'name':'Example protected game','reason':'Another graphics tool is installed.'}]}
            self.action_ready(preview,d,b,f,False);return
        mode=self.mode;adopt=self.settings['recognize_previous'];values=self.tuning_values(self.tuning_widgets) if entire and operation=='reset' else visual_settings
        self.start('Preparing '+title.lower(),lambda:self.service.prepare(rows,mode,operation,adopt,visual_settings=values,save_defaults=entire and operation=='reset'),lambda review:self.action_ready(review,d,b,f,entire))
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
        PANEL_VERTICAL_PADDING=56

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
            self.dialog.set_child(self.progress_shell)

            self.dialog.add_css_class('art-progress')

            # ACTIVE operation only: current game's hero backdrop.
            self.job_art=Gtk.Stack(
                transition_type=Gtk.StackTransitionType.CROSSFADE,
                transition_duration=500,
            )

            self.job_pictures=[
                Gtk.Picture(
                    content_fit=Gtk.ContentFit.COVER,
                    can_shrink=True,
                )
                for _ in range(2)
            ]

            for i,picture in enumerate(self.job_pictures):
                self.job_art.add_named(picture,str(i))

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

        hero=(
            game.get('hero')
            or game.get('capsule')
            or game.get('poster')
        )

        if hero:
            try:
                self.job_pictures[
                    self.job_picture_index
                ].set_paintable(
                    Gdk.Texture.new_from_filename(hero)
                )

                self.job_art.set_visible_child_name(
                    str(self.job_picture_index)
                )
            except Exception:
                pass

        if game.get('poster'):
            try:
                self.poster_images[
                    self.job_picture_index
                ].set_paintable(
                    Gdk.Texture.new_from_filename(
                        game['poster']
                    )
                )

                self.job_poster.set_visible_child_name(
                    str(self.job_picture_index)
                )
            except Exception:
                pass

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

        if start==target:
            dialog.set_content_width(target)
            return

        started=time.monotonic()

        def tick():
            if self.dialog is not dialog:
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

        GLib.timeout_add(16,tick)

    def animate_dialog_height(self,dialog,target,duration=240):
        if dialog is None or self.dialog is not dialog:return
        source=getattr(self,'detail_resize_source',0)
        if source:
            try:GLib.source_remove(source)
            except Exception:pass
            self.detail_resize_source=0
        try:start=int(dialog.get_content_height())
        except Exception:start=int(target)
        target=max(1,int(target))
        if start==target:
            dialog.set_content_height(target);return
        started=time.monotonic()
        def tick():
            if self.dialog is not dialog:
                self.detail_resize_source=0
                return False
            t=min(1.0,(time.monotonic()-started)*1000.0/max(1,duration))
            eased=1.0-(1.0-t)**3
            dialog.set_content_height(round(start+(target-start)*eased))
            if t>=1.0:self.detail_resize_source=0
            return t<1.0
        self.detail_resize_source=GLib.timeout_add(16,tick)


    def finish_progress(self,success,message,footer):
        self.dialog.set_can_close(True)
        clear(footer)
        footer.set_visible(False)
        self.progress_cancel_box=None
        body=self.progress_body
        clear(body)
        backdrop=Gtk.Box()
        backdrop.add_css_class('done-fallback')
        self.progress_shell.set_child(backdrop)
        self.progress_shade.set_visible(False)
        self.progress_panel.add_css_class('done')
        line=Gtk.Box(spacing=24,valign=Gtk.Align.CENTER,vexpand=True)
        body.append(line)
        icon=Gtk.Image.new_from_icon_name('emblem-ok-symbolic' if success else 'dialog-warning-symbolic')
        icon.set_pixel_size(80)
        icon.add_css_class('operation-complete' if success else 'error')
        line.append(icon)
        text=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12,hexpand=True,valign=Gtk.Align.CENTER)
        text.append(label('Done' if success else 'Could not finish','title-1'))
        text.append(label(message))
        line.append(text)
        done=button('Done',lambda *_:(self.dialog.close(),self.scan()),'suggested-action')
        done.set_valign(Gtk.Align.END)
        line.append(done)
        self.dialog.set_content_width(500)
        self.dialog.set_content_height(180)
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

    def action_ready(self,review,d,b,f,automatic=False):
        self.review=review
        clear(b)
        clear(f)

        self.progress_cancel_box=None
        f.set_visible(True)

        b.add_css_class('panel-body')
        self.job_label=None
        d.set_can_close(True)

        if getattr(self,'operation_cancel',None) is not None:
            self.add_cancel(f)
        g=Adw.PreferencesGroup(title=f"Ready · {len(review['rows'])}");b.append(g)
        for item in review['rows']:g.add(row(item['name'],item['detail']))
        if review['blocked']:
            skipped=Adw.PreferencesGroup(title=f"Skipped · {len(review['blocked'])}");b.append(skipped)
            for item in review['blocked']:skipped.add(row(item['name'],item['reason']))
        if not review['rows']:b.append(label('No file changes can be applied.'));f.append(button('Close',lambda *_:d.close()));return
        apply=button('Apply Settings' if review.get('operation')=='reset' else 'Restore Original Files' if review.get('operation')=='uninstall' else 'Apply to Ready Games',lambda *_:self.execute(review,d,b,f),'forge-primary');apply.set_sensitive(not self.options.demo);f.append(apply)
        if self.options.demo:b.append(label('Preview mode · all file changes are disabled.','dim-label'))
        elif automatic:self.execute(review,d,b,f)
    def execute(self,review,d,b,f):
        if self.options.demo:return
        clear(f);d.set_can_close(False);self.progress_view(b,'Applying changes…')
        if review.get('kind')=='engine':
            self.operation_executing=True;review['cancel_event']=self.operation_cancel;self.add_cancel(f)
            # Close the cancellation window on the GTK thread before the engine's
            # final cancellation check. A late click must never promise an undo
            # after the feature transaction has already committed.
            def finalizing():
                ready=threading.Event()
                def finish_ui():
                    try:
                        target=self.progress_cancel_box
                        if target is not None:
                            target.set_sensitive(False)
                        if not self.operation_cancel.is_set() and self.job_label:
                            self.job_caption.set_text('Finishing…')
                    finally:
                        ready.set()
                    return False
                GLib.idle_add(finish_ui)
                ready.wait()
            review['on_finalizing']=finalizing
        self.start('Applying changes',lambda:self.service.execute(review),lambda path:self.completed(path,d,b,f))
    def completed(self,path,d,b,f):
        self.operation_cancel=None
        if self.review and self.review.get('save_defaults'):self.defaults_applied(self.review['save_defaults'])
        count=len(self.review.get('rows',[])) if self.review else 0
        self.log.append('Saved report: '+str(path))
        self.finish_progress(True,f'{count} game'+('s' if count!=1 else '')+' updated.',f)
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
        provider_keys=['y4my','dlss-unlocked'];provider=safe_combo_row(title='Provider',model=Gtk.StringList.new(['y4my Multipass','DLSS-Unlocked']),selected=provider_keys.index(self.settings.get('runtime_provider','y4my')));graphics.add(provider)
        nr_path=Adw.EntryRow(title='Local NR DLL for y4my');nr_path.set_text(self.settings.get('nr_runtime',''));graphics.add(nr_path)
        defaults=Adw.PreferencesGroup(title='Installation')
        modes=['nr-only','mfg-only','nr-mfg'];profile=safe_combo_row(title='Default Mode',model=Gtk.StringList.new(['NR Only','MFG Only','NR + MFG']),selected=modes.index(self.settings.get('default_profile','mfg-only')));defaults.add(profile)
        adopt=Adw.SwitchRow(title='Recognize Existing Features',subtitle='Allow updates to compatible installations from other tools.',active=self.settings['recognize_previous']);defaults.add(adopt)
        appearance=Adw.PreferencesGroup(title='Library Appearance')
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
            self.settings['library_view']=key

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

        appearance.add(
            layout_row
        )

        settings_saved={'value':False}

        def restore_library_preview(*_):
            if settings_saved['value']:
                return

            current_view=self.settings.get(
                'library_view',
                'posters',
            )

            if current_view!=original_library_view:
                self.settings['library_view']=(
                    original_library_view
                )

                self.show_games(
                    self.games,
                    False,
                )

        d.connect(
            'close-request',
            lambda *_:(
                restore_library_preview(),
                False,
            )[1],
        )

        dark=Adw.SwitchRow(title='Dark Appearance',active=self.settings['dark']);appearance.add(dark)
        artwork=Adw.PreferencesGroup(title='Artwork',description='Your Steam poster, capsule, and hero images take priority.')
        art=Adw.SwitchRow(title='Download Missing Artwork',subtitle='Use SteamGridDB and Steam when local images are unavailable.',active=self.settings['online_art']);artwork.add(art)
        metadata=Adw.SwitchRow(title='Download Game Information',subtitle='Descriptions, developers, and release dates from Steam.',active=self.settings['steam_metadata']);artwork.add(metadata)
        refresh=row('Refresh Artwork','Cached images remain available offline.');refresh_button=button('Refresh',lambda *_:self.fetch_media(True));refresh_button.set_valign(Gtk.Align.CENTER);refresh.add_suffix(refresh_button);artwork.add(refresh)
        timeout=Gtk.SpinButton.new_with_range(5,30,1);timeout.set_value(self.settings.get('network_timeout',10));timeout.set_valign(Gtk.Align.CENTER);item=row('Download Timeout','Seconds per request');item.add_suffix(timeout);artwork.add(item)
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
        self.organize_pages(b,[('Graphics',[graphics,defaults]),('Library',[appearance,artwork]),('System',[system,app]),('Recovery',[recovery])])
        def save(*_):
            selected_provider=provider_keys[provider.get_selected()];selected_mode=modes[profile.get_selected()]
            if selected_provider=='y4my' and selected_mode=='nr-only':self.toast('NR Only requires DLSS-Unlocked.');return
            settings_saved['value']=True
            self.settings.update(runtime_provider=selected_provider,nr_runtime=nr_path.get_text().strip(),default_profile=selected_mode,library_view=pending_library_view['value'],dark=dark.get_active(),online_art=art.get_active(),steam_metadata=metadata.get_active(),network_timeout=timeout.get_value_as_int(),recognize_previous=adopt.get_active())
            self.nr_only.set_enabled(selected_provider=='dlss-unlocked')
            self.profile_group.set_active_name(selected_mode)
            Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK if self.settings['dark'] else Adw.ColorScheme.FORCE_LIGHT)
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
            'emblem-ok-symbolic'
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
        d,b,f=self.open_panel('Undo previous changes');g=Adw.PreferencesGroup(title='Recorded changes');b.append(g)
        for record in records:
            item=row(record['name'],record['detail']);item.add_suffix(button('Review',lambda _,r=record:self.start('Checking restore',lambda:self.service.review_recovery(r),lambda review:self.action_ready(review,d,b,f))));g.add(item)
        if not records:b.append(label('No recorded changes yet.'))
    def show_cleanup(self):
        if self.options.demo:return
        d,b,f=self.open_panel('Remove old NR files');b.append(label('Checking global cleanup candidates…'))
        self.start('Scanning old NR files',self.service.review_cleanup,lambda review:self.action_ready(review,d,b,f))
    def capture(self,name):
        """Capture a rendered GTK widget without assuming a node exists."""

        widget=self

        if (
            name in (
                'gnome-game-settings.png',
                'gnome-settings.png',
            )
            and isinstance(
                self.dialog,
                ResizablePanelWindow,
            )
        ):
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
                in ('Reset Presets','Reset Selected Presets')
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
                slots=self.flow.get_max_children_per_line()
                assert (
                    self.settings.get(
                        'library_view'
                    )
                    == view
                )

                self.update_library_spacing()

                assert (
                    self.flow.get_min_children_per_line()
                    == slots
                )

                assert (
                    self.flow.get_max_children_per_line()
                    == slots
                )

                assert (
                    self.flow.get_margin_start()
                    == 16
                )

                assert (
                    self.flow.get_margin_end()
                    >= 16
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
                    widget.set_selected(0)
                else:
                    widget.set_value(0)

                assert (
                    self.reset_all.text_label.get_text()
                    == 'Apply Presets'
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
                    in ('Reset Presets','Reset Selected Presets')
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

    def smoke_library_ready(self):
        try:
            self.capture('gnome-library.png')
            self.search.set_text('Cyberpunk');self.select_all(True);assert all(e['check'].get_active() for e in self.cards.values())
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
        try:self.capture('gnome-game-settings.png');self.show_settings();GLib.timeout_add(700,self.smoke_settings)
        except Exception:traceback.print_exc();self.get_application().exit_code=1;self.get_application().quit()
        return False
    def smoke_settings(self):
        try:
            self.capture('gnome-settings.png')

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
        try:self.capture('gnome-progress.png');self.finish_progress(True,'3 games updated.',self.progress_shell.get_last_child().get_last_child());GLib.timeout_add(300,self.smoke_complete);return False
        except Exception:traceback.print_exc();self.get_application().exit_code=1
        self.get_application().quit();return False
    def smoke_complete(self):
        try:self.capture('gnome-complete.png');print('PASS: controls, tabs, settings, progress and completion; demo writes disabled',flush=True)
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
