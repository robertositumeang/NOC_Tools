import os
import sys
import shutil
import subprocess

def find_python_exe():
    if not getattr(sys, 'frozen', False):
        return sys.executable

    # 1. Check PATH
    py = shutil.which('python')
    if py and not py.lower().endswith('capture_modem.exe'):
        return py

    py_launcher = shutil.which('py')
    if py_launcher:
        return py_launcher

    # 2. Check standard system install paths
    for ver in ['Python314', 'Python313', 'Python312', 'Python311', 'Python310']:
        candidate = f"C:\\{ver}\\python.exe"
        if os.path.exists(candidate):
            return candidate

    # 3. Check AppData local user install paths
    local_app_data = os.environ.get('LOCALAPPDATA', '')
    if local_app_data:
        for ver in ['Python314', 'Python313', 'Python312', 'Python311', 'Python310']:
            candidate = os.path.join(local_app_data, 'Programs', 'Python', ver, 'python.exe')
            if os.path.exists(candidate):
                return candidate

    return 'python'

def main():
    base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    os.chdir(base_dir)
    
    python_bin = find_python_exe()
    gui_script = os.path.join(base_dir, 'gui_app.py')
    
    cmd = [python_bin, gui_script]
    try:
        proc = subprocess.run(cmd)
        if proc.returncode != 0:
            print(f"\nAplikasi ditutup dengan kode: {proc.returncode}")
            print("Jika terjadi error modul (PyQt6/Playwright), silakan klik dua kali 'SETUP_LAPTOP_BARU.bat'.")
            input("\nTekan Enter untuk keluar...")
    except FileNotFoundError:
        print("==================================================================")
        print("  PERINGATAN: Python belum terdeteksi di laptop ini!")
        print("==================================================================")
        print("Silakan jalankan 'SETUP_LAPTOP_BARU.bat' atau install Python 3.10+.")
        input("\nTekan Enter untuk keluar...")
    except Exception as e:
        print(f"Error: {e}")
        input("\nTekan Enter untuk keluar...")

if __name__ == '__main__':
    main()
