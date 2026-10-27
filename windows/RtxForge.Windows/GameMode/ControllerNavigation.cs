namespace RtxForge.Windows.GameMode;

internal static class ControllerNavigation
{
    internal static readonly string[] Tabs = ["library", "presets", "packages", "extras", "settings"];
    internal static int PageDirection(string? previous, string current)
    {
        if (current == "details") return 1;
        if (previous == "details") return -1;
        return Array.IndexOf(Tabs, current) < Array.IndexOf(Tabs, previous ?? "library") ? -1 : 1;
    }

    internal static string NextTab(string page, int direction)
    {
        var index = Array.IndexOf(Tabs, page == "details" ? "library" : page);
        return Tabs[((Math.Max(0, index) + direction) % Tabs.Length + Tabs.Length) % Tabs.Length];
    }

    // Rescale outside the deadzone so slow scrolling starts without a jump.
    internal static double ScrollAxis(double axis, bool nativeUp, bool nativeDown) =>
        double.IsFinite(axis) && Math.Abs(axis) > .18 ? Math.Clamp(axis, -1, 1)
        : nativeUp == nativeDown ? 0 : nativeUp ? 1 : -1;

    internal static double ScrollDelta(double axis, double seconds)
    {
        if (!double.IsFinite(axis) || !double.IsFinite(seconds)) return 0;
        const double deadzone = .18;
        var strength = (Math.Clamp(Math.Abs(axis), 0, 1) - deadzone) / (1 - deadzone);
        return strength <= 0 ? 0 : -Math.Sign(axis) * strength * 1100 * Math.Clamp(seconds, 0, .05);
    }
}
