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

# asm extensions
asm_ext = []

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


# pattern for push pop detection (make sure it covers the inline assembly as well)
# no need to worry for succeeding comments (they are completely removed at this stage)
asm_push_pattern = re.compile(r"pushsp\s+(.*)")
asm_pop_pattern = re.compile(r"popsp\s+(.*)")


# for rh850:
# - pushsp, popsp -> the operands do not change order, so its very easy to map
# - prepare, dispose:
# -- prepare list(regs separated with comma), imm(number of words to reserve stack space)
# -- dispose imm, list, (sometimes)[reg] (put r31(linkreg) on reg -> you get a pop & jmp back to caller)
# -- no need to worry about [reg], all we need to focus is the <list, imm> <imm, list>
# -- but we do need the info for [reg] for correct branch path.
rh850_push_pattern = re.compile(r"pushsp\s+(.*)|prepare\s+(.*),\s*\w+") # we shall only capture the reg part for prepare-dispose
rh850_pop_pattern = re.compile(r"popsp\s+(.*)|dispose\s+\w+,\s*(.*)")
# TODO: we may need the dispose [reg] part for branch ident

# for armv7m:
# - push, pop -> probably not easy (user can become an asshole and change operands order but it is still valid)
# -- will also need to be careful, user can do "push {reg, lr}, pop {reg, pc}" which is similar to "dispose imm, list, [reg]"
# -- we will also need the info for {pc} for correct branch path.
# - stmdb, ldmia -> advanced version of push, pop.
# -- push {r4, lr} -> stmdb sp!, {r4, lr} (this means we can just treat stmdb sp! -> push)
# -- pop {r4, pc} -> ldmia sp!, {r4, pc} (this means we can just treat ldmia sp! -> pop)
# --- anything can be used besides sp! -> ignore because we will not give a fuck other than the stack.
armv7m_push_pattern = re.compile(r"push\s+{((?:(?!,\s*lr)[^}])*).*}")
armv7m_pop_pattern = re.compile(r"pop\s+{((?:(?!,\s*pc)[^}])*).*}")
# we will just capture the whole thing without order. we will remove lr, pc in the process. (TODO: to be taken care of by branch ident)
# we can care about the order thing later.(TODO: further parsing to individual regs maybe)

asm_regname_intrinsics = {"sp" : "r3", "lr" : "r31"}
rh850_regname_intrinsics = {"sp" : "r3", "lr" : "r31"}
armv7m_regname_intrinsics = {"sp" : "r13", "lr" : "r14", "pc" : "r15"}

# we capture the branch op with the obj name. if obj name does not exist, we can find it in previous ops...
asm_branch_pattern = re.compile(r"jr\s+(\w+)|jmp\s+(\w+)|jarl\s+(\w+)|b\w+\s+(\w+)")
rh850_branch_pattern = re.compile(r"jr\s+(\w+)|jmp\s+(\w+)|jarl\s+(\w+)|b\w+\s+(\w+)")  # in rh850, theres no b ~ op
armv7m_branch_pattern = re.compile(r"b\w*\s+(\w+)")    # armv7m branch opnames always start with b
# this is to identify object address that is being passed to previous ops(mov), or in the branch op.
# we need to identify this to figure out if its actually branching into a new function or not.
# any code block that has a object name(blah:~) is considered a separate function.
asm_genericop_pattern = re.compile(r"\w+\s+(.*)")

listup = 0
listup_set = set()
bad_path_list = set()
destructive_only = 0
normality_count = 0 # doomed function if set 1

# get caller flow
def get_caller_flow(calling_path, func):
    global normality_count
    global bad_path_list

    if listup == 1:
        listup_set.add(func)

    file_to_open = "calling_func_list\\" + func + ".txt"
    try:
        with open(file_to_open, 'r', encoding = "UTF-8") as f:
            lines = f.readlines()
            loc = len(lines)

            if loc > 0:
                for i in range(0, loc):
                    next_calling_path = calling_path + "->" + func
                    # check for potential loop before continuing
                    loop_dict = {}
                    for item in next_calling_path.split("->"):
                        if loop_dict.get(item, None) != None:
                            # dead end
                            bad_path_list.add(item)
                            if listup != 1:
                                print("looping " + next_calling_path)
                            return
                        else:
                            loop_dict[item] = 1
                    # continue to the next round
                    next_func = lines[i].strip()
                    get_caller_flow(next_calling_path, next_func)

            else:
                # dead end... finish here
                if listup != 1:
                    bad_path_detected = 0
                    for item in (calling_path + "->" + func).split("->")[1:-1]:
                        if item in bad_path_list:
                            bad_path_detected = 1
                            break
                    if bad_path_detected == 0:
                        if destructive_only == 0:
                            print(calling_path + "->" + func)
                            normality_count += 1
                    else:
                        print("bad " + calling_path + "->" + func)
                return
    except:
        if listup != 1:
            bad_path_detected = 0
            for item in (calling_path + "->" + func).split("->")[1:-1]:
                if item in bad_path_list:
                    bad_path_detected = 1
                    break
            if bad_path_detected == 0:
                if destructive_only == 0:
                    print(calling_path + "->" + func)
                    normality_count += 1
            else:
                print("bad " + calling_path + "->" + func)
            print("incomplete gen")
        return

