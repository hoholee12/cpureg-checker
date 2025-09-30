import sys
import os
import shutil
import concurrent.futures
import subprocess
import re
import argparse
import hashlib

class CpuRegParser:
    
    # workaround for case-insensitive filesystem
    def filename_hashgen(self, func: str) -> str:
        htemp = hashlib.sha1(func.encode("utf-8")).hexdigest()[:8]
        return func + "." + htemp + ".txt"

    def __init__(self):
        # args
        self.mw_workspace_dir = "cpureg_workspace"
        self.pf_workspace_dir = os.path.join(self.mw_workspace_dir, "parsed_gen")
        self.callstack_gen_dir = os.path.join(self.mw_workspace_dir, "callstack_gen")
        self.proc_funcbody_dir = os.path.join(self.mw_workspace_dir, "proc_funcbody")
        self.proc_funcbody_asm_dir = os.path.join(self.mw_workspace_dir, "proc_funcbody_asm")

        # asm extensions
        self.asm_ext = []

        # user args
        self.supported_platforms = ["armv7m", "rh850"]
        self.target_platform = ""

        # patterns for src comments
        self.comment_pattern_1 = re.compile(r'^\s*/\*')
        self.comment_pattern_2 = re.compile(r'\*/\s*$')
        self.comment_pattern_w = re.compile(r'/\*.*?\*/')
        self.comment_pattern_w2 = re.compile(r'(.*)/\*')

        self.not_in_line = re.compile(r'(\w+;|^extern|\s+while|\s+for|\s+if|\s+switch)')
        self.pre_func_pattern = re.compile(r'\)\s*{\s*')
        self.func_pattern = re.compile(r'\s*(\w+)\s*$')

        self.oneliner_func_pattern = re.compile(r'\)\s*{.*}\s*')
        self.stubinfo_pattern = re.compile(r'.*\\(\w+)\.')

        # patterns for asm comments
        self.asm_comment_pattern_1_start = re.compile(r"(.*?)/\*")
        self.asm_comment_pattern_1_end = re.compile(r"\*/(.*?)")
        self.asm_comment_pattern_2 = re.compile(r"(.*?)\s*(?:-|\/\/|;)")
        # if none of the above match, we have a clean line
        # /* hello:
        # --_hello:
        # //_hello:
        # ;_hello:
        # hello: -> matches
        # _hello: -> matches
        self.asm_func_pattern_1 = re.compile(r"^(\w+):")


        # pattern for push pop detection (make sure it covers the inline assembly as well)
        # no need to worry for succeeding comments (they are completely removed at this stage)
        self.asm_push_pattern = re.compile(r"^pushsp\s+(.*)")
        self.asm_pop_pattern = re.compile(r"^popsp\s+(.*)")


        # for rh850:
        # - pushsp, popsp -> the operands do not change order, so its very easy to map
        # - prepare, dispose:
        # -- prepare list(regs separated with comma), imm(number of words to reserve stack space)
        # -- dispose imm, list, (sometimes)[reg] (put r31(linkreg) on reg -> you get a pop & jmp back to caller)
        # -- no need to worry about [reg], all we need to focus is the <list, imm> <imm, list>
        # -- but we do need the info for [reg] for correct branch path.
        self.rh850_push_pattern = re.compile(r"^pushsp\s+(.*)|^prepare\s+(.*),\s*\w+")
        # we shall only capture the reg part for prepare-dispose
        self.rh850_pop_pattern = re.compile(r"^popsp\s+(.*)|^dispose\s+\w+,\s*(.*)")
        # TODO: we may need the dispose [reg] part for branch ident

        # for armv7m:
        # - push, pop -> probably not easy (user can become an asshole and change operands order but it is still valid)
        # -- will also need to be careful, user can do "push {reg, lr}, pop {reg, pc}" which is similar to "dispose imm, list, [reg]"
        # -- we will also need the info for {pc} for correct branch path.
        # - stmdb, ldmia -> advanced version of push, pop.
        # -- push {r4, lr} -> stmdb sp!, {r4, lr} (this means we can just treat stmdb sp! -> push)
        # -- pop {r4, pc} -> ldmia sp!, {r4, pc} (this means we can just treat ldmia sp! -> pop)
        # --- anything can be used besides sp! -> ignore because we will not give a fuck other than the stack.
        self.armv7m_push_pattern = re.compile(r"^push\s+{((?:(?!,\s*lr)[^}])*).*}")
        self.armv7m_pop_pattern = re.compile(r"^pop\s+{((?:(?!,\s*pc)[^}])*).*}")
        # we will just capture the whole thing without order. we will remove lr, pc in the process. 
        # (TODO: to be taken care of by branch ident)
        # we can care about the order thing later.(TODO: further parsing to individual regs maybe)

        self.asm_regname_intrinsics = {"sp": "r3", "lr": "r31"}
        self.rh850_regname_intrinsics = {"sp": "r3", "lr": "r31"}
        self.armv7m_regname_intrinsics = {"sp": "r13", "lr": "r14", "pc": "r15"}

        # we capture the branch op with the obj name. if obj name does not exist, we can find it in previous ops...
        self.asm_branch_pattern = re.compile(r"^jr\s+(\w+)|^jmp\s+(\w+)|^jarl\s+(\w+)|^b\w+\s+(\w+)")
        self.rh850_branch_pattern = re.compile(r"^jr\s+(\w+)|^jmp\s+(\w+)|^jarl\s+(\w+)|^b\w+\s+(\w+)")  # in rh850, theres no b ~ op
        self.armv7m_branch_pattern = re.compile(r"^b\w*\s+(\w+)")    # armv7m branch opnames always start with b
        # this is to identify object address that is being passed to previous ops(mov), or in the branch op.
        # we need to identify this to figure out if its actually branching into a new function or not.
        # any code block that has a object name(blah:~) is considered a separate function.
        self.asm_genericop_pattern = re.compile(r"^\s*\w+\s+(.*)")

        # remove preprocessed garbage texts
        # preprocess_garbage_pattern = re.compile(r"^# \d+ \"(?!.*\.h\").*")

        # capture global variables
        self.global_var_pattern = re.compile(r"(\w+)\s*(?=\[|\s*=|;).*")
        self.global_var_dontuse_pattern = re.compile(r"typedef\s*|enum\s*|struct\s*")
        self.global_var_use_pattern = re.compile(r"(\w+)") # pretty bad but it works for now
        self.global_var_use_asm_pattern = re.compile(r"^\s*\w+\s+(.*),")
        self.local_var_pattern = re.compile(r"\w+\s+(\w+)\s*(?=\[|\s*=|;).*")
        self.param_var_pattern = re.compile(r".*\s+(\w+)")

        self.listup = 0
        self.listup_set = set()
        self.bad_path_list = set()
        self.destructive_only = 0
        self.normality_count = 0 # doomed function if set 1

    def srcpath_isnotc(self, srcpath: str) -> bool:
        if not srcpath.endswith(".c") and not srcpath.endswith(".h"):
            return True
        return False

    # get caller flow
    def get_caller_flow(self, calling_path: str, func: str):
        if self.listup == 1:
            self.listup_set.add(func)

        file_to_open = os.path.join(self.callstack_gen_dir, self.filename_hashgen(func))
        try:
            with open(file_to_open, 'r', encoding="UTF-8") as f:
                lines = f.readlines()
                loc = len(lines)

                if loc > 0:
                    for i in range(0, loc):
                        next_calling_path = calling_path + "->" + func
                        # check for potential loop before continuing
                        loop_dict = {}
                        for item in next_calling_path.split("->"):
                            if loop_dict.get(item, None) is not None:
                                # dead end
                                self.bad_path_list.add(item)
                                if self.listup != 1:
                                    print("looping " + next_calling_path)
                                return
                            else:
                                loop_dict[item] = 1
                        # continue to the next round
                        next_func = lines[i].strip()
                        self.get_caller_flow(next_calling_path, next_func)

                else:
                    # dead end... finish here
                    if self.listup != 1:
                        bad_path_detected = 0
                        for item in (calling_path + "->" + func).split("->")[1:-1]:
                            if item in self.bad_path_list:
                                bad_path_detected = 1
                                break
                        if bad_path_detected == 0:
                            if self.destructive_only == 0:
                                print(calling_path + "->" + func)
                                self.normality_count += 1
                        else:
                            print("bad " + calling_path + "->" + func)
                    return
        except:
            if self.listup != 1:
                bad_path_detected = 0
                for item in (calling_path + "->" + func).split("->")[1:-1]:
                    if item in self.bad_path_list:
                        bad_path_detected = 1
                        break
                if bad_path_detected == 0:
                    if self.destructive_only == 0:
                        print(calling_path + "->" + func)
                        self.normality_count += 1
                else:
                    print("bad " + calling_path + "->" + func)
                print("incomplete gen")
            return

    # get callee flow
    def get_callee_flow(self, func: str):
        test_files = []
        # bring all the data back
        for root, dirs, files in os.walk(self.callstack_gen_dir):
            for file in files:
                if not file.startswith("globals.") and file.endswith(".txt"):   # dont read globals.xxx.txt
                    test_files.append(os.path.join(root, file))
        calling_func_gen = {}
        for file in test_files:
            with open(file, 'r', encoding="UTF-8") as f:
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

            if self.listup == 1:
                self.listup_set.add(called)

            found = 0
            for key in calling_func_gen.keys():
                # found a callee (key), now we append
                if called in calling_func_gen[key]:
                    next_calling_path = toprint + "<-" + called
                    # check for potential loop before continuing
                    loop_dict = {}
                    ok_to_cont = 0
                    for item in next_calling_path.split("<-"):
                        if loop_dict.get(item, None) is not None:
                            # dead end
                            self.bad_path_list.add(item)
                            ok_to_cont = 0
                            if self.listup != 1:
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
            if self.listup != 1:
                bad_path_detected = 0
                for item in (toprint + "<-" + called).split("<-")[1:-1]:
                    if item in self.bad_path_list:
                        bad_path_detected = 1
                        break
                if bad_path_detected == 0:
                    if self.destructive_only == 0:
                        print(toprint + "<-" + called)
                        self.normality_count += 1
                else:
                    print("bad " + toprint + "<-" + called)


    # genfile: generated src path
    # this will strip every comment and index every function from c sources
    # uses mw_workspace_dir to temporarily store the preprocessed files
    def parse_functions_c_persrc(self, srcpath: str, incpaths: list) -> tuple:
        # do macro preprocess first
        mw_gcc_arg = "gcc -E "
        mw_gcc_arg_inc = " -I "
        mw_srcpath = os.path.basename(srcpath)
        mw_srcpath_fnonly = mw_srcpath.split(".")[0]
        mw_srcpath_ext = mw_srcpath.split(".")[1]
        genfile = os.path.join(self.mw_workspace_dir, f"{mw_srcpath_fnonly}.generated.{mw_srcpath_ext}")
        # check and remove old file
        if os.path.exists(genfile) and os.path.isfile(genfile):
            os.remove(genfile)
        # generate args
        mw_gcc_arg += srcpath
        for i in incpaths:
            mw_gcc_arg += mw_gcc_arg_inc + i
        mw_gcc_arg += " -o " + genfile
        # run gcc
        subprocess.call(mw_gcc_arg, shell=True)

        # remove preprocessed info texts..
        with open(genfile, 'r', encoding="UTF-8") as f:
            lines = f.readlines()
            filtered = [line for line in lines if not line.startswith("#")]

        with open(genfile, 'w', encoding="UTF-8") as f:
            f.writelines(filtered)

        global_vars = set() # get the global variables
        src_funcs = {}
        func_unit_tracker_src = {}
        param_vars = {}

        with open(genfile, 'r', encoding="UTF-8") as f:
            lines = f.readlines()
            loc = len(lines)
            tmp_str = ""
            func_name = ""
            in_func = 0
            bstack = 0

            in_tfunc = 0
            in_typedef_struct = 0
            tstack = 0 # curly brackets
            typedef_struct_semicolon_reached = 0

            cstack = 0
            in_param = 0

            comment = 0 # inside comment
            starti = 0 # starting location of function

            for i in range(0, loc):
                # inside a macro comment
                if re.compile(r'^#.*').search(lines[i]):
                    continue

                # inside a comment - do not process
                if self.comment_pattern_1.search(lines[i]):
                    comment = 2

                # end of line comment
                if comment == 2 and self.comment_pattern_2.search(lines[i]):
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

                # --- start of global var parsing ---
                # simple typedef struct blocking
                if in_func == 0 and self.global_var_dontuse_pattern.search(lines[i]):
                    in_typedef_struct = 1
                elif in_func == 0 and in_typedef_struct == 1 and in_tfunc == 0 and typedef_struct_semicolon_reached == 1:
                    in_typedef_struct = 0
                    typedef_struct_semicolon_reached = 0

                # check whether we are in param
                if "(" in lines[i]:
                    if cstack == 0:
                        in_param = 1
                    cstack += 1
                if ")" in lines[i]:
                    cstack -= 1
                    if cstack <= 0:
                        in_param = 2 # we skip one line
                        cstack = 0

                # if we are not in a function, we can start capturing the global variables
                if in_tfunc == 0 and in_param == 0 and in_typedef_struct == 0 and self.global_var_pattern.search(lines[i]):
                    # capture the global variable
                    varname = self.global_var_pattern.search(lines[i]).group(1)
                    if not varname.isdigit():   # hackfix
                        global_vars.add(varname)

                # delay one line for param check
                if in_param == 2:
                    in_param = 0

                if "{" in lines[i]:
                    if tstack == 0:
                        in_tfunc = 1
                    tstack += 1
                if "}" in lines[i]:
                    tstack -= 1
                    if tstack <= 0:
                        in_tfunc = 0
                        tstack = 0

                # check if we reached semicolon in typedef struct
                if in_func == 0 and in_typedef_struct == 1 and tstack == 0 and ';' in lines[i]:
                    typedef_struct_semicolon_reached = 1
                # --- end of global var parsing ---

                # capture all lines preceding possible start of function - don't include extern/while/for/if/switch
                if in_func == 0 and not self.not_in_line.search(lines[i]):
                    tmp_str += lines[i].replace('\n', ' ')
                
                # reset capture if badness found
                if in_func == 0 and self.not_in_line.search(lines[i]):
                    tmp_str = ""

                # found start of function - reverse travel index with captured lines and find function name
                if in_func == 0 and '{' in lines[i]:
                    tmp_str += lines[i].replace('\n', ' ')
                    rline = tmp_str
                    if not self.pre_func_pattern.search(tmp_str):
                        tmp_str = ""
                        continue
                    tloc = len(tmp_str)
                    in_brackets = 0
                    once_set = 0
                    tmp_str_copy = ""
                    param_str = ""
                    for t in range(tloc, 0, -1):
                        if tmp_str[t - 1] == ")":
                            in_brackets += 1
                            once_set = 1
                        elif tmp_str[t - 1] == "(":
                            in_brackets -= 1
                        elif in_brackets == 0 and once_set == 1:
                            tmp_str_copy = tmp_str[0:t]
                            break
                        elif in_brackets != 0:
                            param_str = tmp_str[t - 1] + param_str

                    if self.func_pattern.search(tmp_str_copy):
                        func_name = self.func_pattern.search(tmp_str_copy).group(1)
                        param_vars[func_name] = param_str.strip()
                        starti = i  # record starting location for func_name
                    else:
                        tmp_str = ""
                        continue

                    # one liner function might eist, like this:
                    # void func (int asdf) {}
                    if self.oneliner_func_pattern.search(tmp_str):
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
                    if self.comment_pattern_w2.search(lines[i]):
                        rline = self.comment_pattern_w2.search(lines[i]).group(1) + "\n"
                    else:
                        rline = lines[i]

                    if src_funcs.get(func_name, None) != None:
                        src_funcs[func_name] += rline
                    else:
                        # very first insert, we parse it out so that it doesnt include the func head ever.
                        src_funcs[func_name] = re.compile(r".*?({.*)").search(rline).group(1) + "\n"

                    if in_func == 1:
                        # strip comments
                        src_funcs[func_name] = self.comment_pattern_w.sub('', src_funcs[func_name]).strip()
                        # another set to keep track of which file the function is located in
                        func_unit_tracker_src[func_name] = [starti, i, mw_srcpath]
                        in_func = 0
                        func_name = ""

        print(os.path.basename(genfile) + " number of funcs found: " + str(len(src_funcs)))
        return src_funcs, func_unit_tracker_src, global_vars, param_vars

    def parse_functions_c_write(self, srcpaths: list, incpaths: list) -> tuple:
        global_vars = set()  # global variables
        src_funcs = {}
        func_unit_tracker_src = {}  # this is just for grouping function set for each source file. nothing fancy
        param_vars = {}
        max_workers = int(os.cpu_count() / 4)

        # src_funcs should go in the pre_c
        with concurrent.futures.ThreadPoolExecutor(max_workers = max_workers) as executor:
            futures = [executor.submit(self.parse_functions_c_persrc, srcpath, incpaths) for srcpath in srcpaths]
            for future in concurrent.futures.as_completed(futures):
                results = future.result()
                # merge dicts
                for xfunc in results[0].keys():
                    if src_funcs.get(xfunc, None) == None:
                        src_funcs[xfunc] = results[0][xfunc]
                        func_unit_tracker_src[xfunc] = results[1][xfunc]
                    elif len(results[0][xfunc]) > len(src_funcs[xfunc]):
                        # if the function is longer, we replace it
                        src_funcs[xfunc] = results[0][xfunc]
                        func_unit_tracker_src[xfunc] = results[1][xfunc]
                global_vars.update(results[2])
                param_vars.update(results[3])

        # tidy up
        # anything that is in function tracker but not in the body capture, is probably a one liner empty function
        # we shall include it in the src_funcs too
        for trackerkey in func_unit_tracker_src.keys():
            if trackerkey not in src_funcs:
                src_funcs[trackerkey] = "{}"

        # test inline asm
        for src_func in src_funcs.values():
            inlineasmfuncs = self.parse_functions_c_inlineasm_to_asm(src_func)
            for inlineasm in inlineasmfuncs:
                print("processed inline funcs:\n" + inlineasm)

        return src_funcs, func_unit_tracker_src, global_vars, param_vars

    # returns sorted list of strings of registers
    # takes care of , and -
    def parse_functions_asm_individual_reg(self, regs: str) -> list:
        reglist_ = regs.replace(" ", "").split(",")
        reglist = set()
        for reg_ in reglist_:
            reg = reg_.lower().strip()
            if "-" in reg:
                regprefix = re.compile(r"([a-z]+) ").search(reg).group(1)  # opcode
                regget = re.compile(r"[a-z]+([0-9]+)-[a-z]+([0-9]+)").search(reg)   # operands rx-ry
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
    def parse_functions_asm_persrc(self, srcpath: str, incpaths: list) -> tuple:
        # we generate the c files first
        mw_srcpath = os.path.basename(srcpath)
        mw_srcpath_fnonly = mw_srcpath.split(".")[0]
        mw_srcpath_ext = mw_srcpath.split(".")[1]
        lines = []
        with open(srcpath, 'r') as f:
            lines = f.readlines()
        new_srcpath = os.path.join(self.mw_workspace_dir, f"{mw_srcpath_fnonly}.pregen.c") 
        
        # sanitize before pushing into compiler
        with open(new_srcpath, 'w') as f:
            for i in lines:
                parsedi = i
                if (parsedi.strip().startswith(".if") or parsedi.strip().startswith(".elif") or 
                    parsedi.strip().startswith(".else") or parsedi.strip().startswith(".endif")):
                    parsedi = parsedi.replace(".", "#")   
                    # there is no other place that the . could be other than in the beginning, so this should be fine
                # get rid of the comments
                if self.asm_comment_pattern_2.search(parsedi):
                    parsedi = self.asm_comment_pattern_2.search(parsedi).group(1) + "\n"
                f.write(parsedi)

        # and then do some macro preprocessing
        mw_gcc_arg = "gcc -E "
        mw_gcc_arg_inc = " -I "
        
        genfile = os.path.join(self.mw_workspace_dir, f"{mw_srcpath_fnonly}.generated.{mw_srcpath_ext}")
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
        
        # remove preprocessed info texts..
        with open(genfile, 'r', encoding = "UTF-8") as f:
            lines = f.readlines()
            filtered = [line for line in lines if not line.startswith("#")]

        with open(genfile, 'w', encoding = "UTF-8") as f:
            f.writelines(filtered)

        # file have been preprocessed. now we start parsing
        in_comment = 0  # 1 if inside comment
        sanitizedlines = []

        # sanitize lines from comments first
        with open(genfile, 'r') as f:
            lines = f.readlines()
            loc = len(lines)
            for i in range(0, loc):
                line = lines[i]
                # skip if line begins with a dot or a sharp (., #)
                if line.strip().startswith(".") or line.strip().startswith("#"):
                    continue
                # trim start-end comments first
                if self.asm_comment_pattern_1_start.search(line):
                    line = self.asm_comment_pattern_1_start.search(line).group(1)    # trim comment
                    in_comment = 1
                elif in_comment != 0 and self.asm_comment_pattern_1_end.search(line):
                    line = self.asm_comment_pattern_1_end.search(line).group(1)
                    in_comment = 0
                elif in_comment == 0:
                    # trim other comments if available
                    if self.asm_comment_pattern_2.search(line):
                        line = self.asm_comment_pattern_2.search(line).group(1)
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
            if self.asm_func_pattern_1.search(sanitizedline):
                pre_func_names.add(self.asm_func_pattern_1.search(sanitizedline).group(1))
        # and thats it...
        
        # parse functions: k:func_name - v:body
        asm_funcs = {}
        func_unit_tracker_asm = {}
        func_name = ""
        in_func = 0 # once it is 1, it will never be 0 again until EOF
        starti = 0 # starting location of function
        for i in range(0, sanitizedloc):
            sanitizedline = sanitizedlines[i]
            if self.asm_func_pattern_1.search(sanitizedline):    # will run regardless of in_func.
                func_name = self.asm_func_pattern_1.search(sanitizedline).group(1).lstrip("_")    # lets strip the starting '_'
                # if funcname was not encountered before, init
                if asm_funcs.get(func_name, None) == None:
                    asm_funcs[func_name] = ""
                in_func = 1
                starti = i
            elif in_func == 1:  # will always run, once in_func changed to 1 & is not on a function name
                # capture func body
                asm_funcs[func_name] += sanitizedline
                # another set to keep track of which file the function is located in
                # (will run several times atm, TODO: make it run only once)
                func_unit_tracker_asm[func_name] = [starti, i, mw_srcpath]

        print(os.path.basename(genfile) + " number of funcs found: " + str(len(asm_funcs)))
        return asm_funcs, func_unit_tracker_asm
            

    def parse_functions_asm_write(self, srcpaths: list, incpaths: list) -> tuple:
        asm_funcs = {}
        func_unit_tracker_asm = {}  # this is just for grouping function set for each source file. nothing fancy
        max_workers = int(os.cpu_count() / 4)

        # asm_funcs should go in the pre_asm
        with concurrent.futures.ThreadPoolExecutor(max_workers = max_workers) as executor:
            futures = [executor.submit(self.parse_functions_asm_persrc, srcpath, incpaths) for srcpath in srcpaths]
            for future in concurrent.futures.as_completed(futures):
                results = future.result()
                # merge dicts
                asm_funcs.update(results[0])
                func_unit_tracker_asm.update(results[1])

        # tidy up
        # anything that is in function tracker but not in the body capture, is probably a one liner empty function
        # we shall include it in the asm_funcs too
        for trackerkey in func_unit_tracker_asm.keys():
            if trackerkey not in asm_funcs:
                asm_funcs[trackerkey] = "{}"

        # test
        for asm_func in asm_funcs.values():
            tmp_funcs = self.parse_functions_asm_breakdown_branches(asm_func)
            for mstr in tmp_funcs:
                print("\nbreakdown:\n" + mstr)

            print("\nreassemble:\n" + self.parse_functions_asm_reassemble_branches(asm_func, tmp_funcs))

        return asm_funcs, func_unit_tracker_asm

    # TODO: process both asm and c src for callstack
    def parse_functions_process_callstack(self, funcs: list, func_unit_tracker: list, global_vars: set, param_vars: dict):
        # generate call stack estimation
        callstack_gen = {}
        # get them init first (so we can create files even if empty)
        for key in funcs.keys():
            callstack_gen[key] = set()
        funcs_v = funcs.copy()
        for func in funcs.keys():
            code = funcs[func].splitlines()
            # before we continue, we need to make sure we dont include the header of the function
            # otherwise we get a callstack that calls itself (which is wrong)

            # c and asm to share parse code
            # if os.path.basename(func_unit_tracker[func]).split(".")[1] in asm_ext:
            for cline in code:
                # split the line into tokens and skip any possible empty lines
                # (if possible) we strip the first underscore from the function name due to asm
                # regex: [^] means "not", so we split by anything that is not a-z, A-Z, 0-9, or _
                cc = [x.lstrip("_") for x in re.split(r'[^a-zA-Z0-9_]+', cline) if x.strip() != ""]
                for key in funcs_v.keys():
                    if key in cc:
                        callstack_gen[func].add(key)

        # save lists of all callstacks
        for func in callstack_gen.keys():
            new_file = os.path.join(self.callstack_gen_dir, self.filename_hashgen(func))
            with open(new_file, 'w') as wf:
                for calling in callstack_gen[func]:
                    wf.write(calling + "\n")

        # save global variable list used by functions
        # we will check again for local vars and subtract them from detected global vars (only for c files)
        for func in callstack_gen.keys():
            new_file = os.path.join(self.callstack_gen_dir, "globals." + self.filename_hashgen(func))
            if self.srcpath_isnotc(func_unit_tracker[func][2]):
                with open(new_file, 'w') as wf:
                    findvar = set()
                    # we split the lines
                    lines = funcs[func].splitlines()
                    varmatches = []
                    for line in lines:
                        if self.global_var_use_asm_pattern.search(line):
                            varmatches.append(self.global_var_use_asm_pattern.search(line).group(1))
                    for varmatch in varmatches:
                        for gvar in global_vars:
                            if gvar in varmatch:
                                findvar.add(gvar)
                    for gvar in findvar:
                        wf.write(gvar + "\n")
            else: # c file
                # get local vars
                local_vars = set()
                for line in funcs[func].splitlines():
                    if self.local_var_pattern.search(line) and not line.strip().startswith("return"):
                        local_vars.add(self.local_var_pattern.search(line).group(1))

                # get local vars from param_vars
                if param_vars.get(func, None) != None:
                    param_vars_list = param_vars[func].split(",")
                    for pvar in param_vars_list:
                        if self.param_var_pattern.search(pvar):
                            local_vars.add(self.param_var_pattern.search(pvar).group(1))

                with open(new_file, 'w') as wf:
                    findvar = set()
                    for line in funcs[func].splitlines():
                        matches = self.global_var_use_pattern.findall(line)
                        for gvar in matches:
                            if gvar in global_vars:
                                findvar.add(gvar)
                    findvar -= local_vars # subtract local vars from global vars
                    for gvar in findvar:
                        wf.write(gvar + "\n")

        # save processed function bodies
        for func in funcs.keys():
            new_file = os.path.join(self.proc_funcbody_dir, func_unit_tracker[func][2] + "." + self.filename_hashgen(func))
            with open(new_file, 'w') as wf:
                wf.write(funcs[func])

    # now we will start parsing for all the functions (c and asm alike)
    def parse_functions(self, srcpaths: list, incpaths: list):
        srcpaths_c = []
        srcpaths_asm = []

        funcs = {}
        func_unit_tracker = {}
        funcs_v = {}
        func_unit_tracker_v = {}
        global_vars = set()
        param_vars = {}

        for srcpath in srcpaths:
            if srcpath.split(".")[-1] in self.asm_ext:   # asm file
                srcpaths_asm.append(srcpath)
            else:   # c file
                srcpaths_c.append(srcpath)

        funcs, func_unit_tracker, global_vars, param_vars = self.parse_functions_c_write(srcpaths_c, incpaths)   
        # generate all c files and their func bodies & callstack
        funcs_v, func_unit_tracker_v = self.parse_functions_asm_write(srcpaths_asm, incpaths)   
        # generate all asm func bodies & callstack
        funcs.update(funcs_v)
        func_unit_tracker.update(func_unit_tracker_v)

        # if the codebase is not compilable, some funcs may not have an entry in func_unit_tracker
        # lets fix that
        for func in funcs.keys():
            if func_unit_tracker.get(func, None) == None:
                func_unit_tracker[func] = [0, 0, "unknown.c"]

        self.parse_functions_process_callstack(funcs, func_unit_tracker, global_vars, param_vars) # generate callstack and write to file.

        # TODO: test
        with open("global_vars.txt", 'w') as wf:
            for gvar in global_vars:
                wf.write(gvar + "\n")

    # srcpaths: should return list of source files
    def parse_per_target_platform(self, target_platform: str, incpaths: list) -> set:
        # get extension
        if target_platform not in self.supported_platforms:
            print(target_platform + " not supported")
            sys.exit(1)
        elif target_platform == "rh850":
            # asm extension
            self.asm_ext.append("850")
            # asm push/pop pattern
            self.asm_push_pattern = self.rh850_push_pattern
            self.asm_pop_pattern = self.rh850_pop_pattern
            self.asm_regname_intrinsics = self.rh850_regname_intrinsics
            self.asm_branch_pattern = self.rh850_branch_pattern
        elif target_platform == "armv7m":
            # asm extension
            self.asm_ext.append("s")
            self.asm_ext.append("S")
            # asm push/pop pattern
            self.asm_push_pattern = self.armv7m_push_pattern
            self.asm_pop_pattern = self.armv7m_pop_pattern
            self.asm_regname_intrinsics = self.armv7m_regname_intrinsics
            self.asm_branch_pattern = self.armv7m_branch_pattern

        # get source files
        srcpaths = set()
        for incpath_ in incpaths:
            incpath = incpath_.replace("/", os.path.sep)
            for dirpath, dirnames, filenames in os.walk(incpath):
                for filename in filenames:
                    if filename.endswith(".c") or filename.endswith(".C") or filename.split(".")[-1] in self.asm_ext:
                        srcpaths.add(dirpath + os.path.sep + filename)
        
        return srcpaths

    # we need to parse inlineasm too.
    # returns list of inline asm strings (one string per block)
    def parse_functions_c_inlineasm_to_asm(self, c_func: str) -> list:
        inlineblocks = []
        tmplines = c_func.split('\n')
        lines = [tmpline + '\n' for tmpline in tmplines]
        loc = len(lines)
        insideinlineasm = 0
        inblock = 0
        tmpstr = ""
        for i in range(0, loc):
            if re.compile(r"__asm").search(lines[i]):
                insideinlineasm = 1
            if insideinlineasm == 1 and "(" in lines[i]:
                inblock = 1  # i do not expect any nested brackets in a inlineasm
            if insideinlineasm == 1 and ")" in lines[i]:
                inblock = 2
            if inblock == 2:
                tmpstr += lines[i]
                insideinlineasm = 0
                inblock = 0
                # process shit here and move on to the next inlineasm
                parsedlines_v = re.compile(r"\"(.*?)\"").findall(tmpstr)
                parsedlines = [re.compile(r"^(.*?)\s*(?=\\|$)").search(line).group(1).strip() for line in parsedlines_v]
                parsedtostr = "\n".join(parsedlines)
                inlineblocks.append(parsedtostr)
                tmpstr = ""
            elif inblock == 1:
                # double quote is always expected for strings in c syntax
                tmpstr += lines[i]

        return inlineblocks

    # asm_func is a giant string with newlines as linebreak
    # this returns list of funcs broken down by branch ops
    # i dont intend to save this anywhere
    def parse_functions_asm_breakdown_branches(self, asm_func: str) -> list:
        breakdownlist = []
        # asm_func.splitlines(keepends = True)
        tmplines = asm_func.split('\n') # split the giant string
        lines = [tmpline + '\n' for tmpline in tmplines]    # add the newline back in
        loc = len(lines)
        tmpstr = ""
        for i in range(0, loc):
            if self.asm_branch_pattern.search(lines[i].lower()):
                breakdownlist.append(tmpstr)
                tmpstr = ""
                continue
            else:
                tmpstr += lines[i]
        if tmpstr != "":
            breakdownlist.append(tmpstr)
        return breakdownlist

    # TODO: make a reassembler
    # logic:
    # 1. old lines[0] -> new lines[0]
    # 2. old branch
    # 3. old lines[1] -> new lines[1]
    def parse_functions_asm_reassemble_branches(self, old_asm_func: str, breakdownlist: list) -> str:
        new_asm_func = ""
        # asm_func.splitlines(keepends = True)
        tmplines = old_asm_func.split('\n') # split the giant string
        lines = [tmpline + '\n' for tmpline in tmplines]    # add the newline back in
        loc = len(lines)
        new_asm_func = ""
        locswitch = 0
        breakdownindex = 0
        for i in range(0, loc):
            if self.asm_branch_pattern.search(lines[i].lower()):
                new_asm_func += lines[i]
                locswitch = 0
                breakdownindex += 1
            elif locswitch == 0:
                new_asm_func += breakdownlist[breakdownindex]
                locswitch = 1
        
        return new_asm_func

    def parse_workspace_cleanup(self):
        # delete whole workspace directory
        if os.path.exists(self.mw_workspace_dir) and os.path.isdir(self.mw_workspace_dir):
            shutil.rmtree(self.mw_workspace_dir)
        os.makedirs(self.mw_workspace_dir, exist_ok = True)
        os.makedirs(self.pf_workspace_dir, exist_ok = True)
        os.makedirs(self.callstack_gen_dir, exist_ok = True)
        os.makedirs(self.proc_funcbody_dir, exist_ok = True)
        os.makedirs(self.proc_funcbody_asm_dir, exist_ok = True)

