using System.Diagnostics;
using System.Security.Cryptography;
using System.Text.Json;

namespace RtxForge.Windows.Services;

/// <summary>Launch the verified native UI; no alternate install engine or legacy UI fallback.</summary>
internal static class GameModeLauncher
{
    public static string Resolve(string appDirectory, string localAppData)
    {
        var bundled = Path.Combine(appDirectory, "game-mode");
        if (Directory.Exists(bundled)) return Validate(bundled);
        var root = Path.Combine(localAppData, "Programs", "rtxForge Game Mode");
        var installed = Path.Combine(root, "installed.json");
        if (!File.Exists(installed)) throw new InvalidOperationException("Game Mode is missing. Reinstall the complete rtxForge application.");
        using var record = JsonDocument.Parse(File.ReadAllText(installed));
        var folder = Path.GetFullPath(record.RootElement.GetProperty("path").GetString()!);
        var versions = Path.GetFullPath(Path.Combine(root, "versions")) + Path.DirectorySeparatorChar;
        if (!folder.StartsWith(versions, StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("The Game Mode installation record is invalid.");
        return Validate(folder);
    }

    internal static string Validate(string folder)
    {
        using var receipt = JsonDocument.Parse(File.ReadAllText(Path.Combine(folder, "build.json")));
        var build = receipt.RootElement;
        if (build.GetProperty("schema").GetInt32() != 2 || build.GetProperty("dirty").GetBoolean()
            || !build.TryGetProperty("desktopIntegration", out var protocol) || protocol.GetInt32() != 1)
            throw new InvalidOperationException("Install the current complete Game Mode package before switching interfaces.");
        foreach (var file in new[] { "rtxforge-game-mode.exe", "python/python.exe", "bridge/engine_host.py", "engine/scripts/desktop_service.py", "screening/rtxforge-screenshot-screen.exe" })
            if (!File.Exists(Path.Combine(folder, file))) throw new InvalidOperationException("The Game Mode installation is incomplete: " + file);
        var executable = Path.Combine(folder, "rtxforge-game-mode.exe");
        using var stream = File.OpenRead(executable);
        var hash = Convert.ToHexString(SHA256.HashData(stream));
        if (!string.Equals(hash, build.GetProperty("native").GetProperty("sha256").GetString(), StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("The Game Mode executable has changed. Reinstall the application.");
        return executable;
    }

    public static Process Start(string executable, bool readOnly, bool appearance = false)
    {
        var start = new ProcessStartInfo(executable) { UseShellExecute = false, WorkingDirectory = Path.GetDirectoryName(executable)! };
        if (appearance) start.ArgumentList.Add("--appearance");
        start.ArgumentList.Add("--desktop-parent"); start.ArgumentList.Add(Environment.ProcessId.ToString());
        start.Environment["RTXFORGE_APP_EXE"] = Environment.ProcessPath!;
        start.Environment["RTXFORGE_DESKTOP_COMMAND"] = JsonSerializer.Serialize(new[] { Environment.ProcessPath!, "--desktop-mode" });
        foreach (var key in new[] { "RTXFORGE_ROOT", "RTXFORGE_PYTHON", "PYTHONPATH", "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "SteamAppId", "SteamGameId" }) start.Environment.Remove(key);
        if (readOnly) start.Environment["RTXFORGE_PREVIEW_READ_ONLY"] = "1";
        var child = Process.Start(start) ?? throw new InvalidOperationException("Game Mode could not be opened.");
        // A second activation is redirected by the native single-instance plugin.
        try { child.WaitForInputIdle(15000); } catch (InvalidOperationException) { }
        if (!child.HasExited) return child;
        foreach (var existing in Process.GetProcessesByName("rtxforge-game-mode"))
        {
            try { if (string.Equals(existing.MainModule?.FileName, executable, StringComparison.OrdinalIgnoreCase)) { child.Dispose(); return existing; } }
            catch (System.ComponentModel.Win32Exception) { }
            existing.Dispose();
        }
        var code = child.ExitCode; child.Dispose();
        throw new InvalidOperationException($"Game Mode stopped before opening (exit {code}). The Desktop window has been kept open.");
    }
}
