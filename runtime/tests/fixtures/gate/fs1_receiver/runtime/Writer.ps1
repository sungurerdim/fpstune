# Gate fixture: a runtime file that writes a file through a type held in a variable, which FS1 forbids.
function Save-FixtureNote {
    $fileApi = [IO.File]
    $fileApi::WriteAllBytes((Join-Path $env:TEMP 'fpstune-note.bin'), [byte[]](1))
}