# get callee flow
def get_callee_flow(func):
    global normality_count
    global bad_path_list

    test_files = []
    # bring all the data back
    for root, dirs, files in os.walk("calling_func_list"):
        for file in files:
            if file.endswith(".txt"):
                test_files.append(os.path.join(root, file))
    calling_func_gen = {}
    for file in test_files:
        with open(file, 'r', encoding = "UTF-8") as f:
            lines = f.readlines()
            loc = len(lines)

            tc_func = os.path.basename(file).split(".")[0]
            calling_func_gen[tc_func] = set()
            for i in range(0, loc):
                calling_func_gen[tc_func].add(lines[i].strip())

    # do a iterative dfs search
    mystack = []
    mystack.append([func, ""])
    while len(mystack) > 0:
        top = mystack.pop()
        called = top[0]
        toprint = top[1]

        if listup == 1:
            listup_set.add(called)

        found = 0
        for key in calling_func_gen.keys():
            # found a callee (key), now we append
            if called in calling_func_gen[key]:
                next_calling_path = toprint + "<-" + called
                # check for potential loop before continuing
                loop_dict = {}
                ok_to_cont = 0
                for item in next_calling_path.split("<-"):
                    if loop_dict.get(item, None) != None:
                        # dead end
                        bad_path_list.add(item)
                        ok_to_cont = 0
                        if listup != 1:
                            print("looping " + next_calling_path)
                        break
                    else:
                        ok_to_cont = 1
                        loop_dict[item] = 1
                if ok_to_cont == 0:
                    continue # skip
                # continue to the next round
                mystack.append([key, next_calling_path])
                found = 1

        # dead end
        if found == 0:
            if listup != 1:
                bad_path_detected = 0
                for item in (toprint + "<-" + called).split("<-")[1:-1]:
                    if item in bad_path_list:
                        bad_path_detected = 1
                        break
                if bad_path_detected == 0:
                    if destructive_only == 0:
                        print(toprint + "<-" + called)
                        normality_count += 1
                else:
                    print("bad " + toprint + "<-" + called)


# genfile: generated src path
# this will strip every comment and index every function from c sources
# uses mw_workspace_dir to temporarily store the preprocessed files
def parse_functions_c_persrc(srcpath: str, incpaths: list):
    # do macro preprocess first
    mw_gcc_arg = "gcc -E "
    mw_gcc_arg_inc = " -I "
    mw_srcpath_fnonly = os.path.basename(srcpath).split(".")[0]
    genfile = mw_workspace_dir + "\\" + mw_srcpath_fnonly + ".generated.c"
    # check and remove old file
    if os.path.exists(genfile) and os.path.isfile(genfile):
        os.remove(genfile)
    # generate args
    mw_gcc_arg += srcpath
    for i in incpaths:
        mw_gcc_arg += mw_gcc_arg_inc + i
    mw_gcc_arg += " -o " + genfile
    # run gcc
    subprocess.call(mw_gcc_arg, shell = True)

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

def parse_functions_c_write(srcpaths: list, incpaths: list):
    src_funcs = {}
    func_unit_tracker = {}
    max_workers = int(os.cpu_count() / 4)

    with concurrent.futures.ThreadPoolExecutor(max_workers = max_workers) as executor:
        futures = [executor.submit(parse_functions_c_persrc, srcpath, incpaths) for srcpath in srcpaths]
        for future in concurrent.futures.as_completed(futures):
            results = future.result()
            # merge dicts
            src_funcs.update(results[0])
            func_unit_tracker.update(results[2])

    # tidy up
    # anything that is in function tracker but not in the body capture, is probably a one liner empty function
    # we shall include it in the src_funcs too
    for trackerkey in func_unit_tracker.keys():
        if trackerkey not in src_funcs:
            src_funcs[trackerkey] = "{}"

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

    # save lists of all callstacks
    if os.path.exists(callstack_gen_dir) and os.path.isdir(callstack_gen_dir):
        shutil.rmtree(callstack_gen_dir)
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

