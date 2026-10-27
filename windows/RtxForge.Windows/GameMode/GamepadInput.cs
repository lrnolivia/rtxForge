using Microsoft.UI.Dispatching;
using System.Runtime.InteropServices;
using Windows.Gaming.Input;

namespace RtxForge.Windows.GameMode;

/// <summary>
/// Controller input for Game Mode, the Windows adapter for
/// scripts/controller_input.py: Windows.Gaming.Input instead of SDL2, the
/// same action names, the same 0.4 s first repeat and 0.13 s repeat for
/// directions, and the same button map (A accept, B back, X select,
/// Y library, View settings, Menu menu, LB/RB previous/next, D-pad and the
/// left stick to move).
/// </summary>
public sealed class GamepadInput : IDisposable
{
    readonly DispatcherQueueTimer timer;
    HashSet<string> previous = [];
    readonly Dictionary<string, DateTime> repeats = [];
    Gamepad? pad;
    GamepadReading lastReading;
    readonly EventHandler<Gamepad> added;
    readonly EventHandler<Gamepad> removed;
    readonly Func<bool> foreground;
    readonly ControllerRawInput raw;
    long lastPoll = System.Diagnostics.Stopwatch.GetTimestamp();
    bool xinputConnected;
    bool nativeRightUp, nativeRightDown;
    public bool LegacyInputActive => raw.LegacyInputActive;
    public bool SteamConnected => raw.SteamConnected;
    public bool PollingAvailable => pad is not null || xinputConnected;

    /// <summary>One action per press (and per repeat for directions).</summary>
    public event Action<string>? Action;
    /// <summary>The connected controller changed (attach, detach or a new family).</summary>
    public event Action? Changed;
    public event Action? Activity;
    public event Action<double>? Scroll;

    /// <summary>xbox, playstation, nintendo, steam or generic: drives button labels.</summary>
    public string Family { get; private set; } = "xbox";
    public bool Connected => pad is not null || xinputConnected || raw.SteamConnected;

    public void NativeRightStick(bool up, bool pressed)
    {
        if (up) nativeRightUp = pressed; else nativeRightDown = pressed;
    }

    public GamepadInput(DispatcherQueue queue, nint window, Func<bool> foreground)
    {
        this.foreground = foreground;
        raw = new ControllerRawInput(window, foreground, family =>
        {
            SetFamily(family);
            Activity?.Invoke();
        });
        added = (_, _) => queue.TryEnqueue(Refresh);
        removed = (_, _) => queue.TryEnqueue(Refresh);
        Gamepad.GamepadAdded += added;
        Gamepad.GamepadRemoved += removed;
        timer = queue.CreateTimer();
        timer.Interval = TimeSpan.FromMilliseconds(16);
        timer.Tick += (_, _) => Poll();
        Refresh();
        if (raw.SteamConnected) SetFamily("steam");
        timer.Start();
    }

    void SetFamily(string family)
    {
        if (Family == family) return;
        Family = family;
        Changed?.Invoke();
    }

    void Refresh()
    {
        Gamepad? current;
        try
        {
            // Steam Input's projected collection can support indexed access
            // without exposing the iterable interface used by LINQ.
            var pads = Gamepad.Gamepads;
            current = pads.Count > 0 ? pads[0] : null;
        }
        catch (Exception error) when (error is InvalidCastException or System.Runtime.InteropServices.COMException)
        {
            // A controller provider must not prevent the app from opening.
            current = null;
        }
        if (ReferenceEquals(current, pad)) return;
        pad = current;
        previous = [];
        repeats.Clear();
        Family = current is null ? Family : FamilyOf(current);
        Changed?.Invoke();
    }

    static string FamilyOf(Gamepad gamepad)
    {
        RawGameController? raw;
        try { raw = RawGameController.FromGameController(gamepad); }
        catch (Exception error) when (error is InvalidCastException or System.Runtime.InteropServices.COMException) { return "xbox"; }
        return raw is null ? "xbox" : ControllerDevice.Family(raw.HardwareVendorId);
    }

