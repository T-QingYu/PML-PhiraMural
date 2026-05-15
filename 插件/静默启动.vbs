Set ws = CreateObject("Wscript.Shell")
ws.Run "python """ & CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName) & "\phira_video_bg_plugin.py""", 0
