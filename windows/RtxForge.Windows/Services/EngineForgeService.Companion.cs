using System.Text.Json.Nodes;
using RtxForge.Windows.Models;

namespace RtxForge.Windows.Services;

public sealed partial class EngineForgeService
{
    public async Task<EngineReview> ReviewGlobalControlsAsync(JsonObject changes, IProgress<PrepareProgress>? progress = null) =>
        ToReview(await CallAsync("global_review", changes, m => progress?.Report(Phase(m))));
    public async Task<EngineReview> ReviewOverlayUiAsync(JsonObject changes, IProgress<PrepareProgress>? progress = null) =>
        ToReview(await CallAsync("overlay_ui_review", changes, m => progress?.Report(Phase(m))));
    public async Task<EngineReview> ReviewOverlayPackagesAsync(IProgress<PrepareProgress>? progress = null) =>
        ToReview(await CallAsync("overlay_package_review", null, m => progress?.Report(Phase(m))));
    public Task ReloadCompanionPresetsAsync() => CallAsync("companion_reload");
    public async Task<IReadOnlyList<Game>> CompanionTargetsAsync()
    {
        var rows = await CallAsync("companion_targets") as JsonArray ?? [];
        return rows.OfType<JsonObject>().Select(row => new Game
        {
            Id = row["game"]!.GetValue<string>(), Location = row["game"]!.GetValue<string>(),
            Name = row["name"]?.GetValue<string>() ?? "Game", RuntimeProvider = row["runtime_provider"]?.GetValue<string>() ?? "skynizz",
            AppId = row["appid"]?.GetValue<string>(),
            Installed = true, EngineRow = row,
        }).ToArray();
    }
    public async Task<JsonObject> CompanionAsync(string action, Game game, JsonObject? changes = null, int pid = 0)
    {
        if (game.EngineRow is null) throw new InvalidOperationException("Rescan the library before opening live controls.");
        var parameters = new JsonObject { ["row"] = game.EngineRow.DeepClone() };
        if (changes is not null) parameters["changes"] = changes.DeepClone();
        if (pid > 0) parameters["pid"] = pid;
        return await CallAsync("companion_" + action, parameters) as JsonObject
            ?? throw new InvalidOperationException("The game controls did not return a response.");
    }

    public async Task<JsonObject> ActiveCompanionAsync(IEnumerable<Game> games, uint foreground, int retained)
    {
        var rows = new JsonArray(games.Where(g => g.EngineRow is not null)
            .Select(g => (JsonNode)g.EngineRow!.DeepClone()).ToArray());
        return await CallAsync("companion_active", new JsonObject
        {
            ["rows"] = rows, ["foreground_pid"] = foreground, ["retained_pid"] = retained
        }) as JsonObject ?? throw new InvalidOperationException("Game detection did not respond.");
    }
}
