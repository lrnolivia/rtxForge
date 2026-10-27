namespace RtxForge.Windows.Models;

internal static class OperationRoutes
{
    // Consecutive batches retain the user's alphabetical execution order while
    // sharing each route's package verification and model loading in the host.
    internal static IReadOnlyList<(string Route, IReadOnlyList<Game> Games)> Consecutive(
        IReadOnlyList<Game> games, Func<Game, string> route)
    {
        var groups = new List<(string Route, IReadOnlyList<Game> Games)>();
        List<Game>? current = null;
        string? previous = null;
        foreach (var game in games)
        {
            var key = route(game);
            if (current is null || key != previous)
            {
                current = []; groups.Add((key, current)); previous = key;
            }
            current.Add(game);
        }
        return groups;
    }
}
