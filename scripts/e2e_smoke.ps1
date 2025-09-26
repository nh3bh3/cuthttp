# PowerShell script for end-to-end smoke testing of chfs-py
# Tests basic functionality: list, mkdir, upload, download, delete

param(
    [string]$BaseUrl = "http://127.0.0.1:8080",
    [string]$Username = "alice",
    [string]$Password = "alice123",
    [string]$Share = "public",
    [switch]$Verbose = $false,
    [switch]$Help = $false
)

# Show help
if ($Help) {
    Write-Host "chfs-py End-to-End Smoke Test" -ForegroundColor Green
    Write-Host ""
    Write-Host "Usage: .\scripts\e2e_smoke.ps1 [OPTIONS]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -BaseUrl URL    Base URL of chfs-py server (default: http://127.0.0.1:8080)"
    Write-Host "  -Username USER  Username for authentication (default: alice)"
    Write-Host "  -Password PASS  Password for authentication (default: alice123)"
    Write-Host "  -Share NAME     Share name to test (default: public)"
    Write-Host "  -Verbose        Enable verbose output"
    Write-Host "  -Help           Show this help message"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  .\scripts\e2e_smoke.ps1"
    Write-Host "  .\scripts\e2e_smoke.ps1 -BaseUrl http://localhost:9000 -Verbose"
    Write-Host "  .\scripts\e2e_smoke.ps1 -Username admin -Password admin456 -Share home"
    Write-Host ""
    exit 0
}

# Set console title
$Host.UI.RawUI.WindowTitle = "chfs-py E2E Smoke Test"

Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "chfs-py End-to-End Smoke Test" -ForegroundColor Green
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host ""
Write-Host "Target: $BaseUrl" -ForegroundColor Cyan
Write-Host "User: $Username" -ForegroundColor Cyan
Write-Host "Share: $Share" -ForegroundColor Cyan
Write-Host ""

# Test configuration
$testDir = "e2e-test-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
$testFile = "test-file.txt"
$testContent = "Hello from chfs-py E2E test!`nTimestamp: $(Get-Date)`nTest directory: $testDir"
$testResults = @()

# Helper function for HTTP requests with authentication
function Invoke-ChfsRequest {
    param(
        [string]$Method = "GET",
        [string]$Uri,
        [hashtable]$Headers = @{},
        [object]$Body = $null,
        [string]$ContentType = $null
    )
    
    # Create credential
    $credential = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("${Username}:${Password}"))
    $Headers["Authorization"] = "Basic $credential"
    
    $params = @{
        Method = $Method
        Uri = $Uri
        Headers = $Headers
    }
    
    if ($Body) {
        if ($ContentType) {
            $params.ContentType = $ContentType
        }
        $params.Body = $Body
    }
    
    try {
        $response = Invoke-RestMethod @params
        return @{ Success = $true; Data = $response; Error = $null }
    } catch {
        return @{ Success = $false; Data = $null; Error = $_.Exception.Message }
    }
}

# Helper function to log test results
function Log-Test {
    param(
        [string]$TestName,
        [bool]$Success,
        [string]$Message = "",
        [object]$Details = $null
    )
    
    $result = @{
        Test = $TestName
        Success = $Success
        Message = $Message
        Details = $Details
        Timestamp = Get-Date
    }
    
    $script:testResults += $result
    
    $status = if ($Success) { "PASS" } else { "FAIL" }
    $color = if ($Success) { "Green" } else { "Red" }
    
    Write-Host "[$status] $TestName" -ForegroundColor $color
    if ($Message) {
        Write-Host "      $Message" -ForegroundColor Gray
    }
    if ($Verbose -and $Details) {
        Write-Host "      Details: $($Details | ConvertTo-Json -Compress)" -ForegroundColor DarkGray
    }
}

# Test 1: Health check
Write-Host "Running tests..." -ForegroundColor Yellow
Write-Host ""

$result = Invoke-ChfsRequest -Uri "$BaseUrl/healthz"
Log-Test "Health Check" $result.Success "Server health status" $result.Data

if (-not $result.Success) {
    Write-Host ""
    Write-Host "Error: Server is not responding. Please ensure chfs-py is running at $BaseUrl" -ForegroundColor Red
    exit 1
}

# Test 2: List root directory
$result = Invoke-ChfsRequest -Uri "$BaseUrl/api/list?root=$Share&path="
Log-Test "List Root Directory" $result.Success "List files in root of share '$Share'" $result.Data

# Test 3: Create test directory
$createDirBody = @{
    root = $Share
    path = $testDir
} | ConvertTo-Json

$result = Invoke-ChfsRequest -Method "POST" -Uri "$BaseUrl/api/mkdir" -Body $createDirBody -ContentType "application/json"
Log-Test "Create Directory" $result.Success "Create test directory '$testDir'" $result.Data

# Test 4: List directory after creation
$result = Invoke-ChfsRequest -Uri "$BaseUrl/api/list?root=$Share&path="
$dirExists = $result.Success -and ($result.Data.data.files | Where-Object { $_.name -eq $testDir -and $_.is_dir })
Log-Test "Verify Directory Created" $dirExists "Directory '$testDir' appears in listing" $result.Data

# Test 5: Upload test file
$boundary = [System.Guid]::NewGuid().ToString()
$LF = "`r`n"

$bodyLines = @(
    "--$boundary",
    "Content-Disposition: form-data; name=`"root`"$LF",
    $Share,
    "--$boundary",
    "Content-Disposition: form-data; name=`"path`"$LF",
    $testDir,
    "--$boundary",
    "Content-Disposition: form-data; name=`"file`"; filename=`"$testFile`"",
    "Content-Type: text/plain$LF",
    $testContent,
    "--$boundary--$LF"
)

