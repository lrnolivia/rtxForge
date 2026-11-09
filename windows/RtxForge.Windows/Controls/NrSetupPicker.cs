using System.Text.Json.Nodes;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace RtxForge.Windows.Controls;

/// <summary>The catalog's setup choices, without repeating a row for every model.</summary>
internal sealed class NrSetupPicker
{
    internal StackPanel Root { get; } = new() { Spacing = 12 };
    readonly ComboBox preset = Field("Preset");
    readonly ComboBox environment = Field("Environment");
    readonly ComboBox character = Field("Character detail");
    readonly ComboBox model = Field("DLSS5 model");
    readonly StackPanel manual = new() { Spacing = 12 };
    readonly TextBlock presetDetails = Prefs.Label("", "ForgeCaptionDimTextStyle");
    readonly JsonObject[] addons;
    readonly JsonObject[] models;
    readonly JsonObject[] combos;

    internal NrSetupPicker(JsonObject catalog)
    {
        addons = (catalog["addons"] as JsonArray ?? []).OfType<JsonObject>().ToArray();
        models = (catalog["models"] as JsonArray ?? []).OfType<JsonObject>().ToArray();
        combos = (catalog["combos"] as JsonObject ?? []).Select(item => item.Value).OfType<JsonObject>().ToArray();

        preset.ItemsSource = new[] { "Choose manually" }.Concat(combos.Select(c => c["name"]?.ToString() ?? "Saved setup"));
        var addonNames = new[] { "None" }.Concat(addons.Select(a => AddonName(a["id"]?.ToString()))).ToArray();
        environment.ItemsSource = addonNames;
        character.ItemsSource = addonNames;
        model.ItemsSource = models.Select(m => m["label"]?.ToString() ?? "").ToArray();
        preset.SelectedIndex = environment.SelectedIndex = character.SelectedIndex = 0;
        model.SelectedIndex = Math.Max(0, Array.FindIndex(models, m => m["id"]?.ToString() == "new"));

        manual.Children.Add(environment);
        manual.Children.Add(character);
        manual.Children.Add(model);
        manual.Children.Add(Prefs.Label("If Skynizz already runs NR, leave Environment set to None to add character detail.",
            "ForgeCaptionDimTextStyle"));
        Root.Children.Add(preset);
        Root.Children.Add(manual);
        Root.Children.Add(presetDetails);
        foreach (var control in new[] { preset, environment, character, model })
            control.SelectionChanged += (_, _) => Update();
        Update();
    }

    internal event Action? Changed;
    internal JsonObject? Choice { get; private set; }
    internal string Summary { get; private set; } = "None";

    static ComboBox Field(string title) => new()
    {
        Header = title, HorizontalAlignment = HorizontalAlignment.Stretch, MaxDropDownHeight = 240,
    };

    string AddonName(string? id)
    {
        var name = addons.FirstOrDefault(a => a["id"]?.ToString() == id)?["name"]?.ToString();
        return name?.Split(" (", 2)[0] ?? id ?? "None";
    }

    string DescribeSlot(JsonNode? spec, string empty)
    {
        if (spec?["addon"] is not { } addon) return empty;
        var id = addon.ToString();
        if (id == "optiscaler") return "Installed NR";
        var modelId = spec["model"]?.ToString() ?? "new";
        var modelName = models.FirstOrDefault(m => m["id"]?.ToString() == modelId)?["label"]?.ToString();
        return string.Join(" · ", new[] { AddonName(id), modelName }.OfType<string>());
    }

    void Update()
    {
        var combo = preset.SelectedIndex > 0 ? combos[preset.SelectedIndex - 1] : null;
        manual.Visibility = combo is null ? Visibility.Visible : Visibility.Collapsed;
        presetDetails.Visibility = combo is null ? Visibility.Collapsed : Visibility.Visible;
        if (combo is not null)
        {
            var world = DescribeSlot(combo["environment"], "Installed NR");
            var detail = DescribeSlot(combo["character"], "None");
            presetDetails.Text = $"Environment: {world}\nCharacter detail: {detail}\nWhere Skynizz runs NR, it supplies the environment.";
            Choice = new JsonObject { ["setup"] = combo.DeepClone(), ["adapt"] = true };
            Summary = combo["name"]?.ToString() ?? "Saved setup";
        }
        else
        {
            var setup = new JsonObject();
            var names = new List<string>();
            foreach (var (slot, control) in new[] { ("environment", environment), ("character", character) })
            {
                if (control.SelectedIndex <= 0 || model.SelectedIndex < 0) continue;
                var id = addons[control.SelectedIndex - 1]["id"]?.ToString();
                setup[slot] = new JsonObject { ["addon"] = id, ["model"] = models[model.SelectedIndex]["id"]?.ToString() };
                names.Add(AddonName(id));
            }
            Choice = setup.Count > 0 ? new JsonObject { ["setup"] = setup, ["adapt"] = false } : null;
            Summary = names.Count > 0 ? string.Join(" + ", names) : "None";
            model.IsEnabled = setup.Count > 0 || environment.SelectedIndex > 0 || character.SelectedIndex > 0;
        }
        Changed?.Invoke();
    }
}
