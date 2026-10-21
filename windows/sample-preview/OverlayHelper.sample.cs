using RtxForge.Windows.Models;

namespace RtxForge.Windows.Services;

// A private capture build never starts or commands the real helper or writes its registry.
public static class OverlayHelper
{
    internal static string PipeName => "rtxForge.Sample.Disabled";
    public static string StartupCommand(string executable) => "";
    public static Task CacheGameIdentitiesAsync(IEnumerable<Game> games) => Task.CompletedTask;
    public static void ConfigureStartup(ForgeSettings settings) { }
    internal static void ConfigurePanel(ForgeSettings settings) { }
    public static Task<string?> CommandAsync(string command, bool start = true) =>
        Task.FromResult<string?>("Live overlays are unavailable in this sample.");
}