# returns sorted list of strings of registers
# takes care of , and -
def parse_functions_asm_individual_reg(regs: str):
    global asm_regname_intrinsics
    reglist_ = regs.replace(" ", "").split(",")
    reglist = set()
    for reg_ in reglist_:
        reg = reg_.lower().strip()
        if "-" in reg:
            regprefix = re.match(r"[a-z]+", reg).group(0)
            regget = re.compile(r"[a-z]+([0-9]+)-[a-z]+([0-9]+)").search(reg)
            regstart = regget.group(1)
            regend = regget.group(2)
            for i in range(regstart, regend+1):
                reglist.add(regprefix + str(i))
        else:
            reglist.add(reg)

    # sort it out
    sorted_reglist = sorted(reglist)
    return sorted_reglist

# we shall only get the func body here.
# we shall do macro preprocessing just like the c source as well
# returns asm_funcs(body), func_unit_tracker(for caller stack)
# TODO: 1. we shall parse for callstack first, 2. and then parse push/pop after that.
def parse_functions_asm_persrc(srcpath: str, incpaths: list):
    # we generate the c files first
    mw_srcpath_fnonly = os.path.basename(srcpath).split(".")[0]
    mw_srcpath_ext = os.path.basename(srcpath).split(".")[1]
    lines = []
    with open(srcpath, 'r') as f:
        lines = f.readlines()
    new_srcpath = mw_workspace_dir + "\\" + mw_srcpath_fnonly + ".pregen.c" # temporarily changed to c to preprocess this bitch
    with open(new_srcpath, 'w') as f:
        for i in lines:
            parsedi = i
            if (parsedi.strip().startswith(".if") or parsedi.strip().startswith(".elif") or 
                parsedi.strip().startswith(".else") or parsedi.strip().startswith(".endif")):
                parsedi.replace(".", "#")   # there is no other place that the . could be other than in the beginning, so this should be fine
            f.write(parsedi)

    # and then do some macro preprocessing
    mw_gcc_arg = "gcc -E "
    mw_gcc_arg_inc = " -I "
    
    genfile = mw_workspace_dir + "\\" + mw_srcpath_fnonly + ".generated." + mw_srcpath_ext
    # check and remove old file
    if os.path.exists(genfile) and os.path.isfile(genfile):
        os.remove(genfile)
    # generate args
    mw_gcc_arg += new_srcpath
    for i in incpaths:
        mw_gcc_arg += mw_gcc_arg_inc + i
    mw_gcc_arg += " -o " + genfile
    # run gcc
    subprocess.call(mw_gcc_arg, shell = True)

    # file have been preprocessed. now we start parsing
    in_comment = 0  # 1 if inside comment
    sanitizedlines = []

    # sanitize lines from comments first
    with open(genfile, 'r') as f:
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

    # we sanitized it, now we capture functions on it
    sanitizedloc = len(sanitizedlines)

    # lets skim and find all the function names first
    pre_func_names = set()
    for i in range(0, sanitizedloc):
        sanitizedline = sanitizedlines[i]
        if asm_func_pattern_1.search(sanitizedline):
            pre_func_names.add(asm_func_pattern_1.search(sanitizedline).group(1))
    # and thats it...
    
    # parse functions: k:funcname - v:body
    asm_funcs = {}
    func_unit_tracker = {}
    funcname = ""
    in_func = 0 # once it is 1, it will never be 0 again until EOF
    for i in range(0, sanitizedloc):
        sanitizedline = sanitizedlines[i]
        if asm_func_pattern_1.search(sanitizedline):    # will run regardless of in_func.
            funcname = asm_func_pattern_1.search(sanitizedline).group(1)
            # if funcname was not encountered before, init
            if asm_funcs.get(funcname, None) == None:
                asm_funcs[funcname] = []
            in_func = 1
        elif in_func == 1:  # will always run, once in_func changed to 1 & is not on a function name
            # capture func body
            asm_funcs[funcname].append(sanitizedline)
            # check if the func body contains any branch to other known funcs
            # we must not categorize branch and non-branch op, 
            # because the address to the branch can be inserted & used at any time...
            if asm_genericop_pattern.search(sanitizedline):
                genstrlist = asm_genericop_pattern.search(sanitizedline).replace(" ", "").split(",")
                for genstr in genstrlist:
                    if genstr in pre_func_names:
                        func_unit_tracker[funcname].append(genstr)  # add to tracker

    return asm_funcs, func_unit_tracker
            

