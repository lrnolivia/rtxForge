using System.Text.Json.Nodes;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using RtxForge.Windows.Controls;
using RtxForge.Windows.Models;

namespace RtxForge.Windows.Views;

/// <summary>Tools › DLSS5 NR add-ons: Environment and Character each take the add-on the user picks
/// (Lecram, ShortFuse or GITC Uplift), a pinned build and the Old or New model. Combos fill both
/// slots; every change is checked against this game before Install is offered.</summary>
public sealed partial class GamePage
{
    sealed record NrSlot(ComboBox Addon, ComboBox Build, ComboBox Model);

    UIElement NrAddonsGroup(Game g)
    {
        var group = new PreferencesGroup("DLSS5 NR add-ons",
            "Choose an add-on for the environment and one for characters, each with the Old or New DLSS5 model. "
            + "rtxForge downloads the pinned files and checks this game before anything is installed.");
        var status = group.Add(Prefs.Row("NR add-ons", "Checking…", null, ""));
        _ = FillNrAddonsAsync(g, group, status);
        return group;
    }

    async Task FillNrAddonsAsync(Game g, PreferencesGroup group, Border status)
    {
        JsonObject catalog, current;
        try
        {
            catalog = await shell.Service.NrCatalogAsync();
            current = await shell.Service.NrStatusAsync(g);
        }
        catch (InvalidOperationException error) { SetSubtitle(status, error.Message); return; }
        if (g != game || section != "Tools") return;

        var addons = (catalog["addons"] as JsonArray ?? []).OfType<JsonObject>().ToList();
        string Name(string? id) => addons.FirstOrDefault(a => (string?)a["id"] == id)?["name"]?.ToString() ?? id ?? "";

        if (current["installed"]?.GetValue<bool>() == true)
        {
            var setup = current["setup"] as JsonObject;
            var text = string.Join(" · ", new[] { "environment", "character" }
                .Where(slot => setup?[slot] is JsonObject)
                .Select(slot => $"{char.ToUpper(slot[0])}{slot[1..]}: {Name((string?)setup![slot]!["addon"])} ({setup[slot]!["model"]})"));
            var changed = (current["changed"] as JsonArray ?? []).Count;
            SetSubtitle(status, "Installed · " + text + (changed > 0 ? $" · {changed} file(s) changed since install" : ""));
            var remove = Prefs.ActionButton("Remove", async (_, _) => { await shell.ChangeNrAsync(g, null, remove: true); Build("Tools"); });
            remove.IsEnabled = !shell.Busy && !shell.Service.IsPreview;
            group.Add(Prefs.Row("Remove NR add-ons", "Puts back the game's files and the ReShade settings rtxForge changed. Your own edits are kept.", remove, ""));
            return;
        }

        var models = (catalog["models"] as JsonArray ?? []).OfType<JsonObject>().ToList();
        var combos = (catalog["combos"] as JsonObject ?? []).Select(kv => (Id: kv.Key, Combo: kv.Value as JsonObject)).Where(c => c.Combo is not null).ToList();
        var (comboRow, comboBox) = Prefs.ComboRow("Combo", "Fill both slots from a saved or built-in combo.",
            ["Custom", .. combos.Select(c => (string?)c.Combo!["name"] ?? c.Id)], 0, "");
        group.Add(comboRow);

        NrSlot MakeSlot(string title, bool optional, string glyph)
        {
            var (row, addon) = Prefs.ComboRow(title, null, [.. (optional ? new[] { "None" } : []), .. addons.Select(a => (string?)a["name"] ?? "")], 0, glyph);
            var build = new ComboBox { MinWidth = 180 };
            var model = new ComboBox { MinWidth = 180, ItemsSource = models.Select(m => (string?)m["label"] ?? "").ToList(), SelectedIndex = Math.Max(0, models.FindIndex(m => (string?)m["id"] == "new")) };
            var extra = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8, HorizontalAlignment = HorizontalAlignment.Right };
            extra.Children.Add(build); extra.Children.Add(model);
            group.Add(row);
            group.Add(Prefs.Row(title + " build and model", null, extra));
            return new NrSlot(addon, build, model);
        }
        var environment = MakeSlot("Environment", optional: false, "");
        var character = MakeSlot("Character", optional: true, "");

        JsonObject? AddonAt(NrSlot slot, bool optional)
        {
            var index = slot.Addon.SelectedIndex - (optional ? 1 : 0);
            return index >= 0 && index < addons.Count ? addons[index] : null;
        }
        void FillBuilds(NrSlot slot, bool optional, string? selectBuild = null)
        {
            var builds = (AddonAt(slot, optional)?["builds"] as JsonArray ?? []).OfType<JsonObject>().ToList();
            slot.Build.ItemsSource = builds.Select(b => (string?)b["label"] ?? "").ToList();
            slot.Build.SelectedIndex = Math.Max(0, builds.FindIndex(b => selectBuild is not null ? (string?)b["id"] == selectBuild : b["default"]?.GetValue<bool>() == true));
            slot.Build.IsEnabled = slot.Model.IsEnabled = builds.Count > 0;
        }
        JsonObject? Spec(NrSlot slot, bool optional, JsonObject? values)
        {
            var addon = AddonAt(slot, optional);
            if (addon is null) return null;
            var builds = (addon["builds"] as JsonArray ?? []).OfType<JsonObject>().ToList();
            var spec = new JsonObject
            {
                ["addon"] = (string?)addon["id"],
                ["build"] = slot.Build.SelectedIndex >= 0 && slot.Build.SelectedIndex < builds.Count ? (string?)builds[slot.Build.SelectedIndex]["id"] : null,
                ["model"] = slot.Model.SelectedIndex >= 0 ? (string?)models[slot.Model.SelectedIndex]["id"] : "new",
            };
            if (values is not null) spec["values"] = values.DeepClone();
            return spec;
        }

