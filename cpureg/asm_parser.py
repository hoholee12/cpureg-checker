import re

class CpuRegAsmParser():
    # scour through everywhere for VTOR(armv7m) or SCBP(rh850) insertion code
    # attempt to locate the vector table.
    # def parse_arch_vectors(self, ):



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
