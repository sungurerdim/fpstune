# Catalogue loader and command invoker (decisions D2/D3).
# Dot-sourced by the runtime; Windows PowerShell 5.1 compatible. Defines
# functions only, so loading it has no side effects.

function Get-FpsCatalogue {
    <#
    .SYNOPSIS
      Loads every tweaks/<category>/<name>.json under a root folder.
    .DESCRIPTION
      The row id is "<category>:<name>" derived from the path; it is never read
      from the file. A file that is not valid JSON (or not a JSON object) makes
      the whole load fail with the file named, so a broken row can never be
      silently dropped. Rows come back in ordinal path order.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Root)

    if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
        throw "Catalogue root not found: $Root"
    }
    $rootFull = (Resolve-Path -LiteralPath $Root).ProviderPath.TrimEnd('\', '/')

    $paths = [string[]]@(Get-ChildItem -LiteralPath $rootFull -Filter '*.json' -Recurse -File | ForEach-Object { $_.FullName })
    [Array]::Sort($paths, [StringComparer]::Ordinal)

    foreach ($path in $paths) {
        $relative = $path.Substring($rootFull.Length + 1)
        $parts = $relative -split '[\\/]'
        if ($parts.Count -ne 2) {
            throw "Tweak file must be <root>/<category>/<name>.json: $path"
        }
        $category = $parts[0]
        $name = [IO.Path]::GetFileNameWithoutExtension($parts[1])

        try {
            $text = [IO.File]::ReadAllText($path, (New-Object Text.UTF8Encoding($false)))
            $data = $text | ConvertFrom-Json -ErrorAction Stop
        }
        catch {
            throw "Cannot parse tweak file '$path': $($_.Exception.Message)"
        }
        if ($data -isnot [pscustomobject]) {
            throw "Cannot parse tweak file '$path': the content is not a JSON object."
        }

        [pscustomobject]@{
            Id       = "${category}:${name}"
            Category = $category
            Name     = $name
            Path     = $path
            Data     = $data
        }
    }
}

function Invoke-FpsCommand {
    <#
    .SYNOPSIS
      Runs one catalogue command string and returns its output.
    .DESCRIPTION
      The string becomes a scriptblock with param($Instance, $Target) in front
      and runs with ErrorActionPreference=Stop, so any error is a failure. A
      native executable that exits non-zero is a failure too. A command that
      does not parse throws before anything runs.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Command,
        $Instance,
        $Target
    )

    $scriptBlock = [scriptblock]::Create('param($Instance, $Target) ' + $Command)
    $global:LASTEXITCODE = 0
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Stop'
    try {
        $output = @(& $scriptBlock $Instance $Target)
    }
    finally {
        $ErrorActionPreference = $previous
    }
    if ($global:LASTEXITCODE -ne 0) {
        throw "A native command exited with code $($global:LASTEXITCODE)."
    }
    $output
}
