# Bundle builder (decision D3, unit U7 of #127). Windows PowerShell 5.1; ASCII only.
#
#   powershell -NoProfile -File runtime/tools/build.ps1 -Out <bundle.ps1> [-TweaksRoot <dir>]
#              [-RunOut <run.ps1> -Tag <tag> -BundleUrl <url>]
#
# A dev/release tool, not shipped and not part of the runtime: it writes its
# -Out and -RunOut files normally.
#
# Fail-closed inputs: every row id must match <category>:<name> in lower case
# letters, digits and underscore, and the tweak files must all be tracked and
# committed in git with a clean tree under -TweaksRoot (so the same commit
# always gives the same bundle). Anything else stops the build, naming the file.
#
# The bundle is ONE script: Catalogue, Detect, Summary, Journal, Apply (this
# fixed order), then the strings (en, tr) and the tweak catalogue embedded as
# JSON text that the bundle parses when it loads, then the main flow. It is
# UTF-8 without BOM with LF line endings. It is deterministic: inputs are
# read in ordinal order and nothing in it depends on the time or the machine.
# The build prints the bundle SHA-256 as 64 upper-case hex characters.
param(
    [Parameter(Mandatory)][string]$Out,
    [string]$TweaksRoot,
    [string]$RunOut,
    [string]$Tag,
    [string]$BundleUrl
)

$ErrorActionPreference = 'Stop'
[Threading.Thread]::CurrentThread.CurrentCulture = [Globalization.CultureInfo]::InvariantCulture

$runtime = Split-Path -Parent $PSScriptRoot
if (-not $TweaksRoot) { $TweaksRoot = Join-Path (Split-Path -Parent $runtime) 'tweaks' }
if ($RunOut) {
    if (-not $Tag -or -not $BundleUrl) { throw '-RunOut needs -Tag and -BundleUrl.' }
    if ($Tag -cnotmatch '^[A-Za-z0-9._-]+\z') { throw "-Tag may hold only letters, digits, dot, underscore and hyphen: $Tag" }
    if ($BundleUrl -cnotmatch '^https://[A-Za-z0-9._~:/?#@!$&()*+,;=%-]+\z') { throw "-BundleUrl must be an https URL without quotes or spaces: $BundleUrl" }
}

. (Join-Path $runtime 'Catalogue.ps1')

$utf8 = New-Object Text.UTF8Encoding($false)
$lf = [string][char]10
$cr = [string][char]13

function Read-Text([string]$Path) {
    # UTF-8 read (a BOM is dropped), line endings folded to LF, one final LF.
    $text = [IO.File]::ReadAllText($Path, $utf8).Replace($cr + $lf, $lf).Replace($cr, $lf)
    $text.TrimEnd([char]10) + $lf
}

function Get-HereString([string]$Text, [string]$What) {
    # A single-quoted here-string ends at a line that starts with '@ : refuse text that has one.
    if (("`n" + $Text) -clike "*`n'@*") { throw "$What holds a line that starts with '@ and cannot be embedded." }
    "@'" + $lf + $Text + "'@"
}

function ConvertTo-SingleQuoted([string]$Value) {
    # A value placed inside '...' in generated code: a quote is doubled.
    $Value.Replace("'", "''")
}

function Assert-RowName($Row) {
    # Id, category and name come from file paths and are written into code: allow only the safe form.
    if ($Row.Id -cnotmatch '^[a-z0-9_]+:[a-z0-9_]+\z' -or
        $Row.Category -cnotmatch '^[a-z0-9_]+\z' -or
        $Row.Name -cnotmatch '^[a-z0-9_]+\z') {
        throw "Refusing tweak file '$($Row.Path)': its id '$($Row.Id)' is not <category>:<name> in lower case letters, digits and underscore."
    }
}

function Assert-TweaksCommitted([string]$Root, $Rows) {
    # Only committed files may enter the bundle: the tree must be clean and every row tracked.
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'git was not found; the tweak files cannot be checked as committed.' }
    $rootFull = (Resolve-Path -LiteralPath $Root).ProviderPath.TrimEnd([char]92, [char]47)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'   # git writes errors to stderr; the exit code decides
    try {
        $status = @(& git -C $rootFull status --porcelain --untracked-files=all -- . 2>$null | ForEach-Object { "$_" })
        $statusCode = $LASTEXITCODE
        $tracked = @(& git -C $rootFull ls-files -z -- . 2>$null | ForEach-Object { "$_" })
        $trackedCode = $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $previous }
    if ($statusCode -ne 0) { throw "Tweak root is not inside a git work tree (git status failed): $rootFull" }
    $dirty = @($status | Where-Object { $_ -ne '' })
    if ($dirty.Count -gt 0) { throw ("Refusing to build: the tweak tree has untracked, modified or uncommitted files:`n" + ($dirty -join "`n")) }
    if ($trackedCode -ne 0) { throw "git ls-files failed for the tweak root: $rootFull" }
    $set = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    foreach ($entry in ($tracked -join '').Split([char]0)) { if ($entry -ne '') { [void]$set.Add($entry) } }
    foreach ($row in $Rows) {
        $relative = $row.Path.Substring($rootFull.Length + 1).Replace([string][char]92, '/')
        if (-not $set.Contains($relative)) { throw "Refusing to build: tweak file is not tracked by git (untracked or ignored): $($row.Path)" }
    }
}