class CpuRegApp:
    def __init__(self):
        self.parser = CpuRegParser()

    def check_gcc(self):
        try:
            subprocess.run(["gcc", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        except subprocess.CalledProcessError:
            print("GCC is not installed or not found in PATH.")
            sys.exit(1)
        except FileNotFoundError:
            print("GCC is not installed or not found in PATH.")
            sys.exit(1)

    def main(self):
        self.check_gcc()

        arg_parser = argparse.ArgumentParser()
        group = arg_parser.add_mutually_exclusive_group()
        group.add_argument("-g", "--generate", type=str, choices=self.parser.supported_platforms,
                           help="generate preprocessed functions & callstacks")
        group.add_argument("-p", "--process", action="store_true", help="process and spit out rights & wrongs on your code")

        arg_parser.add_argument("-I", "--include", action="append", metavar="INCLUDE_PATH", type=str, help="include path for the generate option")

        group.add_argument("-c", "--caller", type=str, help="print caller stack of function (test)")
        group.add_argument("-C", "--callee", type=str, help="print caller stack before reaching function (test)")
        arg_parser.add_argument("-s", "--sourceview", action="store_true", help="launch the source viewer GUI")

        args = arg_parser.parse_args()
        target_platform = args.generate
        incpaths = args.include or []

        if target_platform:
            if len(incpaths) == 0:
                arg_parser.error("generate requires at least one include path")

            srcpaths = self.parser.parse_per_target_platform(target_platform, incpaths)
            self.parser.parse_workspace_cleanup()
            self.parser.parse_functions(srcpaths, incpaths)

        elif args.process:
            pass

        elif args.caller:
            self.parser.get_caller_flow("", args.caller)
            pass
        elif args.callee:
            self.parser.get_callee_flow(args.callee)
            pass

        elif args.sourceview:
            from cpureg.source_viewer import SourceViewer
            from PySide6.QtWidgets import QApplication

            app = QApplication()
            viewer = SourceViewer()
            viewer.show()
            sys.exit(app.exec_())

        else:
            arg_parser.print_help()
            sys.exit(1)

if __name__ == "__main__":
    CpuRegApp().main()
