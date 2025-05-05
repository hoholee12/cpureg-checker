import re

# ================================
# Multi-ISA RAW-Only Scheduler
# Supports ARMv7-M (read-after-write hazard only)
# Parses assembly, detects RAW hazards,
# and performs latency-aware instruction reordering
# preserving control-flow boundaries (branches/labels).
# ================================

# Regular expressions for parsing
REGEX_REGISTER = re.compile(r"[A-Za-z]{1,2}\d+")  # matches register names like R1, X2, $0
REGEX_SPLIT    = re.compile(r"[ ,()]+")             # splits opcode and operands
REGEX_LABEL    = re.compile(r"^\w+:$")             # matches label lines ending with ':'

# ISA configuration (ARMv7-M example)
# Only RAW hazards are considered. WAW and WAR are ignored.
ISA_DB = {
    'armv7m': {
        'instrs': {
            'MOV': {'read': [1], 'write': [0], 'latency': 1},  # MOV Rd, Rn
            'ADD': {'read': [1,2], 'write': [0], 'latency': 1},  # ADD Rd, Rn, Rm
            'SUB': {'read': [1,2], 'write': [0], 'latency': 1},  # SUB Rd, Rn, Rm
            'MUL': {'read': [1,2], 'write': [0], 'latency': 3},  # MUL Rd, Rn, Rm
            'LDR': {'read': [1],   'write': [0], 'latency': 2},  # LDR Rt, [Rn]
            'STR': {'read': [0,1], 'write': [],  'latency': 2},  # STR Rt, [Rn]
            'B':   {'read': [],    'write': [],  'latency': 1},  # B label
        },
        'nop': 'NOP'  # ARMv7-M no-op
    }
}

# Branch opcodes mark block boundaries
BRANCH_OPS = {
    'armv7m': {'B'}
}

# --------------------------------
# Extract registers from an operand string
# Uses REGEX_REGISTER to find all register names
def extract_registers(op):
    return REGEX_REGISTER.findall(op.upper())

# --------------------------------
# Parse a single assembly line into metadata
# Returns None for blank lines, comments, or labels
# Fields: id, opc, read set, write set, latency, text
def parse_instr(line, idx, isa):
    text = line.strip()
    # skip empty, comment, or label lines
    if not text or text.startswith(';') or REGEX_LABEL.match(text):
        return None
    # split into opcode and operands
    parts = REGEX_SPLIT.split(text)
    opc = parts[0].upper()
    # if opcode not supported, skip
    if opc not in ISA_DB[isa]['instrs']:
        return None
    data = ISA_DB[isa]['instrs'][opc]
    # determine read/write registers
    reads, writes = [], []
    for i in data['read']:
        if i < len(parts)-1:
            reads += extract_registers(parts[i+1])
    for i in data['write']:
        if i < len(parts)-1:
            writes += extract_registers(parts[i+1])
    return {
        'id': idx,
        'opc': opc,
        'read': set(reads),
        'write': set(writes),
        'latency': data['latency'],
        'text': text
    }

# --------------------------------
# Split instructions into basic blocks
# Blocks end at branch instructions or start at labels
def split_blocks(parsed, isa, lines):
    blocks, current = [], []
    for instr in parsed:
        if instr is None:
            # preserve comments/labels
            current.append(instr)
            continue
        # if this line is a label, start a new block
        if REGEX_LABEL.match(lines[instr['id']].strip()):
            if current:
                blocks.append(current)
            current = [instr]
            continue
        current.append(instr)
        # if branch instruction, close the block
        if instr['opc'] in BRANCH_OPS[isa]:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks

# --------------------------------
# Detect RAW hazards only
# Returns list of (i, j, register) where instruction i writes and j reads same register
def detect_raw(parsed):
    raws = []
    for i in range(len(parsed)):
        a = parsed[i]
        if not a: continue
        for j in range(i+1, len(parsed)):
            b = parsed[j]
            if not b: continue
            # RAW hazard if write set intersects read set
            for r in a['write'] & b['read']:
                raws.append((i, j, r))
    return raws

# --------------------------------
# Schedule one block with latency-awareness
# Ignores WAW/WAR, handles RAW only, branches at end
def schedule_block(block, isa):
    cycle = 0
    ready = {}  # register -> ready cycle
    # separate non-branch and branch instructions
    non_branch = [i for i in block if i and i['opc'] not in BRANCH_OPS[isa]]
    branch_ins = [i for i in block if i and i['opc'] in BRANCH_OPS[isa]]
    scheduled = []
    remaining = non_branch.copy()
    nop = ISA_DB[isa]['nop']
    # schedule non-branch instructions first
    while remaining:
        issued = False
        for _ in range(len(remaining)):
            instr = remaining.pop(0)
            # check RAW readiness
            if all(ready.get(r,0) <= cycle for r in instr['read']):
                scheduled.append(instr['text'])
                # update register ready times
                for w in instr['write']:
                    ready[w] = cycle + instr['latency']
                issued = True
                break
            remaining.append(instr)
        # insert NOP if nothing could issue
        if not issued:
            scheduled.append(nop)
        cycle += 1
    # append branch instructions in original order
    for instr in branch_ins:
        scheduled.append(instr['text'])
        cycle += instr['latency']
    return scheduled

# ================================================
# Example usage
if __name__ == '__main__':
    isa = 'armv7m'  # only ARMv7-M supported in this example
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
    parsed = [parse_instr(l,i,isa) for i,l in enumerate(asm)]
    blocks = split_blocks(parsed, isa, asm)
    result = []
    for blk in blocks:
        result += schedule_block(blk, isa) + ['']
    print("\n".join(result))
