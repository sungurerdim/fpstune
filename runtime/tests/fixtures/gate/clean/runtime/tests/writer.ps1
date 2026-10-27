# Gate fixture: test code may write files; FS1 covers runtime/*.ps1 only, not tests.
function Save-FixtureNote([string]$Folder) {
    Set-Content -LiteralPath (Join-Path $Folder 'note.txt') -Value 'x'
}
