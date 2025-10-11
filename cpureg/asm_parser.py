import re
import os

# CpuRegAsmEngine
# this class provides register tracking (which gpr, sysregs, etc has it touched, 
# push/pop pair counter & order per register, etc..) per given function.
#
# CpuRegAsmEngine().register_component(funcname: str, funcbody: str)
# 1. if function is a c function, funcbody is a inline assembly 
# (processed from outside using CpuRegAsmParser().parse_functions_c_inlineasm_to_asm)
# 2. if function is a asm function, funcbody is an assembly code
# 3. this is saved onto regcomp[funcname] = {funcbody, {}} 
# (the dictionary inside -> register as key, push/pop count as value)
# (push r4 makes it +1, pop r4 makes it -1; if push/pop exists for that register, it is marked 0.)
# (if its not 0, then that register must be popped somewhere else, and is to be tracked further.)
# (dictionary is to be iterated)
#
# CpuRegAsmEngine().generate_regmap() -> {}
# 1. iterate regcomp dictionary
# 2. per funcbody, iterate every lines, if regcomp[funcname][1][reg] is None, regcomp[funcname][1][reg] = 0
# 3. if push or pop hit, get list of registers affected; iterate regcomp[funcname][1][reg]
#    if push, ++; if pop, --.
# 4. return regcomp dictionary

class CpuRegAsmEngine:
    def __init__(self, arch="armv7m"):
        # regcomp[funcname] = (funcbody, {reg: push/pop count})
        self.regcomp = {}
        self.arch = arch
        # define push/pop regex lists per architecture
        self.arch_patterns = {
            "armv7m": {
                "push": [
                    re.compile(r"\s*push\s*\{([^\}]*)\}"),
                    re.compile(r"\s*stm\w*\s+\w+\s*,\s*\{([^\}]*)\}")
                ],
                "pop": [
                    re.compile(r"\s*pop\s*\{([^\}]*)\}"),
                    re.compile(r"\s*ldm\w*\s+\w+\s*,\s*\{([^\}]*)\}")
                ]
            },
            "rh850": {
                "push": [
                    re.compile(r"\s*pushsp\s+([r\d\-\, ]+)"),
                    re.compile(r"\s*prepare\s+([r\d\-\, ]+),\s*\w+")
                ],
                "pop": [
                    re.compile(r"\s*popsp\s+([r\d\-\, ]+)"),
                    re.compile(r"\s*dispose\s+\w+,\s*([r\d\-\, ]+)")
                ]
            }
        }

    def register_component(self, funcname: str, funcbody: str):
        # initialize register tracking dictionary for this function
        reg_dict = {}
        self.regcomp[funcname] = (funcbody, reg_dict)

    def _parse_registers(self, reg_str, arch):
        # for armv7m: "r4, r5, r6"
        # for rh850: "r4-r6, r10"
        regs = []
        reg_str = reg_str.replace(" ", "")
        if arch == "armv7m":
            regs = [r for r in reg_str.split(",") if r]
        elif arch == "rh850":
            for part in reg_str.split(","):
                if "-" in part:
                    start, end = part.split("-")
                    if start.startswith("r") and end.startswith("r"):
                        for i in range(int(start[1:]), int(end[1:]) + 1):
                            regs.append("r" + str(i))
                elif part:
                    regs.append(part)
        else:
            regs = [r for r in reg_str.split(",") if r]
        return regs

    def generate_regmap(self):
        # iterate regcomp dictionary and count push/pop per register
        patterns = self.arch_patterns.get(self.arch, self.arch_patterns["armv7m"])
        push_patterns = patterns["push"]
        pop_patterns = patterns["pop"]

        for funcname in self.regcomp:
            funcbody, reg_dict = self.regcomp[funcname]
            lines = funcbody.splitlines()
            for line in lines:
                # check push patterns
                for push_re in push_patterns:
                    push_search = push_re.search(line)
                    if push_search:
                        regs = self._parse_registers(push_search.group(1), self.arch)
                        for reg in regs:
                            if reg not in reg_dict:
                                reg_dict[reg] = 0
                            reg_dict[reg] += 1
                # check pop patterns
                for pop_re in pop_patterns:
                    pop_search = pop_re.search(line)
                    if pop_search:
                        regs = self._parse_registers(pop_search.group(1), self.arch)
                        for reg in regs:
                            if reg not in reg_dict:
                                reg_dict[reg] = 0
                            reg_dict[reg] -= 1
        return self.regcomp


