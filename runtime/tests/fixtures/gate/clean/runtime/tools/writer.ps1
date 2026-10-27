# Gate fixture: dev tools may write files; FS1 covers runtime/*.ps1 only, not tools.
function Save-FixtureNote([string]$Folder) {
    'x' | Out-File -FilePath (Join-Path $Folder 'note.txt')
}