    void Poll()
    {
        var nowTick = System.Diagnostics.Stopwatch.GetTimestamp();
        var seconds = System.Diagnostics.Stopwatch.GetElapsedTime(lastPoll, nowTick).TotalSeconds;
        lastPoll = nowTick;
        if (!foreground()) { previous.Clear(); repeats.Clear(); lastReading = default; nativeRightUp = nativeRightDown = false; return; }
        var reading = default(GamepadReading);
        var hasReading = false;
        try
        {
            var pads = Gamepad.Gamepads;
            // A dormant first device must not hide the controller being used.
            for (var i = 0; i < pads.Count; i++)
            {
                var candidate = pads[i];
                GamepadReading value;
                try { value = candidate.GetCurrentReading(); }
                catch (Exception error) when (error is InvalidOperationException or System.Runtime.InteropServices.COMException) { continue; }
                if (!hasReading) { reading = value; hasReading = true; }
                if (!HasActivity(value)) continue;
                pad = candidate; reading = value; SetFamily(FamilyOf(candidate)); break;
            }
        }
        catch (Exception error) when (error is InvalidCastException or System.Runtime.InteropServices.COMException) { }
        if ((!hasReading || !HasActivity(reading)) && ReadXInput(out var fallback))
        { reading = fallback; hasReading = true; }
        var rawStick = raw.TryRightStick(out var physicalAxis);
        ControllerDiagnostics.Input(reading.RightThumbstickY, rawStick, physicalAxis, nativeRightUp, nativeRightDown);
        if (!hasReading && !rawStick && !nativeRightUp && !nativeRightDown) return;

        if (reading.Buttons != lastReading.Buttons && reading.Buttons != GamepadButtons.None
            || Math.Abs(reading.RightThumbstickX - lastReading.RightThumbstickX) > .15
            || Math.Abs(reading.RightThumbstickY - lastReading.RightThumbstickY) > .15
            || reading.LeftTrigger > .2 && lastReading.LeftTrigger <= .2
            || reading.RightTrigger > .2 && lastReading.RightTrigger <= .2)
            Activity?.Invoke();
        lastReading = reading;
        var mappedAxis = Math.Abs(reading.RightThumbstickY) > .18 ? reading.RightThumbstickY : rawStick ? physicalAxis : 0;
        var axis = ControllerNavigation.ScrollAxis(mappedAxis, nativeRightUp, nativeRightDown);
        var scroll = ControllerNavigation.ScrollDelta(axis, seconds);
        if (scroll != 0) { Activity?.Invoke(); Scroll?.Invoke(scroll); }

        var pressed = new HashSet<string>();
        void Map(GamepadButtons button, string action) { if ((reading.Buttons & button) != 0) pressed.Add(action); }
        Map(GamepadButtons.A, "accept");
        Map(GamepadButtons.B, "back");
        Map(GamepadButtons.X, "select");
        Map(GamepadButtons.Y, "search");
        Map(GamepadButtons.View, "settings");
        Map(GamepadButtons.Menu, "menu");
        Map(GamepadButtons.LeftShoulder, "previous");
        Map(GamepadButtons.RightShoulder, "next");
        Map(GamepadButtons.DPadUp, "up");
        Map(GamepadButtons.DPadDown, "down");
        Map(GamepadButtons.DPadLeft, "left");
        Map(GamepadButtons.DPadRight, "right");
        // Same deadzone as SDL's ±18000 of 32767.
        const double threshold = 18000.0 / 32767;
        if (reading.LeftThumbstickX < -threshold) pressed.Add("left");
        else if (reading.LeftThumbstickX > threshold) pressed.Add("right");
        if (reading.LeftThumbstickY > threshold) pressed.Add("up");
        else if (reading.LeftThumbstickY < -threshold) pressed.Add("down");

        var now = DateTime.UtcNow;
        foreach (var action in pressed.Order())
        {
            if (!previous.Contains(action))
            {
                repeats[action] = now.AddSeconds(0.4);
                Action?.Invoke(action);
            }
            else if (action is "up" or "down" or "left" or "right" && now >= repeats.GetValueOrDefault(action, now))
            {
                repeats[action] = now.AddSeconds(0.13);
                Action?.Invoke(action);
            }
        }
        previous = pressed;
        foreach (var key in repeats.Keys.Where(k => !pressed.Contains(k)).ToList()) repeats.Remove(key);
    }

    static bool HasActivity(GamepadReading value) => value.Buttons != GamepadButtons.None
        || Math.Abs(value.LeftThumbstickX) > .18 || Math.Abs(value.LeftThumbstickY) > .18
        || Math.Abs(value.RightThumbstickX) > .18 || Math.Abs(value.RightThumbstickY) > .18
        || value.LeftTrigger > .2 || value.RightTrigger > .2;

    bool ReadXInput(out GamepadReading reading)
    {
        reading = default;
        xinputConnected = false;
        // WGI remains primary. This fallback handles virtual XInput devices
        // without dispatching the same physical press through both providers.
        for (uint slot = 0; slot < 4; slot++)
        {
            if (XInputGetState(slot, out var state) != 0) continue;
            xinputConnected = true;
            var value = state.Pad;
            GamepadButtons buttons = 0;
            void Map(ushort bit, GamepadButtons button) { if ((value.Buttons & bit) != 0) buttons |= button; }
            Map(0x1000, GamepadButtons.A); Map(0x2000, GamepadButtons.B); Map(0x4000, GamepadButtons.X); Map(0x8000, GamepadButtons.Y);
            Map(0x20, GamepadButtons.View); Map(0x10, GamepadButtons.Menu);
            Map(0x100, GamepadButtons.LeftShoulder); Map(0x200, GamepadButtons.RightShoulder);
            Map(1, GamepadButtons.DPadUp); Map(2, GamepadButtons.DPadDown); Map(4, GamepadButtons.DPadLeft); Map(8, GamepadButtons.DPadRight);
            reading = new GamepadReading { Buttons = buttons, LeftThumbstickX = value.X / 32768.0, LeftThumbstickY = value.Y / 32768.0,
                RightThumbstickX = value.RX / 32768.0, RightThumbstickY = value.RY / 32768.0, LeftTrigger = value.LT / 255.0, RightTrigger = value.RT / 255.0 };
            if (!HasActivity(reading)) continue;
            SetFamily(raw.SlotFamily((int)slot) ?? (raw.SteamConnected ? "steam" : "xbox"));
            return true;
        }
        return xinputConnected;
    }

    [StructLayout(LayoutKind.Sequential)] struct XPad { public ushort Buttons; public byte LT, RT; public short X, Y, RX, RY; }
    [StructLayout(LayoutKind.Sequential)] struct XState { public uint Packet; public XPad Pad; }
    [DllImport("xinput1_4.dll")] static extern uint XInputGetState(uint slot, out XState state);

    /// <summary>Button labels per family (controller_input.GLYPHS: accept, back, library, menu).</summary>
    public static (string Accept, string Back, string Library, string Menu) Glyphs(string family) => family switch
    {
        "playstation" => ("×", "○", "△", "Options"),
        "nintendo" => ("B", "A", "X", "+"),
        "steam" => ("A", "B", "Y", "Menu"),
        "generic" => ("South", "East", "North", "Start"),
        _ => ("A", "B", "Y", "Menu"),
    };

    public void Dispose()
    {
        timer.Stop();
        Gamepad.GamepadAdded -= added;
        Gamepad.GamepadRemoved -= removed;
        raw.Dispose();
    }
}
