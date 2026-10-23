"""Responsive breakpoints shared with the Windows build.

Values mirror windows/RtxForge.Windows (Controls/PageMargins.cs,
Views/LibraryPage.xaml.cs, Views/GamePage.xaml.cs, MainWindow navigation).
Widths are the page (content) width unless noted as window width.
"""

MAX_COLUMN = 1600          # PageMargins.MaxColumn
PHONE = 640                # PageMargins.PhoneWidth: single-column phone layouts below this

# Navigation pane (window width): WinUI NavigationView Auto thresholds.
NAV_EXPANDED = 1008        # pane open at or above
NAV_MINIMAL = 641          # below this the pane is hidden behind the menu button

# Library (LibraryPage.ApplyLayout)
LIBRARY_LABELS = 1180      # toolbar commands keep their labels
LIBRARY_ONE_ROW = 1000     # one toolbar row; below: search beside title, tools beneath
LIBRARY_HERO_NARROW = 1100 # dashboard actions move under the hero text
LIST_LOCATION = 1060       # list view hides Location below this list width
LIST_FEATURES = 860        # list view hides Features below this list width

# Game Details (GamePage.ApplyLayout)
DETAILS_NARROW = 980       # hero actions drop to their own row


def side_margin(width):
    """3% of the width (16-56 px), widening to keep a centered column of at most MAX_COLUMN."""
    return round(max(min(max(width * 0.03, 16), 56), (width - MAX_COLUMN) / 2))


def is_phone(width):
    return 0 < width < PHONE


def library_layout(width):
    """0 = one toolbar row, 1 = two rows, 2 = phone."""
    return 2 if width < PHONE else 1 if width < LIBRARY_ONE_ROW else 0


def library_labels(width):
    return width >= LIBRARY_LABELS


def list_density(list_width):
    """0 = all columns, 1 = without Location, 2 = without Location and Features."""
    return 2 if list_width < LIST_FEATURES else 1 if list_width < LIST_LOCATION else 0


def details_narrow(width):
    return width < DETAILS_NARROW


def hero_height(width):
    """Expanded Game Details hero: 38% of the page width, 360-620 px."""
    return round(min(max(width * 0.38, 360), 620))


def nav_mode(window_width):
    """'expanded', 'compact' or 'minimal' for the navigation pane."""
    return 'expanded' if window_width >= NAV_EXPANDED else 'compact' if window_width >= NAV_MINIMAL else 'minimal'
