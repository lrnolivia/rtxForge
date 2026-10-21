using Microsoft.UI.Dispatching;
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

    /// <summary>One action per press (and per repeat for directions).</summary>
    public event Action<string>? Action;
    /// <summary>The connected controller changed (attach, detach or a new family).</summary>
    public event Action? Changed;
    public event Action? Activity;

    /// <summary>xbox, playstation, nintendo, steam or generic: drives button labels.</summary>
    public string Family { get; private set; } = "xbox";
    public bool Connected => pad is not null;

    public GamepadInput(DispatcherQueue queue)
    {
        added = (_, _) => queue.TryEnqueue(Refresh);
        removed = (_, _) => queue.TryEnqueue(Refresh);
        Gamepad.GamepadAdded += added;
        Gamepad.GamepadRemoved += removed;
        timer = queue.CreateTimer();
        timer.Interval = TimeSpan.FromMilliseconds(16);
        timer.Tick += (_, _) => Poll();
        Refresh();
        timer.Start();
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
        return raw?.HardwareVendorId switch
        {
            0x054C => "playstation",
            0x057E => "nintendo",
            0x28DE => "steam",
            0x045E => "xbox",
            null => "xbox",
            _ => "generic",
        };
    }

    void Poll()
    {
        if (pad is null) return;
        GamepadReading reading;
        try { reading = pad.GetCurrentReading(); }
        catch (Exception error) when (error is InvalidOperationException or System.Runtime.InteropServices.COMException) { return; }

        if (reading.Buttons != lastReading.Buttons && reading.Buttons != GamepadButtons.None
            || Math.Abs(reading.RightThumbstickX - lastReading.RightThumbstickX) > .15
            || Math.Abs(reading.RightThumbstickY - lastReading.RightThumbstickY) > .15
            || reading.LeftTrigger > .2 && lastReading.LeftTrigger <= .2
            || reading.RightTrigger > .2 && lastReading.RightTrigger <= .2)
            Activity?.Invoke();
        lastReading = reading;

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
    }
}
