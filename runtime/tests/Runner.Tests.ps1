# Regression guard: test.ps1 -Culture must really switch the thread culture.
# test.ps1 exports the requested name in FPSTUNE_TEST_CULTURE; without -Culture
# these checks are skipped.
#
# Asserts the .NET thread culture, which is what all formatting and parsing in
# the runtime uses. Get-Culture/$PSCulture are deliberately not used: under
# Windows PowerShell 5.1 the console host caches the culture it started with,
# so they ignore a thread culture set afterwards.
BeforeDiscovery {
    $script:requested = $env:FPSTUNE_TEST_CULTURE
    $script:noCulture = [string]::IsNullOrEmpty($script:requested)
    $script:commaCulture = $script:requested -in 'fr-FR', 'tr-TR'
}

BeforeAll {
    $script:requested = $env:FPSTUNE_TEST_CULTURE
}

Describe 'Runner culture switch' {
    It 'sets the thread culture to the requested one' -Skip:$script:noCulture {
        [Globalization.CultureInfo]::CurrentCulture.Name | Should -Be $script:requested
    }

    It 'sets the thread UI culture to the requested one' -Skip:$script:noCulture {
        [Globalization.CultureInfo]::CurrentUICulture.Name | Should -Be $script:requested
    }

    It 'formats a decimal with a comma under a comma-decimal culture' -Skip:(-not $script:commaCulture) {
        # .ToString() with no argument uses the current thread culture.
        (1.5).ToString() | Should -Be '1,5'
        # Casting to string in PowerShell is culture-invariant by design.
        [string]1.5 | Should -Be '1.5'
    }
}
