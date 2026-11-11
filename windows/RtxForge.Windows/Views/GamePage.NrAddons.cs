using System.Text.Json.Nodes;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using RtxForge.Windows.Controls;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;

namespace RtxForge.Windows.Views;

/// <summary>Review and install a Split Render preset for this game, or adjust its Feeder pass roles.</summary>
public sealed partial class GamePage
{
    void ShowFeederCharacter(Game g, EngineForgeService engine, PreferencesGroup group, JsonObject settings)
    {
        var passes = new PreferencesGroup("Feeder NR passes",
            "Each pass processes the whole frame. Character turns on the mask so Skin detail can affect detected people.");
        group.Root.Children.Clear();
        group.Root.Children.Add(passes.Root);
        if (settings["available"]?.GetValue<bool>() != true)
        {
            passes.Add(Prefs.Row("Pass roles", settings["reason"]?.GetValue<string>() ?? ""));
            return;
        }

        var current = settings["passes"]!.GetValue<int>();
        var options = ((JsonArray)settings["options"]!).OfType<JsonObject>().ToArray();
        var (passRow, passChoice) = Prefs.ComboRow("Pass", $"{current} of {options.Length} full-frame passes configured.",
            options.Select(option => $"Pass {option["number"]!.GetValue<int>()}").ToArray(), 0);
        var (roleRow, roleChoice) = Prefs.ComboRow("Role", "", ["Standard", "Character"], 0);
        var slider = new Slider { Minimum = -1, Maximum = 1, StepFrequency = .01, MinWidth = 180 };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(slider, "Skin detail for the selected pass");
        var skinRow = Prefs.Row("Skin detail", "", slider);
        passes.Add(passRow);
        passes.Add(roleRow);
        passes.Add(skinRow);

        var blocked = settings["reason"]?.GetValue<string>();
        var busy = false;
        var apply = new Button
        {
            Content = "Save pass role", Style = Prefs.GetStyle("AccentButtonStyle"),
            HorizontalAlignment = HorizontalAlignment.Right, MinHeight = 32, Padding = new Thickness(12, 6, 12, 6),
        };
        var action = passes.Add(Prefs.Row("Apply next launch", "", apply, "\uE74E"));
        JsonObject Selected() => options[passChoice.SelectedIndex];
        double Skin() => slider.Value < 0 ? -1 : slider.Value;
        bool Changed(JsonObject option, int number, bool character) => number > current ||
            character != option["character"]!.GetValue<bool>() ||
            (character && Math.Abs(Skin() - option["skin"]!.GetValue<double>()) > .005);

        void Refresh()
        {
            var option = Selected();
            var number = option["number"]!.GetValue<int>();
            var character = roleChoice.SelectedIndex == 1;
            var available = !busy && !shell.Busy && !shell.Service.IsPreview && blocked is null;
            var roleChanged = character != option["character"]!.GetValue<bool>();
            var skinChanged = character && Math.Abs(Skin() - option["skin"]!.GetValue<double>()) > .005;
            SetSubtitle(roleRow, option["inherited"]!.GetValue<bool>() && (roleChanged || skinChanged)
                ? "Copies the main pass’s model settings before assigning this pass its own settings."
                : number == 1 ? "Passes that follow the main settings also use this role." : "");
            SetSubtitle(skinRow, Skin() < 0 ? "Stock" : $"Selected · {Skin():0.00}");
            skinRow.Visibility = character ? Visibility.Visible : Visibility.Collapsed;
            SetSubtitle(action, blocked ?? (number > current
                ? $"Full-frame passes · {current} → {number}. Extra passes can lower frame rate."
                : "Saves the selected pass settings for the next launch."));
            passChoice.IsEnabled = roleChoice.IsEnabled = slider.IsEnabled = available;
            apply.IsEnabled = available && Changed(option, number, character);
        }
        void SelectPass()
        {
            var option = Selected();
            roleChoice.SelectedIndex = option["character"]!.GetValue<bool>() ? 1 : 0;
            slider.Value = option["skin"]!.GetValue<double>();
            Refresh();
        }
        passChoice.SelectionChanged += (_, _) => SelectPass();
        roleChoice.SelectionChanged += (_, _) => Refresh();
        slider.ValueChanged += (_, _) => Refresh();
        apply.Click += async (_, _) =>
        {
            if (busy || shell.Busy) return;
            var number = Selected()["number"]!.GetValue<int>();
            var character = roleChoice.SelectedIndex == 1;
            busy = true;
            Refresh();
            SetSubtitle(action, $"Saving Pass {number}…");
            try
            {
                var result = await engine.ApplyFeederCharacterAsync(g, settings["stamp"]!.GetValue<string>(),
                    number, character, character ? Skin() : null);
                shell.ShowToast(result);
                if (g == game && section == "Tools") Build("Tools");
            }
            catch (Exception error) when (error is IOException or InvalidOperationException or UnauthorizedAccessException)
            {
                busy = false;
                Refresh();
                SetSubtitle(action, error.Message);
            }
            finally { busy = false; }
        };
        SelectPass();
    }


