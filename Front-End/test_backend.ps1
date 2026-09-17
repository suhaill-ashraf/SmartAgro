# ═══════════════════════════════════════════════════════════
# SmartAgro Backend — Complete Endpoint Test Script
# Tests all 17 endpoints in one run
# Run: .\test_backend.ps1
# Make sure app.py is running before executing this script
# ═══════════════════════════════════════════════════════════

$BASE = "http://127.0.0.1:5000"
$PASS = 0
$FAIL = 0
$RESULTS = @()

function Print-Header($text) {
    Write-Host "`n$("=" * 55)" -ForegroundColor DarkCyan
    Write-Host "  $text" -ForegroundColor Cyan
    Write-Host "$("=" * 55)" -ForegroundColor DarkCyan
}

function Test-API {
    param(
        [string]$No,
        [string]$Name,
        [string]$Method = "GET",
        [string]$Url,
        [hashtable]$Body = $null,
        [int]$ExpectCode = 200
    )

    $label = "[$No] $Name"
    Write-Host "`n$label" -ForegroundColor Yellow
    Write-Host "  $Method $Url" -ForegroundColor Gray

    try {
        $params = @{
            Uri         = $Url
            Method      = $Method
            ContentType = "application/json"
            TimeoutSec  = 15
            ErrorAction = "Stop"
        }
        if ($null -ne $Body) {
            $params.Body = ($Body | ConvertTo-Json -Depth 10)
        }

        $response = Invoke-RestMethod @params
        Write-Host "  PASS ✓" -ForegroundColor Green
        $snippet = ($response | ConvertTo-Json -Depth 3 -Compress)
        if ($snippet.Length -gt 200) { $snippet = $snippet.Substring(0, 200) + "..." }
        Write-Host "  $snippet" -ForegroundColor DarkGray
        $script:PASS++
        $script:RESULTS += [PSCustomObject]@{ No=$No; Name=$Name; Status="PASS"; Method=$Method; Url=$Url }
    }
    catch {
        $msg = $_.Exception.Message
        Write-Host "  FAIL ✗ — $msg" -ForegroundColor Red
        $script:FAIL++
        $script:RESULTS += [PSCustomObject]@{ No=$No; Name=$Name; Status="FAIL"; Method=$Method; Url=$Url }
    }
}

# ═══════════════════════════════════════════
Print-Header "SMARTAGRO — RUNNING ALL ENDPOINT TESTS"
# ═══════════════════════════════════════════


# ── 1. HEALTH ────────────────────────────────────────────────
Test-API -No "01" -Name "Health Check" -Method GET `
    -Url "$BASE/api/health"


# ── 2. SAVE PROFILE (POST) ───────────────────────────────────
Test-API -No "02" -Name "Save Orchard Profile" -Method POST `
    -Url "$BASE/api/profile" `
    -Body @{
        farmer_name      = "Test Farmer"
        location         = "Srinagar, Kashmir"
        lat              = 34.0837
        lon              = 74.7973
        crop_type        = "Apple"
        growth_stage     = "Fruit Set"
        last_spray_date  = "2026-05-01"
        min_interval_days = 14
        preferred_time   = "6 AM - 9 AM"
    }


# ── 3. GET PROFILE ───────────────────────────────────────────
Test-API -No "03" -Name "Get Orchard Profile" -Method GET `
    -Url "$BASE/api/profile"


# ── 4. SPRAY DECISION ────────────────────────────────────────
Test-API -No "04" -Name "AI Spray Decision" -Method GET `
    -Url "$BASE/api/decision"


# ── 5. LIVE WEATHER ──────────────────────────────────────────
Test-API -No "05" -Name "Live Weather" -Method GET `
    -Url "$BASE/api/weather"


# ── 6. SKUAST SCHEDULE ───────────────────────────────────────
Test-API -No "06" -Name "SKUAST-K Schedule" -Method GET `
    -Url "$BASE/api/schedule"


# ── 7. SCHEDULE WITH YEAR ────────────────────────────────────
Test-API -No "07" -Name "SKUAST-K Schedule (year=2026)" -Method GET `
    -Url "$BASE/api/schedule?year=2026"


# ── 8. YEARLY CALENDAR ───────────────────────────────────────
Test-API -No "08" -Name "Yearly Spray Calendar" -Method GET `
    -Url "$BASE/api/calendar"


# ── 9. LOG A SPRAY (POST) ────────────────────────────────────
Test-API -No "09" -Name "Log a Spray" -Method POST `
    -Url "$BASE/api/log" `
    -Body @{
        date         = "2026-05-18"
        spray_name   = "Mancozeb 75 WP"
        dosage       = "300g/100L"
        growth_stage = "Fruit Set"
        status       = "DONE"
        notes        = "Test spray log"
        temp_at_spray      = 22.5
        humidity_at_spray  = 60.0
        wind_at_spray      = 8.0
    }


# ── 10. SPRAY HISTORY ────────────────────────────────────────
Test-API -No "10" -Name "Spray History" -Method GET `
    -Url "$BASE/api/history"


