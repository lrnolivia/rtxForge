namespace RtxForge.Windows.Models;

/// <summary>
/// The hero credit line (developer · release), shared by the desktop Game page and Game Mode.
/// <see cref="Game.Developer"/> keeps the store's full list untouched; the line shows its
/// first-listed developer, with Ubisoft's studio names shown as Ubisoft. First-listed is the
/// store's order, not a verified lead studio, so the full list stays in the tooltip.
/// </summary>
public static class GameCredits
{
    // Company suffixes that follow a comma inside one name ("Valve, Inc."), not a second studio.
    static readonly HashSet<string> Suffixes = new(StringComparer.OrdinalIgnoreCase)
    {
        "Inc", "Inc.", "LLC", "L.L.C.", "Ltd", "Ltd.", "Limited", "Co.", "Co., Ltd.", "Corp", "Corp.", "Corporation",
        "GmbH", "S.A.", "SA", "AB", "Oy", "B.V.", "BV", "S.r.l.", "Srl", "Pty Ltd", "K.K.", "a.s.", "s.r.o.",
    };

    /// <summary>The developers in store order, as listed (comma or semicolon separated).</summary>
    public static IReadOnlyList<string> Developers(string? raw)
    {
        var names = new List<string>();
        foreach (var part in (raw ?? "").Split([',', ';'], StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries))
        {
            if (names.Count > 0 && Suffixes.Contains(part)) names[^1] += ", " + part;
            else if (!names.Contains(part, StringComparer.OrdinalIgnoreCase)) names.Add(part);
        }
        return names;
    }

    /// <summary>The first-listed developer; any Ubisoft studio reads as Ubisoft.</summary>
    public static string? Primary(string? raw)
    {
        var first = Developers(raw).FirstOrDefault();
        return first is not null && IsUbisoft(first) ? "Ubisoft" : first;
    }

    static bool IsUbisoft(string name) =>
        name.Equals("Ubisoft", StringComparison.OrdinalIgnoreCase)
        || name.StartsWith("Ubisoft ", StringComparison.OrdinalIgnoreCase);

    public static string Line(Game game) =>
        string.Join(" · ", new[] { Primary(game.Developer), game.Release }.Where(s => !string.IsNullOrWhiteSpace(s)));

    /// <summary>The full developer list when the line shortens it; otherwise none.</summary>
    public static string? Tooltip(Game game)
    {
        var all = Developers(game.Developer);
        if (all.Count == 0 || (all.Count == 1 && Primary(game.Developer) == all[0])) return null;
        return (all.Count == 1 ? "Developer: " : "Developers: ") + string.Join(", ", all);
    }
}
