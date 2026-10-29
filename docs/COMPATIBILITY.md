# Compatibility list

`providers/compatibility.json` is the reviewed, per-game list that ships with rtxForge. The app shows its verdict when you haven't recorded your own result. Your own **Working** or **Problem** always comes first.

## Where reports come from

Every report uses the same twelve fields, whichever way it's made:

- **In the app:** **Bug Report** on any game, or Settings › About. Send Report files it as a GitHub issue for you; logs go privately to the maintainers.
- **On the website:** [loew.fi/rtxforge/report](https://loew.fi/rtxforge/report).
- **On GitHub:** the **Beta compatibility report** issue form (`.github/ISSUE_TEMPLATE/beta-report.yml`).

The field ids, labels and answer choices live in `scripts/beta_report.py` (`FIELDS`, `CHOICES`). `tests/test_beta_report.py` checks that they match the website page and the issue form. Change all three together.

## Adding a reviewed report

1. Read the issue and its attachments. Confirm that the NR and MFG results describe what the reporter saw in game, not just installed files.
2. Save the issue body, then add it:

   ```sh
   gh issue view 123 --repo lrnolivia/rtxForge --json body -q .body > report.md
   python3 scripts/compat_list.py add-report --issue 123 --body report.md \
       --verdict Working --appid 2208920 --name "Assassin's Creed Valhalla" --note "Feeder NR on DirectX 12"
   ```

   Use `--exe Game.exe` instead of `--appid` for non-Steam games.
3. Commit the updated `providers/compatibility.json` on a branch and open a pull request.

The curator chooses the verdict. Reports never set it on their own. A listed report keeps only the setup and results: OS, distro, RTX series, rtxForge build, package, features attempted, and the NR and MFG results. It never keeps the GPU model, driver, paths or the reporter's notes. Keep `--note` generic too.

## Schema 2

```json
{
  "appid": "2208920", "exe": "ACValhalla.exe", "name": "Assassin's Creed Valhalla",
  "package": "feeder", "verdict": "Working", "note": "Feeder NR on DirectX 12",
  "reports": [
    {"issue": 123, "date": "2026-10-29", "os": "Linux", "distribution": "Bazzite 42",
     "gpu_series": "RTX 40", "app": "1.0.0-beta.3 · Beta", "package": "Feeder NR 1.1",
     "features": "NR only", "nr": "Working in-game", "mfg": "Not installed"}
  ]
}
```

Schema 1 lists (no `name` or `reports`) still load.
