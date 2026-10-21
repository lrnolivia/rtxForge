using RtxForge.Windows.Models;

namespace RtxForge.Windows.Services;

public sealed partial class EngineForgeService
{
    public async Task<AppStorage> AppStorageAsync()
    {
        var r = await CallAsync("storage_inventory");
        return new AppStorage(L(r, "bytes"), Objects(r?["categories"]).Select(c =>
            new AppStorageCategory(S(c, "title") ?? "", S(c, "detail") ?? "", L(c, "bytes"), B(c, "cache"))).ToList(), S(r, "warning"));
    }

    public async Task<EngineReview> ReviewStorageCleanupAsync() => ToReview(await CallAsync("storage_review"));
}
