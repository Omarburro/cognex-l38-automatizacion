# Windows PowerShell 5.1. Solo verifica y ejecuta datos sinteticos.
[CmdletBinding()]
param(
    [string]$Python = 'python',
    [switch]$Demo
)

$ErrorActionPreference = 'Stop'
$raizPaquete = Split-Path -Parent $MyInvocation.MyCommand.Path
$analizador = Join-Path $raizPaquete 'revisar_cajas.py'
$manifiesto = Join-Path $raizPaquete 'SHA256SUMS.txt'

if (Test-Path -LiteralPath $manifiesto) {
    foreach ($linea in Get-Content -LiteralPath $manifiesto -Encoding UTF8) {
        if ($linea -match '^([0-9a-f]{64})  (.+)$') {
            $esperado = $Matches[1]
            $relativo = $Matches[2].Replace('/', [string][IO.Path]::DirectorySeparatorChar)
            $archivo = Join-Path $raizPaquete $relativo
            if (-not (Test-Path -LiteralPath $archivo -PathType Leaf)) {
                throw "Falta un archivo del paquete: $relativo"
            }
            $actual = (Get-FileHash -LiteralPath $archivo -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($actual -cne $esperado) {
                throw "Hash distinto al de la entrega: $relativo"
            }
        }
    }
    Write-Host 'Integridad de archivos verificada.'
}

& $Python -c "import sys, cv2, numpy; assert sys.version_info.major == 3; print(sys.version); print('OpenCV', cv2.__version__, 'numpy', numpy.__version__)"
if ($LASTEXITCODE -ne 0) {
    throw 'Revisa Python3 y dependencias: python -m pip install -r requirements.txt'
}

& $Python $analizador --autoprueba
if ($LASTEXITCODE -ne 0) {
    throw 'Fallo la autoprueba. Conserva la salida antes de continuar.'
}

if ($Demo) {
    $nombreDemo = 'demo_local_' + (Get-Date -Format 'yyyyMMdd_HHmmss')
    $carpetaDemo = Join-Path $raizPaquete $nombreDemo
    & $Python $analizador --crear-demo $carpetaDemo
    if ($LASTEXITCODE -ne 0) {
        throw 'No se pudo crear la demo nueva.'
    }
    & $Python $analizador --carpeta $carpetaDemo --muestras-sincronizadas
    if ($LASTEXITCODE -ne 0) {
        throw 'Fallo el analisis de la demo.'
    }
}

Write-Host 'Validacion sintetica terminada. Esto no valida Cognex ni datos reales.'
