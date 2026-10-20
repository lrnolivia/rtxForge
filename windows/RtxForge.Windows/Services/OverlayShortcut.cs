namespace RtxForge.Windows.Services;

public static class OverlayShortcut
{
    public const string Default = "ScrollLock";
    public const string Disabled = "Disabled";
    static readonly Dictionary<string, uint> Keys = BuildKeys();

    static Dictionary<string, uint> BuildKeys()
    {
        var keys = new Dictionary<string, uint>(StringComparer.OrdinalIgnoreCase)
        {
            ["End"] = 0x23, ["Home"] = 0x24, ["PageUp"] = 0x21, ["PageDown"] = 0x22,
            ["Left"] = 0x25, ["Up"] = 0x26, ["Right"] = 0x27, ["Down"] = 0x28,
            ["Pause"] = 0x13, ["ScrollLock"] = 0x91, ["Delete"] = 0x2E,
            ["Backspace"] = 8, ["Enter"] = 13, ["Space"] = 0x20,
            ["NumMultiply"] = 0x6A, ["NumAdd"] = 0x6B, ["NumSubtract"] = 0x6D,
            ["NumDecimal"] = 0x6E, ["NumDivide"] = 0x6F,
            ["Semicolon"] = 0xBA, ["Equals"] = 0xBB, ["Comma"] = 0xBC, ["Minus"] = 0xBD,
            ["Period"] = 0xBE, ["Slash"] = 0xBF, ["Backtick"] = 0xC0,
            ["LeftBracket"] = 0xDB, ["Backslash"] = 0xDC, ["RightBracket"] = 0xDD, ["Quote"] = 0xDE,
        };
        for (uint key = 0x30; key <= 0x39; key++) keys[((char)key).ToString()] = key;
        for (uint key = 0x41; key <= 0x5A; key++) keys[((char)key).ToString()] = key;
        for (uint number = 0; number <= 9; number++) keys["Num" + number] = 0x60 + number;
        for (uint number = 1; number <= 24; number++)
            if (number != 12) keys["F" + number] = 0x6F + number; // F12 is reserved by Windows for debuggers.
        return keys;
    }

    public static bool IsRetiredDefault(string? value) => string.Equals(value?.Trim(), "Insert", StringComparison.OrdinalIgnoreCase)
        || string.Equals(value?.Trim(), "End", StringComparison.OrdinalIgnoreCase);

    // Only our retired defaults move; other overlays keep their own shortcuts.
    public static string NormalizeStored(string? value) => string.IsNullOrWhiteSpace(value)
        || IsRetiredDefault(value) ? Default
        : TryParse(value, out var normalized, out _, out _) ? normalized : value.Trim();

    public static bool IsModifier(uint key) => key is 0x10 or 0x11 or 0x12 or 0x5B or 0x5C
        or >= 0xA0 and <= 0xA5;

    public static bool TryCreate(uint key, uint modifiers, out string value, out string error)
    {
        value = "";
        error = "Choose a key, with optional Ctrl, Alt or Shift.";
        if (key == 0x2D) { error = "Insert is reserved for OptiScaler. Choose another key."; return false; }
        if (key == 0x23) { error = "End is reserved for OptiScaler frame generation. Choose another key."; return false; }
        if ((modifiers & ~7u) != 0) { error = "Windows-key shortcuts belong to Windows. Choose another shortcut."; return false; }
        var name = Keys.FirstOrDefault(pair => pair.Value == key).Key;
        if (name is null) return false;
        if ((modifiers & 1) != 0 && key is 0x73 or 0x20)
        { error = "That shortcut belongs to Windows. Choose another shortcut."; return false; }
        if ((modifiers & 3) == 3 && key == 0x2E)
        { error = "That shortcut belongs to Windows. Choose another shortcut."; return false; }
        value = ((modifiers & 2) != 0 ? "Ctrl+" : "") + ((modifiers & 1) != 0 ? "Alt+" : "")
            + ((modifiers & 4) != 0 ? "Shift+" : "") + name;
        error = "";
        return true;
    }

    public static bool TryParse(string? value, out string normalized, out (uint Modifiers, uint Key) binding, out string error)
    {
        normalized = ""; binding = (0, 0); error = "Choose a valid shortcut in Settings → Overlay.";
        if (string.Equals(value?.Trim(), Disabled, StringComparison.OrdinalIgnoreCase))
        { normalized = Disabled; error = ""; return true; }
        var parts = (value ?? "").Split('+', StringSplitOptions.TrimEntries);
        uint modifiers = 0;
        foreach (var part in parts.SkipLast(1))
        {
            uint modifier = part.ToLowerInvariant() switch { "ctrl" => 2, "alt" => 1, "shift" => 4, _ => 0 };
            if (modifier == 0 || (modifiers & modifier) != 0) return false;
            modifiers |= modifier;
        }
        if (parts[^1].Equals("Insert", StringComparison.OrdinalIgnoreCase))
        { error = "Insert is reserved for OptiScaler. Choose another key."; return false; }
        if (!Keys.TryGetValue(parts[^1], out var key) || !TryCreate(key, modifiers, out normalized, out error)) return false;
        binding = (modifiers, key);
        return true;
    }
}
