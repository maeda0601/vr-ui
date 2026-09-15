@echo off
chcp 932 > nul
cd /d "%~dp0"
title Hand Mouse 設定

rem --- セットアップ済みなら pythonw で直接開く（コンソールを残さない）---
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "scripts\hand_mouse_settings.py" %*
    exit /b 0
)

rem --- uv を探す（PATH に無ければ標準のインストール先を使う）---
set "UV=uv"
where uv > nul 2>&1
if errorlevel 1 (
    if exist "%USERPROFILE%\.local\bin\uv.exe" (
        set "UV=%USERPROFILE%\.local\bin\uv.exe"
    ) else if exist "%LOCALAPPDATA%\Programs\uv\uv.exe" (
        set "UV=%LOCALAPPDATA%\Programs\uv\uv.exe"
    ) else (
        echo uv が見つかりません。次のどちらかでインストールしてください。
        echo   pip install uv
        echo   powershell -c "irm https://astral.sh/uv/install.ps1 ^| iex"
        pause
        exit /b 1
    )
)

echo 初回セットアップ: 依存パッケージを導入しています...
"%UV%" sync
if errorlevel 1 (
    echo 依存パッケージの導入に失敗しました。
    pause
    exit /b 1
)

"%UV%" run scripts\hand_mouse_settings.py %*
if errorlevel 1 (
    echo.
    echo 設定画面を開けませんでした。上のメッセージを確認してください。
    pause
)
