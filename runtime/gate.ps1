# Catalogue gate (decisions D4 and D7 G2/G3). Windows PowerShell 5.1.
#
#   powershell -NoProfile -File runtime/gate.ps1 [-Root <root>]
#
# <root> holds tweaks/<category>/<name>.json and runtime/*.ps1 (default: the
# repository root). One line per violation: "<rule-id> <file>: <reason>".
# Exit code 0 on a clean root, 1 on any finding.
#
# Rules: LN1 native exe output never feeds applicable/detect/target/instances,
# LN2 human-text properties are never compared or parsed, LN3 every command
# parses, C4 Turkish letters only in tr fields, C8 one registry write per tweak
# unless a compound is named, C9 no machine literal, C11 no number with %, ms or
# fps in why/fixed, ID1 the path forms a valid id, FS1 the runtime writes no
# file, AS1 runtime/run.ps1 is plain ASCII, LD1 the catalogue does not load.
param([string]$Root)

$ErrorActionPreference = 'Stop'
# Case-insensitive matching must not depend on the machine culture (Turkish I).
[Threading.Thread]::CurrentThread.CurrentCulture = [Globalization.CultureInfo]::InvariantCulture
if (-not $Root) { $Root = Split-Path -Parent $PSScriptRoot }
if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
    Write-Output "LD1 ${Root}: root folder not found"
    exit 1
}
. (Join-Path $PSScriptRoot 'Catalogue.ps1')

