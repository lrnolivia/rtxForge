param([Parameter(Mandatory)][string]$AppPath)

# Native regression using only the sample library. No real engine or game writes.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$tree = [System.Windows.Automation.TreeScope]::Descendants
$raw = [System.Windows.Automation.TreeWalker]::RawViewWalker
$previewProcess = $null

function Find-Control([string]$Property, [string]$Value) {
    $key = if ($Property -eq 'Id') {
        [System.Windows.Automation.AutomationElement]::AutomationIdProperty
    } else { [System.Windows.Automation.AutomationElement]::NameProperty }
    $condition = New-Object System.Windows.Automation.PropertyCondition($key, $Value)
    $window.FindFirst($tree, $condition)
}

function Wait-Control([string]$Property, [string]$Value) {
    $limit = [DateTime]::UtcNow.AddSeconds(12)
    do {
        $control = Find-Control $Property $Value
        if ($control) { return $control }
        if ($previewProcess.HasExited) { throw 'Preview app exited unexpectedly.' }
        Start-Sleep -Milliseconds 150
    } while ([DateTime]::UtcNow -lt $limit)
    throw "Timed out waiting for $Property '$Value'."
}

function Invoke-Control($Control) {
    $pattern = $null
    while ($Control) {
        if ($Control.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$pattern)) {
            $pattern.Invoke()
            return
        }
        $Control = $raw.GetParent($Control)
    }
    throw 'No invokable ancestor.'
}

function Select-Control($Control) {
    ([System.Windows.Automation.SelectionItemPattern]$Control.GetCurrentPattern(
        [System.Windows.Automation.SelectionItemPattern]::Pattern)).Select()
    Start-Sleep -Milliseconds 250
}

function Set-Search([string]$Value) {
    $search = Wait-Control Id 'TextBox'
    ([System.Windows.Automation.ValuePattern]$search.GetCurrentPattern(
        [System.Windows.Automation.ValuePattern]::Pattern)).SetValue($Value)
    Start-Sleep -Milliseconds 300
}

function Check-Install([string]$Ready) {
    Invoke-Control (Wait-Control Id 'CompactInstallText')
    Invoke-Control (Wait-Control Name 'Continue')
    $null = Wait-Control Name 'Review Installation'
    $null = Wait-Control Name $Ready
    Invoke-Control (Wait-Control Id 'CloseButton')
    Start-Sleep -Milliseconds 300
}

try {
    $previewProcess = Start-Process -FilePath (Resolve-Path -LiteralPath $AppPath).Path `
        -ArgumentList '--preview' -WindowStyle Hidden -PassThru
    $limit = [DateTime]::UtcNow.AddSeconds(15)
    do {
        Start-Sleep -Milliseconds 200
        $previewProcess.Refresh()
    } while ($previewProcess.MainWindowHandle -eq 0 -and !$previewProcess.HasExited -and [DateTime]::UtcNow -lt $limit)
    if ($previewProcess.MainWindowHandle -eq 0) { throw 'Preview window did not open.' }
    $window = [System.Windows.Automation.AutomationElement]::FromHandle($previewProcess.MainWindowHandle)
    $null = Wait-Control Id 'FilterAvailable'
    $null = Wait-Control Name 'Crimson Desert'

    Select-Control (Wait-Control Id 'FilterAvailable')
    Check-Install '4 games ready'
    Write-Output 'PASS: Available reviews only the four uninstalled sample games.'

    # Leave an unselected page in navigation history, twice. Previously these
    # pages handled compact actions before the active page with its selection.
    foreach ($cycle in 1..2) {
        Select-Control (Wait-Control Id 'SettingsItem')
        $navItems = $window.FindAll($tree, (New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::NameProperty, 'Library')))
        $libraryNav = $navItems | Where-Object { $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::ListItem } | Select-Object -First 1
        if (!$libraryNav) { throw 'Library navigation item missing.' }
        Select-Control $libraryNav
        $null = Wait-Control Id 'FilterAll'
    }
    Select-Control (Wait-Control Id 'FilterAll')
    Set-Search 'The '
    Invoke-Control (Wait-Control Id 'SelectAllButton')
    $null = Wait-Control Name 'Install Selected (2)'
    Check-Install '2 games ready'
    Write-Output 'PASS: After repeated navigation, compact Install reviews only the two checked games.'

    Invoke-Control (Wait-Control Name 'Restore Original Files')
    $null = Wait-Control Name 'Review Restoration'
    $null = Wait-Control Name '1 game ready'
    Invoke-Control (Wait-Control Id 'CloseButton')
    Start-Sleep -Milliseconds 300
    Write-Output 'PASS: Compact Restore reviews only the installed checked game.'

    Invoke-Control (Wait-Control Id 'SelectAllButton')
    Select-Control (Wait-Control Id 'FilterAvailable')
    Set-Search 'Crimson'
    Check-Install '1 game ready'
    Write-Output 'PASS: With no checks, Available plus search limits Install to one game.'
} finally {
    if ($previewProcess -and !$previewProcess.HasExited) { Stop-Process -Id $previewProcess.Id }
}
