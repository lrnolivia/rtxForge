using System.Text.Json.Nodes;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Navigation;
using RtxForge.Windows.Controls;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;

namespace RtxForge.Windows.Views;

/// <summary>
/// Presets: the library presets (NR Strength, Sharpening, MFG) on their own page, as in
/// Game Mode. The footer matches Linux: Reset, Select games and Apply to all.
/// </summary>
public sealed partial class PresetsPage : Page
{
    readonly MainWindow shell = App.Main!;
    readonly PresetControlsView tuning;
    readonly PreferencesGroup splitPresets = new("Split Render Presets", "Set the environment, character and DLSS 5 model for a package. Use saved presets in installation reviews.");
    const string RuntimeId = "optiscaler";
    sealed record NrSlot(ComboBox Addon, ComboBox Build, Border BuildRow, List<JsonObject> Choices, bool Optional);
    readonly Button reset, selectGames, applyAll;
    readonly TextBlock changed = Prefs.Label("", "ForgeCaptionDimTextStyle");

    public PresetsPage()
    {
        InitializeComponent();
        tuning = new PresetControlsView(shell.Settings.Presets, shell.Settings.OverlayControls == "classic");
        tuning.Changed += (_, _) => Refresh();

        var page = new Grid { RowSpacing = 20, Padding = new Thickness(36, 12, 36, 24) };
        page.RowDefinitions.Add(new() { Height = GridLength.Auto });
        page.RowDefinitions.Add(new() { Height = new GridLength(1, GridUnitType.Star) });
        page.RowDefinitions.Add(new() { Height = GridLength.Auto });
        var heading = new StackPanel { Spacing = 6 };
        heading.Children.Add(new TextBlock { Text = "Presets", Style = Prefs.GetStyle("ForgePageTitleTextStyle") });
        heading.Children.Add(Prefs.Label("Your defaults for new installs. Review games to apply them to existing packages."));
        page.Children.Add(heading);
        var sections = new StackPanel { Spacing = 24 };
        sections.Children.Add(splitPresets.Root);
        sections.Children.Add(tuning);
        var scroll = new ScrollViewer { Content = sections, HorizontalScrollMode = ScrollMode.Disabled,
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto, Padding = new Thickness(0, 0, 4, 4) };
        Grid.SetRow(scroll, 1); page.Children.Add(scroll);

        var footer = new Grid { ColumnSpacing = 12 };
        footer.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        footer.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        changed.VerticalAlignment = VerticalAlignment.Center;
        changed.TextWrapping = TextWrapping.WrapWholeWords;
        footer.Children.Add(changed);
        var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8, HorizontalAlignment = HorizontalAlignment.Right };
        reset = Prefs.ActionButton("Reset", (_, _) => { tuning.Value = shell.Settings.Presets; Refresh(); }, glyph: "");
        ToolTipService.SetToolTip(reset, "Discard unsaved preset changes.");
        selectGames = Prefs.ActionButton("Select games", (_, _) => SelectGames(), glyph: "");
        ToolTipService.SetToolTip(selectGames, "Choose games in the Library to apply these presets to.");
        applyAll = Prefs.ActionButton("Apply to all", async (_, _) => await ApplyAllAsync(), accent: true, glyph: "");
        ToolTipService.SetToolTip(applyAll, "Review these presets for every configured game, and keep them as your defaults.");
        actions.Children.Add(reset); actions.Children.Add(selectGames); actions.Children.Add(applyAll);
        Grid.SetColumn(actions, 1); footer.Children.Add(actions);
        Grid.SetRow(footer, 2); page.Children.Add(footer); Content = page;
        // One centered column, as every page (Controls/PageMargins).
        SizeChanged += (_, e) => page.Padding = PageMargins.For(e.NewSize.Width, bottom: 24);
        shell.GamesChanged += Refresh;
        Unloaded += (_, _) => shell.GamesChanged -= Refresh;
    }

    protected override void OnNavigatedTo(NavigationEventArgs e)
    {
        base.OnNavigatedTo(e);
        shell.EndPresetSelection();
        tuning.SetMode(shell.Mode, legacy: shell.Settings.RuntimeProvider != "skynizz", dynamicSupported: shell.Settings.DynamicMfgSupported);
        Refresh();
        _ = LoadSplitPresetsAsync();
    }

    async Task LoadSplitPresetsAsync()
    {
        while (splitPresets.Root.Children.Count > 2)
            splitPresets.Root.Children.RemoveAt(2);
        var body = new StackPanel { Spacing = 12 };
        if (shell.Service is not EngineForgeService engine)
        {
            splitPresets.Add(Prefs.Label("Split Render presets are available in the installed app."));
            return;
        }
        var package = shell.Settings.RuntimeProvider == "skynizz" ? "skynizz" : "native";
        JsonObject first;
        try { first = await engine.SplitPresetCatalogAsync(package); }
        catch (InvalidOperationException error) { splitPresets.Add(Prefs.Label(error.Message)); return; }
        var packages = ((JsonArray)first["preset_packages"]!).OfType<JsonObject>().ToList();
        var index = Math.Max(0, packages.FindIndex(item => (string?)item["id"] == package));
        var (packageRow, selector) = Prefs.ComboRow("Package", null, packages.Select(item => (string)item["label"]!).ToArray(), index, "");
        splitPresets.Add(packageRow);
        splitPresets.Add(body);

        var revision = 0;
        async Task FillAsync(JsonObject? initial = null)
        {
            if (selector.SelectedIndex < 0) return;
            var ticket = ++revision;
            package = (string)packages[selector.SelectedIndex]["id"]!;
            var selected = package;
            body.Children.Clear();
            body.Children.Add(Prefs.Label("Loading Split Render presets…"));
            try
            {
                var catalog = initial ?? await engine.SplitPresetCatalogAsync(selected);
                if (ticket != revision) return;
                body.Children.Clear();
                if ((string?)catalog["blocked"] is { Length: > 0 } reason)
                {
                    body.Children.Add(Prefs.Label(reason + " Open a Feeder game’s Tools to assign pass roles."));
                    return;
                }
                var editor = new PreferencesGroup(null);
                body.Children.Add(editor.Root);
                BuildSplitPresetEditor(engine, selected, catalog, editor, () => FillAsync());
            }
            catch (InvalidOperationException error)
            {
                if (ticket != revision) return;
                body.Children.Clear();
                body.Children.Add(Prefs.Label(error.Message));
            }
        }
        selector.SelectionChanged += (_, _) => _ = FillAsync();
        await FillAsync(first);
    }

    void BuildSplitPresetEditor(EngineForgeService engine, string package, JsonObject catalog,
        PreferencesGroup group, Func<Task> refresh)
    {
        var addons = ((JsonArray)catalog["addons"]!).OfType<JsonObject>().ToList();
        var models = ((JsonArray)catalog["models"]!).OfType<JsonObject>().ToList();
        var runtime = catalog["runtime_nr"];
        var world = (string?)runtime?["name"] ?? "Skynizz";
        var combos = ((JsonObject)catalog["combos"]!).Select(kv => (Id: kv.Key, Combo: (JsonObject)kv.Value!)).ToList();
        var (comboRow, comboBox) = Prefs.ComboRow("Preset", "Choose a saved setup or create your own.",
            ["Choose manually", .. combos.Select(c => (string?)c.Combo["name"] ?? c.Id)], 0, "");
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

        var name = new TextBox { PlaceholderText = "Preset name", MaxLength = 60, MinWidth = 160 };
        group.Add(Prefs.Row("Preset name", null, name));
        var resultLabel = Prefs.Label("");
        group.Add(resultLabel);
        var save = Prefs.ActionButton("Save preset", (_, _) => { }, accent: true);
        group.Add(Prefs.Row("Save Split Render preset", "Available in reviews for compatible games.", save, ""));
        var checking = 0;
        var compatible = false;
        var saving = false;
        void UpdateSave() => save.IsEnabled = compatible && !saving && !engine.IsPreview && !string.IsNullOrWhiteSpace(name.Text);
        name.TextChanged += (_, _) => UpdateSave();
        async Task CheckAsync()
        {
            var ticket = ++checking;
            compatible = false;
            UpdateSave();
            try
            {
                var result = await engine.CheckSplitPresetAsync(package, Setup());
                if (ticket != checking) return;
                compatible = result["ok"]?.GetValue<bool>() == true;
                resultLabel.Text = compatible ? "Ready to save." : (string?)result["reason"] ?? "Choose a compatible setup.";
                UpdateSave();
            }
            catch (InvalidOperationException error) { if (ticket == checking) resultLabel.Text = error.Message; }
        }
        save.Click += async (_, _) =>
        {
            if (!compatible || saving || string.IsNullOrWhiteSpace(name.Text)) return;
            saving = true;
            UpdateSave();
            try
            {
                await engine.SaveSplitPresetAsync(package, name.Text.Trim(), Setup());
                shell.ShowToast("Split Render preset saved.");
                await refresh();
            }
            catch (InvalidOperationException error) { resultLabel.Text = error.Message; }
            finally { saving = false; UpdateSave(); }
        };

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
            name.Text = combo["builtin"]?.GetValue<bool>() == false ? (string?)combo["name"] ?? "" : "";
            _ = CheckAsync();
        };
        filling = true;
        FillBuilds(environment);
        FillBuilds(character);
        filling = false;
        _ = CheckAsync();
    }

    List<Game> Configured() => shell.Games.Where(g => g.Installed && !g.Blocked).ToList();

    void Refresh()
    {
        var count = Configured().Count;
        var dirty = tuning.HasChanges(shell.Settings.Presets);
        reset.IsEnabled = dirty && !shell.Busy;
        selectGames.IsEnabled = count > 0 && !shell.Busy;
        applyAll.IsEnabled = !shell.Busy;
        changed.Text = (dirty ? "Unsaved changes. " : "")
            + (count > 0 ? $"Apply to all reviews {count} configured game{(count == 1 ? "" : "s")} and keeps these as your defaults."
                         : "No games have features installed yet. Apply to all saves these as your defaults for new installs.");
    }

    void Save(Tuning value)
    {
        shell.Settings.NrStrength = value.NrStrength;
        shell.Settings.SharpeningStrength = value.SharpeningStrength;
        shell.Settings.MfgMultiplier = value.MfgMultiplier;
        shell.Settings.NrOnLaunch = value.NrOnLaunch == true;
        shell.Settings.FeatureControls = value.FeatureControls;
        shell.Settings.Save();
        Refresh();
    }

    /// <summary>Library presets mode applies the saved defaults, so unsaved edits are kept first.</summary>
    void SelectGames()
    {
        if (tuning.HasChanges(shell.Settings.Presets)) Save(tuning.Value);
        shell.BeginPresetSelection();
    }

    /// <summary>Reviewed apply to every configured game; the presets become the defaults once it completes.</summary>
    async Task ApplyAllAsync()
    {
        var value = tuning.Value;
        var targets = Configured();
        if (targets.Count == 0) { Save(value); shell.ShowToast("Saved as your defaults for new installs."); return; }
        if (await shell.LaunchAction("apply", targets, value)) Save(value);
        Refresh();
    }
}
