<#
.SYNOPSIS
    Interactive Windows control panel for managing a local chfs-py server.

.DESCRIPTION
    Provides basic administrative operations exposed by the chfs-py REST API,
    including inspecting server status, adjusting share quotas, and managing
    dynamically registered users. All operations are executed against the
    server running on the same machine (loopback only).

.PARAMETER ServerUrl
    Base URL of the running chfs-py server. Defaults to http://127.0.0.1:8080.

.PARAMETER Username
    Username for HTTP Basic authentication. If omitted you will be prompted.

.PARAMETER Password
    Password for HTTP Basic authentication. If omitted you will be prompted.
#>
param(
    [string]$ServerUrl = "http://127.0.0.1:8080",
    [string]$Username,
    [string]$Password
)

function Get-BasicAuthHeader {
    param(
        [Parameter(Mandatory = $true)][string]$User,
        [Parameter(Mandatory = $true)][string]$Pass
    )

    $pair = "$User:$Pass"
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($pair)
    $token = [System.Convert]::ToBase64String($bytes)
    return "Basic $token"
}

if (-not $Username -or -not $Password) {
    $credential = Get-Credential -Message "Enter chfs-py administrator credentials"
    if (-not $credential) {
        Write-Error "Credentials are required."
        exit 1
    }
    if (-not $Username) { $Username = $credential.UserName }
    if (-not $Password) { $Password = $credential.GetNetworkCredential().Password }
}

$AuthHeader = Get-BasicAuthHeader -User $Username -Pass $Password

function Invoke-ChfsApi {
    param(
        [Parameter(Mandatory = $true)][string]$Method,
        [Parameter(Mandatory = $true)][string]$Path,
        [string]$BodyJson
    )

    $uri = "$ServerUrl$Path"
    $headers = @{ Authorization = $AuthHeader }
    if ($BodyJson) {
        $headers['Content-Type'] = 'application/json'
    }

    try {
        $response = Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -Body $BodyJson -ErrorAction Stop
        if ($response.detail) { return $response.detail }
        return $response
    }
    catch {
        throw "API request failed: $($_.Exception.Message)"
    }
}

function Show-ServerStatus {
    try {
        $data = Invoke-ChfsApi -Method GET -Path '/api/admin/status'
        if ($data.code -ne 0) {
            $message = if ($data.msg) { $data.msg } else { 'Failed to retrieve status.' }
            Write-Warning $message
            return
        }

        $status = $data.data
        Write-Host "`nServer:` $($status.server.host):$($status.server.port) ($($status.server.scheme))" -ForegroundColor Cyan
        Write-Host " LAN URLs:" -ForegroundColor DarkGray
        foreach ($url in $status.server.lan_urls) {
            Write-Host "  - $url"
        }

        Write-Host " Shares:" -ForegroundColor DarkGray
        foreach ($share in $status.shares) {
            $quota = if ($share.quota_enabled) { $share.quota.limit_display } else { 'Unlimited' }
            $used = $share.usage.display
            Write-Host "  - $($share.name): $used used (limit: $quota)" -ForegroundColor Green
        }

        Write-Host " Users:" -ForegroundColor DarkGray
        foreach ($user in $status.users) {
            $source = if ($user.dynamic) { 'dynamic' } else { 'config' }
            Write-Host "  - $($user.name) [$source]"
        }
    }
    catch {
        Write-Error $_
    }
}

function Set-ShareQuota {
    param(
        [Parameter(Mandatory = $true)][string]$ShareName,
        [Parameter(Mandatory = $true)][string]$Quota
    )

    try {
        $body = @{ quota = $Quota } | ConvertTo-Json
        $response = Invoke-ChfsApi -Method PUT -Path "/api/admin/shares/$([uri]::EscapeDataString($ShareName))/quota" -BodyJson $body
        if ($response.code -ne 0) {
            $message = if ($response.msg) { $response.msg } else { 'Failed to set quota.' }
            Write-Warning $message
            return
        }
        $share = $response.data.share
        Write-Host "Quota for '$($share.name)' set to $($share.quotaDisplay)." -ForegroundColor Green
    }
    catch {
        Write-Error $_
    }
}

function Clear-ShareQuota {
    param(
        [Parameter(Mandatory = $true)][string]$ShareName
    )

    try {
        $response = Invoke-ChfsApi -Method PUT -Path "/api/admin/shares/$([uri]::EscapeDataString($ShareName))/quota" -BodyJson '{}'
        if ($response.code -ne 0) {
            $message = if ($response.msg) { $response.msg } else { 'Failed to clear quota.' }
            Write-Warning $message
            return
        }
        Write-Host "Quota for '$ShareName' removed." -ForegroundColor Green
    }
    catch {
        Write-Error $_
    }
}

function List-Users {
    try {
        $response = Invoke-ChfsApi -Method GET -Path '/api/admin/users'
        if ($response.code -ne 0) {
            $message = if ($response.msg) { $response.msg } else { 'Failed to list users.' }
            Write-Warning $message
            return
        }
        $users = $response.data.users
        if (-not $users -or $users.Count -eq 0) {
            Write-Host 'No users registered.'
            return
        }

        Write-Host "`nUsers:" -ForegroundColor Cyan
        foreach ($user in $users) {
            $source = if ($user.dynamic) { 'dynamic' } else { 'config' }
            Write-Host " - $($user.name) [$source]"
        }
    }
    catch {
        Write-Error $_
    }
}

function Remove-User {
    param(
        [Parameter(Mandatory = $true)][string]$UserName
    )

    try {
        $response = Invoke-ChfsApi -Method DELETE -Path "/api/admin/users/$([uri]::EscapeDataString($UserName))"
        if ($response.code -ne 0) {
            $message = if ($response.msg) { $response.msg } else { 'Failed to remove user.' }
            Write-Warning $message
            return
        }
        Write-Host "Removed dynamic user '$UserName'." -ForegroundColor Green
    }
    catch {
        Write-Error $_
    }
}

Write-Host "chfs-py Windows Control Panel" -ForegroundColor Cyan
Write-Host "Connected to $ServerUrl as $Username" -ForegroundColor DarkGray

while ($true) {
    Write-Host "`nAvailable actions:" -ForegroundColor Cyan
    Write-Host "  [1] Show server status"
    Write-Host "  [2] Set share quota"
    Write-Host "  [3] Clear share quota"
    Write-Host "  [4] List users"
    Write-Host "  [5] Remove dynamic user"
    Write-Host "  [0] Exit"

    $choice = Read-Host "Select an option"
    switch ($choice) {
        '1' { Show-ServerStatus }
        '2' {
            $name = Read-Host 'Share name'
            if ($name) {
                $quota = Read-Host 'Quota (e.g. 10GB)'
                if ($quota) { Set-ShareQuota -ShareName $name -Quota $quota }
                else { Write-Warning 'Quota value is required.' }
            }
        }
        '3' {
            $name = Read-Host 'Share name'
            if ($name) { Clear-ShareQuota -ShareName $name }
        }
        '4' { List-Users }
        '5' {
            $user = Read-Host 'Username'
            if ($user) { Remove-User -UserName $user }
        }
        '0' { break }
        default { Write-Warning 'Invalid option.' }
    }
}

Write-Host 'Goodbye.' -ForegroundColor DarkGray
