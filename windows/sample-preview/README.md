# Private sample-library capture build

This tooling builds a private fork of an exact committed Windows UI without editing the active Windows checkout. It requires a display-only manifest and always uses simulated operations. Normal launch without the manifest fails closed. It does not replace the installed application.

Export the live display snapshot and locally selected artwork with `export_sample.py --snapshot <library-snapshot.json> --settings <settings.json> --output <%LOCALAPPDATA%/rtxForge-samples/new-profile>`. The output is private; never commit the manifest, settings or artwork. All rows are retained, including duplicate installation entries. Initial installed/tested/ownership state is clean.

Generate the fork using `build_sample.py --repo <isolated-worktree> --revision <exact-commit> --output <new-private-source-folder>`, then build its original `windows/RtxForge.Windows/RtxForge.Windows.csproj` with `dotnet build -c Release -r win-x64 -p:Platform=x64 -o <private-app-folder>`. Run this module's `package_resources(project, output)` function after building: custom output folders need the loose compiled XBF files, including MainWindow.xbf, copied alongside the PRI. Do not publish/bundle the real engine. Launch the resulting executable with `--sample-library <private-profile/library.json>`.

The generated fork redirects all local application data references to the sample profile, uses a profile-specific settings mutex, disables real engine startup and replaces overlay helper commands/registry writes with inert methods. Desktop and Game Mode use the same sample service, persistent removals/preferences and simulated game state. The existing UI and native window sizing are retained.

Use a normal C: source directory for the generated project; the G: artifact junction can produce padded intermediate XML that the native manifest tool rejects. Output may still be on G:. Do not change the original project's intermediate paths.

Build `SampleTests.csproj` with `-p:SampleAppDir=<private-app-folder>`. Copy its console DLL, deps and runtimeconfig next to the private app's runtime files, then execute that console DLL there; the referenced WinUI assembly requires its Windows App Runtime even without creating a window. It exercises the actual generated service/settings implementation, including remove/relaunch, simulated installation, static overlay settings, clones, malformed/missing manifest refusal and unchanged live settings bytes. It does not establish rendered UI acceptance; open and inspect the native sample separately.
