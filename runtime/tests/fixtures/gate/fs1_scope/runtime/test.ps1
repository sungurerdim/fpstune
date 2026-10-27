# Gate fixture: runtime/test.ps1 is a dev file exempt from FS1, so its file write is no finding.
function Save-FixtureNote([string]$Folder) {
    'x' | Out-File -FilePath (Join-Path $Folder 'test-note.txt')
}
