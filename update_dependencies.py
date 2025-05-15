"""
Dependency Update Script for TrendTwitterALys
This script helps install the correct versions of dependencies.
"""
import subprocess
import sys
import os

def run_command(command):
    """Run a command and return its output"""
    print(f"Running: {command}")
    process = subprocess.run(command, shell=True, capture_output=True, text=True)
    if process.returncode != 0:
        print(f"Error: {process.stderr}")
        return False
    print(process.stdout)
    return True

def update_dependencies():
    """Update dependencies in the correct order to avoid conflicts"""
    print("Updating core dependencies first...")
    
    # Update pip
    run_command(f"{sys.executable} -m pip install --upgrade pip")
    
    # Install wheel and setuptools first
    run_command(f"{sys.executable} -m pip install --upgrade wheel setuptools")
    
    # Install the basic dependencies that others depend on
    run_command(f"{sys.executable} -m pip install --upgrade Werkzeug==2.0.1 click==8.0.1")
    
    # Install Flask with a specific version
    run_command(f"{sys.executable} -m pip install --upgrade flask==2.0.1")
    
    # Install PyYAML using binary to avoid compilation issues
    run_command(f"{sys.executable} -m pip install --upgrade pyyaml==6.0.1 --only-binary :all:")
    
    # Install the remaining dependencies from requirements.txt
    print("\nInstalling remaining dependencies from requirements.txt...")
    run_command(f"{sys.executable} -m pip install -r requirements.txt")
    
    print("\nDependency update complete!")

if __name__ == "__main__":
    print("=" * 60)
    print("Twitter Trend Analysis Dependency Updater")
    print("=" * 60)
    
    # Make sure requirements.txt exists
    if not os.path.exists("requirements.txt"):
        print("Error: requirements.txt not found in the current directory.")
        sys.exit(1)
        
    # Ask for confirmation
    print("This will update all dependencies for the TrendTwitterALys project.")
    print("It may take a few minutes, especially for scientific libraries.")
    confirm = input("Continue? (y/n): ")
    
    if confirm.lower() == 'y':
        update_dependencies()
    else:
        print("Update canceled.")
