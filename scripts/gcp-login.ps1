param(
  [Parameter(Mandatory = $false)]
  [string]$ProjectId,

  [Parameter(Mandatory = $false)]
  [ValidateSet("Adc", "ServiceAccount")]
  [string]$AuthMode,

  [Parameter(Mandatory = $false)]
  [string]$CredentialFile,

  [Parameter(Mandatory = $false)]
  [switch]$SkipLogin,

  [Parameter(Mandatory = $false)]
  [switch]$SkipEnableApis,

  [Parameter(Mandatory = $false)]
  [switch]$ListServiceAccounts,

  [Parameter(Mandatory = $false)]
  [switch]$WriteEnv,

  [Parameter(Mandatory = $false)]
  [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"

$requiredApis = @(
  "speech.googleapis.com",
  "translate.googleapis.com",
  "storage.googleapis.com"
)

$projectRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $projectRoot ".env"
$gcloudCandidates = @(
  "C:\Users\admin\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
  "C:\Program Files\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
  "C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
)

$gcloud = $gcloudCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $gcloud) {
  throw "gcloud CLI was not found. Install Google Cloud SDK first."
}

function Invoke-GCloud {
  param(
    [Parameter(Mandatory = $true)]
    [string[]]$Arguments
  )

  & $script:gcloud @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "gcloud command failed: $($Arguments -join ' ')"
  }
}

function Invoke-GCloudJson {
  param(
    [Parameter(Mandatory = $true)]
    [string[]]$Arguments
  )

  $output = & $script:gcloud @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "gcloud command failed: $($Arguments -join ' ')"
  }
  if (-not $output) {
    return @()
  }
  return $output | ConvertFrom-Json
}

function Select-MenuItem {
  param(
    [Parameter(Mandatory = $true)]
    [array]$Items,

    [Parameter(Mandatory = $true)]
    [scriptblock]$LabelScript,

    [string]$Prompt = "Enter the item number"
  )

  if ($Items.Count -eq 1) {
    return $Items[0]
  }

  for ($index = 0; $index -lt $Items.Count; $index++) {
    $label = & $LabelScript $Items[$index]
    Write-Host ("[{0}] {1}" -f ($index + 1), $label)
  }

  while ($true) {
    $answer = Read-Host $Prompt
    if ([string]::IsNullOrWhiteSpace($answer)) {
      $answer = "1"
    }
    $parsed = 0
    if ([int]::TryParse($answer, [ref]$parsed) -and $parsed -ge 1 -and $parsed -le $Items.Count) {
      return $Items[$parsed - 1]
    }
    Write-Host "Invalid selection. Try again."
  }
}

function Resolve-AuthMode {
  if ($AuthMode) {
    return $AuthMode
  }
  if ($CredentialFile) {
    return "ServiceAccount"
  }
  if ($NonInteractive) {
    return "Adc"
  }

  Write-Host ""
  Write-Host "Choose an auth mode:"
  $choice = Select-MenuItem -Items @("Adc", "ServiceAccount") -LabelScript {
    param($item)
    if ($item -eq "Adc") {
      return "Browser login and update ADC (Recommended)"
    }
    return "Use a service account JSON file"
  } -Prompt "Auth mode number"
  return $choice
}

function Resolve-CredentialFile {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Mode
  )

  if ($Mode -ne "ServiceAccount") {
    return $null
  }

  if ($CredentialFile) {
    $resolved = Resolve-Path -Path $CredentialFile -ErrorAction Stop
    return $resolved.Path
  }

  if ($NonInteractive) {
    throw "ServiceAccount mode requires -CredentialFile."
  }

  while ($true) {
    $entered = Read-Host "Enter the service account JSON path"
    if ([string]::IsNullOrWhiteSpace($entered)) {
      Write-Host "The path cannot be empty."
      continue
    }
    if (Test-Path $entered) {
      return (Resolve-Path -Path $entered).Path
    }
    Write-Host "The file was not found. Try again."
  }
}

function Get-CredentialFileType {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path
  )

  $json = Get-Content -Path $Path -Raw | ConvertFrom-Json
  return $json.type
}

