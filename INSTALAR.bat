@echo off
rem Instala o A2R Link (paineis do Premiere e do After + script do DaVinci). Precisa do Python 3.14 (64 bits).
rem Installs A2R Link (Premiere and After panels + DaVinci script). Needs Python 3.14 (64 bit).
cd /d "%~dp0"
rem idioma do sistema -> A2R_LANG (o install.py e os paineis usam)
for /f "usebackq delims=" %%L in (`powershell -NoProfile -Command "(Get-UICulture).TwoLetterISOLanguageName"`) do set A2R_LANG=%%L
set PY=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe
if not exist "%PY%" set PY=python
"%PY%" install.py
if errorlevel 1 (
  echo.
  echo A instalacao nao foi concluida. Leia a mensagem acima. ^| The install did not finish. Read the message above.
)
echo.
pause
