<#
  Actualiza el relay en el servidor (como `git pull` + reiniciar en un despliegue Laravel).

    .\deploy.ps1                       # git pull, dependencias y reinicio
    .\deploy.ps1 -Fresh                # además borra la base local (como migrate:fresh) y la recrea
    .\deploy.ps1 -Fresh -Seed          # igual y carga los proveedores (como db:seed)
    .\deploy.ps1 -Seed                 # solo agrega los proveedores que falten (no borra nada)

  Ejecutar como administrador. Ajusta los nombres de abajo si en tu servidor son otros.
#>
param(
    [switch] $Fresh,
    [switch] $Seed,
    [string] $Pool = 'SupplyRelay',      # Application Pool de IIS
    [string] $Task = 'Supply Relay'      # tarea del Programador de tareas
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

if ($Fresh) {
    $answer = Read-Host 'Se borrarán los proveedores, el historial y las programaciones del relay. Escribe SI para continuar'
    if ($answer -ne 'SI') { Write-Host 'Cancelado.'; exit 1 }
}

Import-Module WebAdministration

Write-Host '1. Deteniendo tarea y sitio...'
Stop-ScheduledTask -TaskName $Task -ErrorAction SilentlyContinue
Stop-WebAppPool -Name $Pool
while ((Get-WebAppPoolState -Name $Pool).Value -ne 'Stopped') { Start-Sleep -Milliseconds 500 }

Write-Host '2. Actualizando código...'
git pull --ff-only
& $python -m pip install -r requirements.txt --quiet

if ($Fresh) {
    Write-Host '3. Respaldando y borrando la base local...'
    New-Item -ItemType Directory -Force data\backups | Out-Null
    if (Test-Path data\relay.db) { Copy-Item data\relay.db "data\backups\relay-$(Get-Date -Format yyyyMMdd-HHmmss).db" }
    Remove-Item data\relay.db, data\relay.db-wal, data\relay.db-shm -ErrorAction SilentlyContinue
}

if ($Seed) {
    Write-Host '4. Cargando proveedores...'
    & $python -m relay.seed   # crea la base si no existe; solo agrega los que faltan
}

Write-Host '5. Iniciando sitio y tarea...'
Start-WebAppPool -Name $Pool
Start-ScheduledTask -TaskName $Task

Write-Host 'Listo.'
