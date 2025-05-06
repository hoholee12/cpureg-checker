import re

# ================================================
# RAW‑Only Out‑of‑Order Scheduler (no NOPs)
# • Supports ARMv7‑M (can be extended to other ISAs)
# • Preserves labels and branches as block boundaries
# • Performs latency‑aware reordering to satisfy RAW
# ================================================

# 1) Regular expressions for parsing
REGEX_REGISTER = re.compile(r"[A-Za-z]{1,2}\d+")  # matches R1, X2, $0, etc.
REGEX_SPLIT    = re.compile(r"[ ,()]+")           # splits opcode and operands
REGEX_LABEL    = re.compile(r"^\w+:$")            # matches lines like "loop:"

# 2) ISA configuration (example: ARMv7‑M)
#    Only RAW hazards are considered; WAW/WAR are ignored.
ISA_DB = {
    'armv7m': {
        'instrs': {
            'MOV': {'read':[1],    'write':[0], 'latency':1},  # MOV Rd, Rn
            'ADD': {'read':[1,2],  'write':[0], 'latency':1},  # ADD Rd, Rn, Rm
            'SUB': {'read':[1,2],  'write':[0], 'latency':1},  # SUB Rd, Rn, Rm
            'MUL': {'read':[1,2],  'write':[0], 'latency':3},  # MUL Rd, Rn, Rm
            'LDR': {'read':[1],    'write':[0], 'latency':2},  # LDR Rt, [Rn]
            'STR': {'read':[0,1],  'write':[],  'latency':2},  # STR Rt, [Rn]
            'B':   {'read':[],     'write':[],  'latency':1},  # B label
        },
        'nop': None  # no-op placeholder is unused
    }
}

# 3) Branch opcodes define block boundaries
BRANCH_OPS = {
    'armv7m': {'B'}
}

# --------------------------------
# Extract all register names from an operand string
def extract_registers(operand):
    return REGEX_REGISTER.findall(operand.upper())

# --------------------------------
# Parse one line of assembly into a metadata dict:
#  • Returns LABEL entries for lines ending with “:”
#  • Returns None for blank/comment/unsupported
def parse_instr(line, index, isa):
    text = line.strip()
    if not text or text.startswith(';'):
        return None
    # label
    if REGEX_LABEL.match(text):
        return {'id':index, 'opc':'LABEL', 'text':text}
    # split opcode+operands
    parts = REGEX_SPLIT.split(text)
    opc   = parts[0].upper()
    if opc not in ISA_DB[isa]['instrs']:
        return None
    data = ISA_DB[isa]['instrs'][opc]
    reads, writes = [], []
    # collect read regs
    for i in data['read']:
        if i+1 < len(parts):
            reads += extract_registers(parts[i+1])
    # collect write regs
    for i in data['write']:
        if i+1 < len(parts):
            writes += extract_registers(parts[i+1])
    return {
        'id': index,
        'opc': opc,
        'read': set(reads),
        'write': set(writes),
        'latency': data['latency'],
        'text': text
    }

# --------------------------------
# Split the parsed stream into basic blocks:
#  • New block at each label
#  • End block at each branch opcode
def split_blocks(parsed, isa):
    blocks = []
    current = []
    for instr in parsed:
        # preserve blank/comments
        if instr is None:
            current.append(instr)
            continue
        # label starts a new block
        if instr['opc'] == 'LABEL':
            if current:
                blocks.append(current)
            current = [instr]
            continue
        # otherwise add instruction
        current.append(instr)
        # if it's a branch, close out this block
        if instr['opc'] in BRANCH_OPS[isa]:
            blocks.append(current)
            current = []
    # append any trailing block
    if current:
        blocks.append(current)
    return blocks

# --------------------------------
# Detect RAW hazards (purely for reporting or verification)
# Returns list of tuples (i, j, register) meaning:
#  instr i writes 'register', instr j reads it later.
def detect_raw(parsed):
    hazards = []
    for i in range(len(parsed)):
        a = parsed[i]
        if not a or a['opc']=='LABEL': 
            continue
        for j in range(i+1, len(parsed)):
            b = parsed[j]
            if not b or b['opc']=='LABEL':
                continue
            # true RAW: write-then-read
            for r in a['write'] & b['read']:
                hazards.append((i, j, r))
    return hazards

# --------------------------------
# Schedule one basic block *without* inserting NOPs:
#  • Emits labels immediately
#  • Reorders only non-branch insts to satisfy RAW readiness
#  • Appends branch(s) at the end in original order
def schedule_block(block, isa):
    cycle = 0
    ready = {}   # map register -> cycle when it becomes ready
    scheduled = []

    # Separate labels / non-branches / branches
    non_branch = []
    branch_ins = []
    for instr in block:
        if instr is None:
            # preserve blank/comment
            scheduled.append(None)
        elif instr['opc']=='LABEL':
            scheduled.append(instr['text'])
        elif instr['opc'] in BRANCH_OPS[isa]:
            branch_ins.append(instr)
        else:
            non_branch.append(instr)

    # Aggressively issue instructions as soon as RAW is satisfied
    while non_branch:
        for i, instr in enumerate(non_branch):
            if all(ready.get(r,0) <= cycle for r in instr['read']):
                # can issue
                scheduled.append(instr['text'])
                for w in instr['write']:
                    ready[w] = cycle + instr['latency']
                non_branch.pop(i)
                break
        else:
            # none ready yet: simulate stall by advancing time
            cycle += 1
            continue
        cycle += 1

    # Finally, append branch instructions in their original order
    for instr in branch_ins:
        scheduled.append(instr['text'])
        cycle += instr['latency']

    # Strip out any None placeholders before returning
    return [line for line in scheduled if line is not None]

# ================================================
# Example usage
if __name__ == '__main__':
    isa = 'armv7m'
    asm = [
        "MOV R1, R2",
        "ADD R3, R1, R4",
        "STR R3, [R5]",
        "B end",
        "loop:",
        "LDR R0, [R1]",
        "end:",
        "MOV R2, R3"
    ]

    parsed = [parse_instr(line, idx, isa) for idx, line in enumerate(asm)]
    blocks = split_blocks(parsed, isa)

    # (optional) report RAW hazards
    hazards = detect_raw(parsed)
    if hazards:
        print("RAW hazards detected:", hazards)

    # schedule each block and print optimized code
    result = []
    for blk in blocks:
        result.extend(schedule_block(blk, isa))
        result.append('')  # blank line between blocks

    print("\n".join(result))
