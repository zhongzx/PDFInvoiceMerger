import os
import subprocess
import sys
from PIL import Image

def create_ico():
    """Convert assets/icon.png to assets/icon.ico for the executable icon."""
    png_path = os.path.join("assets", "icon.png")
    ico_path = os.path.join("assets", "icon.ico")
    
    if not os.path.exists(png_path):
        print(f"Error: {png_path} not found. Please ensure the icon exists.")
        return None
        
    try:
        img = Image.open(png_path)
        img.save(ico_path, format='ICO', sizes=[(256, 256)])
        print(f"Successfully created {ico_path}")
        return ico_path
    except Exception as e:
        print(f"Failed to create .ico file: {e}")
        return None

def build_exe():
    """Run PyInstaller to build the executable."""
    ico_path = create_ico()
    if not ico_path:
        return

    # PyInstaller arguments
    args = [
        "pyinstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", "PDFInvoiceMerger",
        "--icon", ico_path,
        "--add-data", f"assets{os.pathsep}assets",  # Include assets folder
        "--hidden-import", "patool",
        "--clean",
        "main.py"
    ]
    
    print("Running PyInstaller...")
    print(" ".join(args))
    
    try:
        subprocess.check_call(args)
        print("\nBuild successful!")
        print(f"Executable found in: {os.path.join(os.getcwd(), 'dist', 'PDFInvoiceMerger.exe')}")
        print("\nNOTE: This executable was built with Python 3.11.")
        print("It will run on Windows 10 and Windows 11.")
        print("It will NOT run on Windows 7 (requires Python 3.8 or older).")
    except subprocess.CalledProcessError as e:
        print(f"\nBuild failed with error: {e}")

if __name__ == "__main__":
    build_exe()
