using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.Win32;
using RtxForge.Windows.Models;

namespace RtxForge.Windows.Services;

/// <summary>Exact-game screenshots and an isolated, non-injected instance of the real renderer.</summary>
static class OverlayPreview
{
    public sealed record Screenshot(string Path, string Credit, float Crop=0);
    static readonly HttpClient Http = new(new HttpClientHandler { AllowAutoRedirect = false }) { Timeout = TimeSpan.FromSeconds(12) };
    static readonly string Cache = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "rtxForge", "overlay-preview");
    static string Key(Game game) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(game.Id))).ToLowerInvariant()[..24];
    static string? AppId(Game game) => game.AppId is { Length: > 0 } id && id.All(char.IsAsciiDigit) ? id : OverlayArtwork.SteamIdentity(game)?.Id;

    public static async Task<IReadOnlyList<Screenshot>> ScreenshotsAsync(Game game, bool online, CancellationToken cancel)
    {
        var result = new List<Screenshot>();
        var id = AppId(game);
        if (id is not null)
        {
            using var key = Registry.CurrentUser.OpenSubKey(@"Software\Valve\Steam");
            if (key?.GetValue("SteamPath") is string steam && Directory.Exists(Path.Combine(steam, "userdata")))
                foreach (var user in Directory.EnumerateDirectories(Path.Combine(steam, "userdata")).Take(32))
                {
                    var folder = Path.Combine(user, "760", "remote", id, "screenshots");
                    if (Directory.Exists(folder)) result.AddRange(Directory.EnumerateFiles(folder).Where(IsImage).Take(100).Select(path => new Screenshot(path, "Your Steam screenshot")));
                }
        }
        var target = Path.Combine(Cache, Key(game));
        if (Directory.Exists(target)) result.AddRange(Directory.EnumerateFiles(target, "gameplay-*.jpg").Where(IsImage).Take(8).Select(path => new Screenshot(path, "Steam store screenshot · " + game.Name)));
        if (result.Count != 0 || !online || id is null) return result;
        // Identity comes from the scanned Steam app or its enclosing manifest. No title search.
        var json = await BytesAsync(new Uri($"https://store.steampowered.com/api/appdetails?appids={id}&l=english"), 2 * 1024 * 1024, cancel);
        using var doc = JsonDocument.Parse(json);
        if (!doc.RootElement.TryGetProperty(id, out var app) || !app.TryGetProperty("success", out var ok) || !ok.GetBoolean()
            || !app.TryGetProperty("data", out var data) || !data.TryGetProperty("screenshots", out var shots)) return result;
        Directory.CreateDirectory(target);
        // Store entry zero can be a promotional card. Prefer the next gameplay frame.
        var candidates=shots.EnumerateArray().ToArray();
        foreach (var shot in candidates.Skip(candidates.Length>1?1:0).Take(1))
        {
            cancel.ThrowIfCancellationRequested();
            if (!shot.TryGetProperty("path_thumbnail", out var source) || !Uri.TryCreate(source.GetString(), UriKind.Absolute, out var uri) || !Allowed(uri)) continue;
            var bytes = await BytesAsync(uri, 20 * 1024 * 1024, cancel);
            if (bytes.Length < 4 || bytes[0] != 0xff || bytes[1] != 0xd8) continue;
            var path = Path.Combine(target, $"gameplay-{result.Count:D2}.jpg");
            await File.WriteAllBytesAsync(path, bytes, cancel);
            result.Add(new(path, "Steam store screenshot · " + game.Name));
        }
        return result;
    }
    static bool IsImage(string path) => new[] { ".png", ".jpg", ".jpeg" }.Contains(Path.GetExtension(path).ToLowerInvariant()) && OverlayArtwork.Local(path) is not null;
    static bool Allowed(Uri uri) => uri.Scheme == "https" && string.IsNullOrEmpty(uri.UserInfo) && new[] { "store.steampowered.com", "shared.akamai.steamstatic.com", "shared.fastly.steamstatic.com", "cdn.akamai.steamstatic.com", "cdn.cloudflare.steamstatic.com" }.Contains(uri.Host);
    static async Task<byte[]> BytesAsync(Uri uri, int limit, CancellationToken cancel, int redirects = 0)
    {
        if (!Allowed(uri)) throw new IOException("Unsupported screenshot source.");
        using var response = await Http.GetAsync(uri, HttpCompletionOption.ResponseHeadersRead, cancel);
        if((int)response.StatusCode is >=300 and <400 && response.Headers.Location is { } location) {
            if(redirects>=4)throw new IOException("Too many screenshot redirects.");
            return await BytesAsync(location.IsAbsoluteUri?location:new Uri(uri,location),limit,cancel,redirects+1);
        }
        response.EnsureSuccessStatusCode();
        if (!Allowed(response.RequestMessage!.RequestUri!) || response.Content.Headers.ContentLength > limit) throw new IOException("Screenshot exceeds the supported size.");
        await using var input = await response.Content.ReadAsStreamAsync(cancel);
        using var output = new MemoryStream(); var buffer = new byte[32768]; int read;
        while ((read = await input.ReadAsync(buffer, cancel)) != 0) { if (output.Length + read > limit) throw new IOException("Screenshot exceeds the supported size."); output.Write(buffer, 0, read); }
        return output.ToArray();
    }
    public static async Task<Process> StartAsync(string engineRoot, Game game, Screenshot shot, IReadOnlyList<Game>? library=null, global::Windows.UI.Color? initialAccent=null)
    {
        var executable = new[] { Path.Combine(AppContext.BaseDirectory, "OverlayPreview", "OverlayPreview.exe"), Path.Combine(engineRoot, "windows", "out", "glass-overlay", "OverlayPreview.exe") }.FirstOrDefault(File.Exists)
            ?? throw new IOException("The native overlay preview is missing from this build.");
        var assets = Path.Combine(Path.GetDirectoryName(executable)!, "assets");
        if (!File.Exists(Path.Combine(assets, "overlay.rml"))) throw new IOException("The overlay preview assets are missing from this build.");
        var color = initialAccent ?? (await OverlayAccent.ForGameAsync(game)).Color;
        var choices=new[]{game}.Concat(library??[]).DistinctBy(g=>g.Id).Take(1000).ToArray();
        Directory.CreateDirectory(Cache);
        var catalog=Path.Combine(Cache,"session-"+Guid.NewGuid().ToString("N")+".json");
        await File.WriteAllTextAsync(catalog,JsonSerializer.Serialize(choices.Select(g=>g.Name)));
        var start = new ProcessStartInfo(executable) { UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = Path.GetDirectoryName(executable)!,
            RedirectStandardInput=true,RedirectStandardOutput=true,StandardInputEncoding=new UTF8Encoding(false),StandardOutputEncoding=new UTF8Encoding(false) };
        foreach (var arg in new[] { "--desktop-preview", "--assets", assets, "--font", Path.Combine(assets, "RobotoVariable.ttf"), "--background", shot.Path, "--game-title", game.Name,
            "--accent", $"#{color.R:X2}{color.G:X2}{color.B:X2}", "--width", "2560", "--height", "1440", "--parent-process", Environment.ProcessId.ToString(),"--game-catalog",catalog }) start.ArgumentList.Add(arg);
        if(shot.Crop>0){start.ArgumentList.Add("--crop-left");start.ArgumentList.Add(shot.Crop.ToString(System.Globalization.CultureInfo.InvariantCulture));}
        try {
            var process=Process.Start(start) ?? throw new IOException("The overlay preview could not start.");
            _=ServeGamesAsync(process,choices,game,shot,catalog);return process;
        }catch{File.Delete(catalog);throw;}
    }
    // Only this isolated preview receives game choices. The injected overlay
    // continues to target its verified game session, never a picker selection.
    static async Task ServeGamesAsync(Process process, Game[] games, Game initial, Screenshot initialShot, string catalog)
    {
        CancellationTokenSource? pending=null;Task current=Task.CompletedTask;var tasks=new List<Task>();
        using var writes=new SemaphoreSlim(1,1);
        async Task ChangeAsync(int index,int request,CancellationTokenSource cancel)
        {
            bool Latest()=>ReferenceEquals(pending,cancel)&&!cancel.IsCancellationRequested;
            async Task SendAsync(object value){await writes.WaitAsync(cancel.Token);try{if(Latest()){await process.StandardInput.WriteLineAsync(JsonSerializer.Serialize(value));await process.StandardInput.FlushAsync();}}finally{writes.Release();}}
            try {
                var game=games[index];var palette=await OverlayAccent.ForGameAsync(game);var c=palette.Color;
                var accent=$"#{c.R:X2}{c.G:X2}{c.B:X2}";
                await SendAsync(new{request,index,accent});
                var shot=game.Id==initial.Id?initialShot:(await ScreenshotsAsync(game,ForgeSettings.Load().OnlineArt,cancel.Token)).FirstOrDefault();
                if(shot is null){await SendAsync(new{request,index,error="No screenshot available for this game."});return;}
                await SendAsync(new{request,index,accent,title=game.Name,path=shot.Path,crop=shot.Crop});
            }catch(OperationCanceledException){}
            catch(Exception error)when(error is IOException or HttpRequestException or JsonException or UnauthorizedAccessException or InvalidOperationException or ObjectDisposedException){
                try{await SendAsync(new{request,index,error="Could not load this game. Try another."});}catch(Exception sendError)when(sendError is IOException or InvalidOperationException or ObjectDisposedException or OperationCanceledException){}
            }
        }
        try {
            while(await process.StandardOutput.ReadLineAsync() is { } line){
                if(line.Length>1024||!line.StartsWith("{\"previewGame\":"))continue;
                using var json=JsonDocument.Parse(line);var root=json.RootElement;
                if(!root.TryGetProperty("previewGame",out var selected)||!selected.TryGetInt32(out var index)||index<0||index>=games.Length
                    ||!root.TryGetProperty("request",out var sequence)||!sequence.TryGetInt32(out var request)||request<1)continue;
                var previousCancel=pending;previousCancel?.Cancel();var cancel=new CancellationTokenSource();pending=cancel;
                var previous=current;current=ChangeAsync(index,request,cancel);
                tasks.RemoveAll(task=>task.IsCompleted);tasks.Add(current);
                _=previous.ContinueWith(_=>previousCancel?.Dispose(),TaskScheduler.Default);
            }
        }catch(Exception error)when(error is IOException or JsonException or InvalidOperationException or ObjectDisposedException){}
        finally{pending?.Cancel();await Task.WhenAll(tasks);pending?.Dispose();try{File.Delete(catalog);}catch(IOException){}}
    }
    public static void Close(Process? process)
    {
        if (process is null) return;
        try { if (!process.HasExited) process.CloseMainWindow(); } catch (InvalidOperationException) { }
        process.Dispose();
    }
}
