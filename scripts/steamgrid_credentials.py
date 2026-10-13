"""SteamGridDB credentials in the desktop Secret Service; never in app settings.
Call these functions from a worker thread. No plaintext fallback is permitted.
"""
import os
import threading

class CredentialError(ValueError):
    pass

def normalize_key(value):
    key=str(value or '').strip()
    if not 16 <= len(key) <= 512 or not key.isascii() or any(c.isspace() for c in key):
        raise CredentialError('Paste the API key from your SteamGridDB API settings.')
    return key

def _backend():
    try:
        import gi
        gi.require_version('Secret','1')
        from gi.repository import Secret, Gio
        schema=Secret.Schema.new('io.github.lrnolivia.RTXForge.SteamGridDB',
            Secret.SchemaFlags.NONE, {'service':Secret.SchemaAttributeType.STRING})
        return Secret,Gio,schema
    except (ImportError,ValueError):
        raise CredentialError('Secure storage is unavailable. Open Desktop Mode and enable the system password wallet (Secret Service), then try again.') from None

def _invoke(method,*args,cancel=None):
    Secret,Gio,schema=_backend()
    token=cancel or Gio.Cancellable()
    timer=threading.Timer(20,token.cancel);timer.daemon=True;timer.start()
    try:
        if token.is_cancelled():raise CredentialError('Connection cancelled.')
        return getattr(Secret,method)(schema,{'service':'steamgriddb'},*args,token)
    except CredentialError:raise
    except Exception:
        raise CredentialError('Could not access the system password wallet. Open Desktop Mode, unlock the wallet, and try again.') from None
    finally:timer.cancel()

def load_key(cancel=None):
    external=os.environ.get('STEAMGRIDDB_API_KEY','').strip()
    try:key=_invoke('password_lookup_sync',cancel=cancel)
    except CredentialError:
        if external:return normalize_key(external)
        raise
    if key:return normalize_key(key)
    # Existing developer setups remain supported without writing the variable.
    return normalize_key(external) if external else ''

def save_key(key,cancel=None):
    key=normalize_key(key)
    # The default collection persists across Desktop and Game Mode sessions.
    if not _invoke('password_store_sync','default','rtxForge · SteamGridDB',key,cancel=cancel):
        raise CredentialError('The password wallet did not save the connection. Unlock it and try again.')

def clear_key(cancel=None):
    _invoke('password_clear_sync',cancel=cancel)
    return bool(os.environ.get('STEAMGRIDDB_API_KEY','').strip())
