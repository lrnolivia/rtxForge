using System.Runtime.InteropServices;
using System.Text;

namespace RtxForge.Windows.GameMode;

/// <summary>Observes foreground Valve keyboard/mouse activity without consuming it.</summary>
internal sealed class ControllerRawInput : IDisposable
{
    readonly nint window;
    readonly Subclass callback;
    readonly Action<string> activity;
    readonly Dictionary<nint, (string Family, int? Slot)?> devices = [];
    readonly Dictionary<int, string> slots = [];
    readonly Func<bool> foreground;
    public bool LegacyInputActive => Environment.TickCount64 < legacyUntil;
    long legacyUntil;
    public string? SlotFamily(int slot) => slots.GetValueOrDefault(slot);

    public ControllerRawInput(nint window, Func<bool> foreground, Action<string> activity)
    {
        this.window = window; this.foreground = foreground; this.activity = activity;
        callback = WindowProc;
        if (!SetWindowSubclass(window, callback, 0x52584643, 0)) return;
        // No INPUTSINK or NOLEGACY: input remains local to the focused app and
        // Windows still delivers normal keyboard/mouse messages to its controls.
        RawDevice[] registrations = [new(1, 6, 0x2000, window), new(1, 2, 0x2000, window)];
        RegisterRawInputDevices(registrations, (uint)registrations.Length, (uint)Marshal.SizeOf<RawDevice>());
        RefreshSlots();
    }

    (string Family, int? Slot)? Device(nint handle, uint type)
    {
        if (devices.TryGetValue(handle, out var known)) return known;
        uint count = 0;
        GetRawInputDeviceInfo(handle, 0x20000007, null, ref count);
        if (count is 0 or > 2048) return devices[handle] = null;
        var name = new StringBuilder((int)count);
        if (GetRawInputDeviceInfo(handle, 0x20000007, name, ref count) == uint.MaxValue) return devices[handle] = null;
        var identity = ControllerDevice.Identify(name.ToString(), type);
        if (identity is { Slot: int slot } value) slots[slot] = value.Family;
        return devices[handle] = identity;
    }

    void RefreshSlots()
    {
        devices.Clear(); slots.Clear();
        uint count = 0;
        if (GetRawInputDeviceList(null, ref count, (uint)Marshal.SizeOf<DeviceList>()) == uint.MaxValue || count > 512) return;
        var list = new DeviceList[count];
        if (GetRawInputDeviceList(list, ref count, (uint)Marshal.SizeOf<DeviceList>()) == uint.MaxValue) return;
        foreach (var device in list.Take((int)count)) Device(device.Handle, device.Type);
    }

    nint WindowProc(nint hwnd, uint message, nuint wparam, nint lparam, nuint id, nuint data)
    {
        if (message == 0xFE) RefreshSlots();
        if (message == 0xFF && foreground())
        {
            uint size = 0, headerSize = (uint)Marshal.SizeOf<Header>();
            if (GetRawInputData(lparam, 0x10000003, 0, ref size, headerSize) != uint.MaxValue && size >= headerSize && size <= 65536)
            {
                var buffer = Marshal.AllocHGlobal((int)size);
                try
                {
                    if (GetRawInputData(lparam, 0x10000003, buffer, ref size, headerSize) == size)
                    {
                        var header = Marshal.PtrToStructure<Header>(buffer);
                        var body = buffer + (int)headerSize;
                        // Key make only; mouse clicks/wheel or meaningful motion.
                        bool used = header.Type == 1 && size >= headerSize + 16 && (Marshal.ReadInt16(body, 2) & 1) == 0
                            || header.Type == 0 && size >= headerSize + 24 && (Marshal.ReadInt16(body, 4) != 0
                                || Math.Abs((long)Marshal.ReadInt32(body, 12)) + Math.Abs((long)Marshal.ReadInt32(body, 16)) >= 3);
                        if (used && Device(header.Device, header.Type) is { } identity)
                        {
                            legacyUntil = Environment.TickCount64 + 500;
                            activity(identity.Family);
                        }
                    }
                }
                finally { Marshal.FreeHGlobal(buffer); }
            }
        }
        return DefSubclassProc(hwnd, message, wparam, lparam);
    }

    public void Dispose()
    {
        RemoveWindowSubclass(window, callback, 0x52584643);
        RawDevice[] remove = [new(1, 6, 1, 0), new(1, 2, 1, 0)];
        RegisterRawInputDevices(remove, (uint)remove.Length, (uint)Marshal.SizeOf<RawDevice>());
    }

    [StructLayout(LayoutKind.Sequential)] readonly record struct RawDevice(ushort Page, ushort Usage, uint Flags, nint Window);
    [StructLayout(LayoutKind.Sequential)] struct DeviceList { public nint Handle; public uint Type; }
    [StructLayout(LayoutKind.Sequential)] struct Header { public uint Type, Size; public nint Device; public nuint WParam; }
    delegate nint Subclass(nint hwnd, uint message, nuint wparam, nint lparam, nuint id, nuint data);
    [DllImport("comctl32.dll")] static extern bool SetWindowSubclass(nint hwnd, Subclass callback, nuint id, nuint data);
    [DllImport("comctl32.dll")] static extern bool RemoveWindowSubclass(nint hwnd, Subclass callback, nuint id);
    [DllImport("comctl32.dll")] static extern nint DefSubclassProc(nint hwnd, uint message, nuint wparam, nint lparam);
    [DllImport("user32.dll")] static extern bool RegisterRawInputDevices(RawDevice[] devices, uint count, uint size);
    [DllImport("user32.dll")] static extern uint GetRawInputData(nint raw, uint command, nint buffer, ref uint size, uint headerSize);
    [DllImport("user32.dll", CharSet = CharSet.Unicode, EntryPoint = "GetRawInputDeviceInfoW")] static extern uint GetRawInputDeviceInfo(nint device, uint command, StringBuilder? data, ref uint size);
    [DllImport("user32.dll")] static extern uint GetRawInputDeviceList([Out] DeviceList[]? list, ref uint count, uint size);
}
