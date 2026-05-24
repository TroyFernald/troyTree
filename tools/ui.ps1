param(
  [Parameter(Mandatory=$true)][string]$action,
  [int]$x = 0,
  [int]$y = 0,
  [string]$text = "",
  [string]$out = "C:\Tree\troy-family-tree-research\data\exports\screen.png"
)

Add-Type -AssemblyName System.Windows.Forms,System.Drawing

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32 {
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint cButtons, uint dwExtraInfo);
  public const uint LEFTDOWN = 0x0002, LEFTUP = 0x0004;
}
"@

function Shot {
  $b = [System.Windows.Forms.SystemInformation]::VirtualScreen
  $bmp = New-Object System.Drawing.Bitmap($b.Width, $b.Height)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($b.X, $b.Y, 0, 0, $bmp.Size)
  $bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
  $g.Dispose(); $bmp.Dispose()
  Write-Output "shot:$out ($($b.Width)x$($b.Height))"
}

switch ($action) {
  "shot" { Shot }
  "click" {
    [Win32]::SetCursorPos($x, $y); Start-Sleep -Milliseconds 120
    [Win32]::mouse_event([Win32]::LEFTDOWN,0,0,0,0); Start-Sleep -Milliseconds 60
    [Win32]::mouse_event([Win32]::LEFTUP,0,0,0,0); Start-Sleep -Milliseconds 600
    Shot
  }
  "dblclick" {
    [Win32]::SetCursorPos($x, $y); Start-Sleep -Milliseconds 120
    for ($i=0; $i -lt 2; $i++) { [Win32]::mouse_event([Win32]::LEFTDOWN,0,0,0,0); [Win32]::mouse_event([Win32]::LEFTUP,0,0,0,0); Start-Sleep -Milliseconds 80 }
    Start-Sleep -Milliseconds 600; Shot
  }
  "type" {
    [System.Windows.Forms.SendKeys]::SendWait($text); Start-Sleep -Milliseconds 400; Shot
  }
  "move" { [Win32]::SetCursorPos($x, $y); Shot }
  default { Write-Output "unknown action: $action" }
}
