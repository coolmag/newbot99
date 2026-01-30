try {
    $key = "HKLM:\System\CurrentControlSet\Control\Session Manager\Environment"
    $oldPath = (Get-ItemProperty -Path $key -Name Path).Path
    $pathsToAdd = @("C:\Windows\System32", "C:\Windows", "C:\Windows\System32\Wbem")
    
    $existingPaths = New-Object 'System.Collections.Generic.Dictionary[string, bool]' ([System.StringComparer]::OrdinalIgnoreCase)
    $oldPath.Split(';') | ForEach-Object { if (-not [string]::IsNullOrWhiteSpace($_)) { $existingPaths[$_] = $true } }

    $pathsAdded = @()
    $pathsToAdd | ForEach-Object {
        if (-not $existingPaths.ContainsKey($_)) {
            $pathsAdded += $_
        }
    }

    if ($pathsAdded.Count -gt 0) {
        $newPath = ($oldPath.TrimEnd(';') + ';' + ($pathsAdded -join ';')).Trim(';')
        Set-ItemProperty -Path $key -Name Path -Value $newPath
        Write-Host "OK: System PATH has been updated. Added: $($pathsAdded -join ', ')" -ForegroundColor Green
    } else {
        Write-Host "INFO: All required paths are already in the system PATH. No changes were made." -ForegroundColor Yellow
    }
} catch {
    Write-Host "ERROR: Could not read or modify the system PATH." -ForegroundColor Red
    Write-Host "PLEASE MAKE SURE YOU ARE RUNNING POWERSHELL AS AN ADMINISTRATOR." -ForegroundColor Red
    Write-Host "Error details: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`nACTION: Please restart your terminal for the changes to take effect."
Pause