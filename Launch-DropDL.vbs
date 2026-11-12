Option Explicit
Dim shell, fs, root, command, powershell
Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
root = fs.GetParentFolderName(WScript.ScriptFullName)
powershell = shell.ExpandEnvironmentStrings("%WINDIR%") & "\System32\WindowsPowerShell\v1.0\powershell.exe"
If Len(shell.Environment("Process")("PROCESSOR_ARCHITEW6432")) > 0 Then
    powershell = shell.ExpandEnvironmentStrings("%WINDIR%") & "\Sysnative\WindowsPowerShell\v1.0\powershell.exe"
End If
command = """" & powershell & """ -NoLogo -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & root & "\scripts\launch-installed.ps1"""
shell.Run command, 0, False
