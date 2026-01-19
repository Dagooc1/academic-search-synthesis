import sys
import subprocess

def test_installation():
    print("Testing installation...")
    
    # Test basic imports
    try:
        import flask
        print("✓ Flask installed")
    except ImportError:
        print("✗ Flask not installed")
        
    try:
        import requests
        print("✓ Requests installed")
    except ImportError:
        print("✗ Requests not installed")
        
    try:
        import nltk
        print("✓ NLTK installed")
    except ImportError:
        print("✗ NLTK not installed")
    
    print("\nTo run the application:")
    print("1. Make sure virtual environment is activated")
    print("2. Run: python app.py")
    print("3. Open browser to: http://localhost:5000")

if __name__ == "__main__":
    test_installation()