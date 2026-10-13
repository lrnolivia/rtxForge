"""New native navigation around the canonical Classic Library widget.

No duplicate gallery, selection model, artwork scaler, or operation engine.
"""
from gi.repository import Adw, Gtk


def new_shell(owner, library):
    split=Adw.NavigationSplitView()
    split.set_min_sidebar_width(220);split.set_max_sidebar_width(260)
    sidebar=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=28)
    for side in ('top','bottom','start','end'):getattr(sidebar,'set_margin_'+side)(24)
    sidebar.set_margin_top(32)
    identity=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
    identity.append(Gtk.Image(icon_name='io.github.lrnolivia.RTXForge',pixel_size=56,halign=Gtk.Align.START))
    brand=Gtk.Label(label='rtxForge',xalign=0);brand.add_css_class('title-1');identity.append(brand);sidebar.append(identity)
    nav=Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE);nav.add_css_class('navigation-sidebar');sidebar.append(nav)
    stack=Gtk.Stack(hexpand=True,vexpand=True,transition_type=Gtk.StackTransitionType.CROSSFADE,transition_duration=160)
    stack.add_named(library,'library')
    home=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=24)
    for side in ('top','bottom','start','end'):getattr(home,'set_margin_'+side)(32)
    heading=Gtk.Label(label='Ready when you are',xalign=0);heading.add_css_class('title-1');home.append(heading)
    summary=Gtk.Label(label=f'{len(owner.games)} games in your library',xalign=0);summary.add_css_class('dim-label');home.append(summary)
    actions=Adw.PreferencesGroup(title='Get straight to it')
    for title,subtitle,caption,callback in [
        ('Game Library','Your games, selection and actions, just as you left them.','Open',lambda *_:navigate('library')),
        ('Packages','Choose a supported runtime or inspect a custom package.','Choose',owner.show_packages),
        ('Previous Changes','Review recorded changes and restore original files.','Review',owner.show_undo)]:
        row=Adw.ActionRow(title=title,subtitle=subtitle)
        button=owner.make_action_button(caption,callback);row.add_suffix(button);actions.add(row)
    home.append(actions)
    startup=Adw.PreferencesGroup(title='Make it yours')
    choice=Adw.ComboRow(title='Open to',model=Gtk.StringList.new(['Game Library','Home']),selected=1 if owner.settings.get('start_page')=='home' else 0)
    choice.connect('notify::selected',lambda row,*_:owner.set_start_page('home' if row.get_selected() else 'library'));startup.add(choice);home.append(startup)
    scroll=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER);scroll.set_child(home)
    toolbar=Adw.ToolbarView();toolbar.add_top_bar(Adw.HeaderBar());toolbar.set_content(scroll);stack.add_named(toolbar,'home')
    rows={}
    for key,title,icon in [('home','Home','go-home-symbolic'),('library','Game Library','view-grid-symbolic'),('forge','Forge','applications-engineering-symbolic'),('settings','Settings','emblem-system-symbolic'),('recovery','Recovery','document-revert-symbolic')]:
        row=Gtk.ListBoxRow();row.page=key;row.set_margin_bottom(6);content=Gtk.Box(spacing=14)
        for side in ('top','bottom','start','end'):getattr(content,'set_margin_'+side)(12)
        content.set_margin_top(16);content.set_margin_bottom(16)
        content.append(Gtk.Image(icon_name=icon));content.append(Gtk.Label(label=title,xalign=0));row.set_child(content);nav.append(row);rows[key]=row
    def navigate(page):
        nav.select_row(rows[page])
    def selected(_,row):
        if not row:return
        if row.page in ('library','home'):
            summary.set_text(f'{len(owner.games)} games in your library');stack.set_visible_child_name(row.page)
        else:
            {'forge':owner.show_packages,'settings':owner.show_settings,'recovery':owner.show_undo}[row.page]()
            nav.select_row(rows[stack.get_visible_child_name()])
    nav.connect('row-selected',selected)
    split.set_sidebar(Adw.NavigationPage.new(sidebar,'Navigation'))
    split.set_content(Adw.NavigationPage.new(stack,'rtxForge'))
    navigate('home' if owner.settings.get('start_page')=='home' else 'library')
    return split,stack
