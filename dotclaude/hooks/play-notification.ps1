# Play a notification sound when Claude needs attention
# Used by Claude Code hooks: Stop, AskUserQuestion, Notification

$input = $Input | Out-String

Add-Type -AssemblyName presentationCore
$player = New-Object System.Windows.Media.MediaPlayer
$soundFile = "$env:USERPROFILE\.claude\notification.mp3"
if (-not (Test-Path $soundFile)) {
    $soundFile = "C:\Windows\Media\chimes.wav"
}
$player.Open([Uri]$soundFile)
$player.Play()
Start-Sleep -Milliseconds 3000

exit 0