# swiss army knife class
class CpuRegAsmParser():
    # scour through everywhere for VTOR(armv7m) or SCBP(rh850) insertion code
    # attempt to locate the vector table.
    def parse_arch_vectors(self, search_loc: str, arch: str) -> str:
        # Returns the name of the vector table assigned to VTOR (armv7m) or SCBP (rh850)
        genfiles = []
        for root, dirs, files in os.walk(search_loc):
            for file in files:
                if ".generated." in file:
                    genfiles.append(os.path.join(root, file))

        reg_name = ""
        if arch == "armv7m":
            reg_name = "VTOR"
        elif arch == "rh850":
            reg_name = "SCBP"
        else:
            print("Unknown architecture: " + arch)
            return ""

        # Case-insensitive pattern for direct assignment
        assign_pattern = re.compile(r"\b" + reg_name + r"\s*=\s*([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
        # Pattern for GPR assignment (e.g. r0 = VectorTableName)
        gpr_assign_pattern = re.compile(r"\b(r\d+)\s*=\s*([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
        # Pattern for system register assignment from GPR (e.g. VTOR = r0)
        sysreg_from_gpr_pattern = re.compile(r"\b" + reg_name + r"\s*=\s*(r\d+)", re.IGNORECASE)

        for file in genfiles:
            try:
                with open(file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    # First, check for direct assignment
                    for line in lines:
                        m = assign_pattern.search(line)
                        if m:
                            vector_table = m.group(1)
                            print("Found direct assignment in " + file + ": " + reg_name + " = " + vector_table)
                            return vector_table
                    # Next, check for indirect assignment via GPR
                    gpr_map = {}
                    for i, line in enumerate(lines):
                        gpr_match = gpr_assign_pattern.search(line)
                        if gpr_match:
                            gpr = gpr_match.group(1)
                            value = gpr_match.group(2)
                            gpr_map[gpr] = value
                        sysreg_match = sysreg_from_gpr_pattern.search(line)
                        if sysreg_match:
                            gpr = sysreg_match.group(1)
                            # Look back for the last assignment to this GPR
                            if gpr in gpr_map:
                                vector_table = gpr_map[gpr]
                                print("Found indirect assignment in " + file + ": " + reg_name + " = " + gpr + " = " + vector_table)
                                return vector_table
            except Exception as e:
                print("Error reading " + file + ": " + str(e))
        return ""
    
    # inlineasm inside c func parser
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
    def parse_functions_asm_breakdown_branches(self, asm_func: str, asm_branch_pattern: re.Pattern) -> list:
        breakdownlist = []
        # asm_func.splitlines(keepends = True)
        tmplines = asm_func.split('\n') # split the giant string
        lines = [tmpline + '\n' for tmpline in tmplines]    # add the newline back in
        loc = len(lines)
        tmpstr = ""
        for i in range(0, loc):
            if asm_branch_pattern.search(lines[i].lower()):
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
    def parse_functions_asm_reassemble_branches(self, old_asm_func: str, breakdownlist: list, asm_branch_pattern: re.Pattern) -> str:
        new_asm_func = ""
        # asm_func.splitlines(keepends = True)
        tmplines = old_asm_func.split('\n') # split the giant string
        lines = [tmpline + '\n' for tmpline in tmplines]    # add the newline back in
        loc = len(lines)
        new_asm_func = ""
        locswitch = 0
        breakdownindex = 0
        for i in range(0, loc):
            if asm_branch_pattern.search(lines[i].lower()):
                new_asm_func += lines[i]
                locswitch = 0
                breakdownindex += 1
            elif locswitch == 0:
                new_asm_func += breakdownlist[breakdownindex]
                locswitch = 1
        
        return new_asm_func
