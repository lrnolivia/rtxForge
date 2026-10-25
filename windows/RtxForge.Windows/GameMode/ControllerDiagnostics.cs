using System.Diagnostics;
using System.Text.Json;

namespace RtxForge.Windows.GameMode;

// Opt-in preview diagnostics contain axes and scroll geometry only.
internal static class ControllerDiagnostics
{
#if DEBUG
    static readonly string? destination = Environment.GetEnvironmentVariable("RTXFORGE_CONTROLLER_REVIEW");
    static long lastWrite;
    static object? input, view;
#endif
    [Conditional("DEBUG")]
    internal static void Input(double mapped, bool physical, double physicalAxis, bool up, bool down)
    {
#if DEBUG
        input = new { mapped_axis = mapped, physical_report = physical, physical_axis = physicalAxis, native_up = up, native_down = down };
        Write();
#endif
    }
    [Conditional("DEBUG")]
    internal static void View(string page, double before, double requested, double extent)
    {
#if DEBUG
        view = new { page, before, requested, extent };
        Write();
#endif
    }
#if DEBUG
    static void Write()
    {
        if (string.IsNullOrWhiteSpace(destination) || !Path.IsPathFullyQualified(destination)
            || Stopwatch.GetElapsedTime(lastWrite).TotalMilliseconds < 250) return;
        lastWrite = Stopwatch.GetTimestamp();
        try { File.WriteAllText(destination, JsonSerializer.Serialize(new { process_id = Environment.ProcessId, at = DateTimeOffset.UtcNow, input, view })); }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or ArgumentException) { }
    }
#endif
}
