' Double-click or schedule this script to run the dashboard silently in the background (no console window).
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
baseDir = fso.GetParentFolderName(fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName)))
pythonw = baseDir & "\.venv\Scripts\pythonw.exe"
server = baseDir & "\server.py"

If Not fso.FileExists(pythonw) Then
  MsgBox "未找到 .venv\Scripts\pythonw.exe，请先运行一次根目录的 start.bat 完成环境初始化。", 48, "桌边控制屏"
  WScript.Quit 1
End If

shell.CurrentDirectory = baseDir
shell.Run """" & pythonw & """ """ & server & """", 0, False
