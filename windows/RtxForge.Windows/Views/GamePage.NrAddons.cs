using System.Text.Json.Nodes;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using RtxForge.Windows.Controls;
using RtxForge.Windows.Models;

namespace RtxForge.Windows.Views;

/// <summary>Tools › Split Render: Environment and Character each take the add-on the user picks
/// (Lecram, ShortFuse or GITC Uplift), a pinned build and the Old or New model. Where Skynizz runs
/// NR, Skynizz is the Environment. Combos fill both slots; every change is checked against this
/// game before Install is offered.</summary>
public sealed partial class GamePage
{
    sealed record NrSlot(ComboBox Addon, ComboBox Build, Border BuildRow, List<JsonObject> Choices, bool Optional);

    UIElement NrAddonsGroup(Game g)
    {
        var group = new PreferencesGroup("Split Render",
            "Render the environment and characters with DLSS 5 NR, with a separate character pass where supported.");
        var status = group.Add(Prefs.Row("Split Render", "Checking…", null, ""));
        _ = FillNrAddonsAsync(g, group, status);
        return group;
    }

    async Task FillNrAddonsAsync(Game g, PreferencesGroup group, Border status)
    {
        JsonObject catalog, current;
        try
        {
            catalog = await shell.Service.NrCatalogAsync(g);
            current = await shell.Service.NrStatusAsync(g);
        }
        catch (InvalidOperationException error) { SetSubtitle(status, error.Message); return; }
        if (g != game || section != "Tools") return;

        var addons = (catalog["addons"] as JsonArray ?? []).OfType<JsonObject>().ToList();
        // Where Skynizz runs NR, it is the world: the Environment slot's only choice.
        var runtime = (catalog["runtime_nr"] ?? current["runtime_nr"]) as JsonObject;
        const string RuntimeId = "optiscaler";
        var world = (string?)runtime?["name"] ?? "Skynizz";
        string Name(string? id) => id == RuntimeId ? world
            : addons.FirstOrDefault(a => (string?)a["id"] == id)?["name"]?.ToString() ?? id ?? "";
        var models = (catalog["models"] as JsonArray ?? []).OfType<JsonObject>().ToList();

        if (current["installed"]?.GetValue<bool>() == true)
        {
            var setup = current["setup"] as JsonObject;
            var text = string.Join(" · ", new[] { "environment", "character" }
                .Where(slot => setup?[slot] is JsonObject)
                .Select(slot =>
                {
                    var id = (string?)setup![slot]!["addon"];
                    return $"{(slot == "environment" ? "Environment" : "Character detail")}: {Name(id)}";
                }));
            var modelId = (string?)setup?["environment"]?["model"] ?? (string?)setup?["character"]?["model"] ?? "new";
            if ((string?)setup?["environment"]?["addon"] == RuntimeId) text += $" · DLSS 5 model shared with {world}";
            else if (models.Find(item => (string?)item["id"] == modelId) is { } installedModel)
                text += " · " + NrSetupPicker.ModelLabel(installedModel);
            var changed = (current["changed"] as JsonArray ?? []).Count;
            SetSubtitle(status, "Installed · " + text + (changed > 0 ? $" · {changed} file(s) changed since install" : ""));
            var remove = Prefs.ActionButton("Remove Split Render", async (_, _) => { await shell.ChangeNrAsync(g, null, remove: true); Build("Tools"); });
            remove.IsEnabled = !shell.Busy && !shell.Service.IsPreview;
            group.Add(Prefs.Row("Restore original files", "Puts back the files and ReShade settings changed by Split Render.", remove, ""));
            return;
        }

        if (catalog["blocked"]?.GetValue<string>() is { Length: > 0 } reason)
        {
            SetSubtitle(status, reason);
            return;
        }

        var combos = (catalog["combos"] as JsonObject ?? []).Select(kv => (Id: kv.Key, Combo: kv.Value as JsonObject)).Where(c => c.Combo is not null).ToList();
        var (comboRow, comboBox) = Prefs.ComboRow("Preset", "Fill both roles from a saved or built-in preset.",
            ["Choose manually", .. combos.Select(c => (string?)c.Combo!["name"] ?? c.Id)], 0, "");
        group.Add(comboRow);

        NrSlot MakeSlot(string title, List<JsonObject> choices, bool optional, string glyph)
        {
            var (row, addon) = Prefs.ComboRow(title, null, [.. (optional ? new[] { "None" } : []), .. choices.Select(a => (string?)a["name"] ?? "")], 0, glyph);
            addon.IsEnabled = optional || choices.Count > 1;
            var build = new ComboBox { MinWidth = 180 };
            Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(build, title + " build");
            group.Add(row);
            var buildRow = group.Add(Prefs.Row(title + " build", null, build));
            return new NrSlot(addon, build, buildRow, choices, optional);
        }
        var environment = runtime is null
            ? MakeSlot("Environment", addons, optional: true, "")
            : MakeSlot("Environment", [new JsonObject { ["id"] = RuntimeId, ["name"] = world, ["builds"] = new JsonArray() }], optional: false, "");
        var character = MakeSlot("Character detail", addons, optional: true, "");
        int ModelIndex(string id) => Math.Max(0, models.FindIndex(item => (string?)item["id"] == id));
        var model = new RadioButtons { ItemsSource = models.Select(NrSetupPicker.ModelLabel).ToArray(),
            SelectedIndex = ModelIndex("new"), MaxColumns = 2 };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(model, "DLSS 5 model");
        group.Add(runtime is null
            ? Prefs.Row("DLSS 5 model", "Both passes share this model.", model)
            : Prefs.Row("DLSS 5 model", $"The character pass shares the model installed by {world}."));

        JsonObject? AddonAt(NrSlot slot)
        {
            var index = slot.Addon.SelectedIndex - (slot.Optional ? 1 : 0);
            return index >= 0 && index < slot.Choices.Count ? slot.Choices[index] : null;
        }
        int IndexOf(NrSlot slot, string? id)
        {
            var index = slot.Choices.FindIndex(a => (string?)a["id"] == id);
            return index < 0 ? 0 : index + (slot.Optional ? 1 : 0);
        }
        void FillBuilds(NrSlot slot, string? selectBuild = null)
        {
            var builds = (AddonAt(slot)?["builds"] as JsonArray ?? []).OfType<JsonObject>().ToList();
            slot.Build.ItemsSource = builds.Select(b => (string?)b["label"] ?? "").ToList();
            slot.Build.SelectedIndex = Math.Max(0, builds.FindIndex(b => selectBuild is not null ? (string?)b["id"] == selectBuild : b["default"]?.GetValue<bool>() == true));
            slot.BuildRow.Visibility = builds.Count > 0 ? Visibility.Visible : Visibility.Collapsed;
        }
        JsonObject? Spec(NrSlot slot, JsonObject? values)
        {
            var addon = AddonAt(slot);
            if (addon is null) return null;
            if ((string?)addon["id"] == RuntimeId) return new JsonObject { ["addon"] = RuntimeId };  // Skynizz brings its own model
            var builds = (addon["builds"] as JsonArray ?? []).OfType<JsonObject>().ToList();
            var spec = new JsonObject
            {
                ["addon"] = (string?)addon["id"],
                ["build"] = slot.Build.SelectedIndex >= 0 && slot.Build.SelectedIndex < builds.Count ? (string?)builds[slot.Build.SelectedIndex]["id"] : null,
                ["model"] = model.SelectedIndex >= 0 ? (string?)models[model.SelectedIndex]["id"] : "new",
            };
            if (values is not null) spec["values"] = values.DeepClone();
            return spec;
        }

        // Settings carried by the chosen combo, kept only while its add-on stays selected in that slot.
        JsonObject? envValues = null, charValues = null;
        string? envValuesFor = null, charValuesFor = null;
        JsonObject Setup()
        {
            var setup = new JsonObject();
            if (Spec(environment, (string?)AddonAt(environment)?["id"] == envValuesFor ? envValues : null) is { } env) setup["environment"] = env;
            if (Spec(character, (string?)AddonAt(character)?["id"] == charValuesFor ? charValues : null) is { } c) setup["character"] = c;
            return setup;
        }

        var verdict = group.Add(Prefs.Row("Compatibility", "Choose the passes for this game.", null, ""));
        var install = Prefs.ActionButton("Review installation", async (_, _) => { await shell.ChangeNrAsync(g, Setup()); Build("Tools"); }, accent: true);
        var save = Prefs.ActionButton("Save preset…", async (_, _) => await SaveNrComboAsync(Setup()));
        var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8, HorizontalAlignment = HorizontalAlignment.Right };
        actions.Children.Add(save); actions.Children.Add(install);
        group.Add(Prefs.Row("Apply to this game", "Review the exact files before anything changes.", actions, ""));
        install.IsEnabled = false;
        save.IsEnabled = !shell.Service.IsPreview;

