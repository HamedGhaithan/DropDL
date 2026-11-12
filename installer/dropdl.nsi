Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"
!include "nsDialogs.nsh"
!include "FileFunc.nsh"
!include "WordFunc.nsh"
!define RELEASE "2.3.0"
!define APPKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\DropDLStudio"
Var InstalledVersion
Var InstalledPath
Var Mode
Var Dialog
Var RepairRadio
Var UpgradeRadio
Var CachedSetup
!ifndef PAYLOAD
 !define PAYLOAD "../.."
!endif
!ifndef OUTPUT
 !define OUTPUT "DropDL-Setup.exe"
!endif
Name "DropDL Studio"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\DropDLStudio"
RequestExecutionLevel user
SetCompressor /SOLID lzma
BrandingText "DropDL Studio 2.3.0"
VIProductVersion "2.3.0.0"
VIAddVersionKey "ProductName" "DropDL Studio"
VIAddVersionKey "FileDescription" "DropDL Studio online prerequisite installer"
VIAddVersionKey "FileVersion" "2.3.0"
VIAddVersionKey "LegalCopyright" "DropDL Studio contributors"
!define MUI_ICON "dropdl.ico"
!define MUI_UNICON "dropdl.ico"
!define MUI_WELCOMEPAGE_TEXT "This installer sets up DropDL Studio and downloads missing prerequisites: Python, Node.js, FFmpeg, WebView2 and Python libraries.$\r$\n$\r$\nInternet access is required. Some prerequisite installers may request Windows administrator permission. Installer agreements for those prerequisites are accepted during setup.$\r$\n$\r$\nClose DropDL before installing or updating."
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchDropDL
!define MUI_FINISHPAGE_RUN_TEXT "Launch DropDL Studio"
!insertmacro MUI_PAGE_WELCOME
Page custom MaintenancePage MaintenanceLeave
!define MUI_PAGE_CUSTOMFUNCTION_PRE DirectoryPre
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "Arabic"
LangString MaintenanceTitle ${LANG_ENGLISH} "Upgrade or repair DropDL"
LangString MaintenanceTitle ${LANG_ARABIC} "تحديث DropDL أو إصلاحه"
LangString MaintenanceSubtitle ${LANG_ENGLISH} "Existing installation detected"
LangString MaintenanceSubtitle ${LANG_ARABIC} "تم العثور على تثبيت سابق"
LangString MaintenanceDetails ${LANG_ENGLISH} "Installed version: $InstalledVersion$\r$\nLocation: $InstalledPath$\r$\nInstaller version: ${RELEASE}"
LangString MaintenanceDetails ${LANG_ARABIC} "الإصدار المثبت: $InstalledVersion$\r$\nالمسار: $InstalledPath$\r$\nإصدار المثبت: ${RELEASE}"
LangString UpgradeLabel ${LANG_ENGLISH} "Upgrade to ${RELEASE}"
LangString UpgradeLabel ${LANG_ARABIC} "التحديث إلى ${RELEASE}"
LangString RepairLabel ${LANG_ENGLISH} "Repair ${RELEASE}: restore app files, libraries and shortcuts"
LangString RepairLabel ${LANG_ARABIC} "إصلاح ${RELEASE}: استعادة ملفات التطبيق والمكتبات والاختصارات"
LangString MaintenanceNotice ${LANG_ENGLISH} "Your settings, history and downloaded media are preserved. Setup backs up existing app files and stops DropDL processes before continuing. Active downloads will be interrupted. Internet access is required to check or repair prerequisites."
LangString MaintenanceNotice ${LANG_ARABIC} "سيتم الاحتفاظ بالإعدادات والسجل والوسائط التي تم تنزيلها. ينشئ المثبت نسخة احتياطية ويوقف عمليات DropDL قبل المتابعة. ستتوقف التنزيلات الجارية. يلزم اتصال بالإنترنت لفحص المتطلبات أو إصلاحها."
Function LaunchDropDL
 Exec '"$INSTDIR\DropDL.exe"'
