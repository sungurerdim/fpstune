# fpstune bootstrap (decision D3, unit U7 of #127). ASCII only.
#
# This is a template: build.ps1 -RunOut fills the three placeholders below
# (release tag, bundle URL, bundle SHA-256 in upper-case hex).
#
#   irm https://github.com/sungurerdim/fpstune/releases/download/<tag>/run.ps1 | iex
#
# What it does, in this order:
#   1. enables TLS 1.2;
#   2. when not elevated, starts itself again elevated with the same one-liner
#      and stops (nothing is downloaded before elevation);
#   3. downloads the bundle into memory (the only network call);
#   4. refuses to run it unless its SHA-256 equals the pinned value;
#   5. decodes it as UTF-8 and runs it as a script block.
# It writes no file.

$FpsReleaseTag = '__FPS_RELEASE_TAG__'
$FpsBundleUrl = '__FPS_BUNDLE_URL__'
$FpsBundleSha256 = '__FPS_BUNDLE_SHA256__'

function Test-FpsElevated {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    [bool]$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-FpsBundleBytes {
    param([Parameter(Mandatory)][string]$Url)
    $client = New-Object Net.WebClient
    try {
        $client.Proxy.Credentials = [Net.CredentialCache]::DefaultCredentials
        , [byte[]]$client.DownloadData($Url)
    }
    finally {
        $client.Dispose()
    }
}

function Get-FpsSha256Hex {
    param([Parameter(Mandatory)][byte[]]$Bytes)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $hash = $sha.ComputeHash($Bytes)
        -join @($hash | ForEach-Object { $_.ToString('X2', [Globalization.CultureInfo]::InvariantCulture) })
    }
    finally {
        $sha.Dispose()
    }
}

[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

if (-not (Test-FpsElevated)) {
    $oneLiner = "irm https://github.com/sungurerdim/fpstune/releases/download/$FpsReleaseTag/run.ps1 | iex"
    Start-Process -FilePath powershell -Verb RunAs -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-NoExit', '-Command', $oneLiner)
    exit
}

$bytes = Get-FpsBundleBytes -Url $FpsBundleUrl
$actual = Get-FpsSha256Hex -Bytes $bytes
if ($actual -cne $FpsBundleSha256.ToUpperInvariant()) {
    Write-Warning "Refusing to run: the downloaded bundle does not match the pinned SHA-256 for $FpsReleaseTag. Nothing was run."
    exit 1
}

$text = (New-Object Text.UTF8Encoding($false)).GetString($bytes)
& ([scriptblock]::Create($text))
