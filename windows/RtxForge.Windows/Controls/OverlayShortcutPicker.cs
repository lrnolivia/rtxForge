using System.Runtime.InteropServices;
using Microsoft.UI.Input;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;
using Windows.System;
using Windows.UI.Core;

namespace RtxForge.Windows.Controls;

/// <summary>Records only focused key events; no keyboard hook or background polling.</summary>
public sealed class OverlayShortcutPicker : UserControl
{
    readonly Button record = new() { HorizontalAlignment = HorizontalAlignment.Stretch };
    readonly TextBlock hint = new() { FontSize = 12, TextWrapping = TextWrapping.Wrap, Opacity = .8 };
    readonly Microsoft.UI.Dispatching.DispatcherQueueTimer timeout;
    public Func<string, bool>? SaveBinding { get; set; }
    string binding;
    bool recording, arming;
    int revision;

    public OverlayShortcutPicker(string current)
    {
        binding = current;
        var stack = new StackPanel { Spacing = 8 }; Content = stack;
        stack.Children.Add(new TextBlock { Text = "rtxForge shortcut" });
        var row = new Grid { ColumnSpacing = 8 };
        row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        var reset = new Button { Content = "Reset" };
        var disable = new Button { Content = "Disable" };
        ToolTipService.SetToolTip(reset, "Use End (default)");
        AutomationProperties.SetName(record, "Change rtxForge shortcut");
        AutomationProperties.SetName(reset, "Reset rtxForge shortcut to End");
        AutomationProperties.SetName(disable, "Disable rtxForge shortcut");
        row.Children.Add(record); Grid.SetColumn(reset, 1); row.Children.Add(reset);
        Grid.SetColumn(disable, 2); row.Children.Add(disable);
        stack.Children.Add(row); stack.Children.Add(hint);
        timeout = DispatcherQueue.CreateTimer();
        timeout.IsRepeating = false; timeout.Interval = TimeSpan.FromSeconds(20);
        timeout.Tick += (_, _) => Cancel("Recording timed out. Your shortcut is unchanged.");
        record.Click += async (_, _) => { if (!recording && !arming) await BeginAsync(); };
        record.PreviewKeyDown += Capture;
        record.LostFocus += (_, _) => { if (recording || arming) Cancel(); };
        Unloaded += (_, _) => { if (recording || arming) Cancel(); };
        IsEnabledChanged += (_, _) => { if (!IsEnabled && (recording || arming)) Cancel(); };
        reset.Click += (_, _) => Commit(OverlayShortcut.Default);
        disable.Click += (_, _) => Commit(OverlayShortcut.Disabled);
        ShowBinding();
    }

    void ShowBinding()
    {
        record.Content = binding == OverlayShortcut.Disabled ? "Set shortcut" : binding + " · Change";
        hint.Text = "Default: End. Choose a key or combination. Insert stays with OptiScaler.";
    }

    async Task BeginAsync()
    {
        var expected = ++revision; arming = true;
        record.Content = "Preparing…";
        try
        {
            // The current shortcut must not hide the panel while it is being rebound.
            await OverlayHelper.CommandAsync("suspend-shortcut", start: false);
            if (expected != revision) { await OverlayHelper.CommandAsync("reload", start: false); return; }
            arming = false; recording = true;
            record.Content = "Press a shortcut…"; hint.Text = "Press a key, with optional Ctrl, Alt or Shift. Esc cancels.";
            record.Focus(FocusState.Programmatic); timeout.Start();
        }
        catch (Exception error) { Cancel(error.Message); }
    }

    static bool Down(VirtualKey key) => (InputKeyboardSource.GetKeyStateForCurrentThread(key) & CoreVirtualKeyStates.Down) != 0;

    void Capture(object sender, KeyRoutedEventArgs e)
    {
        if (!recording && !arming) return;
        e.Handled = true;
        if (e.Key == VirtualKey.Escape) { Cancel("Cancelled. Your shortcut is unchanged."); return; }
        if (e.Key == VirtualKey.Tab) { Cancel(); e.Handled = false; return; }
        if (!recording || OverlayShortcut.IsModifier((uint)e.Key)) return;
        uint modifiers = (Down(VirtualKey.Control) ? 2u : 0) | (Down(VirtualKey.Menu) ? 1u : 0)
            | (Down(VirtualKey.Shift) ? 4u : 0) | (Down(VirtualKey.LeftWindows) || Down(VirtualKey.RightWindows) ? 8u : 0);
        if (OverlayShortcut.TryCreate((uint)e.Key, modifiers, out var value, out var error)) Commit(value);
        else hint.Text = error;
    }

    void Commit(string value)
    {
        if (!OverlayShortcut.TryParse(value, out var normalized, out var shortcut, out var error)) { hint.Text = error; return; }
        var fresh = ForgeSettings.Load();
        if (normalized != OverlayShortcut.Disabled && normalized == fresh.OptiScalerHotkey)
        { hint.Text = "OptiScaler uses that shortcut. Choose a different key for rtxForge."; return; }
        // Probe without taking focus or sending a key. Preserve the old binding on failure.
        if (shortcut.Key != 0 && (recording || normalized != fresh.PanelHotkey))
        {
            if (!RegisterHotKey(0, 0x5256, shortcut.Modifiers | 0x4000, shortcut.Key))
            { hint.Text = "That shortcut is already in use. Choose another key or combination."; return; }
            UnregisterHotKey(0, 0x5256);
        }
        if (SaveBinding?.Invoke(normalized) != true) return;
        binding = normalized; Cancel();
    }

    void Cancel(string? message = null)
    {
        var resume = recording || arming;
        revision++; recording = arming = false; timeout.Stop(); ShowBinding();
        if (message is not null) hint.Text = message;
        if (resume) _ = ResumeAsync();
    }

    async Task ResumeAsync()
    {
        try { await OverlayHelper.CommandAsync("reload", start: false); }
        catch (Exception error) { hint.Text = error.Message; }
    }

    [DllImport("user32.dll")] static extern bool RegisterHotKey(nint window, int id, uint modifiers, uint key);
    [DllImport("user32.dll")] static extern bool UnregisterHotKey(nint window, int id);
}
