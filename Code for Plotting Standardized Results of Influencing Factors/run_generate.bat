@echo off
setlocal
cd /d "%~dp0"
python generate_factor_tree_images.py --data visualization_data.json --output-dir generated_figures
if errorlevel 1 (
  echo.
  echo Generation failed. Install dependencies with:
  echo python -m pip install -r requirements.txt
  exit /b 1
)
echo.
echo Figures were written to: %~dp0generated_figures
endlocal
