$ErrorActionPreference = 'Stop'
try {
  [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager,Windows.Media.Control,ContentType=WindowsRuntime] | Out-Null
  $mgr = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync().GetAwaiter().GetResult()
  $session = $mgr.GetCurrentSession()
  if ($session) {
    $props = $session.TryGetMediaPropertiesAsync().GetAwaiter().GetResult()
    if ($props.Title) {
      if ($props.Artist) { Write-Output ($props.Artist + ' - ' + $props.Title) }
      else { Write-Output $props.Title }
    } else { Write-Output 'NOTHING' }
  } else { Write-Output 'NOTHING' }
} catch { Write-Output 'NOTHING' }
