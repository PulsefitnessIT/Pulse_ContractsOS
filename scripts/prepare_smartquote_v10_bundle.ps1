# Prepare the original SmartQuote V10 pricing source bundle without Python.
#
# Requires GitHub CLI (`gh`) signed in with read access to the private
# PulsefitnessIT/Pulse_SmartQuote repository. Never copy GitHub tokens here.
# Downloads FOUR original source assets only. Does not fetch customer records.
#
# Usage:
#   .\scripts\prepare_smartquote_v10_bundle.ps1
#
# Upload the resulting ZIP via Contracts OS > SmartQuote >
# Original V10 & August Price Source Setup (Admin only).
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$Branch = 'feature/contracts-os-accepted-handoff',
    [Parameter(Mandatory = $false)]
    [string]$Repository = 'PulsefitnessIT/Pulse_SmartQuote',
    [Parameter(Mandatory = $false)]
    [string]$OutputPath = '.\Pulse_SmartQuote_V10_Original_Sources.zip'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw 'GitHub CLI is not installed. Install gh, then run gh auth login and retry.'
}

# Reject unexpected repository paths instead of constructing an arbitrary URL.
if ($Repository -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$') {
    throw 'Repository must be in owner/name form.'
}

& gh auth status 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'Authenticate GitHub CLI first: gh auth login'
}

$target = [IO.Path]::GetFullPath($OutputPath)
if ([IO.File]::Exists($target)) {
    throw "Output already exists. Refusing to overwrite $target. Select a new output filename."
}

$temporary = Join-Path ([IO.Path]::GetTempPath()) ('pulse-smartquote-' + [guid]::NewGuid().ToString('N'))
$sourceFolder = Join-Path $temporary 'data'
[void](New-Item -Path $sourceFolder -ItemType Directory -Force)

$filenames = @(
    'catalog.json',
    'configs.json',
    'pricing.json',
    'rrp_2026_source.json.gz'
)
try {
    $encodedBranch = [uri]::EscapeDataString($Branch)
    $sourceHashes = @{}

    foreach ($filename in $filenames) {
        # Use Git blob API because the catalogue exceeds the Content API's
        # ordinary inline-content limit for private files above 1 MB.
        $metadataUrl = "repos/$Repository/contents/data/$filename" + "?ref=$encodedBranch"
        $metadataJson = & gh api --method GET $metadataUrl
        if ($LASTEXITCODE -ne 0 -or -not $metadataJson) {
            throw "Unable to locate original V10 source: $filename"
        }
        $metadata = $metadataJson | ConvertFrom-Json
        if ($metadata.type -ne 'file' -or $metadata.sha -notmatch '^[a-f0-9]{40}$') {
            throw "GitHub did not return an auditable file blob for $filename"
        }
        $blobJson = & gh api --method GET "repos/$Repository/git/blobs/$($metadata.sha)"
        if ($LASTEXITCODE -ne 0 -or -not $blobJson) {
            throw "Unable to fetch the original blob for $filename"
        }
        $blob = $blobJson | ConvertFrom-Json
        if ($blob.encoding -ne 'base64') {
            throw "Unexpected GitHub blob encoding for $filename"
        }
        $raw = [Convert]::FromBase64String(($blob.content -replace '\s', ''))
        if ($raw.Length -lt 2 -or $raw.Length -gt 20MB) {
            throw "Original source file has an invalid size: $filename"
        }
        $destination = Join-Path $sourceFolder $filename
        [IO.File]::WriteAllBytes($destination, $raw)
        $sourceHashes[$filename] = (Get-FileHash -Path $destination -Algorithm SHA256).Hash.ToLowerInvariant()
        Write-Host ("Verified source blob {0} : {1} bytes" -f $filename, $raw.Length)
    }

    # These checks catch accidental test ZIPs before the Admin import preview.
    foreach ($filename in @('catalog.json', 'configs.json', 'pricing.json')) {
        $source = Join-Path $sourceFolder $filename
        $text = [IO.File]::ReadAllText($source, [Text.Encoding]::UTF8)
        $null = $text | ConvertFrom-Json -ErrorAction Stop
    }
    $pricing = [IO.File]::ReadAllText((Join-Path $sourceFolder 'pricing.json')) | ConvertFrom-Json
    if ($pricing.currency -ne 'GBP') {
        throw 'V10 tariff is not denominated in GBP.'
    }
    $gzip = [IO.File]::ReadAllBytes((Join-Path $sourceFolder 'rrp_2026_source.json.gz'))
    if ($gzip[0] -ne 0x1f -or $gzip[1] -ne 0x8b) {
        throw 'August 2026 reference is not the expected gzip source.'
    }

    # The contents of $temporary/data are exactly the four original files.
    Compress-Archive -Path $sourceFolder -DestinationPath $target -CompressionLevel Optimal
    $hash = (Get-FileHash $target -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Host ''
    Write-Host 'Original V10 pricing source bundle created (no customer data):'
    Write-Host $target
    Write-Host ("ZIP SHA256: {0}" -f $hash)
    Write-Host 'Next: Admin uploads this ZIP into SmartQuote Source Setup.'
    Write-Host 'Then import the Sage Sales Price export, review and approve the actual'
    Write-Host 'commercial tariff, confirm maintenance terms, and test a customer PDF.'
    Write-Host 'No commercial tariff has been approved merely by creating this ZIP.'
}
finally {
    if (Test-Path -LiteralPath $temporary) {
        Remove-Item -LiteralPath $temporary -Recurse -Force
    }
}
