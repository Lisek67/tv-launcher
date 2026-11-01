$Dir = Split-Path -Parent $MyInvocation.MyCommand.Path
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*$Dir*server.py*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Remove-Item (Join-Path ([Environment]::GetFolderPath('Startup')) 'TV Launcher.lnk') -ErrorAction SilentlyContinue
try { Start-Process powershell -Verb RunAs -Wait -ArgumentList '-NoProfile','-Command',"netsh advfirewall firewall delete rule name='TV Launcher Pilot' | Out-Null" } catch {}
Write-Host 'Usunięto autostart i zatrzymano launcher.'
