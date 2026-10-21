using Microsoft.UI.Xaml;
using RtxForge.Windows.Services;
using System.Text.Json;

namespace RtxForge.Windows;

public partial class App : Application
{
    public static IForgeService Service { get; private set; } = null!;
    public static MainWindow? Main { get; internal set; }
    public static string? EngineProblem => null;
    public App()
    {
        DebugSettings.XamlResourceReferenceFailed += (_, e) => File.AppendAllText(Path.Combine(AppContext.BaseDirectory, "sample-xaml.log"), e.Message + "\n");
        InitializeComponent(); UnhandledException += (_, e) => WriteCrashLog(e.Exception);
    }
    static void WriteCrashLog(Exception error)
    {
        try
        {
            var extra = string.Join("\n", error.Data.Keys.Cast<object>().Select(key => key + ": " + error.Data[key]));
            File.WriteAllText(Path.Combine(AppContext.BaseDirectory, "sample-launch-error.log"), $"{DateTime.Now:O}\n{error}\nHRESULT {error.HResult:X8}\n{extra}");
        }
        catch (IOException) { }
    }
    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        try
        {
            SampleProfile.Configure(Environment.GetCommandLineArgs());
            Service = new PreviewForgeService();
            var window = new MainWindow(Service);
            window.Closed += (_, _) => File.WriteAllText(Path.Combine(SampleProfile.Root, "closed.json"), "{}");
            var root = (FrameworkElement)window.Content;
            root.Loaded += (_, _) =>
            {
                var ready = window.DispatcherQueue.CreateTimer();
                ready.IsRepeating = false; ready.Interval = TimeSpan.FromSeconds(2);
                ready.Tick += (_, _) => File.WriteAllText(Path.Combine(SampleProfile.Root, "window-ready.json"), JsonSerializer.Serialize(new
                { pid = Environment.ProcessId, binary = Environment.ProcessPath, profile = SampleProfile.Root,
                    catalog = SampleProfile.CatalogCount, visible_games = Main!.Games.Count, sample = Service.IsPreview,
                    xaml_host_visible = root.XamlRoot?.IsHostVisible, width = root.ActualWidth, height = root.ActualHeight,
                    loaded_at = DateTimeOffset.Now }));
                ready.Start();
            };
            window.Activate();
        }
        catch (Exception error) { WriteCrashLog(error); Exit(); }
    }
}
