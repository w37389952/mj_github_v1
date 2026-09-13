# 내 컴퓨터에서 순위를 직접 재어 본다.
#
# 밤 수집은 GitHub 서버에서 도는데, 그 주소는 여럿이 나눠 쓰는 공용 IP라
# 네이버가 이따금 막는다(2026-09-12에 마흔 번을 내리 막혔다). 그때는 그날
# 기록을 비우고 넘어가므로 표에 구멍이 생긴다.
#
# 이 파일은 집 인터넷에서 같은 것을 재어 화면에 보여 준다. 저장소에는
# 아무것도 쓰지 않으므로 마음 놓고 돌려도 된다. 구멍이 생겼을 때, 또는
# '정말 밀린 건가' 싶을 때 쓰면 된다.
#
# 쓰는 법: 이 파일에서 오른쪽 클릭 → 'PowerShell에서 실행'
#          또는 PowerShell 창에서  .\tools\순위 확인.ps1

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
$blogId = "haranalice"

# 저장소의 ranks.json에서 무엇을 재는지 읽어 온다. 없으면 알려 주고 끝낸다.
$root = Split-Path -Parent $PSScriptRoot
$store = Join-Path $root "data\ranks.json"
if (-not (Test-Path $store)) {
  Write-Output "data\ranks.json 이 없습니다. 밤 수집이 한 번은 돌아야 합니다."
  Read-Host "엔터를 누르면 닫힙니다"
  exit
}

$d = Get-Content $store -Raw -Encoding UTF8 | ConvertFrom-Json

# 가장 마지막으로 잰 날을 기준으로 삼는다.
$days = @{}
foreach ($p in $d.posts.PSObject.Properties) {
  foreach ($h in $p.Value.history.PSObject.Properties) { $days[$h.Name] = 1 }
}
$lastDay = @($days.Keys | Sort-Object)[-1]

Write-Output ""
Write-Output "내 컴퓨터에서 순위를 다시 잽니다. 저장소에는 아무것도 안 씁니다."
Write-Output "견줄 기준: $lastDay (마지막으로 잰 날)"
Write-Output ""

function Get-Rank($q) {
  $url = "https://search.naver.com/search.naver?ssc=tab.blog.all" + [char]38 +
         "sm=tab_jum" + [char]38 + "query=" + [uri]::EscapeDataString($q)
  for ($try = 1; $try -le 3; $try++) {
    try {
      $r = Invoke-WebRequest -Uri $url -UserAgent $ua -UseBasicParsing -TimeoutSec 25
      $html = $r.Content -replace '\\u002F', '/' -replace '\\u002f', '/'
      $ms = [regex]::Matches($html, 'blog\.naver\.com/([A-Za-z0-9_\-]+)/(\d{6,})')
      $ids = @()
      foreach ($m in $ms) {
        $id = $m.Groups[1].Value
        if ($ids -notcontains $id) { $ids += $id }
      }
      if ($ids.Count -gt 0) {
        $at = [array]::IndexOf($ids, $blogId)
        return @{ ok = $true; rank = $(if ($at -ge 0) { $at + 1 } else { $null }) }
      }
    } catch { }
    Start-Sleep -Seconds (5 * $try)      # 막혔으면 쉬었다 다시
  }
  return @{ ok = $false }
}

$rows = @()
foreach ($p in $d.posts.PSObject.Properties) {
  $h = $p.Value.history.$lastDay
  foreach ($kw in $p.Value.keywords) {
    $was = if ($h) { $h.$kw } else { $null }
    $rows += [pscustomobject]@{ kw = $kw; was = $was }
  }
}
$rows = @($rows | Sort-Object kw -Unique)

Write-Output ("{0,-22} {1,8} {2,8}" -f "검색어", $lastDay.Substring(5), "오늘")
Write-Output ("-" * 52)

$up = 0; $down = 0; $same = 0; $fail = 0
foreach ($r in $rows) {
  $res = Get-Rank $r.kw
  $sWas = if ($null -ne $r.was) { "$($r.was)위" } else { "없음" }
  if (-not $res.ok) {
    $fail++
    Write-Output ("{0,-22} {1,8} {2,8}" -f $r.kw, $sWas, "못읽음")
    Start-Sleep -Seconds 3
    continue
  }
  $now = $res.rank
  $sNow = if ($null -ne $now) { "$now" + "위" } else { "없음" }
  $mark = ""
  if ($null -ne $r.was -and $null -ne $now) {
    $diff = [int]$now - [int]$r.was
    if ($diff -lt 0) { $mark = "  올라감 $([Math]::Abs($diff))"; $up++ }
    elseif ($diff -gt 0) { $mark = "  내려감 $diff"; $down++ }
    else { $mark = "  그대로"; $same++ }
  } elseif ($null -eq $r.was -and $null -ne $now) { $mark = "  새로 들어옴"; $up++ }
  elseif ($null -ne $r.was -and $null -eq $now) { $mark = "  밖으로"; $down++ }
  Write-Output ("{0,-22} {1,8} {2,8}{3}" -f $r.kw, $sWas, $sNow, $mark)
  Start-Sleep -Seconds (Get-Random -Minimum 2 -Maximum 5)
}

Write-Output ("-" * 52)
Write-Output "올라감 $up · 내려감 $down · 그대로 $same · 못 읽음 $fail"
if ($fail -gt 0) {
  Write-Output ""
  Write-Output "못 읽은 것이 있으면 집 인터넷도 잠시 막힌 것입니다. 좀 뒤에 다시 돌려보세요."
}
Write-Output ""
Read-Host "엔터를 누르면 닫힙니다"
