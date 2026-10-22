$ErrorActionPreference = 'Stop'
$nvidiaSpeechRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$nvidiaSpeechDirectory = Join-Path $nvidiaSpeechRoot '.runtime\nvidia-provider-validation'
[IO.Directory]::CreateDirectory($nvidiaSpeechDirectory) | Out-Null
$nvidiaSpeechFile = Join-Path $nvidiaSpeechDirectory 'synthetic-fr-v2.wav'
if (Test-Path -LiteralPath $nvidiaSpeechFile) { throw 'Synthetic speech file already exists; not overwritten.' }
Add-Type -AssemblyName System.Speech
$nvidiaSpeech = [System.Speech.Synthesis.SpeechSynthesizer]::new()
try {
    $nvidiaSpeech.SelectVoice('Microsoft Hortense Desktop')
    $nvidiaSpeechFormat = [System.Speech.AudioFormat.SpeechAudioFormatInfo]::new(16000,[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,[System.Speech.AudioFormat.AudioChannel]::Mono)
    $nvidiaSpeech.SetOutputToWaveFile($nvidiaSpeechFile,$nvidiaSpeechFormat)
    # ASCII source avoids PowerShell 5.1 interpreting UTF-8 accents as ANSI.
    $nvidiaSpeechText = [string]::Concat('Un tas de branches et de d',[char]0xE9,'chets est accumul',[char]0xE9,' pr',[char]0xE8,'s d',[char]0x2019,'une benne.')
    $nvidiaSpeech.Speak($nvidiaSpeechText)
} finally { $nvidiaSpeech.Dispose() }
$nvidiaVideoFile = Join-Path $nvidiaSpeechDirectory 'synthetic-fr-v2.mp4'
if (Test-Path -LiteralPath $nvidiaVideoFile) { throw 'Synthetic video already exists; not overwritten.' }
$nvidiaFfmpeg = Join-Path $nvidiaSpeechRoot '.runtime\tools\ffmpeg.exe'
& $nvidiaFfmpeg -v error -f lavfi -i 'color=c=gray:s=160x120:r=5' -i $nvidiaSpeechFile -shortest -c:v libx264 -pix_fmt yuv420p -c:a aac $nvidiaVideoFile
if ($LASTEXITCODE -ne 0) { throw 'Synthetic video generation failed.' }
Write-Host 'Prepared local synthetic French speech and gray-frame video. No API requests, personal recording or installation.'
$nvidiaSpeechPlan = @{source='Windows local Microsoft Hortense Desktop';synthetic=$true;text=$nvidiaSpeechText;wav_sha256=(Get-FileHash -LiteralPath $nvidiaSpeechFile -Algorithm SHA256).Hash.ToLower();video_sha256=(Get-FileHash -LiteralPath $nvidiaVideoFile -Algorithm SHA256).Hash.ToLower()}
[IO.File]::WriteAllText((Join-Path $nvidiaSpeechDirectory 'synthetic-fr-v2-plan.json'),($nvidiaSpeechPlan | ConvertTo-Json),[Text.UTF8Encoding]::new($false))
