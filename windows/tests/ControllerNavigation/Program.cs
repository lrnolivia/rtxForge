using RtxForge.Windows.GameMode;

var checks = 0;
void Check(bool condition, string message)
{
    checks++;
    if (!condition) throw new Exception(message);
}
Check(ControllerNavigation.ScrollAxis(0, false, true) == -1, "Native right-stick down must scroll without mapped axes");
Check(ControllerNavigation.ScrollAxis(0, true, false) == 1, "Native right-stick up must scroll without mapped axes");
Check(ControllerNavigation.ScrollAxis(-.5, false, true) == -.5, "Native fallback must not double mapped analog input");
Check(ControllerNavigation.ScrollAxis(0, false, false) == 0 && ControllerNavigation.ScrollAxis(0, true, true) == 0, "Released or opposing native directions must stop scrolling");
foreach (var id in new byte[] { 0x42, 0x45, 0x47 })
{
    var packet = new byte[64]; packet[0] = id;
    System.Buffers.Binary.BinaryPrimitives.WriteInt16LittleEndian(packet.AsSpan(16), -16384);
    Check(SteamControllerReport.TryRightStick(packet, out var value) && value == -.5,
        "Steam USB/BLE/timestamp report lost signed right-stick input");
    Check(ControllerNavigation.ScrollDelta(value, .016) > 0, "Physical Steam right-stick down must scroll down");
    packet[16] = packet[17] = 0;
    Check(SteamControllerReport.TryRightStick(packet, out value) && value == 0, "Center report must stop physical scrolling");
    Check(!SteamControllerReport.TryRightStick(packet.AsSpan(0, 17), out _), "Truncated Steam report must not read past the payload");
}
foreach (var id in new byte[] { 0, 1, 0x43, 0x46, 0x79 })
{
    var packet = new byte[64]; packet[0] = id;
    Check(!SteamControllerReport.TryRightStick(packet, out _), "Battery/wireless/legacy report was mistaken for stick input");
}
foreach (var axis in new[] { -.18, -.01, 0, .01, .18, double.NaN, double.PositiveInfinity })
    Check(ControllerNavigation.ScrollDelta(axis, .016) == 0, "Stick drift or invalid input scrolled content");
Check(ControllerNavigation.ScrollDelta(1, .016) < 0, "Stick up must scroll up");
Check(ControllerNavigation.ScrollDelta(-1, .016) > 0, "Stick down must scroll down");
Check(ControllerNavigation.ScrollDelta(-.181, .016) < 1, "Deadzone edge jumped");
Check(ControllerNavigation.ScrollDelta(-.5, .016) < ControllerNavigation.ScrollDelta(-1, .016), "Analog speed did not scale");
Check(Math.Abs(ControllerNavigation.ScrollDelta(-1, 1) - 55) < .001, "Delayed frames caused a scroll jump");
Check(ControllerNavigation.ScrollDelta(-1, -1) == 0, "Invalid time scrolled content");
var at30 = Enumerable.Range(0, 30).Sum(_ => ControllerNavigation.ScrollDelta(-.8, 1d / 30));
var at120 = Enumerable.Range(0, 120).Sum(_ => ControllerNavigation.ScrollDelta(-.8, 1d / 120));
Check(Math.Abs(at30 - at120) < .001, "Scrolling speed depends on poll rate");
var page = "library";
foreach (var expected in new[] { "presets", "packages", "extras", "settings", "library" })
{
    page = ControllerNavigation.NextTab(page, 1);
    Check(page == expected, "Right bumper skipped a main tab");
}
Check(ControllerNavigation.NextTab("library", -1) == "settings", "Left bumper did not wrap");
Check(ControllerNavigation.NextTab("details", 1) == "presets", "Details must belong to Library main tab");
Check(ControllerNavigation.NextTab("details", -1) == "settings", "Details left bumper did not wrap");
Check(ControllerNavigation.PageDirection("library", "presets") == 1, "Forward navigation must arrive from the right");
Check(ControllerNavigation.PageDirection("settings", "library") == -1, "Backward navigation must arrive from the left");
Check(ControllerNavigation.PageDirection("library", "details") == 1 && ControllerNavigation.PageDirection("details", "library") == -1,
    "Details and Back must use opposite slide directions");
foreach (var type in new uint[] { 0, 1, 2 })
{
    var steam = ControllerDevice.Identify(@"\\?\HID#VID_28DE&PID_1304&MI_04&COL02#8&2d78044a&0&0001", type);
    Check(steam?.Family == "steam", "Physical Valve desktop interface not recognized");
}
Check(ControllerDevice.Identify(@"\\?\HID#VID_045E&PID_07F8#keyboard", 1) is null, "Normal keyboard classified as controller");
Check(ControllerDevice.Identify(@"\\?\HID#VID_046D&PID_C548#mouse", 0) is null, "Normal mouse classified as controller");
Check(ControllerDevice.Identify(@"\\.\pipe\HID#VID_045E&PID_028E&IG_00#28de&1304&0123456789abcdef#1#123", 2) == ("steam", 1), "Steam Input physical identity/slot lost");
Console.WriteLine($"PASS: {checks} analog scrolling, bumper order and physical controller identity checks");