$sb = New-Object Text.StringBuilder
[void]$sb.Append('param([switch]$NoMain)' + $lf)
[void]$sb.Append('# fpstune bundle: generated by runtime/build.ps1, do not edit.' + $lf + $lf)

foreach ($module in 'Catalogue', 'Detect', 'Summary', 'Journal', 'Apply') {
    $text = Read-Text (Join-Path $runtime "$module.ps1")
    [void]$sb.Append("# ---- $module ----" + $lf + $text + $lf)
}

[void]$sb.Append('# ---- embedded data ----' + $lf)
[void]$sb.Append('$script:FpsEmbeddedStrings = @{}' + $lf)
foreach ($language in 'en', 'tr') {
    $text = Read-Text (Join-Path (Join-Path $runtime 'strings') "$language.json")
    $null = $text | ConvertFrom-Json
    [void]$sb.Append("`$script:FpsEmbeddedStrings['$language'] = (" + (Get-HereString $text "strings/$language.json") + ') | ConvertFrom-Json' + $lf)
}

[void]$sb.Append('$script:FpsEmbeddedCatalogue = @()' + $lf)
$rowCount = 0
$rows = @(Get-FpsCatalogue -Root $TweaksRoot)
foreach ($row in $rows) { Assert-RowName $row }
Assert-TweaksCommitted $TweaksRoot $rows
foreach ($row in $rows) {
    $text = Read-Text $row.Path
    $null = $text | ConvertFrom-Json
    $rowCount++
    [void]$sb.Append('$script:FpsEmbeddedCatalogue += [pscustomobject]@{ ' +
        "Id = '$(ConvertTo-SingleQuoted $row.Id)'; Category = '$(ConvertTo-SingleQuoted $row.Category)'; Name = '$(ConvertTo-SingleQuoted $row.Name)'; Data = (" +
        (Get-HereString $text "tweak $($row.Id)") + ') | ConvertFrom-Json }' + $lf)
}
[void]$sb.Append($lf)

$main = @'
# ---- main ----
function Invoke-FpsMain {
    # detect -> summary -> one prompt -> apply -> results.
    $language = Get-FpsLanguage
    $states = @(foreach ($row in @(Get-FpsCatalogue)) { Get-FpsRowState -Row $row })
    Show-FpsSummary -Rows $states -Language $language
    $fix = @($states | Where-Object { $_.Class -ceq 'will-fix' })
    if ($fix.Count -ceq 0) { return }
    $s = Get-FpsStrings -Language $language
    $inv = [Globalization.CultureInfo]::InvariantCulture
    $answer = Read-Host ([string]::Format($inv, $s.applyPrompt, $fix.Count))
    if ($answer -cne '') { Write-Host $s.applyCancelled; return }
    $result = Invoke-FpsApply -Rows $states
    foreach ($item in @($result.Rows)) {
        $label = switch -CaseSensitive ([string]$item.Status) {
            'fixed' { $s.statusFixed }
            'failed' { $s.statusFailed }
            'skipped' { $s.statusSkipped }
            default { [string]$item.Status }
        }
        $line = "[$label] $($item.RowId)"
        if ($item.Message) { $line += " - $($item.Message)" }
        Write-Host $line
    }
    if ($result.Stopped) { Write-Host ([string]::Format($inv, $s.applyStopped, $result.StopReason)) }
    if ($result.RebootNeeded) { Write-Host $s.applyReboot }
}

if (-not $NoMain) { Invoke-FpsMain }
'@
[void]$sb.Append(($main.Replace($cr + $lf, $lf).TrimEnd([char]10) + $lf))

$bundle = $utf8.GetBytes($sb.ToString())
$sha = [Security.Cryptography.SHA256]::Create()
try {
    $hash = -join @($sha.ComputeHash($bundle) | ForEach-Object { $_.ToString('X2', [Globalization.CultureInfo]::InvariantCulture) })
}
finally { $sha.Dispose() }

[IO.File]::WriteAllBytes($Out, $bundle)

if ($RunOut) {
    $template = Read-Text (Join-Path $runtime 'run.ps1')
    $filled = $template.Replace('__FPS_RELEASE_TAG__', $Tag).Replace('__FPS_BUNDLE_URL__', $BundleUrl).Replace('__FPS_BUNDLE_SHA256__', $hash)
    if ($filled.Contains('__FPS_')) { throw 'run.ps1 still holds a placeholder after filling.' }
    [IO.File]::WriteAllBytes($RunOut, [Text.Encoding]::ASCII.GetBytes($filled))
    Write-Output "run.ps1 written: $($filled.Length) chars"
}

Write-Output "bundle: $($bundle.Length) bytes, $rowCount tweak row(s)"
Write-Output "SHA-256 $hash"
