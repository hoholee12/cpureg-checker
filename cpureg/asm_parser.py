import re
import os

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