$body = $bodyLines -join $LF
$result = Invoke-ChfsRequest -Method "POST" -Uri "$BaseUrl/api/upload" -Body $body -ContentType "multipart/form-data; boundary=$boundary"
Log-Test "Upload File" $result.Success "Upload '$testFile' to '$testDir'" $result.Data

# Test 6: List directory after upload
$result = Invoke-ChfsRequest -Uri "$BaseUrl/api/list?root=$Share&path=$testDir"
$fileExists = $result.Success -and ($result.Data.data.files | Where-Object { $_.name -eq $testFile -and -not $_.is_dir })
Log-Test "Verify File Uploaded" $fileExists "File '$testFile' appears in directory listing" $result.Data

# Test 7: Download file (test range support)
try {
    $credential = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("${Username}:${Password}"))
    $headers = @{ "Authorization" = "Basic $credential" }
    
    $downloadUri = "$BaseUrl/api/download?root=$Share&path=$testDir/$testFile"
    $response = Invoke-WebRequest -Uri $downloadUri -Headers $headers -Method GET
    
    $downloadSuccess = $response.StatusCode -eq 200 -and $response.Content.Contains("Hello from chfs-py")
    Log-Test "Download File" $downloadSuccess "Download and verify content of '$testFile'" @{ StatusCode = $response.StatusCode; ContentLength = $response.Content.Length }
} catch {
    Log-Test "Download File" $false "Failed to download file: $($_.Exception.Message)"
}

# Test 8: Test range download
try {
    $headers = @{ 
        "Authorization" = "Basic $credential"
        "Range" = "bytes=0-10"
    }
    
    $response = Invoke-WebRequest -Uri $downloadUri -Headers $headers -Method GET
    $rangeSuccess = $response.StatusCode -eq 206 -and $response.Headers["Content-Range"]
    Log-Test "Range Download" $rangeSuccess "Partial content download with Range header" @{ StatusCode = $response.StatusCode; ContentRange = $response.Headers["Content-Range"] }
} catch {
    Log-Test "Range Download" $false "Failed range download: $($_.Exception.Message)"
}

# Test 9: Rename file
$renameBody = @{
    root = $Share
    path = "$testDir/$testFile"
    newName = "renamed-$testFile"
} | ConvertTo-Json

$result = Invoke-ChfsRequest -Method "POST" -Uri "$BaseUrl/api/rename" -Body $renameBody -ContentType "application/json"
Log-Test "Rename File" $result.Success "Rename '$testFile' to 'renamed-$testFile'" $result.Data

# Test 10: WebDAV (if enabled)
if ($BaseUrl.StartsWith("http://")) {
    $webdavUrl = $BaseUrl.Replace("http://", "http://${Username}:${Password}@") + "/webdav/$Share"
    try {
        $webdavResponse = Invoke-WebRequest -Uri $webdavUrl -Method "PROPFIND" -Headers @{"Depth" = "1"} -UseBasicParsing
        $webdavSuccess = $webdavResponse.StatusCode -eq 207
        Log-Test "WebDAV Access" $webdavSuccess "WebDAV PROPFIND request" @{ StatusCode = $webdavResponse.StatusCode }
    } catch {
        Log-Test "WebDAV Access" $false "WebDAV request failed (may be disabled): $($_.Exception.Message)"
    }
}

# Cleanup: Delete test files and directory
Write-Host ""
Write-Host "Cleaning up..." -ForegroundColor Yellow

# Delete files in test directory first
$deleteBody = @{
    root = $Share
    paths = @("$testDir/renamed-$testFile")
} | ConvertTo-Json

$result = Invoke-ChfsRequest -Method "POST" -Uri "$BaseUrl/api/delete" -Body $deleteBody -ContentType "application/json"
Log-Test "Delete File" $result.Success "Delete renamed test file" $result.Data

# Delete test directory
$deleteBody = @{
    root = $Share
    paths = @($testDir)
} | ConvertTo-Json

$result = Invoke-ChfsRequest -Method "POST" -Uri "$BaseUrl/api/delete" -Body $deleteBody -ContentType "application/json"
Log-Test "Delete Directory" $result.Success "Delete test directory" $result.Data

# Summary
Write-Host ""
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "Test Summary" -ForegroundColor Green
Write-Host "=" * 60 -ForegroundColor Cyan

$totalTests = $testResults.Count
$passedTests = ($testResults | Where-Object { $_.Success }).Count
$failedTests = $totalTests - $passedTests

Write-Host ""
Write-Host "Total Tests: $totalTests" -ForegroundColor Cyan
Write-Host "Passed: $passedTests" -ForegroundColor Green
Write-Host "Failed: $failedTests" -ForegroundColor $(if ($failedTests -eq 0) { "Green" } else { "Red" })
Write-Host ""

if ($failedTests -gt 0) {
    Write-Host "Failed Tests:" -ForegroundColor Red
    $testResults | Where-Object { -not $_.Success } | ForEach-Object {
        Write-Host "  - $($_.Test): $($_.Message)" -ForegroundColor Red
    }
    Write-Host ""
}

# Generate test report
$reportPath = "e2e-test-report-$(Get-Date -Format 'yyyyMMdd-HHmmss').json"
$testResults | ConvertTo-Json -Depth 3 | Out-File -FilePath $reportPath -Encoding UTF8

Write-Host "Test report saved to: $reportPath" -ForegroundColor Cyan
Write-Host ""

if ($failedTests -eq 0) {
    Write-Host "All tests passed! ✅" -ForegroundColor Green
    exit 0
} else {
    Write-Host "Some tests failed! ❌" -ForegroundColor Red
    exit 1
}
