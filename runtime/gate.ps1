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
# parses, LN4 a pattern holding the letter i or an ASCII letter range is matched
# case-sensitively, C4 Turkish letters only in tr fields, C8 one registry write per tweak
# unless a compound is named, C9 no machine literal, C11 no number with %, ms or
# fps in why/fixed, ID1 the path forms a valid id, FS1 the runtime writes no
# file (cmdlet, .NET method by type or by name, writer, redirection), AS1 runtime/run.ps1 is plain ASCII, LD1 the catalogue does not load.
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
# File-writing cmdlets and aliases, matched against the lower-cased command name.
$fileWriteCmdRe = '^(set-content|add-content|out-file|new-item|copy-item|move-item|rename-item|export-csv|export-clixml|tee-object|start-transcript|save-help|sc|ac|ni|cpi|copy|cp|mi|move|mv|rni|ren|tee|epcsv)$'
# .NET types that write, and the static methods and instance methods that do so by name.
$fileTypeRe = '^(system\.)?io\.(file|directory|streamwriter|binarywriter|filestream)$'
$fileStaticWriteRe = '^(write|append|create|copy|move|replace|delete|openwrite|encrypt|decrypt|set)'
$instanceWriteRe = '^(save|saveas|writealltext|writeallbytes|writealllines|appendalltext|appendalllines|createtext|appendtext|moveto)$'

function Add-Finding([string]$Rule, [string]$File, [string]$Reason) {
    $oneLine = ($Reason -replace '\s+', ' ').Trim()
    $findings.Add("$Rule ${File}: $oneLine")
}

# The lower-cased command name, or '' when the command has no static name.
function Get-LowerName($Command) {
    $name = $Command.GetCommandName()
    if ($name) { $name.ToLowerInvariant() } else { '' }
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
    if ($Name.ToLowerInvariant() -cmatch '\.(exe|com)$') { $native = $true }
    else {
        $found = $null
        try { $found = Get-Command -Name $Name -ErrorAction SilentlyContinue | Select-Object -First 1 } catch { $found = $null }
        if ($found) { $native = ($found.CommandType -eq 'Application') }
        else { $native = ($Name -cnotmatch '^[A-Za-z]+-[A-Za-z0-9]+$') }
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
                if ($next -is [Management.Automation.Language.CommandAst] -and (Get-LowerName $next) -ceq 'out-null') { return $false }
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
            return ($parent.TokenKind.ToString().ToLowerInvariant() -cmatch '^[ic]split$')
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
                return ($next -is [Management.Automation.Language.CommandAst] -and (Get-LowerName $next) -cmatch '^(select-string|sls)$')
            }
            return $false
        }
        if ($parent -is [Management.Automation.Language.InvokeMemberExpressionAst]) {
            $method = if ($parent.Member -is [Management.Automation.Language.StringConstantExpressionAst]) { $parent.Member.Value } else { '' }
            if ([object]::ReferenceEquals($parent.Expression, $current)) {
                if ($keepTextMethods -contains $method) { $current = $parent; continue }
                return ($parseTextMethods -contains $method)
            }
            return ($parent.Static -and $parent.Expression -is [Management.Automation.Language.TypeExpressionAst] -and $parent.Expression.TypeName.Name.ToLowerInvariant() -cmatch '^(system\.text\.regularexpressions\.)?regex$')
        }
        if ($parent -is [Management.Automation.Language.CommandAst]) {
            return ((Get-LowerName $parent) -cmatch '^(select-string|sls)$')
        }
        return $false
    }
}

function Test-TextWhereObject($Command) {
    if ((Get-LowerName $Command) -cnotmatch '^(where-object|where|\?)$') { return $false }
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
        if ($name.ToLowerInvariant() -cmatch '^(set-itemproperty|new-itemproperty|sp)$') { $count++ }
        elseif ($name.ToLowerInvariant() -cmatch '^reg(\.exe)?$' -and $command.CommandElements.Count -gt 1) {
            $verb = $command.CommandElements[1]
            if ($verb -is [Management.Automation.Language.StringConstantExpressionAst] -and $verb.Value.ToLowerInvariant() -cmatch '^(add|import)$') { $count++ }
        }
    }
    $count
}

