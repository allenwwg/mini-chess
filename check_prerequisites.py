#!/usr/bin/env python3
"""
Check if all prerequisites are installed for running the chess server
"""

import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(errors='replace')
    except (ValueError, OSError):
        pass

def check_python_version():
    """Check Python version"""
    version = sys.version_info
    print(f"Python version: {version.major}.{version.minor}.{version.micro}")
    if version.major >= 3 and version.minor >= 7:
        print("✓ Python version is OK (3.7+)")
        return True
    else:
        print("✗ Python version too old. Need 3.7+")
        return False

def check_module(module_name, package_name=None):
    """Check if a module is installed"""
    if package_name is None:
        package_name = module_name

    try:
        __import__(module_name)
        print(f"✓ {package_name} is installed")
        return True
    except ImportError:
        print(f"✗ {package_name} is NOT installed")
        print(f"  Install with: pip install {package_name}")
        return False

def main():
    print("=" * 60)
    print("Checking Prerequisites for Chinese Chess Server")
    print("=" * 60)

    results = []

    # Check Python version
    results.append(check_python_version())
    print()

    # Check required modules
    print("Checking required Python packages:")
    results.append(check_module('flask', 'flask'))
    results.append(check_module('flask_cors', 'flask-cors'))
    print()

    # Check chess engine files
    print("Checking required files:")
    import os

    required_files = [
        'mini_chess.py',
        'chess_server.py',
        'index.html'
    ]

    for filename in required_files:
        if os.path.exists(filename):
            print(f"✓ {filename} exists")
            results.append(True)
        else:
            print(f"✗ {filename} is MISSING")
            results.append(False)

    print()
    print("=" * 60)

    if all(results):
        print("✓ All prerequisites are satisfied!")
        print("\nYou can now run:")
        print("  python chess_server.py")
        print("\nThen open index.html in your browser")
        return 0
    else:
        print("✗ Some prerequisites are missing")
        print("\nInstall missing packages with:")
        print("  pip install flask flask-cors")
        return 1

if __name__ == '__main__':
    sys.exit(main())
