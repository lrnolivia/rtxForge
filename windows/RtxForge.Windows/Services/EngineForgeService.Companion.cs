using System.Text.Json.Nodes;
using RtxForge.Windows.Models;

namespace RtxForge.Windows.Services;

public sealed partial class EngineForgeService
{
    public async Task<JsonObject> CompanionAsync(string action, Game game, JsonObject? changes = null)
    {
        if (game.EngineRow is null) throw new InvalidOperationException("Rescan the library before opening live controls.");
        var parameters = new JsonObject { ["row"] = game.EngineRow.DeepClone() };
        if (changes is not null) parameters["changes"] = changes.DeepClone();
        return await CallAsync("companion_" + action, parameters) as JsonObject
            ?? throw new InvalidOperationException("The game controls did not return a response.");
    }
}
