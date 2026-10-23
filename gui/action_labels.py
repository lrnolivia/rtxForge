"""Action wording shared by the native Desktop and Game Mode views."""
INSTALL = 'Install Features'
RESTORE = 'Restore Original Files'
UPDATE_DLSS = 'Update DLSS'
REPAIR = 'Repair Feature Files'


def library(selected_count=0):
    return (f'Install Selected ({selected_count})' if selected_count else INSTALL,
            f'Restore Selected ({selected_count})' if selected_count else RESTORE,
            UPDATE_DLSS)
