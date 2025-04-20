import sys
import os
import shutil
import concurrent.futures
import subprocess
import re

# args
mw_workspace_dir = "cpureg_workspace"
pf_workspace_dir = "cpureg_parsed"
callstack_gen_dir = "callstack_gen"
proc_funcbody_dir = "proc_funcbody"
proc_funcbody_asm_dir = "proc_funcbody_asm"

# user args
target_platform = ""

# patterns for src comments
comment_pattern_1 = re.compile(r'^\s*/\*')
comment_pattern_2 = re.compile(r'\*/\s*$')
comment_pattern_w = re.compile(r'/\*.*?\*/')
comment_pattern_w2 = re.compile(r'(.*)/\*')

not_in_line = re.compile(r'(\w+;|^extern|\s+while|\s+for|\s+if|\s+switch)')
pre_func_pattern = re.compile(r'\)\s*{\s*')
func_pattern = re.compile(r'\s*(\w+)\s*$')

oneliner_func_pattern = re.compile(r'(.*})\s*')
stubinfo_pattern = re.compile(r'.*\\(\w+)\.')

# patterns for asm comments
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
    with concurrent.futures.ThreadPoolExecutor(max_workers = 4) as executor:
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

            # TODO


        if in_func == 1:
            captured_func_body

            # TODO

# genfile: generated src path
# this will strip every comment and index every function from c sources
def parse_functions_c_each_file(genfile: str):
    src_funcs = {}
    func_unit_tracker = {}

    with open(genfile, 'r', encoding = "UTF-8") as f:
        lines = f.readlines()
        loc = len(lines)
        tmp_str = ""
        func_name = ""
        in_func = 0
        bstack = 0
        comment = 0 # inside comment

        for i in range(0, loc):

            # inside a comment - do not process
            if comment_pattern_1.search(lines[i]):
                comment = 2

            # end of line comment
            if comment == 2 and comment_pattern_2.search(lines[i]):
                comment = 1
            elif comment == 2 and "*/" in lines[i]:
                # has a code after comment
                comment = 0

            # in a multiline comment - do nothing
            if comment >= 1:
                if comment == 2:
                    continue
                if comment == 1:
                    comment = 0
                    continue

            # capture all lines preceding possible start of function - don't include extern/while/for/if/switch
            if in_func == 0 and not not_in_line.search(lines[i]):
                tmp_str += lines[i].replace('\n', ' ')
            
            # reset capture if badness found
            if in_func == 0 and not_in_line.search(lines[i]):
                tmp_str = ""

            # found start of function - reverse travel index with captured lines and find function name
            if in_func == 0 and '{' in lines[i]:
                tmp_str += lines[i].replace('\n', ' ')
                rline = tmp_str
                if not pre_func_pattern.search(tmp_str):
                    tmp_str = ""
                    continue
                tloc = len(tmp_str)
                in_brackets = 0
                once_set = 0
                tmp_str_copy = ""
                for t in range(tloc, 0, -1):
                    if tmp_str[t - 1] == ")":
                        in_brackets += 1
                        once_set = 1
                    elif tmp_str[t - 1] == "(":
                        in_brackets -= 1
                    elif in_brackets == 0 and once_set == 1:
                        tmp_str_copy = tmp_str[0:t]
                        break

                if func_pattern.search(tmp_str_copy):
                    func_name = func_pattern.search(tmp_str_copy).group(1)
                    # another set to keep track of which file the function is located in
                    func_unit_tracker[func_name] = os.path.basename(genfile).split(".")[0]
                else:
                    tmp_str = ""
                    continue

                # one liner function might eist, like this:
                # void func (int asdf) {}
                if oneliner_func_pattern.search(tmp_str):
                    tmp_str = ""
                    continue

                bstack = 1
                in_func = 2

            # the section is a one-liner
            elif in_func == 2 and '{' in lines[i] and '}' in lines[i]:
                rline = lines[i] # copy line

            # going in section
            elif in_func == 2 and '{' in lines[i]:
                rline = lines[i]
                bstack += 1

            # getting out of section - if bstack is 0: its the end of function
            elif in_func == 2 and '}' in lines[i]:
                rline = lines[i]
                bstack -= 1
                if bstack <= 0:
                    tmp_str = ""
                    in_func = 1 # quit

            # while in function
            elif in_func == 2:
                rline = lines[i]

            # save the contents(copy line) of the function (if in function)
            if in_func >= 1:
                # strip last line cocmment
                if comment_pattern_w2.search(lines[i]):
                    rline = comment_pattern_w2.search(lines[i]).group(1) + "\n"
                else:
                    rline = lines[i]

                if src_funcs.get(func_name, None) != None:
                    src_funcs[func_name] += rline
                else:
                    src_funcs[func_name] = rline

                if in_func == 1:
                    # strip comments
                    src_funcs[func_name] = comment_pattern_w.sub('', src_funcs[func_name]).strip()
                    in_func = 0
                    func_name = ""

    print(os.path.basename(genfile) + " number of funcs found: " + str(len(src_funcs)))
    return src_funcs, func_unit_tracker

def parse_functions_c_merge_result(genfiles: list):
    src_funcs = {}
    src_funcs_wcomments = {}
    func_unit_tracker = {}
    max_workers = int(os.cpu_count() / 2)

    with concurrent.futures.ThreadPoolExecutor(max_workers = max_workers) as executor:
        futures = [executor.submit(parse_functions_c_each_file, genfile) for genfile in genfiles]
        for future in concurrent.futures.as_completed(futures):
            results = future.result()
            # merge dicts
            src_funcs.update(results[0])
            src_funcs_wcomments.update(results[1])
            func_unit_tracker.update(results[2])

    # tidy up
    # anything that is in function tracker but not in the body capture, is probably a one liner empty function
    # we shall include it in the src_funcs too
    for trackerkey in func_unit_tracker.keys():
        if trackerkey not in src_funcs:
            src_funcs[trackerkey] = "{}"
        if trackerkey not in src_funcs_wcomments:
            src_funcs_wcomments[trackerkey] = "{}"

    # generate call stack estimation
    callstack_gen = {}
    # get them init first (so we can create files even if empty)
    for key in src_funcs.keys():
        callstack_gen[key] = set()

    src_funcs_v = src_funcs.copy()
    for func in src_funcs.keys():
        code = src_funcs[func].splitlines()
        for cline in code:
            for key in src_funcs_v.keys():
                cc = re.split(r'[^a-zA-Z0-9_]+', cline)
                if key in cc:
                    callstack_gen[func].add(key)

    # del old folder
    if os.path.exists(callstack_gen_dir) and os.path.isdir(callstack_gen_dir):
        shutil.rmtree(callstack_gen_dir)

    # make folder and list all callstack
    os.makedirs(callstack_gen_dir, exist_ok = True)
    for func in callstack_gen.keys():
        new_file = callstack_gen_dir + os.path.sep + func + ".txt"
        with open(new_file, 'w') as wf:
            for calling in callstack_gen[func]:
                wf.write(calling + "\n")

    # save processed function bodies
    if os.path.exists(proc_funcbody_dir) and os.path.isdir(proc_funcbody_dir):
        shutil.rmtree(proc_funcbody_dir)

    os.makedirs(proc_funcbody_dir, exist_ok = True)

    for func in src_funcs.keys():
        new_file = proc_funcbody_dir + os.path.sep + func_unit_tracker[func] + "." + func + ".txt"
        with open(new_file, 'w') as wf:
            wf.write(src_funcs[func])




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
