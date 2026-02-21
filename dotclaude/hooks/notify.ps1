# Unified notification - detects SSH vs local
$input = $Input | Out-String

if ($env:SSH_CLIENT) {
    # SSH session: send UDP ping to the laptop, which runs a listener that beeps
    $ip = ($env:SSH_CLIENT -split ' ')[0]
    $client = [System.Net.Sockets.UdpClient]::new()
    $bytes = [byte[]]@(1)
    $client.Send($bytes, 1, $ip, 9999) | Out-Null
    $client.Close()
} else {
    # Local session: play sound file
    # Uses custom MP3 if present, falls back to built-in Windows sound
    Add-Type -AssemblyName presentationCore
    $player = New-Object System.Windows.Media.MediaPlayer
    $soundFile = "$env:USERPROFILE\.claude\notification.mp3"
    if (-not (Test-Path $soundFile)) {
        $soundFile = "C:\Windows\Media\chimes.wav"
    }
    $player.Open([Uri]$soundFile)
    $player.Play()
    Start-Sleep -Milliseconds 3000
}

exit 0
