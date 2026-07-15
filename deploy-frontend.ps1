<#
.SYNOPSIS
    构建前端静态文件并部署到后端 static 目录

.DESCRIPTION
    1. 在 web/ 目录下执行 pnpm build，生成静态导出到 web/out/
    2. 清空 server/static/ 目录
    3. 将 web/out/ 的全部内容复制到 server/static/

.PARAMETER SkipBuild
    跳过 pnpm build 步骤，仅刷新部署目录

.EXAMPLE
    .\deploy-frontend.ps1              # 构建 + 部署
    .\deploy-frontend.ps1 -SkipBuild   # 仅部署已有构建产物
#>

param(
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

# ------ 路径 ------
$RootDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$WebDir    = Join-Path $RootDir "web"
$OutDir    = Join-Path $WebDir "out"
$StaticDir = Join-Path (Join-Path $RootDir "server") "static"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  前端构建部署脚本" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ------ Step 1: 构建 ------
if (-not $SkipBuild) {
    Write-Host "▶ Step 1/3: 构建前端 (pnpm build) ..." -ForegroundColor Yellow

    Push-Location $WebDir
    try {
        pnpm build
        if ($LASTEXITCODE -ne 0) {
            Write-Host "✖ 构建失败，退出码: $LASTEXITCODE" -ForegroundColor Red
            exit $LASTEXITCODE
        }
    }
    finally {
        Pop-Location
    }

    Write-Host "✓ 构建完成" -ForegroundColor Green
    Write-Host ""
}
else {
    Write-Host "▶ Step 1/3: 跳过构建（-SkipBuild）" -ForegroundColor Yellow
    Write-Host ""
}

# ------ Step 2: 确认构建产物存在 ------
if (-not (Test-Path $OutDir)) {
    Write-Host "✖ 构建产物目录不存在: $OutDir" -ForegroundColor Red
    Write-Host "  请先执行 pnpm build 或不要使用 -SkipBuild" -ForegroundColor Red
    exit 1
}

# ------ Step 3: 清空 static ------
Write-Host "▶ Step 2/3: 清空后端 static 目录 ..." -ForegroundColor Yellow

if (Test-Path $StaticDir) {
    Remove-Item -Path "$StaticDir\*" -Recurse -Force -ErrorAction Continue
    Remove-Item -Path "$StaticDir\.*" -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "  ✓ 已清空 $StaticDir" -ForegroundColor Green
}
else {
    New-Item -ItemType Directory -Path $StaticDir -Force | Out-Null
    Write-Host "  ✓ 已创建 $StaticDir" -ForegroundColor Green
}
Write-Host ""

# ------ Step 4: 复制 ------
Write-Host "▶ Step 3/3: 复制构建产物 -> server/static/ ..." -ForegroundColor Yellow

Copy-Item -Path "$OutDir\*" -Destination $StaticDir -Recurse -Force

$fileCount = (Get-ChildItem -Path $StaticDir -Recurse -File).Count
Write-Host "  ✓ 已复制 $fileCount 个文件" -ForegroundColor Green
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  部署完成" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "后端 static 目录: $StaticDir" -ForegroundColor Gray
Write-Host "启动后端查看效果: uv run python server/main.py" -ForegroundColor Gray
