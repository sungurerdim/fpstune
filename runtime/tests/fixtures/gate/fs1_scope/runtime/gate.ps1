# Gate fixture: runtime/gate.ps1 is a dev file exempt from FS1, so its file write is no finding.
function Save-FixtureNote([string]$Folder) {
    Set-Content -LiteralPath (Join-Path $Folder 'gate-note.txt') -Value 'x'
}
