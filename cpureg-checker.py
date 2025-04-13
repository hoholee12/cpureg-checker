import sys
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from subprocess import Popen, PIPE

# args
mw_workspace_dir = "cpureg-workspace"

def make_workspace_persrc(srcpath: str, incpaths: list):
    # args
    global mw_workspace_dir
    mw_gcc_arg = "/usr/bin/gcc -E "
    mw_gcc_arg_inc = " -I "
    mw_srcpath_fnonly = os.path.basename(srcpath).split(".")[0]
    # generate args
    mw_gcc_arg += srcpath
    for i in incpaths:
        mw_gcc_arg += mw_gcc_arg_inc + i
    mw_gcc_arg += " -o " + mw_workspace_dir + "\\" + mw_srcpath_fnonly + ".generated.c"
    # run gcc
    p = Popen("C:/cygwin64/bin/bash.exe", stdin=PIPE, stdout=PIPE)
    mw_gcc_arg_b = mw_gcc_arg.encode()
    p.stdin.write(mw_gcc_arg_b)
    p.stdin.close()

# all the preprocessed source files go here
# we generate preprocessed source files and process checker according to those files
def make_workspace(incpaths: list):
    # args
    global mw_workspace_dir
    # ready workspace
    # delete old workspace
    if os.path.exists(mw_workspace_dir) and os.path.isdir(mw_workspace_dir):
        shutil.rmtree(mw_workspace_dir, ignore_errors = True)
    # create a new one
    os.makedirs(mw_workspace_dir, exist_ok = True)
    # make srcpaths from incpaths
    srcpaths = set()
    for incpath_ in incpaths:
        incpath = incpath_.replace("/", os.path.sep)
        for dirpath, dirnames, filenames in os.walk(incpath):
            for filename in filenames:
                if filename.endswith(".c") or filename.endswith(".h"):
                    srcpaths.add(dirpath + os.path.sep + filename)
    # launch individual src generation
    with ThreadPoolExecutor(max_workers = 4) as executor:
        running_tasks = [executor.submit(make_workspace_persrc, srcpath, incpaths) for srcpath in srcpaths]
        for running_task in running_tasks:
            running_task.result()   # block until completed

if __name__ == "__main__":
    print("hello")
    if len(sys.argv) <= 2:
        print("input needed: arg1 - generate, arg2+ - all of the source paths including all the files needed for macro")
    make_workspace(sys.argv[2:])
