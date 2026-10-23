namespace RtxForge.Windows.GameMode;

readonly record struct ScrollFadeProfile(double Height, double Depth, double Top, double Bottom)
{
    public static ScrollFadeProfile Create(double height, double offset, double extent, double unit)
    {
        var ramp = Math.Max(1, GmMotionTokens.ScrollFadeRamp * unit);
        return new(height, Math.Max(0, Math.Min(GmMotionTokens.ScrollFadeDepth * unit,
            height * GmMotionTokens.ScrollFadeRatio)), Math.Clamp(offset / ramp, 0, 1),
            Math.Clamp((extent - offset) / ramp, 0, 1));
    }

    public double Alpha(double position)
    {
        if (Depth <= 0) return 1;
        static double Smooth(double value)
        {
            var x = Math.Clamp(value, 0, 1);
            return x * x * x * (x * (x * 6 - 15) + 10);
        }
        return (1 - Top * (1 - Smooth(position / Depth)))
            * (1 - Bottom * (1 - Smooth((Height - position) / Depth)));
    }
}
