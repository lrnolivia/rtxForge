using System.Globalization;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;

namespace RtxForge.Windows.Models;

/// <summary>The same ordered vocabulary is embedded in the app and compiled into the game panel.</summary>
public sealed class FeatureControl
{
    public string Key { get; set; } = "";
    public string Label { get; set; } = "";
    public string Advanced { get; set; } = "";
    public string Group { get; set; } = "";
    public string Kind { get; set; } = "";
    public string Unit { get; set; } = "";
    public double Min { get; set; }
    public double Max { get; set; }
    public double Default { get; set; }
    public double Step { get; set; }
    public int Protocol { get; set; }
    public double[] Values { get; set; } = [];
    public string[] Choices { get; set; } = [];
    public bool Integer => Kind != "slider";
    public string Caption(bool advanced) => (advanced ? Advanced : Label).Replace("Colour", "Color", StringComparison.Ordinal);
    public string Display(double value, bool advanced) => Key == "skin" && value < 0 && !advanced ? "Follow structure"
        : Kind == "toggle" ? value == 0 ? "Off" : "On"
        : Values.Length > 0 ? Choices[Math.Max(0, Array.IndexOf(Values, value))]
        : Unit == "percent" || Unit == "strength" && !advanced ? value.ToString("0%", CultureInfo.CurrentCulture)
        : value.ToString(Integer ? "0" : "0.00", CultureInfo.CurrentCulture);
}

public sealed class FeatureControlGroup
{
    public string Name { get; set; } = "";
    public bool Expanded { get; set; }
    public string? Parent { get; set; }
}

public sealed class FeatureControlSchema
{
    public FeatureControl[] Controls { get; set; } = [];
    public FeatureControlGroup[] Groups { get; set; } = [];
    public static FeatureControlSchema Shared { get; } = Load();
    static FeatureControlSchema Load()
    {
        using var stream = typeof(FeatureControlSchema).Assembly.GetManifestResourceStream("RtxForge.FeatureControls.json")
            ?? throw new InvalidOperationException("The feature control definitions are missing.");
        return JsonSerializer.Deserialize<FeatureControlSchema>(stream, new JsonSerializerOptions { PropertyNameCaseInsensitive = true })
            ?? throw new InvalidOperationException("The feature control definitions are invalid.");
    }
    public static double Read(JsonNode? node, double fallback = 0) => node is null ? fallback
        : double.Parse(node.ToString(), CultureInfo.InvariantCulture);
    public static double Number(JsonObject values, FeatureControl field) => Read(values[field.Key], field.Default);
    public static void Put(JsonObject values, FeatureControl field, double value)
    {
        if (!double.IsFinite(value) || value < field.Min || value > field.Max || field.Integer && value != Math.Truncate(value)
            || field.Values.Length > 0 && !field.Values.Contains(value)) throw new ArgumentException("Choose a supported value for " + field.Label);
        values[field.Key] = field.Integer ? JsonValue.Create((int)value) : JsonValue.Create(value);
    }
    public static JsonObject Resolve(Tuning tuning)
    {
        var values = new JsonObject();
        foreach (var field in Shared.Controls) Put(values, field, Read(tuning.FeatureControls?[field.Key], field.Default));
        if (tuning.FeatureControls is null)
        {
            values["intensity"] = tuning.NrStrength;
            values["sharpness"] = tuning.SharpeningStrength;
            values["sharpen"] = tuning.SharpeningStrength > 0 ? 1 : 0;
            values["sharp_override"] = tuning.SharpeningStrength > 0 ? 1 : 0;
            values["multiplier"] = tuning.MfgMultiplier == "auto" ? -1 : int.Parse(tuning.MfgMultiplier);
            values["enabled"] = tuning.NrOnLaunch == true ? 1 : 0;
        }
        return values;
    }
    public static Tuning Tuning(JsonObject values) => new(Read(values["intensity"]), Read(values["sharpness"]),
        Read(values["multiplier"]) < 0 ? "auto" : values["multiplier"]!.ToString(), Read(values["enabled"]) == 1,
        (JsonObject)values.DeepClone());
    public static bool Available(FeatureControl field, string mode, bool legacy = false) =>
        (!legacy || field.Key is "intensity" or "sharpness" or "multiplier")
        && (field.Key == "multiplier" ? mode != "nr-only" : field.SectionIsNr() ? mode != "mfg-only" : true);
}

static class FeatureControlKinds
{
    public static bool SectionIsNr(this FeatureControl field) => field.Group is "Neural rendering" or "Image tuning" or "Fine tuning" or "Performance";
}