# ---- LN4: case-folding patterns ----------------------------------------------
# The literal text of a pattern operand, or $null when it is not a literal.
# A replace/split operand may be a list: its first element is the pattern.
function Get-PatternLiteral($Node) {
    if ($Node -is [Management.Automation.Language.ArrayLiteralAst]) { $Node = $Node.Elements[0] }
    while ($Node -is [Management.Automation.Language.ParenExpressionAst]) {
        $inner = @($Node.Pipeline.PipelineElements)
        if ($inner.Count -ne 1 -or $inner[0] -isnot [Management.Automation.Language.CommandExpressionAst]) { return $null }
        $Node = $inner[0].Expression
    }
    if ($Node -is [Management.Automation.Language.StringConstantExpressionAst]) { return $Node.Value }
    if ($Node -is [Management.Automation.Language.ExpandableStringExpressionAst]) {
        return ($Node.Value -creplace '\$\{[^}]*\}|\$\([^)]*\)|\$[A-Za-z_][\w:]*', '')
    }
    $null
}

# An ASCII letter range inside brackets, or the letter i/I (the Turkish pair).
function Test-FoldingPattern([string]$Pattern) {
    ($Pattern -cmatch '[iI]') -or ($Pattern -cmatch '\[[^\]]*[A-Za-z]-[A-Za-z][^\]]*\]')
}

# An inline option that turns case-insensitivity on: (?i) (?mi) (?i:...) (?i-s).
function Test-InlineIgnoreCase([string]$Pattern) {
    $Pattern -cmatch '\(\?[imnsx]*i[imnsx]*(-[imnsx]+)?[:)]'
}

# The pattern argument of a Select-String call: -Pattern, else the first positional.
function Get-SelectStringPattern($Command) {
    $switches = 'AllMatches', 'CaseSensitive', 'List', 'NotMatch', 'Quiet', 'SimpleMatch', 'Raw'
    $elements = @($Command.CommandElements)
    $positional = 0
    for ($i = 1; $i -lt $elements.Count; $i++) {
        $element = $elements[$i]
        if ($element -is [Management.Automation.Language.CommandParameterAst]) {
            $name = $element.ParameterName
            if ($name.Length -ge 4 -and 'Pattern'.StartsWith($name, [StringComparison]::OrdinalIgnoreCase)) {
                if ($element.Argument) { return $element.Argument }
                if ($i + 1 -lt $elements.Count) { return $elements[$i + 1] }
                return $null
            }
            if ($element.Argument) { continue }
            $isSwitch = $false
            foreach ($candidate in $switches) { if ($candidate.StartsWith($name, [StringComparison]::OrdinalIgnoreCase)) { $isSwitch = $true } }
            if (-not $isSwitch) { $i++ }
            continue
        }
        if ($positional -eq 0) { return $element }
        $positional++
    }
    $null
}

function Test-SelectStringCaseSensitive($Command) {
    foreach ($element in $Command.CommandElements) {
        if ($element -is [Management.Automation.Language.CommandParameterAst] -and
            $element.ParameterName.Length -ge 2 -and
            'CaseSensitive'.StartsWith($element.ParameterName, [StringComparison]::OrdinalIgnoreCase)) { return $true }
    }
    $false
}

