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
    readonly RadioButtons model = new() { Header = "DLSS 5 model", MaxColumns = 2 };
    readonly StackPanel manual = new() { Spacing = 12 };
    readonly TextBlock presetDetails = Prefs.Label("", "ForgeCaptionDimTextStyle");
    readonly JsonObject[] addons;
    readonly JsonObject[] models;
    readonly JsonObject[] combos;
    int manualModel;
    bool settingPreset;
    bool overridePresetModel;

    internal NrSetupPicker(JsonObject catalog)
    {
        addons = (catalog["addons"] as JsonArray ?? []).OfType<JsonObject>().ToArray();
        models = (catalog["models"] as JsonArray ?? []).OfType<JsonObject>().ToArray();
        combos = (catalog["combos"] as JsonObject ?? []).Select(item => item.Value).OfType<JsonObject>().ToArray();

        preset.ItemsSource = new[] { "Choose manually", "Auto · match each game" }
            .Concat(combos.Select(c => c["name"]?.ToString() ?? "Saved setup"));
        var addonNames = new[] { "None" }.Concat(addons.Select(a => AddonName(a["id"]?.ToString()))).ToArray();
        environment.ItemsSource = addonNames;
        character.ItemsSource = addonNames;
        model.ItemsSource = models.Select(ModelLabel).ToArray();
        preset.SelectedIndex = environment.SelectedIndex = character.SelectedIndex = 0;
        manualModel = FindModel("new");
        model.SelectedIndex = manualModel;

        manual.Children.Add(environment);
        manual.Children.Add(character);
        manual.Children.Add(Prefs.Label("If Skynizz already runs NR, leave Environment set to None to add character detail.",
            "ForgeCaptionDimTextStyle"));
        Root.Children.Add(preset);
        Root.Children.Add(manual);
        Root.Children.Add(presetDetails);
        Root.Children.Add(model);
        Root.Children.Add(Prefs.Label("Both add-ons share this model. A game using Skynizz NR keeps its installed model.",
            "ForgeCaptionDimTextStyle"));
        foreach (var control in new[] { environment, character })
            control.SelectionChanged += (_, _) => Update();
        preset.SelectionChanged += (_, _) => ChangePreset();
        model.SelectionChanged += (_, _) =>
        {
            if (settingPreset) return;
            if (ActivePreset is null) manualModel = model.SelectedIndex;
            else overridePresetModel = true;
            Update();
        };
        Update();
    }

    internal event Action? Changed;
    internal JsonObject? Choice { get; private set; }
    internal string Summary { get; private set; } = "None";

    internal static string ModelLabel(JsonObject model) => (model["label"]?.ToString() ?? "")
        .Replace(" DLSS 5 (", " · ", StringComparison.Ordinal).TrimEnd(')');

    static ComboBox Field(string title) => new()
    {
        Header = title, HorizontalAlignment = HorizontalAlignment.Stretch, MaxDropDownHeight = 240,
    };

    string AddonName(string? id)
    {
        var name = addons.FirstOrDefault(a => a["id"]?.ToString() == id)?["name"]?.ToString();
        return name?.Split(" (", 2)[0] ?? id ?? "None";
    }

    bool IsAuto => preset.SelectedIndex == 1;
    JsonObject? ActivePreset => preset.SelectedIndex >= 2 ? combos[preset.SelectedIndex - 2] : null;

    int FindModel(string id)
    {
        var index = Array.FindIndex(models, value => value["id"]?.ToString() == id);
        return index >= 0 || models.Length == 0 ? index : 0;
    }

    void ChangePreset()
    {
        settingPreset = true;
        overridePresetModel = false;
        var combo = ActivePreset;
        if (combo is null) model.SelectedIndex = manualModel;
        else
        {
            var modelId = combo["environment"]?["model"] ?? combo["character"]?["model"];
            model.SelectedIndex = FindModel(modelId?.ToString() ?? "new");
        }
        settingPreset = false;
        Update();
    }

    string DescribeSlot(JsonNode? spec, string empty)
    {
        if (spec?["addon"] is not { } addon) return empty;
        var id = addon.ToString();
        return id == "optiscaler" ? "Installed NR" : AddonName(id);
    }

    void Update()
    {
        var combo = ActivePreset;
        var modelId = model.SelectedIndex >= 0 ? models[model.SelectedIndex]["id"]?.ToString() : null;
        manual.Visibility = combo is null && !IsAuto ? Visibility.Visible : Visibility.Collapsed;
        presetDetails.Visibility = combo is not null || IsAuto ? Visibility.Visible : Visibility.Collapsed;
        if (IsAuto)
        {
            presetDetails.Text = "Choose a compatible setup for each game. Review shows which passes each game will use.";
            Choice = modelId is not null ? new JsonObject { ["auto"] = true, ["model"] = modelId } : null;
            Summary = "Auto";
        }
        else if (combo is not null)
        {
            var world = DescribeSlot(combo["environment"], "Installed NR");
            var detail = DescribeSlot(combo["character"], "None");
            presetDetails.Text = $"Environment: {world}\nCharacter detail: {detail}\nWhere Skynizz runs NR, it supplies the environment.";
            var setup = combo.DeepClone().AsObject();
            if (overridePresetModel && modelId is not null)
                foreach (var role in new[] { "environment", "character" })
                    if (setup[role] is JsonObject slot && slot["addon"]?.ToString() != "optiscaler")
                        slot["model"] = modelId;
            Choice = new JsonObject { ["setup"] = setup, ["adapt"] = true };
            Summary = combo["name"]?.ToString() ?? "Saved setup";
        }
        else
        {
            var setup = new JsonObject();
            var names = new List<string>();
            foreach (var (slot, control) in new[] { ("environment", environment), ("character", character) })
            {
                if (control.SelectedIndex <= 0 || modelId is null) continue;
                var id = addons[control.SelectedIndex - 1]["id"]?.ToString();
                setup[slot] = new JsonObject { ["addon"] = id, ["model"] = modelId };
                names.Add(AddonName(id));
            }
            Choice = setup.Count > 0 ? new JsonObject { ["setup"] = setup, ["adapt"] = false } : null;
            Summary = names.Count > 0 ? string.Join(" + ", names) : "None";
        }
        if (Choice is not null && model.SelectedItem is string label)
            Summary += " · " + label;
        Changed?.Invoke();
    }
}
