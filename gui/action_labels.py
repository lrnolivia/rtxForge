"""Action wording shared by the native Desktop and Game Mode views."""
INSTALL = 'Install Features'
RESTORE = 'Restore Original Files'
UPDATE_DLSS = 'Update DLSS'
REPAIR = 'Repair Feature Files'


def library(selected_count=0):
    return (f'Install Selected ({selected_count})' if selected_count else INSTALL,
            f'Restore Selected ({selected_count})' if selected_count else RESTORE,
            UPDATE_DLSS)


# Package names in reviews and the Game Mode header, as on Windows (OperationDialog, GameModeView.ProviderName).
PROVIDERS = {'skynizz': 'Skynizz', 'feeder': 'Feeder NR', 'dlss-unlocked': 'DLSS-Unlocked', 'custom': 'Custom package',
             'vulkan-native': 'Vulkan NR + Universal MFG'}


def provider_name(provider, short=True):
    """A runtime provider id as people read it; y4my is "y4my Multipass" where there is room."""
    return PROVIDERS.get(provider) or ('y4my' if short else 'y4my Multipass')
