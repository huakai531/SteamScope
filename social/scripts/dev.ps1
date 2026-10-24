param(
    [ValidateSet('setup','up','down','logs','api','frontend','worker','migrate','test','integration','lint','typecheck','format','validate','types')]
    [string]$Task = 'validate'
)
$ErrorActionPreference = 'Stop'
$socialRoot = Split-Path $PSScriptRoot -Parent
function Invoke-Checked([string]$Command, [string[]]$Arguments) {
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Command failed (exit $LASTEXITCODE)" }
}
Push-Location $socialRoot
try {
    switch ($Task) {
        'setup' {
            if (-not (Test-Path '.env')) { Copy-Item '.env.example' '.env' }
            Invoke-Checked 'uv' @('sync','--frozen','--project','backend')
            Invoke-Checked 'npm' @('--prefix','frontend','ci','--ignore-scripts')
        }
        'up' {
            Invoke-Checked 'docker' @('compose','--env-file','.env','up','--build','--wait','--wait-timeout','180')
            Invoke-Checked 'docker' @('compose','--env-file','.env','exec','-T','api','alembic','upgrade','head')
        }
        'down' { Invoke-Checked 'docker' @('compose','--env-file','.env','down') }
        'logs' { Invoke-Checked 'docker' @('compose','--env-file','.env','logs','--tail','100') }
        'api' { Invoke-Checked 'uv' @('run','--frozen','--project','backend','uvicorn','steamscope_social.main:create_app','--factory','--host','127.0.0.1','--port','8100','--no-access-log','--no-proxy-headers') }
        'frontend' { Invoke-Checked 'npm' @('--prefix','frontend','run','dev') }
        'worker' { Invoke-Checked 'uv' @('run','--frozen','--project','backend','python','-m','steamscope_social.worker') }
        'migrate' { Push-Location backend; try { Invoke-Checked 'uv' @('run','--frozen','alembic','upgrade','head') } finally { Pop-Location } }
        'test' { Push-Location backend; try { Invoke-Checked 'uv' @('run','--frozen','pytest','-q','-m','not integration') } finally { Pop-Location }; Invoke-Checked 'npm' @('--prefix','frontend','test') }
        'integration' {
            if ($env:SOCIAL_ENVIRONMENT -ne 'test') { throw 'Set SOCIAL_ENVIRONMENT=test and SOCIAL_DATABASE_URL for steamscope_social_test first.' }
            $previousIntegration = [Environment]::GetEnvironmentVariable('SOCIAL_INTEGRATION', 'Process')
            try {
                $env:SOCIAL_INTEGRATION = '1'
                Push-Location backend
                try { Invoke-Checked 'uv' @('run','--frozen','pytest','-q','-m','integration') } finally { Pop-Location }
            } finally {
                if ($null -eq $previousIntegration) {
                    Remove-Item Env:SOCIAL_INTEGRATION -ErrorAction SilentlyContinue
                } else {
                    [Environment]::SetEnvironmentVariable('SOCIAL_INTEGRATION', $previousIntegration, 'Process')
                }
            }
        }
        'lint' { Invoke-Checked 'uv' @('run','--frozen','--project','backend','ruff','check','backend'); Invoke-Checked 'uv' @('run','--frozen','--project','backend','ruff','format','--check','backend'); Invoke-Checked 'npm' @('--prefix','frontend','run','lint'); Invoke-Checked 'npm' @('--prefix','frontend','run','format:check') }
        'typecheck' { Push-Location backend; try { Invoke-Checked 'uv' @('run','--frozen','mypy','src') } finally { Pop-Location }; Invoke-Checked 'npm' @('--prefix','frontend','run','typecheck') }
        'format' { Invoke-Checked 'uv' @('run','--frozen','--project','backend','ruff','format','backend'); Invoke-Checked 'npm' @('--prefix','frontend','run','format') }
        'types' { Invoke-Checked 'uv' @('run','--frozen','--project','backend','python','-m','steamscope_social.export_openapi'); Invoke-Checked 'npm' @('--prefix','frontend','run','api:types') }
        'validate' {
            & (Join-Path $PSScriptRoot 'test_dev_script.ps1')
            foreach ($nextTask in @('lint','typecheck','test')) { & $PSCommandPath -Task $nextTask }
            Invoke-Checked 'npm' @('--prefix','frontend','run','build')
        }
    }
} finally { Pop-Location }
