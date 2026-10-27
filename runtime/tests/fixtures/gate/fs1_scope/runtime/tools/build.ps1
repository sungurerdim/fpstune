# Gate fixture: runtime/tools/build.ps1 is a dev tool outside FS1, so its file write is no finding.
function Save-FixtureBuild([string]$Folder) {
    [IO.File]::WriteAllText((Join-Path $Folder 'build-note.txt'), 'x')
}
