using RtxForge.Windows.Models;
using RtxForge.Windows.Services;

var tests = 0;
void EqualIds(string name, IEnumerable<Game> actual, params string[] expected)
{
    var ids = actual.Select(g => g.Id).Order().ToArray();
    if (!ids.SequenceEqual(expected.Order()))
        throw new Exception($"{name}: expected [{string.Join(", ", expected)}], got [{string.Join(", ", ids)}]");
    tests++;
}

Game[] library =
[
    new() { Id = "new-a", Name = "Matching new game" },
    new() { Id = "new-b", Name = "Another new game" },
    new() { Id = "installed-a", Name = "Matching installed game", Installed = true },
    new() { Id = "installed-b", Name = "Other installed game", Installed = true },
    new() { Id = "blocked", Name = "Matching blocked game", Blocked = true },
];
var none = new HashSet<string>();
EqualIds("Available excludes installed and unsupported games", LibraryScope.Targets(library, "available", "", none), "new-a", "new-b");
EqualIds("Installed view limits restoration", LibraryScope.Targets(library, "installed", "", none), "installed-a", "installed-b");
EqualIds("Available search", LibraryScope.Targets(library, "available", "mAtChInG", none), "new-a");
EqualIds("Installed search", LibraryScope.Targets(library, "installed", "matching", none), "installed-a");
EqualIds("No search results stays empty", LibraryScope.Targets(library, "all", "missing", none));
EqualIds("Empty library stays empty", LibraryScope.Targets([], "all", "", none));
EqualIds("Explicit games override the view", LibraryScope.Targets(library, "available", "matching", new HashSet<string> { "new-b", "installed-b" }), "new-b", "installed-b");
EqualIds("Game Mode selection without checks stays empty", LibraryScope.Targets(library, "all", "", none, selecting: true));
EqualIds("Removed selected game never falls back to the view", LibraryScope.Targets(library, "all", "", new HashSet<string> { "removed" }));
EqualIds("Partial stale selection keeps only remaining targets", LibraryScope.Targets(library, "all", "", new HashSet<string> { "removed", "new-b" }), "new-b");
EqualIds("Available restoration has no targets", LibraryScope.Targets(library, "available", "", none).Where(g => g.Installed));
EqualIds("All view retains supported and blocked rows", LibraryScope.Filter(library, "all"), library.Select(g => g.Id).ToArray());

// Selection is keyed by stable identity, even when a rescan replaces the objects or names collide.
Game[] refreshed = [new() { Id = "new-a", Name = "Same name" }, new() { Id = "new-b", Name = "Same name" }];
EqualIds("Refreshed objects and duplicate names", LibraryScope.Targets(refreshed, "all", "", new HashSet<string> { "new-b" }), "new-b");

// Exercise the actual preview review/execute service. No game files or settings are written.
var service = new PreviewForgeService();
var games = await service.ScanAsync();
var originallyInstalled = games.Where(g => g.Installed).Select(g => g.Id).ToArray();
var chosen = new HashSet<string> { "3321460", "1449110" };
var targets = LibraryScope.Targets(games, "available", "", chosen);
var tuning = new Tuning(1.0, 0.5, "4");
var checkedIds = new List<string>();
var review = await service.PrepareAsync("install", targets, tuning, "mfg-only");
EqualIds("Install review contains only the two selected games", review.Ready.Select(r => r.Game), chosen.ToArray());
await service.ExecuteAsync(review, new InlineProgress<OperationStep>(p => checkedIds.Add(p.Game.Id)));
if (checkedIds.Count != 2 || checkedIds.Any(id => !chosen.Contains(id))) throw new Exception("Install visited an unselected game");
tests++;
EqualIds("Install preserves the rest of the library", games.Where(g => g.Installed), originallyInstalled.Concat(chosen).ToArray());

checkedIds.Clear();
var restore = LibraryScope.Targets(games, "installed", "", new HashSet<string> { "3321460" }).Where(g => g.Installed).ToList();
review = await service.PrepareAsync("uninstall", restore, tuning, "mfg-only");
EqualIds("Restore review contains only the selected game", review.Ready.Select(r => r.Game), "3321460");
await service.ExecuteAsync(review, new InlineProgress<OperationStep>(p => checkedIds.Add(p.Game.Id)));
if (!checkedIds.SequenceEqual(["3321460"])) throw new Exception("Restore visited an unselected game");
tests++;
EqualIds("Restore preserves other installs", games.Where(g => g.Installed), originallyInstalled.Append("1449110").ToArray());

// Removing an entry is path-specific, reversible and independent of game files.
var librarySettings = new ForgeSettings();
var sameName = new[]
{
    new Game { Id = "live", Name = "PRAGMATA", Location = @"G:\SteamLibrary\steamapps\common\PRAGMATA" },
    new Game { Id = "pinned", Name = "PRAGMATA", Location = @"G:\SteamLibrary\PinnedBuilds\PRAGMATA-22357085" },
};
LibraryLocations.Remove(librarySettings, [sameName[1]]);
EqualIds("Remove affects only the selected installation", LibraryLocations.Visible(sameName, librarySettings.RemovedGames), "live");
var reloaded = librarySettings.Clone();
EqualIds("Removed entry survives settings reload/rescan", LibraryLocations.Visible(sameName, reloaded.RemovedGames), "live");
LibraryLocations.Show(reloaded, sameName[1].Location.ToLowerInvariant());
EqualIds("Show again restores the same installation", LibraryLocations.Visible(sameName, reloaded.RemovedGames), "live", "pinned");
LibraryLocations.Remove(librarySettings, [sameName[1], sameName[1]]);
if (librarySettings.RemovedGames.Count != 1) throw new Exception("Duplicate removal records");
tests++;
Console.WriteLine($"PASS: {tests} scope and library visibility checks (no game writes).");

sealed class InlineProgress<T>(Action<T> report) : IProgress<T>
{
    public void Report(T value) => report(value);
}
