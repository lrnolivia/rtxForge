using System.Text.Json.Nodes;

namespace RtxForge.Windows.Services;

public sealed partial class EngineForgeService
{
    public async Task<JsonObject> OverlayStatusAsync() =>
        (await CallAsync("overlay_status"))?.AsObject()
        ?? throw new InvalidOperationException("Overlay Status could not be read. Refresh your library and try again.");
}
