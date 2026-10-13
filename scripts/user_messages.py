"""Human-facing messages. Original diagnostics stay available in details/logs."""
import re

# Match causes we actually know; never guess what an unknown failure changed.
ERRORS=(
    (('no terminal-engine baseline','no baseline'), "There’s no saved backup for this game. If you installed features with an older rtxForge version, open Previous Changes to look for its backup."),
    (('executable selection changed',), "The game’s launch file has changed. Refresh your library, then try again."),
    (('game or baseline changed','changed since preview'), "This game changed after the review was prepared. Close this review and try again to check its current files."),
    (('hash mismatch','digest mismatch','checksum'), "The downloaded file didn’t pass its safety check. Download it again, then retry."),
    (('provider changed during extraction',), "The feature package changed while it was being opened. Select the package again and retry."),
    (('unsupported','invalid package'), "This package isn’t supported. Choose a compatible package in Settings → Graphics, then try again."),
    (('privileged backup',), "This backup needs administrator access. Restore it using rtxForge’s terminal tool."),
    (('proxy dll','another graphics tool'), "Another graphics tool already uses a file this change needs. Review that tool’s installation before trying again."),
    (('linked installer input','symlink'), "A required file points to another location. Choose the original file or folder, then try again."),
    (('duplicate or overlapping',), "Some selected games share the same folder. Select one entry for each game, then try again."),
    (('close steam',), "Close Steam, then try again so rtxForge can safely update your launch settings."),
    (('close running games',), "Close the running games, then try again. Your recovery files are still available."),
    (('no steam launch settings','no unique steam shortcut'), "rtxForge couldn’t find this game’s Steam entry. Add it to Steam or check its shortcut, then refresh your library."),
    (('uninstall before changing',), "Restore this game’s original files before switching its feature package or mode."),
    (('launch settings need attention',), "The feature files were installed, but the launch settings couldn’t be updated. Open Technical details to see what needs attention."),
    (('permission denied','not writable','read-only file system'), "rtxForge can’t write to this folder. Check its permissions and make sure the drive allows changes, then retry."),
    (('no space left','disk full'), "There isn’t enough free space. Free up some space on this drive, then retry."),
    (('timed out','connection','network','urlopen','http error'), "rtxForge couldn’t complete the download. Check your connection and try again."),
    (('choose a custom package',), "Choose your custom package in Settings → Graphics before continuing."),
    (('cancelled','canceled'), "The operation was cancelled. Open Technical details to check whether any recovery step is needed."),
)

def friendly_error(message):
    raw=str(message).strip();lower=raw.lower()
    for needles,description in ERRORS:
        if any(needle in lower for needle in needles):return description
    return 'rtxForge couldn’t complete this step. Try again. If it keeps happening, open Technical details for more information.'


def friendly_status(message):
    text=str(message)
    for pattern,replacement in (
        (r'(?i)terminal-engine baseline','saved backup'),
        (r'(?i)\bbaseline\b','saved backup'),
        (r'(?i)\bproxy DLLs?\b','graphics file'),
        (r'(?i)\bmanaged files\b','feature files'),
        (r'(?i)\bvalidating (?:hash|digest)\b','Checking the download'),
        (r'(?i)\bProton overrides\b','game launch settings'),
    ):text=re.sub(pattern,replacement,text)
    return text
