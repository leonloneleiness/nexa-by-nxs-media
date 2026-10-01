# Đăng ký Native Messaging host của NEXA Bridge cho người dùng hiện tại (không cần quyền admin).
# Cách dùng:
#   powershell -ExecutionPolicy Bypass -File browser_bridge\install_bridge.ps1            # cài cho Chrome + Edge
#   powershell -ExecutionPolicy Bypass -File browser_bridge\install_bridge.ps1 -Uninstall # gỡ
param(
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$HostName = "com.nxsmedia.nexa_bridge"
$ExtensionId = "ghkmpnijfoceebnoolnbhedljpelgnhp"
$BridgeDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ManifestDir = Join-Path $env:LOCALAPPDATA "NEXA\bridge"
$ManifestPath = Join-Path $ManifestDir "$HostName.json"
$RegistryKeys = @(
    "HKCU:\Software\Google\Chrome\NativeMessagingHosts\$HostName",
    "HKCU:\Software\Microsoft\Edge\NativeMessagingHosts\$HostName"
)

if ($Uninstall) {
    foreach ($key in $RegistryKeys) {
        if (Test-Path $key) { Remove-Item -Path $key -Force; Write-Host "Đã gỡ $key" }
    }
    if (Test-Path $ManifestPath) { Remove-Item $ManifestPath -Force }
    Write-Host "Đã gỡ NEXA Bridge native host."
    exit 0
}

$HostBat = Join-Path $BridgeDir "native_host.bat"
$VenvPython = Join-Path (Split-Path -Parent $BridgeDir) ".venv\Scripts\python.exe"
if (-not (Test-Path $HostBat)) { throw "Không thấy $HostBat" }
if (-not (Test-Path $VenvPython)) {
    Write-Warning "Chưa có môi trường ảo .venv. Hãy chạy setup_windows.bat trước."
}

New-Item -ItemType Directory -Force -Path $ManifestDir | Out-Null
$manifest = [ordered]@{
    name            = $HostName
    description     = "NEXA Bridge - kênh cục bộ giữa extension và ứng dụng NEXA"
    path            = $HostBat
    type            = "stdio"
    allowed_origins = @("chrome-extension://$ExtensionId/")
}
$json = $manifest | ConvertTo-Json -Depth 4
[System.IO.File]::WriteAllText($ManifestPath, $json, (New-Object System.Text.UTF8Encoding($false)))

foreach ($key in $RegistryKeys) {
    New-Item -Path $key -Force | Out-Null
    Set-ItemProperty -Path $key -Name "(default)" -Value $ManifestPath
    Write-Host "Đã đăng ký $key"
}

Write-Host ""
Write-Host "Manifest: $ManifestPath"
Write-Host "Bước tiếp theo: mở chrome://extensions (hoặc edge://extensions), bật Developer mode,"
Write-Host "bấm 'Load unpacked' và chọn thư mục: $(Join-Path $BridgeDir 'extension')"
Write-Host "ID extension phải là: $ExtensionId"
