using System.Security.Cryptography;
using System.Text.Json;
using RtxForge.Windows.Services;

if (args.Contains("--desktop-parent"))
{
    File.WriteAllText(Environment.GetEnvironmentVariable("RTXFORGE_TEST_OUTPUT")!,JsonSerializer.Serialize(new {
        args,root=Environment.GetEnvironmentVariable("RTXFORGE_ROOT"), steam=Environment.GetEnvironmentVariable("SteamAppId"),
        readOnly=Environment.GetEnvironmentVariable("RTXFORGE_PREVIEW_READ_ONLY"),desktop=Environment.GetEnvironmentVariable("RTXFORGE_APP_EXE") }));
    Thread.Sleep(1500);return;
}
var root=Path.Combine(Path.GetTempPath(),"rtxforge-handoff-"+Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(root);
void Check(bool value,string message){if(!value)throw new Exception(message);}
void Reject(Action action){try{action();}catch(Exception error) when(error is InvalidOperationException or IOException){return;}throw new Exception("Invalid package accepted");}
try
{
    var bundle=Path.Combine(root,"app","game-mode");Directory.CreateDirectory(bundle);
    foreach(var file in new[]{"rtxforge-game-mode.exe","python/python.exe","bridge/engine_host.py","engine/scripts/desktop_service.py","screening/rtxforge-screenshot-screen.exe"})
    {var path=Path.Combine(bundle,file);Directory.CreateDirectory(Path.GetDirectoryName(path)!);File.WriteAllText(path,"fixture");}
    var exe=Path.Combine(bundle,"rtxforge-game-mode.exe");
    void Receipt(int protocol=1)=>File.WriteAllText(Path.Combine(bundle,"build.json"),JsonSerializer.Serialize(new{schema=2,dirty=false,desktopIntegration=protocol,native=new{sha256=Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(exe)))}}));
    Receipt();Check(GameModeLauncher.Resolve(Path.Combine(root,"app"),root)==exe,"Bundled UI must take precedence");
    Receipt(0);Reject(()=>GameModeLauncher.Validate(bundle));Receipt();
    File.AppendAllText(exe,"changed");Reject(()=>GameModeLauncher.Validate(bundle));Receipt();
    File.Delete(Path.Combine(bundle,"python/python.exe"));Reject(()=>GameModeLauncher.Validate(bundle));
    var output=Path.Combine(root,"child.json");Environment.SetEnvironmentVariable("RTXFORGE_TEST_OUTPUT",output);
    Environment.SetEnvironmentVariable("RTXFORGE_ROOT","must-not-leak");Environment.SetEnvironmentVariable("SteamAppId","123");
    using var child=GameModeLauncher.Start(Environment.ProcessPath!,true);
    child.WaitForExit(10000);using var observed=JsonDocument.Parse(File.ReadAllText(output));var result=observed.RootElement;
    Check(result.GetProperty("root").ValueKind==JsonValueKind.Null,"Parent engine root leaked");
    Check(result.GetProperty("steam").ValueKind==JsonValueKind.Null,"Steam session leaked");
    Check(result.GetProperty("readOnly").GetString()=="1","Read-only launch lost");
    Check(result.GetProperty("args")[1].GetString()==Environment.ProcessId.ToString(),"Wrong parent PID");
    Check(result.GetProperty("desktop").GetString()==Environment.ProcessPath,"Wrong Steam launch target");
    Console.WriteLine("Package rejection, bundled resolution, parent PID and launch environment passed.");
}
finally{Directory.Delete(root,true);}
