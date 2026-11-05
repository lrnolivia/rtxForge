# Development

rtxForge has a shared Python engine, a GTK4/libadwaita Linux interface, and a WinUI 3 Windows interface on its development branch. Provider identities, runtime manifests and original-file recovery records are part of the product and must remain compatible.

Use `python3 -m unittest engine.tests.test_v13_core_hardening` and the focused tests under `tests/` for the affected subsystem. Linux packaging and native GUI checks run in Fedora 44 through `.github/workflows/linux-build.yml` and `package-ui-review.yml`. macOS fixture tests do not establish GTK, Gamescope or controller acceptance. Windows build instructions live under `windows/` when that branch is checked out.

## Testing on games

Feature testing on a game is done on a Forge Lab copy, never on the player's own installation. Copies live under `Forge Lab/games-windows` on Windows and `Forge Lab/games` on Linux, and launch with their own logs and prefixes. Hand-placing builds in a real install leaves its install record stale, so the next overlay update reports it as changed and refuses to touch it. If a game cannot yet run from a copy, for example because it must start through its store's authentication, ask the maintainer before changing the real install and keep a backup that matches its install record.

Continuous builds validate main pushes and retain Actions artifacts. Publishing the updater requires an explicit workflow dispatch with `publish_preview` enabled on a reviewed main or approved preview branch. Redesign beta publication requires an explicit dispatch with `publish_beta` enabled on reviewed main. Check the exact source revision, successful required checks, and retained rollback assets before publishing. Documentation and history maintenance alone should not refresh application release assets.

Preserve human authorship and upstream license, copyright and provenance notices. Tool-assisted changes use the maintainer's verified repository identity. Commit messages describe the change without unsolicited tool coauthors, generated-by advertising or session credits. This policy does not remove names of actual dependencies or product features.

For this repository, configure the verified maintainer identity locally and enable the supplied commit-message hook:

```sh
git config --local user.name 'Lauren Olivia'
git config --local user.email 'lrnoliv@gmail.com'
git config --local core.hooksPath .githooks
```

The hook covers local normal and squash commits. The Commit attribution workflow checks proposed commits and PR title/body text used for a squash. Hooks and advisory workflows cannot enforce external API writers: a writer must supply verified author/committer fields and an explicitly reviewed squash message, and the maintainer must verify the returned commit. Repository protection and required checks remain separate controls.

Coordinate shared work through the current `lrnolivia/loew-runner` project record before modifying active branches or integrating changes. Operational handoffs, task status and release history belong under `docs/rtxforge/` there. This repository contains product source, product documentation and required tooling.