$rootFull = (Resolve-Path -LiteralPath $Root).ProviderPath.TrimEnd('\', '/')
$utf8 = New-Object Text.UTF8Encoding($false)
$findings = New-Object Collections.Generic.List[string]
$nativeCache = @{}

# Language AST types, spelled once.
$L = 'Management.Automation.Language'

# Turkish letters from code points (c, g, i-dotless, I-dotted, o, s, u and the capitals).
$turkishRe = '[' + (-join (@(0x00E7, 0x011F, 0x0131, 0x0130, 0x00F6, 0x015F, 0x00FC, 0x00C7, 0x011E, 0x00D6, 0x015E, 0x00DC) | ForEach-Object { [char]$_ })) + ']'

# C9 machine literals, joined from parts so this file never holds them.
$c9Literals = @(
    @('Q25G4', 'S'), @('41613607', '3'), @('Oyunla', 'r'), @('RTX 307', '0'), @('i7-11800', 'H')
) | ForEach-Object { [regex]::Escape(-join $_) }
$c9Re = '(?i)(' + ($c9Literals -join '|') + ')'
$c9ProfileRe = '(?i)(?<![A-Za-z])[A-Z]:\\Users\\(?!Public\b|Default\b|All Users\b)[^\\''"\s$%]+'
$c9DriveRe = '(?i)(?<![A-Za-z])[D-Z]:\\'

$humanProps = 'InterfaceDescription', 'Description', 'FriendlyName', 'DisplayName', 'DisplayValue', 'Caption', 'Message'
$compareRe = '^[ic]?(eq|ne|gt|ge|lt|le|like|notlike|match|notmatch|replace|split|contains|notcontains|in|notin)$'
$keepTextMethods = 'ToLower', 'ToUpper', 'ToLowerInvariant', 'ToUpperInvariant', 'Trim', 'TrimStart', 'TrimEnd', 'ToString'
$parseTextMethods = 'Contains', 'StartsWith', 'EndsWith', 'Split', 'Replace', 'IndexOf', 'LastIndexOf', 'Match', 'Matches', 'IsMatch', 'Substring', 'Remove', 'Insert'
$fileWriteCmdRe = '^(?i)(Set-Content|Add-Content|Out-File|New-Item|Copy-Item|Move-Item|Rename-Item|Export-Csv|Export-Clixml|Tee-Object|Start-Transcript|Save-Help|sc|ac|ni|cpi|copy|cp|mi|move|mv|rni|ren|tee|epcsv)$'

function Add-Finding([string]$Rule, [string]$File, [string]$Reason) {
    $oneLine = ($Reason -replace '\s+', ' ').Trim()
    $findings.Add("$Rule ${File}: $oneLine")
}

function Get-Rel([string]$Path) {
    $Path.Substring($rootFull.Length + 1).Replace('\', '/')
}

function Read-Utf8([string]$Path) {
    [IO.File]::ReadAllText($Path, $utf8)
}

function Read-Script([string]$Text) {
    $tokens = $null
    $errors = $null
    $ast = [Management.Automation.Language.Parser]::ParseInput($Text, [ref]$tokens, [ref]$errors)
    [pscustomobject]@{ Ast = $ast; Errors = @($errors) }
}

function Find-Ast($Ast, [type]$Type) {
    $Ast.FindAll({ param($a) $a -is $Type }.GetNewClosure(), $true)
}

# All string values below a JSON node, skipping every property named "tr".
function Get-JsonStrings($Node, [bool]$SkipTr) {
    if ($Node -is [string]) { $Node; return }
    if ($Node -is [pscustomobject]) {
        foreach ($property in $Node.PSObject.Properties) {
            if ($SkipTr -and $property.Name -ceq 'tr') { continue }
            $property.Name
            Get-JsonStrings $property.Value $SkipTr
        }
        return
    }
    if ($Node -is [System.Collections.IEnumerable]) {
        foreach ($item in $Node) { Get-JsonStrings $item $SkipTr }
    }
}

function Get-CommandFields($Data) {
    foreach ($name in 'applicable', 'instances', 'detect', 'apply', 'revert') {
        $property = $Data.PSObject.Properties[$name]
        if ($property -and $property.Value -is [string]) { [pscustomobject]@{ Field = $name; Text = $property.Value } }
    }
    $target = $Data.PSObject.Properties['target']
    if ($target -and $target.Value -is [pscustomobject]) {
        $command = $target.Value.PSObject.Properties['command']
        if ($command -and $command.Value -is [string]) { [pscustomobject]@{ Field = 'target.command'; Text = $command.Value } }
    }
}

# A command name is native when it is an .exe/.com, resolves to an application,
# or resolves to nothing and is not shaped like Verb-Noun.
function Test-Native([string]$Name) {
    if ($nativeCache.ContainsKey($Name)) { return $nativeCache[$Name] }
    $native = $false
    if ($Name -match '(?i)\.(exe|com)$') { $native = $true }
    else {
        $found = $null
        try { $found = Get-Command -Name $Name -ErrorAction SilentlyContinue | Select-Object -First 1 } catch { $found = $null }
        if ($found) { $native = ($found.CommandType -eq 'Application') }
        else { $native = ($Name -notmatch '^[A-Za-z]+-[A-Za-z0-9]+$') }
    }
    $nativeCache[$Name] = $native
    $native
}

# True when the output of the command is assigned, piped on, or nested in an
# expression ($(), @(), parentheses, conversions, members, operators).
function Test-OutputUsed($Node) {
    $current = $Node
    while ($true) {
        $parent = $current.Parent
        if ($null -eq $parent) { return $false }
        if ($parent -is [Management.Automation.Language.PipelineAst]) {
            $elements = @($parent.PipelineElements)
            $index = [array]::IndexOf($elements, $current)
            if ($index -ge 0 -and $index -lt $elements.Count - 1) {
                $next = $elements[$index + 1]
                if ($next -is [Management.Automation.Language.CommandAst] -and $next.GetCommandName() -match '^(?i)Out-Null$') { return $false }
                return $true
            }
            $current = $parent
            continue
        }
        if ($current -is [Management.Automation.Language.StatementBlockAst] -and $parent -isnot [Management.Automation.Language.SubExpressionAst] -and $parent -isnot [Management.Automation.Language.ArrayExpressionAst]) {
            $current = $parent
            continue
        }
        if ($parent -is [Management.Automation.Language.StatementBlockAst]) {
            $grand = $parent.Parent
            if ($grand -is [Management.Automation.Language.SubExpressionAst] -or $grand -is [Management.Automation.Language.ArrayExpressionAst]) { return $true }
            $current = $parent
            continue
        }
        if ($parent -is [Management.Automation.Language.NamedBlockAst] -or $parent -is [Management.Automation.Language.ScriptBlockAst]) { return $false }
        return $true
    }
}

# True when the member access is compared, split, replaced or pattern-matched.
function Test-TextUse($Member) {
    $current = $Member
    while ($true) {
        $parent = $current.Parent
        if ($null -eq $parent) { return $false }
        if ($parent -is [Management.Automation.Language.BinaryExpressionAst]) {
            return ($parent.Operator.ToString().ToLowerInvariant() -match $compareRe)
        }
        if ($parent -is [Management.Automation.Language.UnaryExpressionAst]) {
            return ($parent.TokenKind.ToString() -match '^(?i)[ic]split$')
        }
        if ($parent -is [Management.Automation.Language.ParenExpressionAst] -or
            $parent -is [Management.Automation.Language.CommandExpressionAst] -or
            $parent -is [Management.Automation.Language.ConvertExpressionAst] -or
            $parent -is [Management.Automation.Language.CommandParameterAst]) {
            $current = $parent
            continue
        }
        if ($parent -is [Management.Automation.Language.PipelineAst]) {
            $elements = @($parent.PipelineElements)
            if ($elements.Count -eq 1) { $current = $parent; continue }
            $index = [array]::IndexOf($elements, $current)
            if ($index -ge 0 -and $index -lt $elements.Count - 1) {
                $next = $elements[$index + 1]
                return ($next -is [Management.Automation.Language.CommandAst] -and $next.GetCommandName() -match '^(?i)(Select-String|sls)$')
            }
            return $false
        }
        if ($parent -is [Management.Automation.Language.InvokeMemberExpressionAst]) {
            $method = if ($parent.Member -is [Management.Automation.Language.StringConstantExpressionAst]) { $parent.Member.Value } else { '' }
            if ([object]::ReferenceEquals($parent.Expression, $current)) {
                if ($keepTextMethods -contains $method) { $current = $parent; continue }
                return ($parseTextMethods -contains $method)
            }
            return ($parent.Static -and $parent.Expression -is [Management.Automation.Language.TypeExpressionAst] -and $parent.Expression.TypeName.Name -match '^(?i)(System\.Text\.RegularExpressions\.)?regex$')
        }
        if ($parent -is [Management.Automation.Language.CommandAst]) {
            return ($parent.GetCommandName() -match '^(?i)(Select-String|sls)$')
        }
        return $false
    }
}

function Test-TextWhereObject($Command) {
    if ($Command.GetCommandName() -notmatch '^(?i)(Where-Object|where|\?)$') { return $false }
    $compares = $false
    $named = $false
    foreach ($element in $Command.CommandElements) {
        if ($element -is [Management.Automation.Language.CommandParameterAst] -and $element.ParameterName.ToLowerInvariant() -match $compareRe) { $compares = $true }
        if ($element -is [Management.Automation.Language.StringConstantExpressionAst] -and $humanProps -contains $element.Value) { $named = $true }
    }
    $compares -and $named
}

function Get-RegistryWriteCount($Ast) {
    $count = 0
    foreach ($command in (Find-Ast $Ast ([Management.Automation.Language.CommandAst]))) {
        $name = $command.GetCommandName()
        if (-not $name) { continue }
        if ($name -match '^(?i)(Set-ItemProperty|New-ItemProperty|sp)$') { $count++ }
        elseif ($name -match '^(?i)reg(\.exe)?$' -and $command.CommandElements.Count -gt 1) {
            $verb = $command.CommandElements[1]
            if ($verb -is [Management.Automation.Language.StringConstantExpressionAst] -and $verb.Value -match '^(?i)(add|import)$') { $count++ }
        }
    }
    $count
}

# ---- tweaks -----------------------------------------------------------------
$tweaksRoot = Join-Path $rootFull 'tweaks'
if (Test-Path -LiteralPath $tweaksRoot -PathType Container) {
    $rows = @()
    try { $rows = @(Get-FpsCatalogue -Root $tweaksRoot) }
    catch { Add-Finding 'LD1' 'tweaks' $_.Exception.Message }

    foreach ($row in $rows) {
        $file = Get-Rel $row.Path
        $data = $row.Data

        # ID1
        if ($row.Id -cnotmatch '^[a-z0-9_]+:[a-z0-9_]+$') {
            Add-Finding 'ID1' $file "path gives the id '$($row.Id)', which is not <category>:<name> in lower case letters, digits and underscore"
        }

        # C4 outside tr fields
        foreach ($text in @(Get-JsonStrings $data $true)) {
            if ($text -cmatch $turkishRe) { Add-Finding 'C4' $file 'Turkish letters outside a tr field'; break }
        }

        # C11 in why and fixed
        foreach ($name in 'why', 'fixed') {
            $property = $data.PSObject.Properties[$name]
            if (-not $property) { continue }
            foreach ($text in @(Get-JsonStrings $property.Value $false)) {
                if ($text -match '(?i)(\d\s*(%|ms\b|fps\b))|(%\s*\d)') { Add-Finding 'C11' $file "$name claims a measured number: '$text'"; break }
            }
        }

        # command rules
        $registryWrites = 0
        foreach ($item in @(Get-CommandFields $data)) {
            $field = $item.Field
            $text = $item.Text

            if ($text -cmatch $turkishRe) { Add-Finding 'C4' $file "Turkish letters in $field" }
            if ($text -match $c9Re -or $text -cmatch $c9ProfileRe -or $text -match $c9DriveRe) {
                Add-Finding 'C9' $file "machine-specific literal in $field"
            }

            $parsed = Read-Script $text
            if ($parsed.Errors.Count -gt 0) {
                Add-Finding 'LN3' $file "$field does not parse: $($parsed.Errors[0].Message)"
                continue
            }
            $ast = $parsed.Ast

            if ($field -in 'applicable', 'instances', 'detect', 'target.command') {
                foreach ($command in (Find-Ast $ast ([Management.Automation.Language.CommandAst]))) {
                    $name = $command.GetCommandName()
                    if ($name -and (Test-Native $name) -and (Test-OutputUsed $command)) {
                        Add-Finding 'LN1' $file "$field uses the output of the native command '$name'"
                    }
                }
            }

            $textUse = $false
            foreach ($member in (Find-Ast $ast ([Management.Automation.Language.MemberExpressionAst]))) {
                if ($member -is [Management.Automation.Language.InvokeMemberExpressionAst] -or $member.Static) { continue }
                if ($member.Member -isnot [Management.Automation.Language.StringConstantExpressionAst]) { continue }
                if ($humanProps -contains $member.Member.Value -and (Test-TextUse $member)) { $textUse = $true }
            }
            foreach ($command in (Find-Ast $ast ([Management.Automation.Language.CommandAst]))) {
                if (Test-TextWhereObject $command) { $textUse = $true }
            }
            if ($textUse) { Add-Finding 'LN2' $file "$field compares or parses a human-text property" }

            if ($field -eq 'apply') { $registryWrites = Get-RegistryWriteCount $ast }
        }

        # C8
        $compound = $data.PSObject.Properties['compound']
        $hasCompound = $compound -and $compound.Value -is [string] -and $compound.Value.Length -gt 0
        if ($registryWrites -gt 1 -and -not $hasCompound) {
            Add-Finding 'C8' $file "apply makes $registryWrites registry writes and the tweak names no compound"
        }
    }
}

# ---- runtime ----------------------------------------------------------------
$runtimeRoot = Join-Path $rootFull 'runtime'
if (Test-Path -LiteralPath $runtimeRoot -PathType Container) {
    foreach ($item in @(Get-ChildItem -LiteralPath $runtimeRoot -Filter '*.ps1' -File | Sort-Object Name)) {
        $file = Get-Rel $item.FullName
        $text = Read-Utf8 $item.FullName

        if ($text -cmatch $turkishRe) { Add-Finding 'C4' $file 'Turkish letters in a runtime script' }
        if ($text -match $c9Re -or $text -cmatch $c9ProfileRe -or $text -match $c9DriveRe) {
            Add-Finding 'C9' $file 'machine-specific literal in a runtime script'
        }

        $parsed = Read-Script $text
        if ($parsed.Errors.Count -gt 0) {
            Add-Finding 'LN3' $file "does not parse: $($parsed.Errors[0].Message)"
            continue
        }
        $ast = $parsed.Ast

        $writes = New-Object Collections.Generic.List[string]
        foreach ($command in (Find-Ast $ast ([Management.Automation.Language.CommandAst]))) {
            $name = $command.GetCommandName()
            if ($name -and $name -match $fileWriteCmdRe) { $writes.Add($name) }
            elseif ($name -match '^(?i)New-Object$' -and $command.Extent.Text -match '(?i)StreamWriter|FileStream') { $writes.Add('New-Object file stream') }
        }
        foreach ($call in (Find-Ast $ast ([Management.Automation.Language.InvokeMemberExpressionAst]))) {
            if ($call.Static -and $call.Expression -is [Management.Automation.Language.TypeExpressionAst] -and
                $call.Expression.TypeName.Name -match '^(?i)(System\.)?IO\.(File|Directory|StreamWriter|FileStream)$' -and
                $call.Member -is [Management.Automation.Language.StringConstantExpressionAst] -and
                $call.Member.Value -match '^(?i)(Write|Append|Create|Copy|Move|Replace|Delete|new)') {
                $writes.Add("$($call.Expression.TypeName.Name)::$($call.Member.Value)")
            }
        }
        foreach ($redirect in (Find-Ast $ast ([Management.Automation.Language.FileRedirectionAst]))) {
            if ($redirect.Location.Extent.Text -ne '$null') { $writes.Add('redirection') }
        }
        if ($writes.Count -gt 0) {
            Add-Finding 'FS1' $file "the runtime writes a file ($((@($writes | Select-Object -Unique)) -join ', '))"
        }

        if ($item.Name -ceq 'run.ps1') {
            $bytes = [IO.File]::ReadAllBytes($item.FullName)
            if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
                Add-Finding 'AS1' $file 'starts with a UTF-8 byte order mark'
            }
            else {
                for ($i = 0; $i -lt $bytes.Length; $i++) {
                    if ($bytes[$i] -gt 127) { Add-Finding 'AS1' $file "non-ASCII byte at offset $i"; break }
                }
            }
        }
    }

    # C4 in the runtime string tables: only tr.json may hold Turkish letters.
    $stringsRoot = Join-Path $runtimeRoot 'strings'
    if (Test-Path -LiteralPath $stringsRoot -PathType Container) {
        foreach ($item in @(Get-ChildItem -LiteralPath $stringsRoot -Filter '*.json' -File | Sort-Object Name)) {
            if ($item.Name -ceq 'tr.json') { continue }
            if ((Read-Utf8 $item.FullName) -cmatch $turkishRe) { Add-Finding 'C4' (Get-Rel $item.FullName) 'Turkish letters outside runtime/strings/tr.json' }
        }
    }
}

foreach ($line in $findings) { Write-Output $line }
if ($findings.Count -gt 0) { exit 1 }
exit 0
