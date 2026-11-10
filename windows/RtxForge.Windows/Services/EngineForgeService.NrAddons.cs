using System.Text.Json.Nodes;
using RtxForge.Windows.Models;

namespace RtxForge.Windows.Services;

/// <summary>Split Render over win_features.py nr_* methods: Environment and Character slots,
/// the Old/New model, and saved combos. Installs and removals come back as an EngineReview.</summary>
public sealed partial class EngineForgeService
{
    /// <summary>The catalog; for a game, its combos as they apply there and the world Skynizz provides (runtime_nr).</summary>
    public async Task<JsonObject> NrCatalogAsync(Game? game = null) =>
        await CallAsync("nr_catalog", game is null ? null : new JsonObject { ["row"] = Row(game) }) as JsonObject
            ?? throw new InvalidOperationException("Split Render is unavailable.");

    public async Task<JsonObject> SplitPresetCatalogAsync(string package) =>
        await CallAsync("nr_catalog", new JsonObject { ["package"] = package }) as JsonObject
            ?? throw new InvalidOperationException("Split Render presets are unavailable.");

    public async Task<JsonObject> CheckSplitPresetAsync(string package, JsonObject setup) =>
        await CallAsync("nr_check", new JsonObject { ["package"] = package, ["setup"] = setup.DeepClone() }) as JsonObject
            ?? throw new InvalidOperationException("The Split Render check is unavailable.");

    public async Task<JsonObject> SaveSplitPresetAsync(string package, string name, JsonObject setup) =>
        await CallAsync("nr_combo_save", new JsonObject { ["package"] = package, ["name"] = name, ["combo"] = setup.DeepClone() }) as JsonObject
            ?? throw new InvalidOperationException("The preset was not saved.");

    public async Task<JsonArray> PlanSplitRenderAsync(OperationReview review, JsonObject? choice, int revision)
    {
        var steps = review.Steps.Count > 0 ? review.Steps : new[] { review }.Where(r => r.Ready.Count > 0);
        var tokens = new JsonArray(steps.Concat(review.Supported.Select(offer => offer.Review))
            .Select(step => (JsonNode?)JsonValue.Create(step.Token)).ToArray());
        var result = await CallAsync("split_render_review", new JsonObject
        {
            ["tokens"] = tokens, ["choice"] = choice?.DeepClone(), ["revision"] = revision,
        });
        return result?["rows"] as JsonArray ?? throw new InvalidOperationException("Split Render could not be reviewed.");
    }

    public async Task<JsonObject> NrCheckAsync(Game game, JsonObject setup) =>
        await CallAsync("nr_check", new JsonObject { ["row"] = Row(game), ["setup"] = setup.DeepClone() }) as JsonObject
            ?? throw new InvalidOperationException("The Split Render check is unavailable.");

    public async Task<string> ApplyFeederCharacterAsync(Game game, string stamp, int passNumber, bool character, double? skin)
    {
        var result = await CallAsync("feeder_character_apply", new JsonObject
        {
            ["row"] = Row(game), ["stamp"] = stamp, ["pass_number"] = passNumber,
            ["character"] = character, ["skin"] = skin,
        });
        return result?["message"]?.GetValue<string>() ?? throw new InvalidOperationException("Could not save the Feeder NR pass role.");
    }

    public async Task<JsonObject> NrStatusAsync(Game game) =>
        await CallAsync("nr_status", new JsonObject { ["row"] = Row(game) }) as JsonObject ?? new JsonObject { ["installed"] = false };

    public async Task<EngineReview> ReviewNrAsync(Game game, JsonObject? setup, bool remove = false) =>
        ToReview(await CallAsync("nr_review", new JsonObject { ["row"] = Row(game), ["setup"] = setup?.DeepClone(), ["remove"] = remove }));

    public async Task<EngineReview> ReviewNrBatchAsync(IReadOnlyList<Game> games, JsonObject choice, IProgress<PrepareProgress> progress) =>
        ToReview(await CallAsync("nr_review", new JsonObject { ["rows"] = Rows(games), ["choice"] = choice.DeepClone() },
            message => progress.Report(Phase(message))));

    internal async Task<Dictionary<string, string>> MatchNrGamesAsync(Game[] games, JsonObject choice)
    {
        var matches = await CallAsync("nr_match", new JsonObject { ["rows"] = Rows(games), ["choice"] = choice.DeepClone() })
            as JsonArray ?? throw new InvalidOperationException("Split Render compatibility could not be checked.");
        return matches.OfType<JsonObject>().ToDictionary(match => games[match["index"]!.GetValue<int>()].Id,
            match => match["summary"]!.GetValue<string>());
    }

    public async Task<JsonObject> SaveNrComboAsync(string name, JsonObject combo) =>
        await CallAsync("nr_combo_save", new JsonObject { ["name"] = name, ["combo"] = combo.DeepClone() }) as JsonObject
            ?? throw new InvalidOperationException("The combo was not saved.");

    public async Task<JsonObject> DeleteNrComboAsync(string id) =>
        await CallAsync("nr_combo_delete", new JsonObject { ["id"] = id }) as JsonObject
            ?? throw new InvalidOperationException("The combo was not deleted.");
}
