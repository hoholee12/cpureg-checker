import os
import subprocess
import shutil
from PIL import Image
import pip

def make_icon(png_path, ico_path):
    if not os.path.exists(png_path):
        raise FileNotFoundError(f"PNG file not found: {png_path}")
    img = Image.open(png_path)
    img.save(ico_path)
    print(f"Icon created: {ico_path}")

def build_executable(script_path, icon_path, exe_name):
    if not os.path.exists(script_path):
        raise FileNotFoundError(f"Script not found: {script_path}")
    cmd = [
        "pyinstaller",
        "--onefile",
        f"--name={exe_name}",
        f"--icon={icon_path}",
        script_path
    ]
    print(f"Building executable: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    shutil.move(f"dist/{exe_name}.exe", exe_name + ".exe")
    print(f"Executable built: {exe_name}.exe")

def clean_build_artifacts(project_name):
    paths = [
        "build",
        "dist",
        f"{project_name}.spec",
        "__pycache__"
    ]
    for path in paths:
        if os.path.isdir(path):
            shutil.rmtree(path)
        elif os.path.isfile(path):
            os.remove(path)

if __name__ == "__main__":
    png_file = "cpureg.png"
    ico_file = "cpureg.ico"
    script_file = "cpureg-checker.py"
    output_name = "cpureg-checker"

    pip.main(['install', '-r', 'requirements.txt'])

    make_icon(png_file, ico_file)
    build_executable(script_file, ico_file, output_name)
    clean_build_artifacts(output_name)
