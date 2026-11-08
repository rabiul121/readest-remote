$action = New-ScheduledTaskAction -Execute "C:\Program Files\Readest\readest.exe" -WorkingDirectory "C:\Program Files\Readest"
Register-ScheduledTask -TaskName "StartReadestApp" -Action $action -User "desktop-h302ddr\robi" -Force
Start-ScheduledTask -TaskName "StartReadestApp"
Start-Sleep -Seconds 3
Unregister-ScheduledTask -TaskName "StartReadestApp" -Confirm:$false