# One reason per case-folding or ignore-case pattern found in the script.
function Get-CaseFoldFindings($Ast) {
    $reasons = New-Object Collections.Generic.List[string]
    foreach ($binary in (Find-Ast $Ast ([Management.Automation.Language.BinaryExpressionAst]))) {
        $kind = $binary.Operator.ToString()
        if ($kind -cnotmatch '^[IC](match|notmatch|like|notlike|replace|split)$') { continue }
        $pattern = Get-PatternLiteral $binary.Right
        if ($null -eq $pattern) { continue }
        $base = $kind.Substring(1).ToLowerInvariant()
        if ($kind[0] -ceq 'I') {
            if (Test-FoldingPattern $pattern) { $reasons.Add("-$base folds case by the thread culture on the pattern '$pattern'; use -c$base") }
        }
        elseif ($base -cnotmatch '^(like|notlike)$' -and (Test-InlineIgnoreCase $pattern)) {
            $reasons.Add("-c$base pattern '$pattern' turns case-insensitivity back on with an inline option")
        }
    }
    foreach ($command in (Find-Ast $Ast ([Management.Automation.Language.CommandAst]))) {
        $name = $command.GetCommandName()
        if (-not $name -or $name.ToLowerInvariant() -cnotmatch '^(select-string|sls)$') { continue }
        $patternNode = Get-SelectStringPattern $command
        if ($null -eq $patternNode) { continue }
        $pattern = Get-PatternLiteral $patternNode
        if ($null -eq $pattern) { continue }
        if (Test-SelectStringCaseSensitive $command) {
            if (Test-InlineIgnoreCase $pattern) { $reasons.Add("Select-String -CaseSensitive pattern '$pattern' turns case-insensitivity back on with an inline option") }
        }
        elseif (Test-FoldingPattern $pattern) { $reasons.Add("Select-String without -CaseSensitive folds case by the thread culture on the pattern '$pattern'") }
    }
    foreach ($switch in (Find-Ast $Ast ([Management.Automation.Language.SwitchStatementAst]))) {
        $flags = $switch.Flags
        $regex = (($flags -band [Management.Automation.Language.SwitchFlags]::Regex) -ne 0)
        $wildcard = (($flags -band [Management.Automation.Language.SwitchFlags]::Wildcard) -ne 0)
        if (-not ($regex -or $wildcard)) { continue }
        $sensitive = (($flags -band [Management.Automation.Language.SwitchFlags]::CaseSensitive) -ne 0)
        $label = if ($regex) { '-Regex' } else { '-Wildcard' }
        foreach ($clause in @($switch.Clauses)) {
            $pattern = Get-PatternLiteral $clause.Item1
            if ($null -eq $pattern) { continue }
            if ($sensitive) {
                if ($regex -and (Test-InlineIgnoreCase $pattern)) { $reasons.Add("switch $label -CaseSensitive pattern '$pattern' turns case-insensitivity back on with an inline option") }
            }
            elseif (Test-FoldingPattern $pattern) {
                $reasons.Add("switch $label without -CaseSensitive folds case by the thread culture on the pattern '$pattern'")
            }
        }
    }
    @($reasons | Select-Object -Unique)
}

# ---- FS1: file writes --------------------------------------------------------
# The type names an expression stands for: [T], ([T]), [type]'T', or a variable
# assigned one of those.
function Get-ReceiverTypeNames($Expression, $VariableTypes) {
    $node = $Expression
    while ($node -is [Management.Automation.Language.ParenExpressionAst]) {
        $inner = @($node.Pipeline.PipelineElements)
        if ($inner.Count -ne 1 -or $inner[0] -isnot [Management.Automation.Language.CommandExpressionAst]) { return @() }
        $node = $inner[0].Expression
    }
    if ($node -is [Management.Automation.Language.TypeExpressionAst]) { return @($node.TypeName.Name) }
    if ($node -is [Management.Automation.Language.ConvertExpressionAst] -and
        $node.Type.TypeName.Name.ToLowerInvariant() -ceq 'type' -and
        $node.Child -is [Management.Automation.Language.StringConstantExpressionAst]) { return @($node.Child.Value) }
    if ($node -is [Management.Automation.Language.VariableExpressionAst]) {
        $key = $node.VariablePath.UserPath.ToLowerInvariant()
        if ($VariableTypes.ContainsKey($key)) { return @($VariableTypes[$key]) }
    }
    @()
}

# A stream argument list that only reads: a Read access and no write marker.
function Test-ReadOnlyStreamText([string]$Text) {
    ($Text -cmatch '\b[Rr]ead\b') -and ($Text -cnotmatch '[Ww]rite|[Aa]ppend|[Cc]reate|[Tt]runcate')
}

