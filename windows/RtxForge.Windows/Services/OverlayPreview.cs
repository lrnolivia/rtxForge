using System.Diagnostics;
using System.Runtime.InteropServices.WindowsRuntime;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.Win32;
using RtxForge.Windows.Models;
using Windows.Graphics.Imaging;

namespace RtxForge.Windows.Services;

/// <summary>Exact-game screenshots and an isolated, non-injected instance of the real renderer.</summary>
static class OverlayPreview
{
    public sealed record Screenshot(string Path, string Credit, float Crop=0);
    sealed record Scene(Game Game, Screenshot Photo);
    static readonly HttpClient Http = new(new HttpClientHandler { AllowAutoRedirect = false }) { Timeout = TimeSpan.FromSeconds(12) };
    static readonly string Cache = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "rtxForge", "overlay-preview");
    static string Key(Game game) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(game.Id))).ToLowerInvariant()[..24];
    static string? AppId(Game game) => game.AppId is { Length: > 0 } id && id.All(char.IsAsciiDigit) ? id : OverlayArtwork.SteamIdentity(game)?.Id;

    public static async Task<IReadOnlyList<Screenshot>> ScreenshotsAsync(Game game, bool online, CancellationToken cancel)
    {
        var local = new List<Screenshot>();
        var id = AppId(game);
        if (id is not null)
        {
            using var key = Registry.CurrentUser.OpenSubKey(@"Software\Valve\Steam");
            if (key?.GetValue("SteamPath") is string steam && Directory.Exists(Path.Combine(steam, "userdata")))
                foreach (var user in Directory.EnumerateDirectories(Path.Combine(steam, "userdata")).Take(32))
                {
                    var folder = Path.Combine(user, "760", "remote", id, "screenshots");
                    if (Directory.Exists(folder)) local.AddRange(Directory.EnumerateFiles(folder).Where(IsImage).Take(24).Select(path => new Screenshot(path, "Your Steam screenshot")));
                }
        }
        var target = Path.Combine(Cache, Key(game));
        if (Directory.Exists(target))
            local.AddRange(Directory.EnumerateFiles(target, "gameplay-*.jpg").Where(IsImage).Take(16).Select(path => new Screenshot(path, "Steam store screenshot · " + game.Name)));
        var qualifying = new List<(Screenshot Shot, ulong Pixels)>();
        foreach (var shot in local.Take(96))
        {
            cancel.ThrowIfCancellationRequested();
            var pixels = await ScenePixelsAsync(shot.Path);
            if (pixels > 0) qualifying.Add((shot, pixels));
        }
        if (qualifying.Count > 0 || !online || id is null)
            return qualifying.OrderByDescending(item => item.Pixels).Select(item => item.Shot).ToArray();

        // Use the original store image. Thumbnail dimensions are never enough
        // to qualify a scene, even when the filename looks like a full image.
        var json = await BytesAsync(new Uri($"https://store.steampowered.com/api/appdetails?appids={id}&l=english"), 2 * 1024 * 1024, cancel);
        using var doc = JsonDocument.Parse(json);
        if (!doc.RootElement.TryGetProperty(id, out var app) || !app.TryGetProperty("success", out var ok) || !ok.GetBoolean()
            || !app.TryGetProperty("data", out var data) || !data.TryGetProperty("screenshots", out var shots)) return [];
        var candidates = shots.EnumerateArray().ToArray();
        // Prefer gameplay frames but let the first image qualify when it is the only one.
        foreach (var shot in candidates.Skip(1).Concat(candidates.Take(1)).Take(8))
        {
            cancel.ThrowIfCancellationRequested();
            if (!shot.TryGetProperty("path_full", out var source) || !Uri.TryCreate(source.GetString(), UriKind.Absolute, out var uri) || !Allowed(uri)) continue;
            // Steam's "full" URL can still name a 1920×1080 rendition.
            var original = new UriBuilder(uri)
            {
                Path = Regex.Replace(uri.AbsolutePath, @"\.[0-9]{3,5}x[0-9]{3,5}(?=\.jpg$)", "", RegexOptions.IgnoreCase),
            }.Uri;
            byte[] bytes;
            try { bytes = await BytesAsync(original, 20 * 1024 * 1024, cancel); }
            catch (Exception error) when (error is IOException or HttpRequestException) { continue; }
            if (bytes.Length < 4 || bytes[0] != 0xff || bytes[1] != 0xd8) continue;
            using var image = new MemoryStream(bytes, writable: false);
            if (await ScenePixelsAsync(image) == 0) continue;
            Directory.CreateDirectory(target);
            var name = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant()[..16];
            var path = Path.Combine(target, $"gameplay-full-{name}.jpg");
            if (!File.Exists(path))
            {
                var temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
                try
                {
                    await File.WriteAllBytesAsync(temporary, bytes, cancel);
                    File.Move(temporary, path, overwrite: true);
                }
                finally { File.Delete(temporary); }
            }
            return [new(path, "Steam store screenshot · " + game.Name)];
        }
        return [];
    }

    public static async Task<ulong> ScenePixelsAsync(string path)
    {
        if (OverlayArtwork.Local(path) is null) return 0;
        try
        {
            await using var stream = File.OpenRead(path);
            return await ScenePixelsAsync(stream);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException) { return 0; }
    }

    static async Task<ulong> ScenePixelsAsync(Stream stream)
    {
        try
        {
            using var random = stream.AsRandomAccessStream();
            var image = await BitmapDecoder.CreateAsync(random);
            var width = image.OrientedPixelWidth;
            var height = image.OrientedPixelHeight;
            return width >= 2560 && height >= 1440 && width <= 8192 && height <= 8192 ? (ulong)width * height : 0;
        }
        catch (Exception error) when (error is ArgumentException or System.Runtime.InteropServices.COMException) { return 0; }
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
    public static string? Poster(Game game,ForgeSettings? settings=null)
    {
        settings??=ForgeSettings.Load();
        var media=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"rtxForge","state","desktop","media");
        return OverlayArtwork.Find(game,settings,media)??OverlayArtwork.Local(new SteamArtwork(false).Poster(game.AppId??OverlayArtwork.SteamIdentity(game)?.Id));
    }
    public static async Task<Process> StartAsync(string engineRoot, Game game, Screenshot shot, IReadOnlyList<Game>? library=null, global::Windows.UI.Color? initialAccent=null, string? preferencesPath=null)
    {
        var executable = new[] { Path.Combine(AppContext.BaseDirectory, "OverlayPreview", "OverlayPreview.exe"), Path.Combine(engineRoot, "windows", "out", "glass-overlay", "OverlayPreview.exe") }.FirstOrDefault(File.Exists)
            ?? throw new IOException("The native overlay preview is missing from this build.");
        var assets = Path.Combine(Path.GetDirectoryName(executable)!, "assets");
        if (!File.Exists(Path.Combine(assets, "overlay.rml"))) throw new IOException("The overlay preview assets are missing from this build.");
        if (await ScenePixelsAsync(shot.Path) == 0)
            throw new IOException("Choose a game with a 1440p or 4K screenshot to open the preview.");
        var color = initialAccent ?? (await OverlayAccent.ForGameAsync(game)).Color;
        var choices=(library??[]).Where(item=>item.Id!=game.Id && (game.AppId is null || item.AppId!=game.AppId)
            && !string.IsNullOrWhiteSpace(item.Name) && Encoding.UTF8.GetByteCount(item.Name)<=4096)
            .DistinctBy(item=>item.Id).Take(999).ToArray();
        Directory.CreateDirectory(Cache);
        var catalog=Path.Combine(Cache,"session-"+Guid.NewGuid().ToString("N")+".json");
        await File.WriteAllTextAsync(catalog,JsonSerializer.Serialize(new[]{game.Name}));
        var start = new ProcessStartInfo(executable) { UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = Path.GetDirectoryName(executable)!,
            RedirectStandardInput=true,RedirectStandardOutput=true,StandardInputEncoding=new UTF8Encoding(false),StandardOutputEncoding=new UTF8Encoding(false) };
        foreach (var arg in new[] { "--desktop-preview", "--assets", assets, "--font", Path.Combine(assets, "RobotoVariable.ttf"), "--background", shot.Path, "--game-title", game.Name,
            "--accent", $"#{color.R:X2}{color.G:X2}{color.B:X2}", "--width", "2560", "--height", "1440", "--parent-process", Environment.ProcessId.ToString(),"--game-catalog",catalog }) start.ArgumentList.Add(arg);
        if(Poster(game) is { } poster){start.ArgumentList.Add("--poster");start.ArgumentList.Add(poster);}
        start.ArgumentList.Add("--preferences");start.ArgumentList.Add(preferencesPath ?? GlassAppearance.FilePath);
        if(shot.Crop>0){start.ArgumentList.Add("--crop-left");start.ArgumentList.Add(shot.Crop.ToString(System.Globalization.CultureInfo.InvariantCulture));}
        try {
            var process=Process.Start(start) ?? throw new IOException("The overlay preview could not start.");
            _=ServeGamesAsync(process,choices,new(game,shot),catalog);return process;
        }catch{File.Delete(catalog);throw;}
    }
    // Only this isolated preview receives game choices. The injected overlay
    // continues to target its verified game session, never a picker selection.
    static async Task ServeGamesAsync(Process process, Game[] candidates, Scene initial, string catalog)
    {
        var games=new List<Scene>{initial};
        CancellationTokenSource? pending=null;Task current=Task.CompletedTask;var tasks=new List<Task>();
        using var writes=new SemaphoreSlim(1,1);
        using var lifetime=new CancellationTokenSource();
        async Task WriteAsync(object value,CancellationToken token)
        {
            await process.StandardInput.WriteLineAsync(JsonSerializer.Serialize(value).AsMemory(),token);
            await process.StandardInput.FlushAsync(token);
        }

        async Task DiscoverAsync()
        {
            var online=ForgeSettings.Load().OnlineArt;
            var options=new ParallelOptions { MaxDegreeOfParallelism=3, CancellationToken=lifetime.Token };
            await Parallel.ForEachAsync(candidates,options,async (game,token)=>
            {
                Screenshot? shot;
                using var lookup=CancellationTokenSource.CreateLinkedTokenSource(token);
                lookup.CancelAfter(TimeSpan.FromSeconds(30));
                try { shot=(await ScreenshotsAsync(game,online,lookup.Token)).FirstOrDefault(); }
                catch(OperationCanceledException) when(!token.IsCancellationRequested) { return; }
                catch(Exception error) when(error is IOException or HttpRequestException or JsonException or UnauthorizedAccessException) { return; }
                if(shot is null)return;

                await writes.WaitAsync(token);
                try
                {
                    int index;
                    lock(games) { index=games.Count; games.Add(new(game,shot)); }
                    await WriteAsync(new{available=game.Name,index},token);
                }
                finally { writes.Release(); }
            });
        }

        async Task ChangeAsync(Scene scene,int index,int request,CancellationTokenSource cancel)
        {
            bool Latest()=>ReferenceEquals(pending,cancel)&&!cancel.IsCancellationRequested;
            async Task SendAsync(object value){await writes.WaitAsync(cancel.Token);try{if(Latest())await WriteAsync(value,cancel.Token);}finally{writes.Release();}}
            try {
                var (game,shot)=scene;
                var palette=await OverlayAccent.ForGameAsync(game);var c=palette.Color;
                var accent=$"#{c.R:X2}{c.G:X2}{c.B:X2}";
                if(!File.Exists(shot.Path)){await SendAsync(new{request,index,error="This preview screenshot is no longer available."});return;}
                await SendAsync(new{request,index,accent,title=game.Name,path=shot.Path,crop=shot.Crop,poster=Poster(game)??""});
            }catch(OperationCanceledException){}
            catch(Exception error)when(error is IOException or HttpRequestException or JsonException or UnauthorizedAccessException or InvalidOperationException or ObjectDisposedException){
                try{await SendAsync(new{request,index,error="Could not load this game. Try another."});}catch(Exception sendError)when(sendError is IOException or InvalidOperationException or ObjectDisposedException or OperationCanceledException){}
            }
        }
        var discovery=DiscoverAsync();
        try {
            while(await process.StandardOutput.ReadLineAsync() is { } line){
                if(line.Length>1024||!line.StartsWith("{\"previewGame\":"))continue;
                using var json=JsonDocument.Parse(line);var root=json.RootElement;
                if(!root.TryGetProperty("previewGame",out var selected)||!selected.TryGetInt32(out var index)||index<0
                    ||!root.TryGetProperty("request",out var sequence)||!sequence.TryGetInt32(out var request)||request<1)continue;
                Scene scene;
                lock(games) { if(index>=games.Count)continue; scene=games[index]; }
                var previousCancel=pending;previousCancel?.Cancel();var cancel=new CancellationTokenSource();pending=cancel;
                var previous=current;current=ChangeAsync(scene,index,request,cancel);
                tasks.RemoveAll(task=>task.IsCompleted);tasks.Add(current);
                _=previous.ContinueWith(_=>previousCancel?.Dispose(),TaskScheduler.Default);
            }
        }catch(Exception error)when(error is IOException or JsonException or InvalidOperationException or ObjectDisposedException){}
        finally
        {
            lifetime.Cancel();
            pending?.Cancel();
            try { await discovery; }
            catch(Exception error) when(error is IOException or InvalidOperationException or OperationCanceledException) {}
            await Task.WhenAll(tasks);
            pending?.Dispose();
            try { File.Delete(catalog); } catch(IOException) {}
        }
    }
    public static void Close(Process? process)
    {
        if (process is null) return;
        try { if (!process.HasExited) process.CloseMainWindow(); } catch (InvalidOperationException) { }
        process.Dispose();
    }
}
