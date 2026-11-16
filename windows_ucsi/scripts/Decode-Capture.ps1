param([string]$Capture = (Join-Path $PSScriptRoot '..\captures\ucsi-results.txt'),
      [string]$Output = (Join-Path $PSScriptRoot '..\analysis\decoded.json'))
$ErrorActionPreference = 'Stop'
$text = Get-Content -LiteralPath $Capture -Raw
$records = @()
foreach ($section in ($text -split '(?m)^=== ')) {
    if ($section -notmatch '^Connector (\d+) Partner source PDOs') { continue }
    $connector = [int]$Matches[1]
    foreach ($block in ($section -split 'PDO offset: ' | Select-Object -Skip 1)) {
        $offset = [int]($block -split '\r?\n')[0]
        $match = [regex]::Match($block, 'UCSI MESSAGE_IN:\s*=+\s*([0-9a-fA-F]{2} [0-9a-fA-F]{2} [0-9a-fA-F]{2} [0-9a-fA-F]{2})')
        if (!$match.Success) { continue }
        [byte[]]$bytes = $match.Groups[1].Value.Split(' ') | ForEach-Object { [Convert]::ToByte($_,16) }
        [uint32]$pdo = [BitConverter]::ToUInt32($bytes,0)
        $type = $pdo -shr 30
        $v = $null; $a = $null; $w = $null
        if ($type -eq 0) { $v = (($pdo -shr 10) -band 1023)*0.05; $a = ($pdo -band 1023)*0.01; $w = $v*$a }
        $records += [pscustomobject]@{Connector=$connector;Position=$offset+1;RawHex=('0x{0:X8}' -f $pdo);RawBytes=$match.Groups[1].Value;Type=$type;FixedVolts=$v;FixedMaxAmps=$a;FixedMaxWatts=$w}
    }
}
$statuses = @()
foreach ($section in ($text -split '(?m)^=== ')) {
    if ($section -notmatch '^Connector (\d+) status') { continue }
    $connector = [int]$Matches[1]
    $r = [regex]::Match($section,'RequestDataObject: 0x([0-9a-fA-F]+)')
    if (!$r.Success) { continue }
    [uint32]$rdo = [Convert]::ToUInt32($r.Groups[1].Value,16)
    $position = ($rdo -shr 28) -band 7
    $selected = $records | Where-Object { $_.Connector -eq $connector -and $_.Position -eq $position } | Select-Object -First 1
    $connected = [int]([regex]::Match($section,'ConnectStatus: (\d+)').Groups[1].Value)
    $op = $null; $max = $null; $watts = $null
    if ($connected -eq 1 -and $null -ne $selected -and $selected.Type -eq 0) {
        $op = (($rdo -shr 10) -band 1023)*0.01
        $max = ($rdo -band 1023)*0.01
        $watts = $selected.FixedVolts*$op
    }
    $statuses += [pscustomobject]@{Connector=$connector;Connected=$connected;RdoHex=('0x{0:X8}' -f $rdo);SelectedPosition=$position;OperatingAmps=$op;MaximumOperatingAmps=$max;RequestedWatts=$watts}
}
[pscustomobject]@{SourceFile=(Split-Path $Capture -Leaf);SourceSha256=(Get-FileHash $Capture -Algorithm SHA256).Hash;Note='Sequential firmware snapshots; fixed partner-source PDO decoding only; requested power is not measured draw.';PartnerSourcePdos=$records;ConnectorStatus=$statuses} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $Output -Encoding UTF8
Write-Output "Decoded capture written to $Output"
