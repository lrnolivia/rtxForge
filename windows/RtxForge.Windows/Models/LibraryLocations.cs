namespace RtxForge.Windows.Models;

/// <summary>Visibility is per installation path; removing an entry never touches game files.</summary>
public static class LibraryLocations
{
    public static string Identity(string path) => Path.TrimEndingDirectorySeparator(Path.GetFullPath(path));

    public static bool Same(string first, string second) =>
        string.Equals(Identity(first), Identity(second), StringComparison.OrdinalIgnoreCase);

    public static List<Game> Visible(IEnumerable<Game> games, IEnumerable<string> removed)
    {
        var hidden = new HashSet<string>(removed.Select(Identity), StringComparer.OrdinalIgnoreCase);
        return games.Where(game => !hidden.Contains(Identity(game.Location))).ToList();
    }

    public static void Remove(ForgeSettings settings, IEnumerable<Game> games)
    {
        foreach (var game in games)
            if (!settings.RemovedGames.Any(path => Same(path, game.Location)))
                settings.RemovedGames.Add(Identity(game.Location));
    }

    public static void Show(ForgeSettings settings, string path) =>
        settings.RemovedGames.RemoveAll(item => Same(item, path));
}
