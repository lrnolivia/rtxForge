"""Action wording shared by the native Desktop and Game Mode views."""
INSTALL = 'Install Features'
RESTORE = 'Restore Original Files'
UPDATE_DLSS = 'Update DLSS'
REPAIR = 'Repair Feature Files'
# On Linux, games installed with rtxForge on Windows: Install sets them up for Proton
# without touching the game folder or the Windows install, and Restore undoes only that.
ADAPT = 'Adapt to Linux'
REMOVE_ADAPT = 'Remove Linux Setup'


def library(selected_count=0, adapt=False, pending=0):
    """Install, Restore and Update DLSS; adapt when every game they act on was installed on Windows.

    With nothing selected, games installed with rtxForge on Windows that still need
    Linux setup take over Install as "Adapt to Linux (N)", whatever the filter."""
    install, restore = (ADAPT, REMOVE_ADAPT) if adapt else (INSTALL, RESTORE)
    if selected_count:
        install, restore = ((f'Adapt Selected ({selected_count})', f'Remove Linux Setup ({selected_count})') if adapt else
                            (f'Install Selected ({selected_count})', f'Restore Selected ({selected_count})'))
    elif pending:
        install = f'{ADAPT} ({pending})'
    return install, restore, UPDATE_DLSS


def game(windows_install=False):
    """One game's Install and Restore labels."""
    return (ADAPT, REMOVE_ADAPT) if windows_install else (INSTALL, RESTORE)


# Package names in reviews and the Game Mode header, as on Windows (OperationDialog, GameModeView.ProviderName).
PROVIDERS = {'skynizz': 'Skynizz', 'feeder': 'Feeder NR', 'dlss-unlocked': 'DLSS-Unlocked', 'custom': 'Custom package',
             'vulkan-native': 'Vulkan NR + Universal MFG'}


def provider_name(provider, short=True):
    """A runtime provider id as people read it; y4my is "y4my Multipass" where there is room."""
    return PROVIDERS.get(provider) or ('y4my' if short else 'y4my Multipass')
