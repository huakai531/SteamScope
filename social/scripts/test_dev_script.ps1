# Tests command orchestration only; this does not substitute for real service integration.
$ErrorActionPreference = 'Stop'
$originalEnvironment = [Environment]::GetEnvironmentVariable('SOCIAL_ENVIRONMENT', 'Process')
$originalIntegration = [Environment]::GetEnvironmentVariable('SOCIAL_INTEGRATION', 'Process')
$originalLocation = Get-Location
$global:SteamScopeStubCalls = 0
$global:SteamScopeStubExit = 0
function uv {
    if ($env:SOCIAL_INTEGRATION -ne '1') { throw 'Integration opt-in was not set for the command' }
    $global:SteamScopeStubCalls++
    $global:LASTEXITCODE = $global:SteamScopeStubExit
}
try {
    $env:SOCIAL_ENVIRONMENT = 'test'
    foreach ($previous in @($null, 'caller-owned-value')) {
        foreach ($exitCode in @(0, 7)) {
            if ($null -eq $previous) {
                Remove-Item Env:SOCIAL_INTEGRATION -ErrorAction SilentlyContinue
            } else {
                [Environment]::SetEnvironmentVariable('SOCIAL_INTEGRATION', $previous, 'Process')
            }
            $global:SteamScopeStubExit = $exitCode
            $failed = $false
            try { & (Join-Path $PSScriptRoot 'dev.ps1') -Task integration } catch {
                $failed = $true
                if ($exitCode -eq 0) { throw }
            }
            if ($failed -ne ($exitCode -ne 0)) { throw 'Child command failure was not propagated correctly' }
            if ([Environment]::GetEnvironmentVariable('SOCIAL_INTEGRATION', 'Process') -cne $previous) {
                throw "Caller integration environment was not restored (expected-null=$($null -eq $previous), actual-null=$($null -eq [Environment]::GetEnvironmentVariable('SOCIAL_INTEGRATION', 'Process')), exit=$exitCode)"
            }
            if ((Get-Location).Path -ne $originalLocation.Path) { throw 'Working directory was not restored' }
        }
    }
    $env:SOCIAL_ENVIRONMENT = 'development'
    $guarded = $false
    try { & (Join-Path $PSScriptRoot 'dev.ps1') -Task integration } catch { $guarded = $true }
    if (-not $guarded -or $global:SteamScopeStubCalls -ne 4) { throw 'Development environment did not fail closed' }
    Write-Output 'PASS: 5 developer-script cases; environment/location restored on success and failure; development integration rejected. Command stub only, no service I/O.'
} finally {
    if ($null -eq $originalEnvironment) { Remove-Item Env:SOCIAL_ENVIRONMENT -ErrorAction SilentlyContinue }
    else { [Environment]::SetEnvironmentVariable('SOCIAL_ENVIRONMENT', $originalEnvironment, 'Process') }
    if ($null -eq $originalIntegration) { Remove-Item Env:SOCIAL_INTEGRATION -ErrorAction SilentlyContinue }
    else { [Environment]::SetEnvironmentVariable('SOCIAL_INTEGRATION', $originalIntegration, 'Process') }
    Set-Location $originalLocation
    Remove-Item Function:uv
    Remove-Variable SteamScopeStubCalls, SteamScopeStubExit -Scope Global
}
