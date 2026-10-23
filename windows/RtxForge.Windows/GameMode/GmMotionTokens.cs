namespace RtxForge.Windows.GameMode;

/// <summary>The native Game Mode motion contract. Times are response profiles, never input delays.</summary>
static class GmMotionTokens
{
    static readonly System.Text.Json.JsonDocument contract = System.Text.Json.JsonDocument.Parse(
        typeof(GmMotionTokens).Assembly.GetManifestResourceStream("RtxForge.GameMode.Motion.json")
        ?? throw new InvalidOperationException("Game Mode motion contract is missing."));
    static double Number(string key) => contract.RootElement.GetProperty(key).GetDouble();
    public static int Press => (int)Number("press_ms");
    public static int Focus => (int)Number("focus_ms");
    public static int Surface => (int)Number("surface_ms");
    public static int Fade => (int)Number("fade_ms");
    public static int Feedback => (int)Number("feedback_ms");
    public static int Exit => (int)Number("exit_ms");
    public static float FocusDamping => (float)Number("focus_damping");
    public static float PressDamping => (float)Number("press_damping");
    public static float SceneDamping => (float)Number("scene_damping");
    public static float CardScale => (float)Number("card_scale");
    public static float CardLift => (float)Number("card_lift");
    public static float CardCompression => (float)Number("card_compression");
    public static float ButtonCompression => (float)Number("button_compression");
    public static float DialogScale => (float)Number("dialog_scale");
    public static float DialogTravel => (float)Number("dialog_travel");
    public static double ArtworkStroke => Number("artwork_stroke");
    public static (float Travel, int Period) Region(int index)
    {
        var regions = contract.RootElement.GetProperty("page_regions");
        var region = regions[Math.Min(index, regions.GetArrayLength() - 1)];
        return (region.GetProperty("travel").GetSingle(), region.GetProperty("period_ms").GetInt32());
    }
}

/// <summary>Analytic state sampled at input time: reversals preserve position and velocity.</summary>
sealed class GmSpring(double period, double damping)
{
    double origin, velocity, target, started;
    public double Target => target;
    public (double Value, double Velocity) Sample(double now)
    {
        var elapsed = Math.Max(0, now - started);
        if (elapsed > 2) return (target, 0);
        var omega = 2 * Math.PI / period;
        var displacement = origin - target;
        if (damping >= .9999)
        {
            var b = velocity + omega * displacement; var decay = Math.Exp(-omega * elapsed);
            return (target + (displacement + b * elapsed) * decay, (velocity - omega * b * elapsed) * decay);
        }
        var frequency = omega * Math.Sqrt(1 - damping * damping);
        var c = (velocity + damping * omega * displacement) / frequency;
        var sine = Math.Sin(frequency * elapsed); var cosine = Math.Cos(frequency * elapsed);
        var e = Math.Exp(-damping * omega * elapsed); var offset = displacement * cosine + c * sine;
        return (target + e * offset, e * ((-displacement * sine + c * cosine) * frequency - damping * omega * offset));
    }
    public (double Value, double Velocity) Retarget(double value, double now, bool immediate = false)
    {
        var current = immediate ? (value, 0d) : Sample(now);
        origin = current.Item1; velocity = current.Item2; target = value; started = now;
        return current;
    }
}
