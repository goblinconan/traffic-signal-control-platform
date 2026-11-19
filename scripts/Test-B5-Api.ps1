[CmdletBinding()]
param(
    [string]$BaseUrl = 'http://127.0.0.1:8000'
)

$ErrorActionPreference = 'Stop'
$BaseUrl = $BaseUrl.TrimEnd('/')

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
    Write-Host "[PASS] $Message" -ForegroundColor Green
}

try {
    Write-Host "B5 只读 API 冒烟测试：$BaseUrl" -ForegroundColor Cyan

    $health = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/health" -TimeoutSec 10
    Assert-True ($health.status -eq 'ok') 'GET /api/health 返回 ok'

    $state = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/simulation/state" -TimeoutSec 15
    Assert-True ($state.schema_version -eq '1.0') '统一状态 schema_version 为 1.0'
    Assert-True ($state.type -eq 'simulation_snapshot') 'REST 状态类型为 simulation_snapshot'
    Assert-True (@('STOPPED','STARTING','RUNNING','STOPPING','FAILED') -contains $state.simulation_status) '仿真生命周期状态属于 B4 枚举'

    $tlsId = [Uri]::EscapeDataString([string]$state.signal_control.tls_id)
    Assert-True (-not [string]::IsNullOrWhiteSpace($tlsId)) '快照包含 tls_id'
    Assert-True (@('ENABLED','DISABLING','DISABLED') -contains $state.signal_control.control_status) '控制状态属于 B3/B4 枚举'
    Assert-True (@('AUTO','MANUAL') -contains $state.signal_control.control_mode) '控制模式属于 AUTO/MANUAL'

    $groupIds = @($state.signal_control.groups | ForEach-Object { $_.group_id })
    $expectedGroups = @('NS_LEFT','NS_STRAIGHT','EW_LEFT','EW_STRAIGHT')
    foreach ($groupId in $expectedGroups) {
        Assert-True ($groupIds -contains $groupId) "统一快照包含信号组 $groupId"
    }

    $timing = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/signals/$tlsId/timing" -TimeoutSec 10
    $timingFields = @('ns_left_green','ns_left_yellow','ns_straight_green','ns_straight_yellow','ew_left_green','ew_left_yellow','ew_straight_green','ew_straight_yellow')
    foreach ($field in $timingFields) {
        Assert-True ($null -ne $timing.active.$field) "配时 active 包含 $field"
    }
    Assert-True ($timing.timing_version -ge 1) '配时版本号有效'

    $network = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/intersections/$tlsId/network" -TimeoutSec 20
    Assert-True ($network.network_version -eq $state.network_version) '静态网络版本与运行状态 network_version 一致'
    Assert-True (@($network.geometry.edges).Count -gt 0) '静态网络包含外部道路 geometry'
    Assert-True (@($network.geometry.internal_lanes).Count -gt 0) '静态网络包含内部连接车道 geometry'

    Write-Host ''
    Write-Host 'B5 只读 API 冒烟测试全部通过。' -ForegroundColor Green
    Write-Host "当前仿真状态：$($state.simulation_status)；控制状态：$($state.signal_control.control_status)；模式：$($state.signal_control.control_mode)"
    Write-Host '注意：本脚本不启动/停止仿真，也不执行任何信号控制或配时写操作。'
}
catch {
    Write-Host "[FAIL] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
