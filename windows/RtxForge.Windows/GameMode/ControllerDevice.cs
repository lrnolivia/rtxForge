using System.Globalization;
using System.Text.RegularExpressions;

namespace RtxForge.Windows.GameMode;

/// <summary>Physical device identity, including Valve's documented virtual gamepad name.</summary>
internal static class ControllerDevice
{
    public static string Family(uint vendor) => vendor switch
    {
        0x054C => "playstation", 0x057E => "nintendo", 0x28DE => "steam",
        0x045E => "xbox", _ => "generic",
    };

    public static (string Family, int? Slot)? Identify(string name, uint type)
    {
        // Steam Input preserves the physical VID and XInput slot in its pipe.
        var steam = Regex.Match(name, @"^\\\\\.\\pipe\\HID#VID_045E&PID_028E&IG_00#([0-9a-f]{4})&[0-9a-f]{4}&[0-9a-f]{16}#([0-3])#\d+$", RegexOptions.IgnoreCase);
        if (steam.Success)
            return (Family(uint.Parse(steam.Groups[1].Value, NumberStyles.HexNumber)), int.Parse(steam.Groups[2].Value));
        var hid = Regex.Match(name, @"(?:^|[#\\])[^#\\]*VID_([0-9a-f]{4})&PID_[0-9a-f]{4}", RegexOptions.IgnoreCase);
        if (!hid.Success) return null;
        var vendor = uint.Parse(hid.Groups[1].Value, NumberStyles.HexNumber);
        // Valve desktop/lizard mappings arrive as keyboard or mouse. Ordinary
        // keyboards and mice must never be mistaken for controller activity.
        return type is 0 or 1 ? vendor == 0x28DE ? ("steam", null) : null : (Family(vendor), null);
    }
}
