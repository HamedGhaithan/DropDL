Unicode true
!ifndef OUTPUT
 !define OUTPUT "../DropDL.exe"
!endif
Name "DropDL Studio"
OutFile "${OUTPUT}"
Icon "dropdl.ico"
RequestExecutionLevel user
SilentInstall silent
AutoCloseWindow true
VIProductVersion "2.3.0.0"
VIAddVersionKey "ProductName" "DropDL Studio"
VIAddVersionKey "FileDescription" "DropDL desktop launcher"
VIAddVersionKey "FileVersion" "2.3.0"
VIAddVersionKey "LegalCopyright" "DropDL Studio contributors"
Section
 SetOutPath "$EXEDIR"
 ; nsExec creates the bootstrap without a console; WindowStyle alone can flash.
 nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "$EXEDIR\scripts\launch-installed.ps1"'
 Pop $0
 Pop $1
 StrCmp $0 "0" launch_done
 MessageBox MB_OK|MB_ICONSTOP "DropDL could not start. Rerun setup to repair the installation."
 launch_done:
SectionEnd
