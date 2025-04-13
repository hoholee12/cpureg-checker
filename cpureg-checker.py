import sys
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
import subprocess
import re

# args
mw_workspace_dir = "cpureg-workspace"
pf_workspace_dir = "cpureg-parsed"

# user args
target_platform = ""

# patterns for src comments
asm_comment_pattern_1_start = re.compile(r"(.*?)/\*")   # /*
# asm_comment_pattern_1 - make a flag to skip inbetween lines
asm_comment_pattern_1_end = re.compile(r"\*/(.*?)")     # */
asm_comment_pattern_2 = re.compile(r"(.*?)\s*-")        # - (? is to make the capture group less greedy)
asm_comment_pattern_3 = re.compile(r"(.*?)\/\/")        # //
# if none of the above match, we have a clean line
# /* hello:
# --_hello:
# //_hello:
# ;_hello:
# hello: -> matches
# _hello: -> matches
asm_func_pattern_1 = re.compile(r"^(\w+):")

comment_pattern_4 = re.compile("")

def make_workspace_persrc(srcpath: str, incpaths: list):
    # args
    global mw_workspace_dir
    mw_gcc_arg = "gcc -E "
    mw_gcc_arg_inc = " -I "
    mw_srcpath_fnonly = os.path.basename(srcpath).split(".")[0]
    # generate args
    mw_gcc_arg += srcpath
    for i in incpaths:
        mw_gcc_arg += mw_gcc_arg_inc + i
    mw_gcc_arg += " -o " + mw_workspace_dir + "\\" + mw_srcpath_fnonly + ".generated.c"
    # run gcc
    subprocess.call(mw_gcc_arg, shell = True)

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
                if filename.endswith(".c"):
                    srcpaths.add(dirpath + os.path.sep + filename)
    # launch individual src generation
    with ThreadPoolExecutor(max_workers = 4) as executor:
        running_tasks = [executor.submit(make_workspace_persrc, srcpath, incpaths) for srcpath in srcpaths]
        for running_task in running_tasks:
            running_task.result()   # block until completed


def parse_functions_asm(srcpath: str):
    in_comment = 0  # 1 if inside comment
    sanitizedlines = []

    # sanitize lines from comments
    with open(srcpath, 'r') as f:
        lines = f.readlines()
        loc = len(lines)

        for i in range(0, loc):
            line = lines[i]
            # trim start-end comments first
            if asm_comment_pattern_1_start.search(line):
                line = asm_comment_pattern_1_start.search(line).group(1)    # trim comment
                in_comment = 1
            elif in_comment != 0 and asm_comment_pattern_1_end.search(line):
                line = asm_comment_pattern_1_end.search(line).group(1)
                in_comment = 0
            elif in_comment == 0:
                # trim other comments if available
                if asm_comment_pattern_2.search(line):
                    line = asm_comment_pattern_2.search(line).group(1)
                elif asm_comment_pattern_3.search(line):
                    line = asm_comment_pattern_3.search(line).group(1)
                else:   # the line is clean
                    pass
            elif in_comment == 1:   # inside comment
                in_comment = 2      # ignore everything

            # clean by strip and add newline
            line = line.strip() + "\n"

            if in_comment != 2: # will capture in_comment == 0 & 1
                sanitizedlines += [line]

    # parse functions: k:funcname - v:body
    captured_func_body = {}
    # get registers used: k:funcname - v:regs
    # r1-r3  will be converted to r1, r2, r3
    # r3, r1, r2 will be converted to r1, r2, r3
    # sp -> r13, lr -> r14
    captured_func_regs = {}
    # get funcs called: k:funcname - v:calls
    captured_func_calls = {}

    funcname = ""
    in_func = 0 # is probably 1 all the time after start

    sanitizedloc = len(sanitizedlines)
    for i in range(0, sanitizedloc):
        sanitizedline = sanitizedlines[i]
        if asm_func_pattern_1.search(sanitizedline):
            funcname = asm_func_pattern_1.search(sanitizedline).group(1)
            in_func = 1
        elif in_func == 1:




        if in_func == 1:
            captured_func_body



def parse_functions_c(srcpath: str):
    with open(srcpath, 'r') as f:
        lines = f.readlines()
        loc = len(lines)

        for i in range(0, loc):

# type0 -> c, type1 -> asm
def parse_functions_persrc(srcpath: str, type: int):
    if type == 0:
        # type0 -> c
        parse_functions_c(srcpath)
    elif type == 1:
        # type1 -> asm
        parse_functions_asm(srcpath)


# now we will start parsing for all the functions (c and asm alike)
def parse_functions():
    # args
    global pf_workspace_dir
    # ready workspace
    # delete old workspace
    if os.path.exists(pf_workspace_dir) and os.path.isdir(pf_workspace_dir):
        shutil.rmtree(pf_workspace_dir, ignore_errors = True)
    # create a new one
    os.makedirs(pf_workspace_dir, exist_ok = True)



if __name__ == "__main__":
    print("hello")
    if len(sys.argv) <= 2:
        print("input needed: arg1 - target platform (armv7m, rh850), arg2+ - all of the source paths including all the files needed for macro")
    target_platform = sys.argv[1]
    if target_platform not in ["armv7m", "rh850"]:
        print(target_platform + " not supported")
        quit()
    make_workspace(sys.argv[2:])
    parse_functions()
