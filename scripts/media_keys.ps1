param([string]$Action)

$code = @"
using System;
using System.Runtime.InteropServices;
public class MediaKeys {
    [DllImport("user32.dll")]
    public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, IntPtr dwExtraInfo);
    public const byte VK_MEDIA_NEXT_TRACK = 0xB0;
    public const byte VK_MEDIA_PREV_TRACK = 0xB1;
    public const byte VK_MEDIA_PLAY_PAUSE = 0xB3;
    public const uint KEYEVENTF_KEYUP = 0x0002;
}
"@
Add-Type -TypeDefinition $code

switch ($Action) {
    "next"  { [MediaKeys]::keybd_event([MediaKeys]::VK_MEDIA_NEXT_TRACK, 0, 0, [IntPtr]::Zero); Start-Sleep -Milliseconds 50; [MediaKeys]::keybd_event([MediaKeys]::VK_MEDIA_NEXT_TRACK, 0, [MediaKeys]::KEYEVENTF_KEYUP, [IntPtr]::Zero) }
    "prev"  { [MediaKeys]::keybd_event([MediaKeys]::VK_MEDIA_PREV_TRACK, 0, 0, [IntPtr]::Zero); Start-Sleep -Milliseconds 50; [MediaKeys]::keybd_event([MediaKeys]::VK_MEDIA_PREV_TRACK, 0, [MediaKeys]::KEYEVENTF_KEYUP, [IntPtr]::Zero) }
    "pause" { [MediaKeys]::keybd_event([MediaKeys]::VK_MEDIA_PLAY_PAUSE, 0, 0, [IntPtr]::Zero); Start-Sleep -Milliseconds 50; [MediaKeys]::keybd_event([MediaKeys]::VK_MEDIA_PLAY_PAUSE, 0, [MediaKeys]::KEYEVENTF_KEYUP, [IntPtr]::Zero) }
}
