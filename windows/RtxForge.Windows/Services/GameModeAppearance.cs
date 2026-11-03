using System.Diagnostics;
using System.Text;
using System.Text.Json.Nodes;

namespace RtxForge.Windows.Services;

/// <summary>The same validated preference file used by the native Game Mode UI.</summary>
internal sealed class GameModeAppearance(string engineRoot)
{
    public static JsonObject Defaults => new() { ["theme"]="clear", ["tint"]=true, ["tintStrength"]=50,
        ["accentMode"]="custom", ["accent"]="#d8d5ce", ["motion"]=true, ["text"]="standard",
        ["navigation"]="top", ["detailsNavigation"]="sidebar", ["scale"]="auto", ["libraryScale"]=100,
        ["appearanceDefaultsVersion"]=2, ["libraryScaleVersion"]=1, ["detailsNavigationVersion"]=1 };

    public Task<JsonObject?> ReadAsync() => RunAsync("read");
    public async Task<JsonObject> WriteAsync(JsonObject value) =>
        await RunAsync("write", value) ?? throw new InvalidOperationException("Game Mode appearance was not saved.");

    async Task<JsonObject?> RunAsync(string operation, JsonObject? value = null)
    {
        var helper = Path.Combine(engineRoot, "scripts", "game_mode_appearance.py");
        if (!File.Exists(helper)) throw new IOException("Install the complete current build to edit Game Mode appearance.");
        var python = Path.Combine(AppContext.BaseDirectory, "python", "python.exe");
        if (!File.Exists(python)) python = "python";
        var start = new ProcessStartInfo(python) { UseShellExecute=false, CreateNoWindow=true,
            RedirectStandardInput=true, RedirectStandardOutput=true, RedirectStandardError=true,
            StandardInputEncoding=new UTF8Encoding(false), StandardOutputEncoding=Encoding.UTF8, StandardErrorEncoding=Encoding.UTF8 };
        foreach (var argument in new[] { "-I", "-B", helper, operation }) start.ArgumentList.Add(argument);
        using var process = Process.Start(start) ?? throw new IOException("The appearance preferences could not be opened.");
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(15));
        var output = process.StandardOutput.ReadToEndAsync(timeout.Token);
        var error = process.StandardError.ReadToEndAsync(timeout.Token);
        try
        {
            if (value is not null) await process.StandardInput.WriteAsync(value.ToJsonString().AsMemory(), timeout.Token);
            process.StandardInput.Close(); await process.WaitForExitAsync(timeout.Token);
            var text = await output; var problem = await error;
            if (process.ExitCode != 0) throw new InvalidOperationException(string.IsNullOrWhiteSpace(problem) ? "Appearance could not be saved." : problem.Trim());
            if (text.Length > 1700000) throw new IOException("The appearance response is too large.");
            return JsonNode.Parse(text)?.AsObject();
        }
        catch (OperationCanceledException) { if (!process.HasExited) process.Kill(); throw new IOException("Game Mode appearance timed out. Try again."); }
    }
}