# Names of the file-writing calls in the script: cmdlets, .NET methods (by type
# and by method name, also through a variable holding the type), writers,
# FileStream opened for writing, instance Save/WriteAll*/CreateText, redirection.
function Get-FileWrites($Ast) {
    $writes = New-Object Collections.Generic.List[string]

    $variableTypes = @{}
    foreach ($assign in (Find-Ast $Ast ([Management.Automation.Language.AssignmentStatementAst]))) {
        if ($assign.Left -isnot [Management.Automation.Language.VariableExpressionAst]) { continue }
        if ($assign.Right -isnot [Management.Automation.Language.CommandExpressionAst]) { continue }
        $names = @(Get-ReceiverTypeNames $assign.Right.Expression @{})
        if ($names.Count -eq 0) { continue }
        $key = $assign.Left.VariablePath.UserPath.ToLowerInvariant()
        $known = @()
        if ($variableTypes.ContainsKey($key)) { $known = @($variableTypes[$key]) }
        $variableTypes[$key] = $known + $names
    }

    foreach ($command in (Find-Ast $Ast ([Management.Automation.Language.CommandAst]))) {
        $name = $command.GetCommandName()
        if (-not $name) { continue }
        $lower = $name.ToLowerInvariant()
        if ($lower -cmatch $fileWriteCmdRe) { $writes.Add($name) }
        elseif ($lower -ceq 'new-object') {
            $text = $command.Extent.Text
            if ($text -cmatch '(Stream|Binary)Writer') { $writes.Add('New-Object file writer') }
            elseif ($text -cmatch 'FileStream' -and -not (Test-ReadOnlyStreamText $text)) { $writes.Add('New-Object file stream') }
        }
    }

    foreach ($call in (Find-Ast $Ast ([Management.Automation.Language.InvokeMemberExpressionAst]))) {
        if ($call.Member -isnot [Management.Automation.Language.StringConstantExpressionAst]) { continue }
        $method = $call.Member.Value
        $methodLower = $method.ToLowerInvariant()
        if (-not $call.Static) {
            if ($methodLower -cmatch $instanceWriteRe) { $writes.Add(".$method") }
            continue
        }
        foreach ($typeName in @(Get-ReceiverTypeNames $call.Expression $variableTypes)) {
            $typeLower = $typeName.ToLowerInvariant()
            if ($typeLower -cnotmatch $fileTypeRe) { continue }
            $kind = $typeLower -creplace '^(system\.)?io\.', ''
            $isWrite = $false
            if ($kind -ceq 'file') {
                $isWrite = ($methodLower -cmatch $fileStaticWriteRe) -or ($methodLower -ceq 'open' -and -not (Test-ReadOnlyStreamText $call.Extent.Text))
            }
            elseif ($kind -ceq 'directory') { $isWrite = ($methodLower -cmatch '^(create|move|delete|set)') }
            elseif ($kind -ceq 'filestream') { $isWrite = ($methodLower -ceq 'new' -and -not (Test-ReadOnlyStreamText $call.Extent.Text)) }
            else { $isWrite = ($methodLower -ceq 'new' -or $methodLower -cmatch '^create') }
            if ($isWrite) { $writes.Add("${typeName}::$method") }
        }
    }

    foreach ($redirect in (Find-Ast $Ast ([Management.Automation.Language.FileRedirectionAst]))) {
        if ($redirect.Location.Extent.Text -cne '$null') { $writes.Add('redirection') }
    }
    @($writes | Select-Object -Unique)
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
                if ($text.ToLowerInvariant() -cmatch '(\d\s*(%|ms\b|fps\b))|(%\s*\d)') { Add-Finding 'C11' $file "$name claims a measured number: '$text'"; break }
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

            foreach ($reason in @(Get-CaseFoldFindings $ast)) { Add-Finding 'LN4' $file "$field $reason" }

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

        foreach ($reason in @(Get-CaseFoldFindings $ast)) { Add-Finding 'LN4' $file $reason }

        # runtime/gate.ps1 and runtime/test.ps1 are dev files: exempt from FS1 by name.
        $writes = @()
        if ($item.Name -cne 'gate.ps1' -and $item.Name -cne 'test.ps1') { $writes = @(Get-FileWrites $ast) }
        if ($writes.Count -gt 0) {
            Add-Finding 'FS1' $file "the runtime writes a file ($($writes -join ', '))"
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
