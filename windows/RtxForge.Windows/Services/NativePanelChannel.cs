using System.IO.MemoryMappedFiles;
using System.Text;
using System.Text.Json.Nodes;

namespace RtxForge.Windows.Services;

/// <summary>Bounded local-session UI messages; game identity is verified before opening.</summary>
internal sealed class NativePanelChannel : IDisposable
{
    public const int Magic = 0x50465852, Capacity = 32768, Header = 64, Size = Header + Capacity * 2;
    readonly MemoryMappedFile mapping;
    readonly MemoryMappedViewAccessor view;
    readonly int pid;
    int lastRead;
    static readonly UTF8Encoding Utf8 = new(false, true);
    public NativePanelChannel(int pid)
    {
        this.pid = pid;
        mapping = MemoryMappedFile.OpenExisting("Local\\rtxForge.panel." + pid, MemoryMappedFileRights.ReadWrite);
        try
        {
            view = mapping.CreateViewAccessor(0, Size, MemoryMappedFileAccess.ReadWrite);
            if (view.ReadInt32(0) != Magic || view.ReadInt32(4) != 1 || view.ReadInt32(8) != pid)
                throw new IOException("Unsupported in-game panel channel.");
        }
        catch { view?.Dispose(); mapping.Dispose(); throw; }
    }
    public bool IsValid => view.ReadInt32(0) == Magic && view.ReadInt32(4) == 1 && view.ReadInt32(8) == pid;
    public bool Visible => IsValid && view.ReadInt32(20) == 1;
    public bool OwnsShortcut => IsValid && view.ReadInt32(36) == 1;
    void EnsureValid() { if (!IsValid) throw new IOException("The game panel channel has closed."); }
    public bool TryRead(out int sequence, out JsonObject? message)
    {
        EnsureValid(); sequence = view.ReadInt32(12); message = null;
        if (sequence <= 0 || (sequence & 1) != 0 || sequence == lastRead) return false;
        if (sequence == view.ReadInt32(16) && CompletedReply(sequence)) { lastRead = sequence; return false; }
        var length = view.ReadInt32(24);
        if (length <= 0 || length > Capacity) throw new IOException("The panel request is too large.");
        var bytes = new byte[length]; view.ReadArray(Header, bytes, 0, length);
        Thread.MemoryBarrier();
        if (sequence != view.ReadInt32(12)) return false;
        message = JsonNode.Parse(Utf8.GetString(bytes), documentOptions: new() { MaxDepth = 16 }) as JsonObject
            ?? throw new IOException("Invalid panel request.");
        lastRead = sequence;
        return true;
    }
    bool CompletedReply(int sequence)
    {
        // A restarted helper may finish an interrupted read/save/review. An old
        // apply-review has no live review token and is refused by the coordinator.
        var revision = view.ReadInt32(32);
        var length = view.ReadInt32(28);
        if (revision <= 0 || (revision & 1) != 0 || length <= 0 || length > Capacity) return false;
        var bytes = new byte[length]; view.ReadArray(Header + Capacity, bytes, 0, length);
        Thread.MemoryBarrier();
        if (revision != view.ReadInt32(32) || sequence != view.ReadInt32(16)) return false;
        try { return JsonNode.Parse(Utf8.GetString(bytes), documentOptions: new() { MaxDepth = 16 })?["busy"]?.GetValue<bool>() != true; }
        catch (Exception error) when (error is System.Text.Json.JsonException or DecoderFallbackException or InvalidOperationException) { return false; }
    }
    public void Reply(int sequence, JsonObject result)
    {
        EnsureValid();
        if (sequence <= 0 || (sequence & 1) != 0 || view.ReadInt32(12) != sequence)
            throw new IOException("The panel request changed before its reply.");
        var bytes = Utf8.GetBytes(result.ToJsonString());
        if (bytes.Length > Capacity) throw new IOException("This review is too large for the game panel. Review it in rtxForge.");
        var revision = view.ReadInt32(32);
        view.Write(32, (revision + 1) | 1); view.Write(16, sequence | 1);
        view.WriteArray(Header + Capacity, bytes, 0, bytes.Length); view.Write(28, bytes.Length);
        Thread.MemoryBarrier(); view.Write(16, sequence); view.Write(32, ((revision + 1) | 1) + 1);
    }
    public void Dispose() { view.Dispose(); mapping.Dispose(); }
}
