namespace RtxForge.Windows.Models;

/// <summary>The library view and its operation targets share the same filter.</summary>
public static class LibraryScope
{
    public static IEnumerable<Game> Filter(IEnumerable<Game> games, string filter, string query = "") => games
        .Where(g => filter switch
        {
            "available" => !g.Installed && !g.Blocked,
            "installed" => g.Installed,
            _ => true,
        })
        .Where(g => query.Length == 0 || g.Name.Contains(query, StringComparison.OrdinalIgnoreCase))
        .OrderBy(g => g.Name, StringComparer.CurrentCultureIgnoreCase);

    /// <summary>Explicit selection takes priority, including an empty selection in Game Mode.</summary>
    public static List<Game> Targets(IReadOnlyList<Game> games, string filter, string query,
        IReadOnlySet<string> selectedIds, bool selecting = false) =>
        selecting || selectedIds.Count > 0
            ? games.Where(g => selectedIds.Contains(g.Id)).ToList()
            : Filter(games, filter, query).ToList();
}
