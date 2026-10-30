using Microsoft.UI.Dispatching;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml.Controls;
using RtxForge.Windows.Services;

namespace RtxForge.Windows;

public sealed partial class MainWindow
{
    DispatcherQueueTimer? updateTimer;
    bool checkingUpdate, applyingUpdate, updateCloseAllowed, windowClosed;
    bool updateReady;
    string updateStatus = "Checks automatically and installs when you close rtxForge.";
    public string UpdateStatus => InstalledApp ? updateStatus : "Portable app: download and extract the latest ZIP.";
    public string UpdateAction => !InstalledApp ? "Get latest ZIP" : updateReady ? "Restart to update" : "Check for updates";
    public string AutomaticUpdateDescription => InstalledApp
        ? "Download in the background and install when you close. Close games before installation."
        : "Available in installed copies. Portable copies use the latest ZIP.";
    public bool InstalledApp => File.Exists(Path.Combine(AppContext.BaseDirectory, "unins000.exe"));

    void InitializeUpdates()
    {
        if (Service.IsPreview || !InstalledApp) return;
        AppWindow.Closing += OnUpdateClosing;
        Closed += (_, _) => { windowClosed = true; updateTimer?.Stop(); };
        updateTimer = DispatcherQueue.CreateTimer();
        updateTimer.Interval = TimeSpan.FromSeconds(30);
        updateTimer.Tick += async (_, _) =>
        {
            updateTimer.Interval = TimeSpan.FromHours(6);
            if (!Settings.AutoUpdate || updateReady) return;
            if (Busy || LibraryRefreshing) { updateTimer.Interval = TimeSpan.FromMinutes(1); return; }
            await DownloadAppUpdateAsync(false);
        };
        updateTimer.Start();
    }

    async Task DownloadAppUpdateAsync(bool manual)
    {
        if (checkingUpdate || applyingUpdate) return;
        if (Busy || LibraryRefreshing) { if (manual) ShowToast("Finish the current operation before updating."); return; }
        checkingUpdate = true;
        try
        {
            updateStatus = "Checking and downloading updates…";
            if (manual) ShowToast(updateStatus);
            var result = await Service.StageAppUpdateAsync();
            if (windowClosed) return;
            updateReady = result.Path is not null;
            updateStatus = updateReady ? "Update ready. Installs when you close, or restart now." : result.Message;
            if (manual || updateReady || result.Message.StartsWith("Previous update failed")) ShowToast(updateStatus);
            if (updateReady)
            {
                var restart = new Button { Content = "Restart to update" };
                restart.Click += async (_, _) => await ApplyAppUpdateAsync(true);
                Toast.ActionButton = restart;
                toastTimer?.Stop();
            }
            SettingsChanged?.Invoke();
        }
        catch (Exception error) when (error is InvalidOperationException or IOException)
        {
            updateStatus = "Update check failed. Try again when you’re online.";
            AddLog("App update: " + error.Message);
            if (manual) ShowToast(updateStatus + " " + error.Message);
            if (updateTimer is not null) updateTimer.Interval = TimeSpan.FromMinutes(30);
        }
        finally { checkingUpdate = false; }
    }

    async void OnUpdateClosing(AppWindow sender, AppWindowClosingEventArgs args)
    {
        if (updateCloseAllowed) return;
        if (Busy || applyingUpdate) { args.Cancel = true; ShowToast("Finish the current operation before closing."); return; }
        if (LibraryRefreshing) return;
        if (!Settings.AutoUpdate || !updateReady) return;
        args.Cancel = true;
        await ApplyAppUpdateAsync(false);
    }

    async Task ApplyAppUpdateAsync(bool restart)
    {
        if (Busy || applyingUpdate || LibraryRefreshing) { ShowToast("Finish the current operation before updating."); return; }
        applyingUpdate = true;
        Busy = true;
        try
        {
            await Service.ApplyAppUpdateAsync(Games, restart, InGameMode);
            updateCloseAllowed = true;
            Close();
        }
        catch (Exception error) when (error is InvalidOperationException or IOException or System.ComponentModel.Win32Exception)
        {
            AddLog("Update postponed: " + error.Message);
            ShowToast("Update postponed: " + error.Message);
            // A running game must not prevent the user from closing the manager.
            if (!restart) { updateCloseAllowed = true; Close(); }
        }
        finally { applyingUpdate = false; Busy = false; }
    }
}
