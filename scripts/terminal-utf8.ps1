# 在任意 PowerShell 会话中执行: . .\scripts\terminal-utf8.ps1
# 或写入 $PROFILE 实现每次启动自动 UTF-8
chcp 65001 | Out-Null
[Console]::InputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