FunctionEnd
Function .onInit
 ${IfNot} ${RunningX64}
  MessageBox MB_ICONSTOP "64-bit Windows 10 or 11 is required."
  Abort
 ${EndIf}
 !insertmacro MUI_LANGDLL_DISPLAY
 StrCpy $Mode "install"
 ReadRegStr $InstalledPath HKCU "${APPKEY}" "InstallLocation"
 ReadRegStr $InstalledVersion HKCU "${APPKEY}" "DisplayVersion"
 ${If} $InstalledPath == ""
  IfFileExists "$INSTDIR\backend\desktop.py" 0 detection_done
  StrCpy $InstalledPath $INSTDIR
 ${EndIf}
 ${If} $InstalledPath != ""
  StrCpy $INSTDIR $InstalledPath
  StrCpy $Mode "upgrade"
  ${If} $InstalledVersion != ""
   ${VersionCompare} $InstalledVersion "${RELEASE}" $0
   ${If} $0 == 1
    MessageBox MB_ICONSTOP "DropDL $InstalledVersion is newer than this installer (${RELEASE}). Downgrading is blocked. Use an installer matching your installed version or newer."
    Abort
   ${EndIf}
   ${If} $0 == 0
    StrCpy $Mode "repair"
   ${EndIf}
  ${EndIf}
 ${EndIf}
 detection_done:
 ${GetParameters} $0
 ClearErrors
 ${GetOptions} $0 "/REPAIR" $1
 ${IfNot} ${Errors}
  ${If} $InstalledPath == ""
   MessageBox MB_ICONSTOP "No existing DropDL installation was found to repair. Run setup normally to install."
   Abort
  ${EndIf}
  ${If} $InstalledVersion != "${RELEASE}"
   MessageBox MB_ICONSTOP "Repair requires an installer matching the installed release. Run setup normally to upgrade to ${RELEASE}."
   Abort
  ${EndIf}
  StrCpy $Mode "repair"
 ${EndIf}
FunctionEnd
Function DirectoryPre
 ${If} $InstalledPath != ""
  Abort
 ${EndIf}
FunctionEnd
Function MaintenancePage
 ${If} $InstalledPath == ""
  Abort
 ${EndIf}
 !insertmacro MUI_HEADER_TEXT "$(MaintenanceTitle)" "$(MaintenanceSubtitle)"
 nsDialogs::Create 1018
 Pop $Dialog
 ${NSD_CreateLabel} 0 0 100% 35u "$(MaintenanceDetails)"
 Pop $0
 ${NSD_CreateRadioButton} 0 45u 100% 16u "$(UpgradeLabel)"
 Pop $UpgradeRadio
 ${NSD_CreateRadioButton} 0 70u 100% 22u "$(RepairLabel)"
 Pop $RepairRadio
 ${If} $InstalledVersion == "${RELEASE}"
  EnableWindow $UpgradeRadio 0
  ${NSD_Check} $RepairRadio
 ${Else}
  EnableWindow $RepairRadio 0
  ${NSD_Check} $UpgradeRadio
 ${EndIf}
 ${NSD_CreateLabel} 0 100u 100% 65u "$(MaintenanceNotice)"
 Pop $0
 nsDialogs::Show
FunctionEnd
Function MaintenanceLeave
 ${NSD_GetState} $RepairRadio $0
 ${If} $0 == ${BST_CHECKED}
  StrCpy $Mode "repair"
 ${Else}
  StrCpy $Mode "upgrade"
 ${EndIf}
