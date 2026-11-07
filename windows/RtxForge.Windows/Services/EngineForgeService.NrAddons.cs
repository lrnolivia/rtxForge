using System.Text.Json.Nodes;
using RtxForge.Windows.Models;

namespace RtxForge.Windows.Services;

/// <summary>DLSS5 NR add-ons over win_features.py nr_* methods: Environment and Character slots,
/// the Old/New model, and saved combos. Installs and removals come back as an EngineReview.</summary>
public sealed partial class EngineForgeService
{
    public async Task<JsonObject> NrCatalogAsync() =>
        await CallAsync("nr_catalog") as JsonObject ?? throw new InvalidOperationException("NR add-ons are unavailable.");

    public async Task<JsonObject> NrCheckAsync(Game game, JsonObject setup) =>
        await CallAsync("nr_check", new JsonObject { ["row"] = Row(game), ["setup"] = setup.DeepClone() }) as JsonObject
            ?? throw new InvalidOperationException("The NR add-on check is unavailable.");

    public async Task<JsonObject> NrStatusAsync(Game game) =>
        await CallAsync("nr_status", new JsonObject { ["row"] = Row(game) }) as JsonObject ?? new JsonObject { ["installed"] = false };

    public async Task<EngineReview> ReviewNrAsync(Game game, JsonObject? setup, bool remove = false) =>
        ToReview(await CallAsync("nr_review", new JsonObject { ["row"] = Row(game), ["setup"] = setup?.DeepClone(), ["remove"] = remove }));

    public async Task<JsonObject> SaveNrComboAsync(string name, JsonObject combo) =>
        await CallAsync("nr_combo_save", new JsonObject { ["name"] = name, ["combo"] = combo.DeepClone() }) as JsonObject
            ?? throw new InvalidOperationException("The combo was not saved.");

    public async Task<JsonObject> DeleteNrComboAsync(string id) =>
        await CallAsync("nr_combo_delete", new JsonObject { ["id"] = id }) as JsonObject
            ?? throw new InvalidOperationException("The combo was not deleted.");
}