# ── 11. DELETE SPRAY LOG ─────────────────────────────────────
Test-API -No "11" -Name "Delete Spray Log (ID=1)" -Method DELETE `
    -Url "$BASE/api/log/1"


# ── 12. MONTHLY REPORT ───────────────────────────────────────
Test-API -No "12" -Name "Monthly Report (May 2026)" -Method GET `
    -Url "$BASE/api/report?year=2026&month=5"


# ── 13. EXPORT CSV REPORT ────────────────────────────────────
Write-Host "`n[13] Export CSV Report" -ForegroundColor Yellow
Write-Host "  GET $BASE/api/report/export" -ForegroundColor Gray
try {
    $csv = Invoke-WebRequest -Uri "$BASE/api/report/export?year=2026&month=5" -TimeoutSec 15
    if ($csv.StatusCode -eq 200) {
        Write-Host "  PASS ✓  Content-Type: $($csv.Headers['Content-Type'])" -ForegroundColor Green
        $PASS++
        $RESULTS += [PSCustomObject]@{ No="13"; Name="Export CSV Report"; Status="PASS"; Method="GET"; Url="$BASE/api/report/export" }
    }
} catch {
    Write-Host "  FAIL ✗ — $($_.Exception.Message)" -ForegroundColor Red
    $FAIL++
    $RESULTS += [PSCustomObject]@{ No="13"; Name="Export CSV Report"; Status="FAIL"; Method="GET"; Url="$BASE/api/report/export" }
}


# ── 14. ALL SPRAY STAGES ─────────────────────────────────────
Test-API -No "14" -Name "All Spray Stages" -Method GET `
    -Url "$BASE/api/spray-stages"


# ── 15. GET SETTINGS ─────────────────────────────────────────
Test-API -No "15" -Name "Get Settings" -Method GET `
    -Url "$BASE/api/settings"


# ── 16. SAVE SETTINGS ────────────────────────────────────────
Test-API -No "16" -Name "Save Settings" -Method POST `
    -Url "$BASE/api/settings" `
    -Body @{
        notification_enabled = "true"
        preferred_time       = "6 AM - 9 AM"
        language             = "en"
    }


# ── 17. GET NOTIFICATIONS ────────────────────────────────────
Test-API -No "17" -Name "Get All Notifications" -Method GET `
    -Url "$BASE/api/notifications"


# ── 18. GET UNREAD COUNT ─────────────────────────────────────
Test-API -No "18" -Name "Notifications Unread Count" -Method GET `
    -Url "$BASE/api/notifications/count"


# ── 19. GET UNREAD ONLY ──────────────────────────────────────
Test-API -No "19" -Name "Get Unread Notifications" -Method GET `
    -Url "$BASE/api/notifications?unread=1"


# ── 20. MARK NOTIFICATION READ ───────────────────────────────
Test-API -No "20" -Name "Mark Notification Read (ID=1)" -Method POST `
    -Url "$BASE/api/notifications/1/read"


# ── 21. MARK ALL READ ────────────────────────────────────────
Test-API -No "21" -Name "Mark All Notifications Read" -Method POST `
    -Url "$BASE/api/notifications/read-all"


# ── 22. DELETE NOTIFICATION ──────────────────────────────────
Test-API -No "22" -Name "Delete Notification (ID=1)" -Method DELETE `
    -Url "$BASE/api/notifications/1"


# ── 23. AI CHATBOT ───────────────────────────────────────────
Test-API -No "23" -Name "AI Chatbot (Groq)" -Method POST `
    -Url "$BASE/api/chat" `
    -Body @{ message = "Should I spray today?" }


# ═══════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════
$TOTAL = $PASS + $FAIL
Print-Header "TEST SUMMARY"
Write-Host "  Total  : $TOTAL" -ForegroundColor White
Write-Host "  PASS   : $PASS" -ForegroundColor Green
Write-Host "  FAIL   : $FAIL" -ForegroundColor Red

Write-Host "`n  Results:" -ForegroundColor Cyan
$RESULTS | Format-Table -AutoSize

if ($FAIL -gt 0) {
    Write-Host "`n  Failed endpoints:" -ForegroundColor Red
    $RESULTS | Where-Object { $_.Status -eq "FAIL" } | ForEach-Object {
        Write-Host "    ✗ [$($_.No)] $($_.Name) — $($_.Method) $($_.Url)" -ForegroundColor Red
    }
}

if ($FAIL -eq 0) {
    Write-Host "`n  All endpoints passed!" -ForegroundColor Green
} else {
    Write-Host "`n  Fix failed endpoints then re-run this script." -ForegroundColor Yellow
}