    UIElement NrAddonsGroup(Game g)
    {
        var group = new PreferencesGroup("Split Render",
            "Render the environment and characters with DLSS 5 NR, with a separate character pass where supported.");
        var enabled = shell.Service is EngineForgeService { SplitRenderEnabled: true };
        if (!enabled) group.Root.Visibility = Visibility.Collapsed;
        var status = group.Add(Prefs.Row("Split Render", "Checking…", null, ""));
        _ = FillNrAddonsAsync(g, group, status, enabled);
        return group;
    }

    async Task FillNrAddonsAsync(Game g, PreferencesGroup group, Border status, bool enabled)
    {
        JsonObject catalog, current;
        try
        {
            current = await shell.Service.NrStatusAsync(g);
            if (!enabled && current["installed"]?.GetValue<bool>() != true) return;
            catalog = await shell.Service.NrCatalogAsync(g);
        }
        catch (InvalidOperationException error) { SetSubtitle(status, error.Message); return; }
        if (g != game || section != "Tools") return;
        group.Root.Visibility = Visibility.Visible;

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
            if (catalog["feeder_character"] is JsonObject feeder && shell.Service is EngineForgeService engine)
                ShowFeederCharacter(g, engine, group, feeder);
            else
                SetSubtitle(status, reason);
            return;
        }

        var combos = (catalog["combos"] as JsonObject ?? []).Select(kv => (Id: kv.Key, Combo: kv.Value as JsonObject))
            .Where(c => c.Combo is not null).ToList();
        var (presetRow, preset) = Prefs.ComboRow("Preset", "Create and customize setups in Presets.",
            ["Recommended for this game", .. combos.Select(c => (string?)c.Combo!["name"] ?? c.Id)], 0, "");
        group.Add(presetRow);
        JsonObject Setup()
        {
            var chosen = preset.SelectedIndex > 0 ? combos[preset.SelectedIndex - 1].Combo : current["default"] as JsonObject;
            var setup = new JsonObject();
            foreach (var role in new[] { "environment", "character" })
                if (chosen?[role] is JsonObject slot) setup[role] = slot.DeepClone();
            return setup;
        }

        var install = Prefs.ActionButton("Review installation", async (_, _) =>
        {
            await shell.ChangeNrAsync(g, Setup());
            Build("Tools");
        }, accent: true);
        group.Add(Prefs.Row("Install Split Render", "Review what this game will use before installing.", install, ""));
        var checking = 0;
        async Task CheckAsync()
        {
            var ticket = ++checking;
            install.IsEnabled = false;
            SetSubtitle(status, "Checking compatibility…");
            try
            {
                var result = await shell.Service.NrCheckAsync(g, Setup());
                if (ticket != checking || g != game) return;
                var ok = result["ok"]?.GetValue<bool>() == true;
                SetSubtitle(status, ok
                    ? (result["verified"]?.GetValue<bool>() == true ? "Available to review." : "Available to review · pairing unverified.")
                    : (string?)result["reason"] ?? "Not available for this game.");
                install.IsEnabled = ok && !shell.Busy && !shell.Service.IsPreview;
            }
            catch (InvalidOperationException error) { if (ticket == checking) SetSubtitle(status, error.Message); }
        }
        preset.SelectionChanged += (_, _) => _ = CheckAsync();
        await CheckAsync();
    }
}
