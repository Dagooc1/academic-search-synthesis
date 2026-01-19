@echo off
echo Setting up Academic Search & Synthesis...

REM Create virtual environment
echo Creating virtual environment...
python -m venv venv

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install requirements
echo Installing requirements...
pip install -r requirements.txt

REM Download NLTK data
echo Downloading NLTK data...
python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords')"

echo.
echo Setup complete!
echo.
echo To run the application:
echo 1. Activate virtual environment: venv\Scripts\activate.bat
echo 2. Run: python app.py
echo 3. Open browser to: http://localhost:5000
echo.
pause