using RtxForge.Windows.Models;

namespace RtxForge.Windows.Services;

public sealed partial class EngineForgeService
{
    public async Task LaunchOfflineAsync(Game game)
    {
        await CallAsync("launch_offline", new { row = game.EngineRow });
    }
}
