using RtxForge.Windows.GameMode;

var checks = 0;
void Assert(bool condition, string name) { if (!condition) throw new InvalidOperationException(name); checks++; }
foreach (var profile in new[] { (.17, .92), (.10, 1d) })
{
    var spring = new GmSpring(profile.Item1, profile.Item2);
    spring.Retarget(1, 0);
    Assert(spring.Sample(.001).Value > 0, "Responds on first sample");
    var before = spring.Sample(.047);
    var reversal = spring.Retarget(0, .047);
    Assert(Math.Abs(before.Value - reversal.Value) < 1e-12, "Reversal preserves position");
    Assert(Math.Abs(before.Velocity - reversal.Velocity) < 1e-12, "Reversal preserves velocity");
    for (var i = 1; i <= 1000; i++)
    {
        var at = .047 + i * .009;
        var sample = spring.Sample(at);
        Assert(double.IsFinite(sample.Value) && double.IsFinite(sample.Velocity), "Rapid retarget stays finite");
        Assert(sample.Value > -.15 && sample.Value < 1.15, "No rubbery or accumulating overshoot");
        var next = spring.Retarget(i % 2, at);
        Assert(Math.Abs(next.Value - sample.Value) < 1e-12 && Math.Abs(next.Velocity - sample.Velocity) < 1e-12, "No queued/reset motion");
    }
    spring.Retarget(1, 10);
    Assert(Math.Abs(spring.Sample(10.35).Value - 1) < .001, "Settles within large-transition budget");
    var reduced = spring.Retarget(0, 10.36, true);
    Assert(reduced.Value == 0 && reduced.Velocity == 0, "Reduced motion cancels velocity");
}
Console.WriteLine($"PASS: {checks} spring continuity, rapid reversal, bounds, settling and reduced-motion checks");

foreach (var unit in new[] { .7, 1d, 1.3 })
{
    var plain = ScrollFadeProfile.Create(700, 0, 0, unit);
    Assert(plain.Alpha(0) == 1 && plain.Alpha(700) == 1, "No overflow remains opaque");
    var start = ScrollFadeProfile.Create(700, 0, 1000, unit);
    Assert(start.Alpha(0) == 1 && start.Alpha(700) == 0, "Real top stays visible");
    var end = ScrollFadeProfile.Create(700, 1000, 1000, unit);
    Assert(end.Alpha(0) == 0 && end.Alpha(700) == 1, "Real bottom stays visible");
    var middle = ScrollFadeProfile.Create(700, 500, 1000, unit);
    Assert(middle.Alpha(0) == 0 && middle.Alpha(700) == 0 && middle.Alpha(350) == 1, "Both edges reach zero, center stays opaque");
    for (var i = 0; i < 100; i++)
        Assert(middle.Alpha(i * middle.Depth / 100) <= middle.Alpha((i + 1) * middle.Depth / 100), "Smooth monotonic edge");
}
Console.WriteLine($"PASS: {checks} motion and scroll fade checks");