        // Settings carried by the chosen combo, kept only while its add-on stays selected in that slot.
        JsonObject? envValues = null, charValues = null;
        string? envValuesFor = null, charValuesFor = null;
        JsonObject Setup()
        {
            var setup = new JsonObject { ["environment"] = Spec(environment, false, (string?)AddonAt(environment, false)?["id"] == envValuesFor ? envValues : null) };
            if (Spec(character, true, (string?)AddonAt(character, true)?["id"] == charValuesFor ? charValues : null) is { } c) setup["character"] = c;
            return setup;
        }

        var verdict = group.Add(Prefs.Row("Check", "Choose the add-ons for this game.", null, ""));
        var install = Prefs.ActionButton("Install", async (_, _) => { await shell.ChangeNrAsync(g, Setup()); Build("Tools"); }, accent: true);
        var save = Prefs.ActionButton("Save combo…", async (_, _) => await SaveNrComboAsync(Setup()));
        var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8, HorizontalAlignment = HorizontalAlignment.Right };
        actions.Children.Add(save); actions.Children.Add(install);
        group.Add(Prefs.Row("Apply to this game", "Review the exact files before anything changes.", actions, ""));
        install.IsEnabled = false;
        save.IsEnabled = !shell.Service.IsPreview;

        var checking = 0;
        async Task CheckAsync()
        {
            var ticket = ++checking;
            try
            {
                var result = await shell.Service.NrCheckAsync(g, Setup());
                if (ticket != checking || g != game) return;
                var ok = result["ok"]?.GetValue<bool>() == true;
                var text = ok
                    ? (result["verified"]?.GetValue<bool>() == true ? "Works in this game." : "Works in this game · this pairing is not verified on a test copy yet.")
                      + ((result["skipped"] as JsonArray ?? []).Count > 0 ? " Some settings aren't verified for this add-on and are left out." : "")
                    : (string?)result["reason"] ?? "Not available for this game.";
                SetSubtitle(verdict, text);
                install.IsEnabled = ok && !shell.Busy && !shell.Service.IsPreview;
            }
            catch (InvalidOperationException error) { if (ticket == checking) SetSubtitle(verdict, error.Message); }
        }

        var filling = false;
        void Changed() { if (!filling) { comboBox.SelectedIndex = 0; _ = CheckAsync(); } }
        environment.Addon.SelectionChanged += (_, _) => { FillBuilds(environment, false); Changed(); };
        character.Addon.SelectionChanged += (_, _) => { FillBuilds(character, true); Changed(); };
        foreach (var box in new[] { environment.Build, environment.Model, character.Build, character.Model })
            box.SelectionChanged += (_, _) => Changed();
        comboBox.SelectionChanged += (_, _) =>
        {
            if (comboBox.SelectedIndex <= 0) return;
            var combo = combos[comboBox.SelectedIndex - 1].Combo!;
            filling = true;
            void Apply(NrSlot slot, bool optional, JsonObject? spec, Action<JsonObject?, string?> keep)
            {
                var id = (string?)spec?["addon"];
                var index = addons.FindIndex(a => (string?)a["id"] == id);
                slot.Addon.SelectedIndex = id is null ? 0 : index + (optional ? 1 : 0);
                FillBuilds(slot, optional, (string?)spec?["build"]);
                slot.Model.SelectedIndex = Math.Max(0, models.FindIndex(m => (string?)m["id"] == ((string?)spec?["model"] ?? "new")));
                keep(spec?["values"] as JsonObject, id);
            }
            Apply(environment, false, combo["environment"] as JsonObject, (v, id) => { envValues = v; envValuesFor = id; });
            Apply(character, true, combo["character"] as JsonObject, (v, id) => { charValues = v; charValuesFor = id; });
            filling = false;
            _ = CheckAsync();
        };
        filling = true;
        environment.Addon.SelectedIndex = Math.Max(0, addons.FindIndex(a => (string?)a["id"] == "lecram"));
        FillBuilds(environment, false); FillBuilds(character, true);
        filling = false;
        SetSubtitle(status, "Not installed in this game.");
        _ = CheckAsync();
    }

    async Task SaveNrComboAsync(JsonObject setup)
    {
        var name = new TextBox { PlaceholderText = "Combo name", MaxLength = 60 };
        var dialog = new ContentDialog
        {
            XamlRoot = XamlRoot, Title = "Save combo", Content = name, PrimaryButtonText = "Save", CloseButtonText = "Cancel",
            DefaultButton = ContentDialogButton.Primary,
        };
        if (await dialog.ShowAsync() != ContentDialogResult.Primary || string.IsNullOrWhiteSpace(name.Text)) return;
        try
        {
            await shell.Service.SaveNrComboAsync(name.Text.Trim(), setup);
            shell.ShowToast("Combo saved. It's available for every game.");
            Build("Tools");
        }
        catch (InvalidOperationException error) { shell.ShowToast(error.Message); }
    }
}