function Write-OrUpdateEnvValue {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Key,

    [Parameter(Mandatory = $true)]
    [string]$Value
  )

  $lines = @()
  if (Test-Path $script:envFile) {
    $lines = Get-Content $script:envFile
  }

  $updated = $false
  $escapedKey = [regex]::Escape($Key)
  for ($index = 0; $index -lt $lines.Count; $index++) {
    if ($lines[$index] -match "^$escapedKey=") {
      $lines[$index] = "$Key=$Value"
      $updated = $true
    }
  }

  if (-not $updated) {
    $lines += "$Key=$Value"
  }

  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllLines($script:envFile, $lines, $utf8NoBom)
}

function Should-WriteEnv {
  if ($WriteEnv) {
    return $true
  }
  if ($NonInteractive) {
    return $false
  }
  $answer = Read-Host "Write the selected project and credential path to .env? (y/N)"
  return $answer -match '^(y|yes)$'
}

function Maybe-ListServiceAccounts {
  param(
    [Parameter(Mandatory = $true)]
    [string]$ChosenProjectId
  )

  $shouldList = $ListServiceAccounts
  if (-not $shouldList -and -not $NonInteractive) {
    $answer = Read-Host "List this project's service accounts? (y/N)"
    $shouldList = $answer -match '^(y|yes)$'
  }

  if (-not $shouldList) {
    return
  }

  $accounts = Invoke-GCloudJson -Arguments @(
    "iam", "service-accounts", "list",
    "--project", $ChosenProjectId,
    "--format=json"
  )

  if (-not $accounts -or $accounts.Count -eq 0) {
    Write-Host "No visible service accounts were found for this project."
    return
  }

  Write-Host ""
  Write-Host "Service Accounts:"
  foreach ($account in $accounts) {
    Write-Host ("- {0} ({1})" -f $account.email, $account.displayName)
  }
}

$resolvedAuthMode = Resolve-AuthMode
$resolvedCredentialFile = Resolve-CredentialFile -Mode $resolvedAuthMode

if (-not $SkipLogin) {
  if ($resolvedAuthMode -eq "Adc") {
    Invoke-GCloud -Arguments @("auth", "login", "--update-adc")
  } else {
    $credentialType = Get-CredentialFileType -Path $resolvedCredentialFile
    if ($credentialType -ne "service_account") {
      throw "The file '$resolvedCredentialFile' is type '$credentialType', not 'service_account'. Use ADC mode for application_default_credentials.json."
    }
    Invoke-GCloud -Arguments @(
      "auth", "activate-service-account",
      "--key-file", $resolvedCredentialFile
    )
  }
}

$chosenProjectId = $ProjectId
if (-not $chosenProjectId) {
  $projects = @(Invoke-GCloudJson -Arguments @("projects", "list", "--format=json"))
  if (-not $projects -or $projects.Count -eq 0) {
    throw "No accessible GCP projects were found for the current account."
  }

  if ($NonInteractive) {
    if ($projects.Count -ne 1) {
      throw "NonInteractive mode requires -ProjectId when multiple projects exist."
    }
    $chosenProjectId = $projects[0].projectId
  } else {
    Write-Host ""
    Write-Host "Choose a project:"
    $selectedProject = Select-MenuItem -Items $projects -LabelScript {
      param($item)
      return "{0} [{1}]" -f $item.name, $item.projectId
    } -Prompt "Project number"
    $chosenProjectId = $selectedProject.projectId
  }
}

Invoke-GCloud -Arguments @("config", "set", "project", $chosenProjectId)

if (-not $SkipEnableApis) {
  Invoke-GCloud -Arguments (@("services", "enable") + $requiredApis + @("--project", $chosenProjectId))
}

if (Should-WriteEnv) {
  Write-OrUpdateEnvValue -Key "GOOGLE_CLOUD_PROJECT" -Value $chosenProjectId
  if ($resolvedCredentialFile) {
    Write-OrUpdateEnvValue -Key "GOOGLE_APPLICATION_CREDENTIALS" -Value $resolvedCredentialFile
  }
}

Maybe-ListServiceAccounts -ChosenProjectId $chosenProjectId

Write-Host ""
Write-Host ("Project ready: {0}" -f $chosenProjectId)
if ($resolvedAuthMode -eq "Adc") {
  Write-Host "Auth mode: ADC"
} else {
  Write-Host ("Auth mode: Service Account ({0})" -f $resolvedCredentialFile)
}
if (-not $SkipEnableApis) {
  Write-Host ("Enabled APIs: {0}" -f ($requiredApis -join ", "))
}
