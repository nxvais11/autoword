Option Explicit
Dim shell, fso, folder, command, result
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = folder
command = "cmd.exe /d /c " & Chr(34) & Chr(34) & folder & "\INICIAR.bat" & Chr(34) & " --preparar" & Chr(34)
On Error Resume Next
result = shell.Run(command, 0, True)
If Err.Number <> 0 Then
    MsgBox "Nao foi possivel abrir o aplicativo: " & Err.Description, 16, "Condominio Facil"
    WScript.Quit 1
End If
On Error GoTo 0
If result = 2 Then
    MsgBox "Instale Python 3.11 ou superior com Python Launcher e Tcl/Tk. Depois abra INICIAR.vbs novamente." & vbCrLf & "Download: https://www.python.org/downloads/windows/", 16, "Condominio Facil"
ElseIf result <> 0 Then
    MsgBox "Nao foi possivel preparar o aplicativo. Verifique o Python e a conexao com a internet para a primeira instalacao, e tente novamente.", 16, "Condominio Facil"
End If
