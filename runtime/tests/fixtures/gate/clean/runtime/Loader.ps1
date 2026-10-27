# Gate fixture: a runtime file that only reads, so FS1, C4 and AS1 stay quiet.
function Get-FixtureText([string]$Path) {
    [IO.File]::ReadAllText($Path, (New-Object Text.UTF8Encoding($false)))
}

function Show-FixtureText([string]$Path) {
    Get-Content -LiteralPath $Path | Out-String | Write-Host
    Get-FixtureText -Path $Path | Out-Null
}
