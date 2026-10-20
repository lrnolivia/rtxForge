using System.IO.MemoryMappedFiles;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using RtxForge.Windows.Services;

if (!OperatingSystem.IsWindows()) throw new PlatformNotSupportedException("These checks use Windows named mappings.");
int checks = 0;
void Check(bool valid, string name) { if (!valid) throw new Exception(name); checks++; }
void Refuses<T>(Action action, string name) where T : Exception
{ try { action(); } catch (T) { checks++; return; } throw new Exception(name); }
int pid = Random.Shared.Next(1_000_000, int.MaxValue);
using var mapping = MemoryMappedFile.CreateNew("Local\\rtxForge.panel." + pid, NativePanelChannel.Size);
using var game = mapping.CreateViewAccessor();
void Header(int magic = NativePanelChannel.Magic, int version = 1, int? process = null)
{
    game.Write(0, magic); game.Write(4, version); game.Write(8, process ?? pid);
    game.Write(12, 0); game.Write(16, 0); game.Write(20, 1); game.Write(36, 1);
}
void Request(int sequence, byte[] body)
{
    game.Write(12, sequence | 1);
    game.WriteArray(NativePanelChannel.Header, body, 0, body.Length); game.Write(24, body.Length);
    Thread.MemoryBarrier(); game.Write(12, sequence);
}
void JsonRequest(int sequence, string text) => Request(sequence, Encoding.UTF8.GetBytes(text));
Header(0); Refuses<IOException>(() => new NativePanelChannel(pid), "accepts unknown magic");
Header(version: 2); Refuses<IOException>(() => new NativePanelChannel(pid), "accepts unknown protocol");
Header(process: pid - 1); Refuses<IOException>(() => new NativePanelChannel(pid), "accepts wrong process identity");
Header();
using var channel = new NativePanelChannel(pid);
Check(channel.IsValid && channel.Visible && channel.OwnsShortcut, "valid native owner is unavailable");
JsonRequest(2, "{\"op\":\"save\",\"changes\":{\"colour\":3.25},\"note\":\"é\"}");
Check(channel.TryRead(out var sequence, out var request) && sequence == 2 && request?["changes"]?["colour"]?.GetValue<double>() == 3.25
    && request["note"]?.GetValue<string>() == "é", "request bytes/units did not round trip");
channel.Reply(2, new JsonObject { ["message"] = "Saved · 4×", ["busy"] = false });
Check(game.ReadInt32(16) == 2 && game.ReadInt32(32) > 0 && (game.ReadInt32(32) & 1) == 0, "reply was not committed atomically");
var reply = new byte[game.ReadInt32(28)]; game.ReadArray(NativePanelChannel.Header + NativePanelChannel.Capacity, reply, 0, reply.Length);
Check(JsonNode.Parse(reply)?["message"]?.GetValue<string>() == "Saved · 4×", "reply UTF-8 did not round trip");
Check(!channel.TryRead(out _, out _), "acknowledged request repeated");
JsonRequest(3, "{\"op\":\"hello\"}"); Check(!channel.TryRead(out _, out _), "partial odd request read");
JsonRequest(4, "{\"op\":\"hello\"}");
Refuses<IOException>(() => channel.Reply(2, new()), "old reply overwrites a new request");
Refuses<IOException>(() => channel.Reply(3, new()), "odd sequence accepted");
game.Write(24, NativePanelChannel.Capacity + 1); Refuses<IOException>(() => channel.TryRead(out _, out _), "oversize request accepted");
game.Write(24, 0); Refuses<IOException>(() => channel.TryRead(out _, out _), "empty request accepted");
Request(6, [0xc3, 0x28]); Refuses<DecoderFallbackException>(() => channel.TryRead(out _, out _), "invalid UTF-8 accepted");
JsonRequest(8, "[]"); Refuses<IOException>(() => channel.TryRead(out _, out _), "non-object request accepted");
JsonRequest(10, new string('[', 20) + "0" + new string(']', 20));
Refuses<JsonException>(() => channel.TryRead(out _, out _), "excessive nesting accepted");
JsonRequest(12, "{\"op\":\"global-review\"}");
channel.Reply(12, new JsonObject { ["busy"] = true, ["message"] = "Preparing" });
using (var restarted = new NativePanelChannel(pid))
    Check(restarted.TryRead(out var retry, out var retryRequest) && retry == 12 && retryRequest?["op"]?.GetValue<string>() == "global-review",
        "restarted helper cannot recover an interrupted review");
var revision = game.ReadInt32(32);
channel.Reply(12, new JsonObject { ["busy"] = false, ["ready"] = true });
Check(game.ReadInt32(32) > revision, "final reply did not supersede progress");
using (var restarted = new NativePanelChannel(pid))
    Check(!restarted.TryRead(out _, out _), "restarted helper replays a finished operation");
revision = game.ReadInt32(32);
Refuses<IOException>(() => channel.Reply(12, new JsonObject { ["message"] = new string('x', NativePanelChannel.Capacity) }), "oversize review accepted");
Check(game.ReadInt32(32) == revision, "oversize review changed published response");
game.Write(20, 0); Check(!channel.Visible && channel.OwnsShortcut, "context reset drops native hotkey ownership");
game.Write(20, 1); Check(channel.Visible, "recreated context cannot reuse channel");
game.Write(0, 0); Check(!channel.IsValid && !channel.Visible && !channel.OwnsShortcut, "closed publisher still owns the shortcut");
Refuses<IOException>(() => channel.TryRead(out _, out _), "closed publisher accepts requests");
Refuses<IOException>(() => channel.Reply(12, new()), "closed publisher accepts replies");
Console.WriteLine($"PASS: {checks} native UI channel checks: identity, publication, UTF-8, bounds, depth, progress and graphics-context reuse.");
