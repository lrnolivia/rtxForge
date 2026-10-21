using System.Text.Json.Nodes;

namespace RtxForge.Windows.Models;

/// <summary>Saved MFG intent shared by both native preset editors; not a report of live frame generation.</summary>
public sealed class MfgPreset
{
    public static readonly string[] Modes = ["Auto", "Custom", "Dynamic"];
    public static readonly int[] Multipliers = [2, 3, 4, 5, 6];
    public bool Enabled { get; private set; }
    public int Mode { get; private set; }
    public int Multiplier { get; private set; } = 2;
    public string Description => !Enabled ? "Multi-Frame Generation is off."
        : Mode == 0 ? "Follows the game's frame generation setting."
        : Mode == 1 ? "Uses a fixed multiplier. Enable frame generation in the game."
        : "Uses up to the selected multiplier. Requires a game and driver with Dynamic MFG support.";

    public MfgPreset(JsonObject values)
    {
        var ratio = FeatureControlSchema.Read(values["multiplier"], -1);
        Enabled = ratio != 0;
        Mode = !Enabled ? (int)FeatureControlSchema.Read(values["mfg_saved_mode"])
            : FeatureControlSchema.Read(values["dynamic_mfg"]) != 0 && ratio > 0 ? 2 : ratio >= 2 ? 1 : 0;
        Multiplier = ratio >= 2 ? (int)ratio : (int)FeatureControlSchema.Read(values["mfg_saved_multiplier"], 2);
    }
    public void SetEnabled(bool enabled) => Enabled = enabled;
    public void SetMode(int mode)
    {
        if (mode < 0 || mode >= Modes.Length) throw new ArgumentOutOfRangeException(nameof(mode));
        Mode = mode;
    }
    public void SetMultiplier(int multiplier)
    {
        if (!Multipliers.Contains(multiplier)) throw new ArgumentOutOfRangeException(nameof(multiplier));
        Multiplier = multiplier;
    }
    public void Store(JsonObject values)
    {
        values["multiplier"] = !Enabled ? 0 : Mode == 0 ? -1 : Multiplier;
        values["dynamic_mfg"] = Enabled && Mode == 2 ? 1 : 0;
        values["mfg_saved_mode"] = Mode;
        values["mfg_saved_multiplier"] = Multiplier;
    }
}
