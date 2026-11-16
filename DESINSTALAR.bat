@echo off
rem Remove o A2R Link (paineis do Premiere e do After, script do DaVinci e arquivos de configuracao). Nao apaga timelines nem bins do DaVinci.
rem Removes A2R Link (Premiere/After panels, DaVinci script and config files). DaVinci timelines and bins are kept.
cd /d "%~dp0"
for /f "usebackq delims=" %%L in (`powershell -NoProfile -Command "(Get-UICulture).TwoLetterISOLanguageName"`) do set A2R_LANG=%%L
set PY=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe
if not exist "%PY%" set PY=python
"%PY%" install.py --remover
echo.
pause
