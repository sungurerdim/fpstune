# Detect: classifies each catalogue row (decisions D2/D3).
# Requires Catalogue.ps1 to be dot-sourced first. Windows PowerShell 5.1
# compatible; defines functions only.
#
# Classes: already-right, will-fix, manual, not-applicable, unreadable.
# A command that throws, or returns something that is not one scalar, makes the
# row unreadable. It never counts as already-right.

function ConvertTo-FpsCanonical {
    <#
    .SYNOPSIS
      Writes a scalar in the one comparison form: invariant-culture text, trimmed.
    #>
    param($Value)

    $v = if ($Value -is [System.Management.Automation.PSObject]) { $Value.BaseObject } else { $Value }
    $invariant = [Globalization.CultureInfo]::InvariantCulture

    if ($null -eq $v) { throw 'A null value cannot be compared.' }
    if ($v -is [bool]) { if ($v) { return 'true' } else { return 'false' } }
    if ($v -is [string]) { return $v.Trim() }
    if ($v -is [char]) { return ([string]$v).Trim() }
    if ($v -is [double] -or $v -is [single]) { return $v.ToString('R', $invariant) }
    if ($v -is [decimal]) { return ($v / 1.000000000000000000d).ToString($invariant) }
    if ($v -is [byte] -or $v -is [sbyte] -or $v -is [int16] -or $v -is [uint16] -or
        $v -is [int32] -or $v -is [uint32] -or $v -is [int64] -or $v -is [uint64]) {
        return $v.ToString($invariant)
    }
    if ($v -is [enum]) { return $v.ToString().Trim() }
    throw "A value of type $($v.GetType().FullName) is not a comparable scalar."
}

function Test-FpsEqual {
    <#
    .SYNOPSIS
      True when both values have the same canonical form (ordinal, case-sensitive).
    #>
    param($Left, $Right)
    [string]::Equals((ConvertTo-FpsCanonical $Left), (ConvertTo-FpsCanonical $Right), [StringComparison]::Ordinal)
}

function Get-FpsScalar {
    # Runs a command that must return exactly one scalar; returns its canonical form.
    param([string]$Command, $Instance, $Target)
    $values = @(Invoke-FpsCommand -Command $Command -Instance $Instance -Target $Target)
    if ($values.Count -ne 1) { throw "The command returned $($values.Count) values; exactly one is required." }
    ConvertTo-FpsCanonical $values[0]
}

function New-FpsState {
    param($Row, $Instance, $Label, [string]$Class, $Current, $Target, $ErrorText)
    $rowId = if ($null -ne $Instance) { "$($Row.Id)@$Instance" } else { $Row.Id }
    [pscustomobject]@{
        RowId    = $rowId
        Id       = $Row.Id
        Instance = $Instance
        Label    = $Label
        Class    = $Class
        Current  = $Current
        Target   = $Target
        Error    = $ErrorText
    }
}

function Get-FpsRowState {
    <#
    .SYNOPSIS
      Classifies one catalogue row; returns one state per instance (or one state).
    .DESCRIPTION
      Order: applicable, instances, then per instance detect, target, class.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Row)

    $data = $Row.Data
    if ($data.kind -eq 'manual') {
        return New-FpsState -Row $Row -Class 'manual'
    }

    $instances = @($null)
    $labels = @{}
    try {
        if ($data.PSObject.Properties['applicable']) {
            $applicable = @(Invoke-FpsCommand -Command $data.applicable)
            if ($applicable.Count -ne 1 -or $applicable[0] -isnot [bool]) {
                throw 'applicable must return exactly one boolean.'
            }
            if (-not $applicable[0]) {
                return New-FpsState -Row $Row -Class 'not-applicable'
            }
        }
        if ($data.PSObject.Properties['instances']) {
            $found = @(Invoke-FpsCommand -Command $data.instances)
            if ($found.Count -eq 0) {
                return New-FpsState -Row $Row -Class 'not-applicable'
            }
            $instances = @()
            foreach ($item in $found) {
                $instanceId = if ($null -ne $item) { [string]$item.id } else { '' }
                $instanceId = $instanceId.Trim()
                if ($instanceId.Length -eq 0) { throw 'Every instance needs a non-empty id.' }
                if ($labels.ContainsKey($instanceId)) { throw "Duplicate instance id '$instanceId'." }
                $labels[$instanceId] = if ($item.PSObject.Properties['label'] -and $item.label) { [string]$item.label } else { $instanceId }
                $instances += $instanceId
            }
        }
    }
    catch {
        return New-FpsState -Row $Row -Class 'unreadable' -ErrorText $_.Exception.Message
    }

    foreach ($instance in $instances) {
        $label = if ($null -ne $instance) { $labels[$instance] } else { $null }
        $current = $null
        $target = $null
        try {
            if (-not $data.PSObject.Properties['detect']) { throw 'The row has no detect command.' }
            $current = Get-FpsScalar -Command $data.detect -Instance $instance -Target $null
            if (-not $data.PSObject.Properties['target']) { throw 'The row has no target.' }
            if ($data.target.PSObject.Properties['command']) {
                $target = Get-FpsScalar -Command $data.target.command -Instance $instance -Target $null
            }
            else {
                $target = ConvertTo-FpsCanonical $data.target.value
            }
            $class = if ([string]::Equals($current, $target, [StringComparison]::Ordinal)) { 'already-right' } else { 'will-fix' }
            New-FpsState -Row $Row -Instance $instance -Label $label -Class $class -Current $current -Target $target
        }
        catch {
            New-FpsState -Row $Row -Instance $instance -Label $label -Class 'unreadable' -Current $current -Target $target -ErrorText $_.Exception.Message
        }
    }
}

function Get-FpsState {
    <#
    .SYNOPSIS
      Classifies every row under a catalogue root.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Root)
    foreach ($row in @(Get-FpsCatalogue -Root $Root)) {
        Get-FpsRowState -Row $row
    }
}
