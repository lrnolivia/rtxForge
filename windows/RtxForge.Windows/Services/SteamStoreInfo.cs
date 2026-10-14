using System.Text.Json;
using System.Text.RegularExpressions;
using RtxForge.Windows.Models;

namespace RtxForge.Windows.Services;

/// <summary>
/// Settings › Download game information: description, developer and release
/// date from the Steam store (library_media.LibraryMedia._enrich on Linux).
/// Steam games use their app id; other games use an exact-title store search,
/// so Non-Steam copies of Steam titles get the same information. Shared by
/// the desktop Game page and Game Mode Details.
/// </summary>
public static partial class SteamStoreInfo
{
    static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(8) };
    static readonly Dictionary<string, Task<bool>> Pending = [];

    /// <summary>Fills Summary / Developer / Release once per game; true when anything changed.</summary>
    public static Task<bool> FillAsync(Game game, bool enabled)
    {
        if (!enabled || (game.Summary is not null && game.Developer is not null && game.Release is not null))
            return Task.FromResult(false);
        if (!Pending.TryGetValue(game.Id, out var task)) Pending[game.Id] = task = LoadAsync(game);
        return task;
    }

    static async Task<bool> LoadAsync(Game game)
    {
        try
        {
            var appid = game.AppId ?? (game.Id.All(char.IsDigit) ? game.Id : null) ?? await SearchAsync(game.Name);
            if (appid is null) return false;
            var json = await Http.GetStringAsync($"https://store.steampowered.com/api/appdetails?appids={appid}&l=english");
            using var document = JsonDocument.Parse(json);
            var app = document.RootElement.GetProperty(appid);
            if (!app.GetProperty("success").GetBoolean()) return false;
            var data = app.GetProperty("data");
            var changed = false;
            if (game.Summary is null && data.TryGetProperty("short_description", out var description))
            {
                game.Summary = System.Net.WebUtility.HtmlDecode(Tags().Replace(description.GetString() ?? "", "")).Trim();
                changed = true;
            }
            if (game.Developer is null && data.TryGetProperty("developers", out var developers) && developers.GetArrayLength() > 0)
            {
                game.Developer = developers[0].GetString();
                changed = true;
            }
            if (game.Release is null && data.TryGetProperty("release_date", out var release) && release.TryGetProperty("date", out var date))
            {
                game.Release = date.GetString();
                changed = true;
            }
            return changed;
        }
        catch (Exception error) when (error is HttpRequestException or TaskCanceledException or JsonException
                                      or KeyNotFoundException or InvalidOperationException)
        {
            return false;
        }
    }

    /// <summary>Store search by title; only an exact (normalized) single match is trusted.</summary>
    static async Task<string?> SearchAsync(string name)
    {
        var json = await Http.GetStringAsync("https://store.steampowered.com/api/storesearch?l=english&cc=us&term=" + Uri.EscapeDataString(name));
        using var document = JsonDocument.Parse(json);
        if (!document.RootElement.TryGetProperty("items", out var items)) return null;
        var target = Normalize(name);
        var exact = items.EnumerateArray()
            .Where(i => i.TryGetProperty("name", out var n) && Normalize(n.GetString() ?? "") == target)
            .Select(i => i.GetProperty("id").ToString())
            .Where(id => id.All(char.IsDigit))
            .Distinct().ToList();
        return exact.Count == 1 ? exact[0] : null;
    }

    static string Normalize(string text) => NonAlphanumeric().Replace(text.ToLowerInvariant(), "");

    [GeneratedRegex("<[^>]+>")] private static partial Regex Tags();
    [GeneratedRegex("[^a-z0-9]")] private static partial Regex NonAlphanumeric();
}
