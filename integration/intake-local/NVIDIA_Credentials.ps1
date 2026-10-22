# Project-local Windows DPAPI credential handling. Loading this file makes no calls.
function Get-ProjectNvidiaCredentialPath {
    [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\.runtime\credentials\nvidia.dpapi'))
}

function Assert-ProjectNvidiaKey {
    param([string]$Key)
    if ([string]::IsNullOrWhiteSpace($Key) -or $Key -match '[^\x21-\x7E]' -or
        $Key.Contains('"') -or $Key.Contains("'") -or
        $Key -match '^(NVIDIA_API_KEY|NVIDIA_NIM_API_KEY|NGC_API_KEY)=' -or
        $Key -match '^https?://|^Bearer\s') {
        throw 'Invalid key formatting. Copy only the key value; use terminal right-click Paste at the hidden prompt.'
    }
}

function Save-ProjectNvidiaKey {
    param([Parameter(Mandatory=$true)][Security.SecureString]$SecureKey,
          [string]$CredentialPath = (Get-ProjectNvidiaCredentialPath), [switch]$Replace)
    $nvidiaPointer = [IntPtr]::Zero
    try {
        $nvidiaPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureKey)
        $nvidiaValue = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($nvidiaPointer)
        Assert-ProjectNvidiaKey -Key $nvidiaValue
    } finally {
        $nvidiaValue = $null
        if ($nvidiaPointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($nvidiaPointer) }
    }
    $nvidiaEncrypted = ConvertFrom-SecureString -SecureString $SecureKey
    [IO.Directory]::CreateDirectory((Split-Path -Parent $CredentialPath)) | Out-Null
    $nvidiaMode = if ($Replace) { [IO.FileMode]::Create } else { [IO.FileMode]::CreateNew }
    $nvidiaStream = [IO.File]::Open($CredentialPath,$nvidiaMode,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try {
        $nvidiaWriter = [IO.StreamWriter]::new($nvidiaStream)
        try { $nvidiaWriter.Write($nvidiaEncrypted) } finally { $nvidiaWriter.Dispose() }
    } finally { $nvidiaStream.Dispose() }
}

function Invoke-WithProjectNvidiaKey {
    param([Parameter(Mandatory=$true)][scriptblock]$Action,
          [string]$CredentialPath = (Get-ProjectNvidiaCredentialPath))
    if (-not (Test-Path -LiteralPath $CredentialPath -PathType Leaf)) {
        throw 'No NVIDIA key saved. Run ./integration/intake-local/Configure_NVIDIA_Key.ps1 first.'
    }
    $nvidiaPrevious = @{}
    foreach ($nvidiaName in @('NVIDIA_API_KEY','INTAKE_NVIDIA_KEY_SOURCE')) {
        $nvidiaPrevious[$nvidiaName] = [Environment]::GetEnvironmentVariable($nvidiaName,'Process')
    }
    $nvidiaSecure = $null
    $nvidiaPointer = [IntPtr]::Zero
    try {
        try {
            $nvidiaEncrypted = (Get-Content -LiteralPath $CredentialPath -Raw -ErrorAction Stop).Trim()
            $nvidiaSecure = ConvertTo-SecureString -String $nvidiaEncrypted -ErrorAction Stop
            $nvidiaPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($nvidiaSecure)
            $nvidiaValue = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($nvidiaPointer)
        } catch { throw 'Cannot decrypt the NVIDIA project key. Use the same Windows account that saved it.' }
        Assert-ProjectNvidiaKey -Key $nvidiaValue
        [Environment]::SetEnvironmentVariable('NVIDIA_API_KEY',$nvidiaValue,'Process')
        [Environment]::SetEnvironmentVariable('INTAKE_NVIDIA_KEY_SOURCE','project-dpapi','Process')
        & $Action
    } finally {
        foreach ($nvidiaName in $nvidiaPrevious.Keys) {
            [Environment]::SetEnvironmentVariable($nvidiaName,$nvidiaPrevious[$nvidiaName],'Process')
        }
        $nvidiaValue = $null
        if ($nvidiaPointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($nvidiaPointer) }
        if ($null -ne $nvidiaSecure) { $nvidiaSecure.Dispose() }
    }
}
