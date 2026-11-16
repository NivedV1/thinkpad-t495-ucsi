$ErrorActionPreference = 'Stop'
$log = Join-Path $PSScriptRoot 'ucsi-results.txt'
Start-Transcript -Path $log -Force
$key = 'HKLM:\SYSTEM\CurrentControlSet\Enum\ACPI\USBC000\0\Device Parameters'
$device = 'ACPI\USBC000\0'
$changed = $false
try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Run this script in an administrator PowerShell window.' }
    $old = Get-ItemProperty -LiteralPath $key
    $hadValue = $null -ne $old.PSObject.Properties['TestInterfaceEnabled']
    $oldValue = $old.TestInterfaceEnabled
    New-ItemProperty -LiteralPath $key -Name TestInterfaceEnabled -PropertyType DWord -Value 1 -Force | Out-Null
    $changed = $true
    & pnputil.exe /restart-device $device
    if ($LASTEXITCODE -ne 0) { throw 'UCSI device restart failed.' }
    Start-Sleep -Seconds 3
    $tool = Join-Path $PSScriptRoot 'UCSIControl.exe'
    & $tool /?
    Write-Output '=== Global capability ==='
    & $tool Send 0 6
    foreach ($connector in 1,2) {
        Write-Output "=== Connector $connector capability ==="
        & $tool Send 0 ('{0:X}' -f (($connector -shl 16) -bor 7))
        Write-Output "=== Connector $connector status ==="
        & $tool Send 0 ('{0:X}' -f (($connector -shl 16) -bor 0x12))
        foreach ($request in @(@('Local source',7,0),@('Local sink',3,0),@('Partner source',7,0x800000),@('Partner sink',3,0x800000))) {
            Write-Output "=== Connector $connector $($request[0]) PDOs (initial batch) ==="
            for ($offset = 0; $offset -lt 7; $offset++) {
                Write-Output "PDO offset: $offset"
                $high = $request[1] -band 4
                & $tool Send $high ('{0:X}' -f (($connector -shl 16) -bor 0x10 -bor $request[2] -bor ($offset -shl 24)))
            }
        }
    }
} catch {
    Write-Output "ERROR: $_"
} finally {
    if ($changed) {
        if ($hadValue) {
            Set-ItemProperty -LiteralPath $key -Name TestInterfaceEnabled -Value $oldValue
        } else {
            Remove-ItemProperty -LiteralPath $key -Name TestInterfaceEnabled
        }
        & pnputil.exe /restart-device $device
        Write-Output "Cleanup restart exit code: $LASTEXITCODE"
    }
    Stop-Transcript
}
