# Gate fixture: a runtime file that writes a file, which FS1 forbids.
function Save-FixtureNote {
    Set-Content -LiteralPath (Join-Path $env:TEMP 'fpstune-note.txt') -Value 'x'
}
