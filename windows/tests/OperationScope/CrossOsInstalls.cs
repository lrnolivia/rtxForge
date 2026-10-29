using System.Runtime.CompilerServices;
using System.Text.Json.Nodes;
using RtxForge.Windows.Models;

static class CrossOsInstalls
{
    [ModuleInitializer]
    public static void Verify()
    {
        var both = new Game { Id = "shared", Name = "Shared drive", Installed = true, InstalledOn = "linux",
            InstalledOses = CrossOs.Read(JsonNode.Parse("[\"windows\",\"linux\",\"windows\",null,7,\"unknown\"]")) };
        if (!both.InstalledOses.SequenceEqual(["windows", "linux"]) || both.InstalledOnLinux || both.InstallLabel == "Set Up for Windows")
            throw new Exception("A dual-OS adaptation must retain native Windows actions and one mark per OS.");
        if (CrossOs.Tooltip(both.InstalledOses) != "Installed with rtxForge on Windows and Linux")
            throw new Exception("Dual-OS tooltip lost an OS.");
        foreach (var os in new[] { "windows", "linux" })
        {
            var legacy = new Game { Id = os, Name = os, Installed = true, InstalledOn = os };
            if (!legacy.InstalledOses.SequenceEqual([os]) || legacy.InstalledOnLinux != (os == "linux"))
                throw new Exception("Legacy install ownership must remain usable without installed_oses.");
        }
        both.Installed = false;
        if (both.InstalledOses.Count > 0 || both.InstalledOnLinux) throw new Exception("An available game must not display stale OS marks.");
        if (CrossOs.Read(JsonNode.Parse("{\"windows\":true}")).Count != 0) throw new Exception("Malformed OS metadata must not become install support.");
        var unknown = new Game { Id = "unknown", Name = "Unknown", Installed = true, InstalledOn = "unknown" };
        if (unknown.InstalledOses.Count != 0) throw new Exception("Unknown platforms must not acquire a mark.");
        Console.WriteLine("PASS: dual-OS actions, legacy fallback, malformed metadata, deduplication and available-game badges.");
    }
}
