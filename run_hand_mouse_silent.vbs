' ハンドマウスをコンソール（黒い画面）を出さずに起動する。
' 初回セットアップ（.venv や検出モデル）が未完のときは、run_hand_mouse.bat を表示付きで実行する。
' 終了は Ctrl+Alt+Q。ログは logs\hand_mouse.log に残る。
Option Explicit
Dim fso, sh, root, pyw, model, args, i, q
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
q = Chr(34)
root = fso.GetParentFolderName(WScript.ScriptFullName)
pyw = root & "\.venv\Scripts\pythonw.exe"
model = root & "\models\hand_landmarker.task"
sh.CurrentDirectory = root

If fso.FileExists(pyw) And fso.FileExists(model) Then
    args = ""
    For i = 0 To WScript.Arguments.Count - 1
        args = args & " " & q & WScript.Arguments(i) & q
    Next
    ' 第2引数 0 = ウィンドウを表示しない。pythonw.exe なのでコンソールも出ない
    sh.Run q & pyw & q & " " & q & root & "\scripts\hand_mouse.py" & q & args, 0, False
Else
    ' 初回はセットアップの進行が見えるように、通常のバッチを表示付きで実行する
    sh.Run q & root & "\run_hand_mouse.bat" & q, 1, False
End If