FunctionEnd
Section "DropDL Studio"
 InitPluginsDir
 SetOutPath "$PLUGINSDIR"
 ; Backslashes: makensis on Windows rejects forward slashes here (Linux makensis accepts both).
 File /oname=prepare-maintenance.ps1 "${PAYLOAD}\scripts\prepare-maintenance.ps1"
 nsExec::ExecToStack '"$WINDIR\Sysnative\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "$PLUGINSDIR\prepare-maintenance.ps1" -Root "$INSTDIR" -Mode "$Mode" -Release "${RELEASE}"'
 Pop $0
 Pop $1
 DetailPrint "$1"
 ${If} $0 != 0
  MessageBox MB_ICONSTOP "Setup could not prepare the existing installation. No app files were replaced.$\r$\n$1"
  Abort
 ${EndIf}
 ; Remove obsolete hashed UI assets before copying the current release.
 RMDir /r "$INSTDIR\frontend\dist"
 SetOutPath "$INSTDIR"
 File /r "${PAYLOAD}\*"
 DetailPrint "Installing prerequisites. Follow progress in the setup window."
 System::Call 'kernel32::SetEnvironmentVariableW(w "DROPDL_INSTALLER", w "1")i.r0'
 System::Call 'kernel32::SetEnvironmentVariableW(w "DROPDL_SETUP_MODE", w "$Mode")i.r0'
 ExecWait '"$WINDIR\Sysnative\cmd.exe" /D /C ""$INSTDIR\Setup-DropDL.bat""' $0
 ${If} $0 != 0
  MessageBox MB_ICONSTOP "Prerequisite setup failed (code $0). See $INSTDIR\Setup-Log.txt. Repair the reported problem, then rerun this installer."
  Abort
 ${EndIf}
 CopyFiles /SILENT "$INSTDIR\installer\dropdl.ico" "$INSTDIR\installer\dropdl-${RELEASE}.ico"
 CreateDirectory "$SMPROGRAMS\DropDL Studio"
 Delete "$SMPROGRAMS\DropDL Studio\DropDL Studio.lnk"
 Delete "$DESKTOP\DropDL Studio.lnk"
 CreateShortCut "$SMPROGRAMS\DropDL Studio\DropDL Studio.lnk" "$INSTDIR\DropDL.exe" '' "$INSTDIR\installer\dropdl-${RELEASE}.ico"
 CreateShortCut "$DESKTOP\DropDL Studio.lnk" "$INSTDIR\DropDL.exe" '' "$INSTDIR\installer\dropdl-${RELEASE}.ico"
 ; Tell Explorer to refresh shortcut associations and images without clearing user caches.
 System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
 WriteUninstaller "$INSTDIR\Uninstall.exe"
 StrCpy $CachedSetup "$LOCALAPPDATA\DropDL\installer\DropDL-Setup.exe"
 CreateDirectory "$LOCALAPPDATA\DropDL\installer"
 ${If} $EXEPATH != $CachedSetup
  ClearErrors
  CopyFiles /SILENT "$EXEPATH" "$CachedSetup"
  ${If} ${Errors}
   MessageBox MB_ICONEXCLAMATION "Setup succeeded, but the repair installer could not be cached. Keep this installer to repair later."
  ${EndIf}
 ${EndIf}
 CreateShortCut "$SMPROGRAMS\DropDL Studio\Repair DropDL Studio.lnk" "$CachedSetup" '/REPAIR' "$INSTDIR\installer\dropdl.ico"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\DropDLStudio" "DisplayName" "DropDL Studio"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\DropDLStudio" "DisplayVersion" "2.3.0"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\DropDLStudio" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\DropDLStudio" "DisplayIcon" "$INSTDIR\installer\dropdl.ico"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\DropDLStudio" "InstallLocation" "$INSTDIR"
 WriteRegStr HKCU "${APPKEY}" "ModifyPath" '$\"$CachedSetup$\" /REPAIR'
 WriteRegStr HKCU "${APPKEY}" "QuietUninstallString" '$\"$INSTDIR\Uninstall.exe$\" /S'
 WriteRegDWORD HKCU "${APPKEY}" "NoModify" 0
 WriteRegDWORD HKCU "${APPKEY}" "NoRepair" 0
SectionEnd
Section "Uninstall"
 nsExec::ExecToStack '"$WINDIR\Sysnative\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\scripts\prepare-maintenance.ps1" -Root "$INSTDIR" -Mode "uninstall" -Release "${RELEASE}"'
 Pop $0
 Pop $1
 ${If} $0 != 0
  MessageBox MB_ICONSTOP "Could not stop DropDL. Close the app and retry uninstall.$\r$\n$1"
  Abort
 ${EndIf}
 Delete "$DESKTOP\DropDL Studio.lnk"
 RMDir /r "$SMPROGRAMS\DropDL Studio"
 DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\DropDLStudio"
 ; Personal downloads, settings and history are outside the app install directory.
 RMDir /r "$INSTDIR\backend"
 RMDir /r "$INSTDIR\frontend"
 RMDir /r "$INSTDIR\scripts"
 RMDir /r "$INSTDIR\installer"
 RMDir /r "$INSTDIR\tests"
 RMDir /r "$INSTDIR\.venv"
 Delete "$INSTDIR\Setup-DropDL.bat"
 Delete "$INSTDIR\Start-Desktop.bat"
 Delete "$INSTDIR\Start-Native-Windows.bat"
 Delete "$INSTDIR\Start-Windows.bat"
 Delete "$INSTDIR\Launch-DropDL.vbs"
 Delete "$INSTDIR\DropDL.exe"
 RMDir /r "$INSTDIR\browser-extension"
 Delete "$INSTDIR\setup-env.ps1"
 Delete "$INSTDIR\Setup-Log.txt"
 Delete "$INSTDIR\README.md"
 Delete "$INSTDIR\Uninstall.exe"
 Delete "$LOCALAPPDATA\DropDL\installer\DropDL-Setup.exe"
 RMDir "$INSTDIR"
SectionEnd
