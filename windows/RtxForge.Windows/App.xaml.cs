using Microsoft.UI.Xaml;
using RtxForge.Windows.Services;

namespace RtxForge.Windows;

public partial class App : Application
{
    public static IForgeService Service { get; private set; } = null!;
    /// <summary>Set by the MainWindow constructor before its first page loads.</summary>
    public static MainWindow? Main { get; internal set; }

    public App()
    {
        InitializeComponent();
        UnhandledException += (_, e) => WriteCrashLog(e.Exception);
    }

    /// <summary>Last unhandled exception, for support reports: %LOCALAPPDATA%\rtxForge\crash.log.</summary>
    static void WriteCrashLog(Exception error)
    {
        try
        {
            var folder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "rtxForge");
            Directory.CreateDirectory(folder);
            File.WriteAllText(Path.Combine(folder, "crash.log"), $"{DateTime.Now:O}{Environment.NewLine}{error}");
        }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
    }

    /// <summary>Why the real engine is unavailable when the app fell back to preview mode.</summary>
    public static string? EngineProblem { get; private set; }

    protected override async void OnLaunched(LaunchActivatedEventArgs args)
    {
        // The real engine (bundled Python host) unless --preview is passed or
        // it cannot start; preview is `rtxforge_gtk.py --demo`: sample
        // library, no game writes.
        var preview = Environment.GetCommandLineArgs().Contains("--preview", StringComparer.OrdinalIgnoreCase);
        if (!preview)
        {
            var (engine, problem) = await EngineForgeService.TryStartAsync();
            EngineProblem = problem;
            Service = engine is not null ? engine : new PreviewForgeService();
        }
        else Service = new PreviewForgeService();
        try
        {
            new MainWindow(Service).Activate();
        }
        catch (Exception error)
        {
            WriteCrashLog(error);
            throw;
        }
    }
}
