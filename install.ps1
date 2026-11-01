# TV Launcher - instalator dla Windows 10/11
# Uruchom przez install.bat (dwuklik) albo: powershell -ExecutionPolicy Bypass -File install.ps1
$ErrorActionPreference = 'Stop'
$Dir = Split-Path -Parent $MyInvocation.MyCommand.Path
function Say($t) { Write-Host "`n== $t ==" -ForegroundColor Cyan }
function AskYN($q) { $a = Read-Host "$q [T/n]"; return ($a -eq '' -or $a -match '^[TtYy]') }

Say 'TV Launcher: instalacja'

# 1. Python ---------------------------------------------------------------
Say '1/4 Python'
function Find-Python {
    $exe = $null
    try { $exe = (& py -3 -c "import sys;print(sys.executable)" 2>$null) } catch {}
    if ($exe -and (Test-Path "$exe")) { return "$exe".Trim() }
    $exe = $null
    try { $exe = (& python -c "import sys;print(sys.executable)" 2>$null) } catch {}
    if ($exe -and (Test-Path "$exe")) { return "$exe".Trim() }
    $g = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1
    if ($g) { return $g.FullName }
    return $null
}
$py = Find-Python
if (-not $py) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host 'Nie znaleziono Pythona - instaluję przez winget (Python 3.12)...'
        winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
        $py = Find-Python
    }
}
if (-not $py) {
    Write-Host 'Zainstaluj Python 3 z https://www.python.org/downloads/ (zaznacz "Add python.exe to PATH") i uruchom instalator ponownie.' -ForegroundColor Yellow
    exit 1
}
$pyw = Join-Path (Split-Path $py) 'pythonw.exe'
if (-not (Test-Path $pyw)) { $pyw = $py }
Write-Host "Python: $py"

# 2. Autostart ------------------------------------------------------------
Say '2/4 Autostart'
$withBrowser = AskYN 'Uruchamiać launcher w przeglądarce na pełnym ekranie po zalogowaniu do Windows?'
$launchArgs = "`"$Dir\server.py`""
if ($withBrowser) { $launchArgs += ' --browser' }
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Startup')) 'TV Launcher.lnk'))
$lnk.TargetPath = $pyw
$lnk.Arguments = $launchArgs
$lnk.WorkingDirectory = $Dir
$lnk.WindowStyle = 7
$lnk.Description = 'TV Launcher'
$lnk.Save()
Write-Host 'Dodano skrót w folderze Autostart.'

# 3. Zapora (pilot na telefon) -------------------------------------------
Say '3/4 Pilot na telefon (zapora)'
Write-Host 'Pilot używa portu 8766 w sieci domowej. Windows może sam zapytać o zgodę przy pierwszym uruchomieniu (zaznacz "Sieci prywatne").'
if (AskYN 'Dodać regułę zapory teraz (wymaga uprawnień administratora)?') {
    try {
        Start-Process powershell -Verb RunAs -Wait -ArgumentList '-NoProfile','-Command',"netsh advfirewall firewall delete rule name='TV Launcher Pilot' | Out-Null; netsh advfirewall firewall add rule name='TV Launcher Pilot' dir=in action=allow protocol=TCP localport=8766 profile=private | Out-Null"
        Write-Host 'Dodano regułę zapory (tylko sieci prywatne).'
    } catch { Write-Host 'Pominięto regułę zapory.' -ForegroundColor Yellow }
}

# 4. Start ----------------------------------------------------------------
Say '4/4 Uruchamianie'
$old = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*$Dir*server.py*" }
$old | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Process -FilePath $pyw -ArgumentList $launchArgs -WorkingDirectory $Dir -WindowStyle Hidden
Start-Sleep -Seconds 2
try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 http://127.0.0.1:8765/ping | Out-Null; Write-Host 'OK: launcher działa: http://127.0.0.1:8765/' -ForegroundColor Green }
catch { Write-Host 'Launcher nie odpowiada. Uruchom ręcznie: python server.py (w tym folderze) i sprawdź komunikaty błędów.' -ForegroundColor Yellow }
if (-not $withBrowser) { Start-Process 'http://127.0.0.1:8765/' }
Write-Host "`nPierwsze uruchomienie pokaże kreator konfiguracji."
