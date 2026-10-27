# Gate fixture: a runtime file that matches an i with the case-insensitive -like, which LN4 forbids.
function Test-FixtureId([string]$Name) {
    $Name -like 'id_*'
}