        var checking = 0;
        async Task CheckAsync()
        {
            var ticket = ++checking;
            install.IsEnabled = false;
            try
            {
                var result = await shell.Service.NrCheckAsync(g, Setup());
                if (ticket != checking || g != game) return;
                var ok = result["ok"]?.GetValue<bool>() == true;
                var text = ok
                    ? (result["optiscaler_nr"]?.GetValue<bool>() == true ? $"{world} covers the environment. " : "")
                      + (result["verified"]?.GetValue<bool>() == true ? "Available to review." : "Available to review · this pairing is not verified on a test copy yet.")
                      + ((result["skipped"] as JsonArray ?? []).Count > 0 ? " Some settings aren't verified for this add-on and are left out." : "")
                    : (string?)result["reason"] ?? "Not available for this game.";
                SetSubtitle(verdict, text);
                install.IsEnabled = ok && !shell.Busy && !shell.Service.IsPreview;
            }
            catch (InvalidOperationException error) { if (ticket == checking) SetSubtitle(verdict, error.Message); }
        }

        var filling = false;
        void Changed() { if (!filling) { comboBox.SelectedIndex = 0; _ = CheckAsync(); } }
        environment.Addon.SelectionChanged += (_, _) => { FillBuilds(environment); Changed(); };
        character.Addon.SelectionChanged += (_, _) => { FillBuilds(character); Changed(); };
        foreach (var box in new[] { environment.Build, character.Build })
            box.SelectionChanged += (_, _) => Changed();
        model.SelectionChanged += (_, _) => Changed();
        comboBox.SelectionChanged += (_, _) =>
        {
            if (comboBox.SelectedIndex <= 0) return;
            var combo = combos[comboBox.SelectedIndex - 1].Combo!;
            filling = true;
            // The combo as it applies to this game: beside Skynizz, Skynizz is its world.
            void Apply(NrSlot slot, JsonObject? spec, Action<JsonObject?, string?> keep)
            {
                var id = (string?)spec?["addon"];
                slot.Addon.SelectedIndex = IndexOf(slot, id);
                FillBuilds(slot, (string?)spec?["build"]);
                keep(spec?["values"] as JsonObject, id);
            }
            Apply(environment, combo["environment"] as JsonObject, (v, id) => { envValues = v; envValuesFor = id; });
            Apply(character, combo["character"] as JsonObject, (v, id) => { charValues = v; charValuesFor = id; });
            model.SelectedIndex = ModelIndex((string?)combo["environment"]?["model"] ?? (string?)combo["character"]?["model"] ?? "new");
            filling = false;
            _ = CheckAsync();
        };
        filling = true;
        // Starts on Lecram for the environment, or Skynizz with ShortFuse for characters where Skynizz runs NR.
        var start = current["default"] as JsonObject;
        foreach (var (slot, key) in new[] { (environment, "environment"), (character, "character") })
        {
            slot.Addon.SelectedIndex = IndexOf(slot, (string?)start?[key]?["addon"]);
            FillBuilds(slot);
        }
        filling = false;
        SetSubtitle(status, "Not installed in this game.");
        _ = CheckAsync();
    }

    async Task SaveNrComboAsync(JsonObject setup)
    {
        var name = new TextBox { PlaceholderText = "Preset name", MaxLength = 60 };
        var dialog = new ContentDialog
        {
            XamlRoot = XamlRoot, Title = "Save preset", Content = name, PrimaryButtonText = "Save", CloseButtonText = "Cancel",
            DefaultButton = ContentDialogButton.Primary,
        };
        if (await dialog.ShowAsync() != ContentDialogResult.Primary || string.IsNullOrWhiteSpace(name.Text)) return;
        try
        {
            await shell.Service.SaveNrComboAsync(name.Text.Trim(), setup);
            shell.ShowToast("Preset saved. It's available for every game.");
            Build("Tools");
        }
        catch (InvalidOperationException error) { shell.ShowToast(error.Message); }
    }
}
