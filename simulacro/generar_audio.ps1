# Genera el audio del simulacro con la voz de Windows en español.
# Uso: powershell -ExecutionPolicy Bypass -File generar_audio.ps1 [-PausaPregunta 18]
param(
  [int]$PausaPregunta = 18,   # segundos de silencio después de cada pregunta (para leer la respuesta)
  [int]$PausaIntro = 2
)
Add-Type -AssemblyName System.Speech
$dir = $PSScriptRoot
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voz = $synth.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'es*' } | Select-Object -First 1
if ($voz) { $synth.SelectVoice($voz.VoiceInfo.Name) }
$synth.Rate = 0

$pb = New-Object System.Speech.Synthesis.PromptBuilder
$pb.AppendBreak([TimeSpan]::FromSeconds(2))
foreach ($linea in Get-Content (Join-Path $dir 'preguntas_fullstack.txt') -Encoding UTF8) {
  if (-not $linea.Trim()) { continue }
  $tipo, $texto = $linea -split '\|', 2
  $pb.AppendText($texto)
  $pausa = if ($tipo -eq 'P') { $PausaPregunta } else { $PausaIntro }
  $pb.AppendBreak([TimeSpan]::FromSeconds($pausa))
}

$out = Join-Path $dir 'simulacro_fullstack.wav'
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(22050, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$synth.SetOutputToWaveFile($out, $fmt)
$synth.Speak($pb)
$synth.Dispose()
Write-Output "Listo: $out"
