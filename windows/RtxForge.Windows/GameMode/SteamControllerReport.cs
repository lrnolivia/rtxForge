using System.Buffers.Binary;

namespace RtxForge.Windows.GameMode;

// Valve Triton USB/BLE state layout, documented in SDL's
// src/joystick/hidapi/steam/controller_structs.h (TritonMTUNoQuat*).
// Read-only decoding: no feature reports or controller-mode changes.
internal static class SteamControllerReport
{
    internal static bool TryRightStick(ReadOnlySpan<byte> report, out double axis)
    {
        axis = 0;
        if (report.Length < 46 || report[0] is not (0x42 or 0x45 or 0x47)) return false;
        axis = BinaryPrimitives.ReadInt16LittleEndian(report[16..18]) / 32768d;
        return true;
    }
}