def parse_functions_asm_write(srcpaths: list, incpaths: list):
    asm_funcs = {}
    func_unit_tracker = {}
    max_workers = int(os.cpu_count() / 4)

    with concurrent.futures.ThreadPoolExecutor(max_workers = max_workers) as executor:
        futures = [executor.submit(parse_functions_asm_persrc, srcpath, incpaths) for srcpath in srcpaths]
        for future in concurrent.futures.as_completed(futures):
            results = future.result()
            # merge dicts
            asm_funcs.update(results[0])
            func_unit_tracker.update(results[2])

    # generate call stack estimation
    callstack_gen = {}
    # get them init first (so we can create files even if empty)
    for key in asm_funcs.keys():
        callstack_gen[key] = set()
    asm_funcs_v = asm_funcs.copy()
    for func in asm_funcs.keys():
        code = asm_funcs[func].splitlines()
        for cline in code:
            for key in asm_funcs_v.keys():
                cc = re.split(r'[^a-zA-Z0-9_]+', cline)
                if key in cc:
                    callstack_gen[func].add(key)

    # save lists of all callstacks
    if os.path.exists(callstack_gen_dir) and os.path.isdir(callstack_gen_dir):
        shutil.rmtree(callstack_gen_dir)
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
    for func in asm_funcs.keys():
        new_file = proc_funcbody_dir + os.path.sep + func_unit_tracker[func] + "." + func + ".txt"
        with open(new_file, 'w') as wf:
            wf.write(asm_funcs[func])

# now we will start parsing for all the functions (c and asm alike)
def parse_functions(srcpaths: list, incpaths: list):
    global asm_ext
    srcpaths_c = []
    srcpaths_asm = []

    for srcpath in srcpaths:
        if srcpath.split(".")[-1] in asm_ext:   # asm file
            srcpaths_asm.append(srcpath)
        else:   # c file
            srcpaths_c.append(srcpath)

    parse_functions_asm_write(srcpaths_asm, incpaths)   # generate all asm func bodies & callstack
    parse_functions_c_write(srcpaths_c, incpaths)   # generate all c files and their func bodies & callstack

# srcpaths: should return list of source files
def parse_per_target_platform(target_platform: str, incpaths: list):
    global asm_ext
    global asm_push_pattern
    global asm_pop_pattern
    global asm_regname_intrinsics
    global asm_branch_pattern
    # get extension
    if target_platform not in ["armv7m", "rh850"]:
        print(target_platform + " not supported")
        quit()
    elif target_platform == "rh850":
        # asm extension
        asm_ext.append("850")
        # asm push/pop pattern
        asm_push_pattern = rh850_push_pattern
        asm_pop_pattern = rh850_pop_pattern
        asm_regname_intrinsics = rh850_regname_intrinsics
        asm_branch_pattern = rh850_branch_pattern
    elif target_platform == "armv7m":
        # asm extension
        asm_ext.append("s")
        asm_ext.append("S")
        # asm push/pop pattern
        asm_push_pattern = armv7m_push_pattern
        asm_pop_pattern = armv7m_pop_pattern
        asm_regname_intrinsics = armv7m_regname_intrinsics
        asm_branch_pattern = armv7m_branch_pattern

    # get source files
    srcpaths = set()
    for incpath_ in incpaths:
        incpath = incpath_.replace("/", os.path.sep)
        for dirpath, dirnames, filenames in os.walk(incpath):
            for filename in filenames:
                if filename.endswith(".c") or filename.endswith(".C") or filename.split(".")[-1] in asm_ext:
                    srcpaths.add(dirpath + os.path.sep + filename)
    
    return srcpaths

if __name__ == "__main__":
    print("hello")
    if len(sys.argv) <= 2:
        print("input needed: arg1 - target platform (armv7m, rh850), arg2+ - all of the source paths including all the files needed for macro")
    
    # get all the needed info
    target_platform = sys.argv[1]
    incpaths = sys.argv[2:]
    srcpaths = parse_per_target_platform(target_platform, incpaths)

    # start parsing source files
    parse_functions(srcpaths, incpaths)
