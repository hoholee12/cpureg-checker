import re

# ================================
# Multi-ISA RAW-Only Scheduler
# ================================

# Regular expressions for parsing
REGEX_REGISTER = re.compile(r"[A-Za-z]{1,2}\d+")    # R1, X2, etc.
REGEX_SPLIT    = re.compile(r"[ ,()]+")             # splits opcode and operands
REGEX_LABEL    = re.compile(r"^\w+:$")              # label lines

# ISA configuration (ARMv7-M only for now)
ISA_DB = {
    'armv7m': {
        'instrs': {
            'MOV': {'read': [1], 'write': [0]},
            'ADD': {'read': [1,2], 'write': [0]},
            'SUB': {'read': [1,2], 'write': [0]},
            'MUL': {'read': [1,2], 'write': [0]},
            'LDR': {'read': [1], 'write': [0]},
            'STR': {'read': [0,1], 'write': []},
            'B':   {'read': [], 'write': []}
        }
    }
}

BRANCH_OPS = {'armv7m': {'B'}}

# Extract registers from a string
def extract_registers(op):
    return REGEX_REGISTER.findall(op.upper())

# Parse a single instruction
def parse_instr(line, idx, isa):
    text = line.strip()
    if not text or text.startswith(';'):
        return None
    if REGEX_LABEL.match(text):
        return {'id': idx, 'opc': 'LABEL', 'text': text}
    parts = REGEX_SPLIT.split(text)
    opc = parts[0].upper()
    if opc not in ISA_DB[isa]['instrs']:
        return None
    info = ISA_DB[isa]['instrs'][opc]
    reads, writes = [], []
    for i in info['read']:
        if i + 1 < len(parts):
            reads += extract_registers(parts[i+1])
    for i in info['write']:
        if i + 1 < len(parts):
            writes += extract_registers(parts[i+1])
    return {
        'id': idx,
        'opc': opc,
        'read': set(reads),
        'write': set(writes),
        'text': text
    }

# Split into basic blocks
def split_blocks(parsed, isa, lines):
    blocks = []
    current = []
    for instr in parsed:
        if instr is None:
            current.append(instr)
            continue
        if REGEX_LABEL.match(lines[instr['id']].strip()):
            if current:
                blocks.append(current)
            current = [instr]
            continue
        current.append(instr)
        if instr['opc'] in BRANCH_OPS[isa]:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks

# Schedule a block: reorder to avoid RAW hazards
def schedule_block(block, isa):
    scheduled = []
    remaining = [i for i in block if i and i['opc'] not in BRANCH_OPS[isa] and i['opc'] != 'LABEL']
    labels = [i for i in block if i and i['opc'] == 'LABEL']
    branches = [i for i in block if i and i['opc'] in BRANCH_OPS[isa]]
    ready = set()
    done = []

    while remaining:
        issued = False
        for i in range(len(remaining)):
            instr = remaining[i]
            if instr['read'].issubset(ready):
                done.append(instr)
                ready.update(instr['write'])
                del remaining[i]
                issued = True
                break
        if not issued:
            # no instruction ready, pick the next and just move on
            instr = remaining.pop(0)
            done.append(instr)
            ready.update(instr['write'])

    scheduled.extend(l['text'] for l in labels)
    scheduled.extend(i['text'] for i in done)
    scheduled.extend(b['text'] for b in branches)
    return scheduled

# ========= Entry point =========

if __name__ == '__main__':
    isa = 'armv7m'
    input_file = 'input.asm'
    output_file = 'output.asm'

    # Read input assembly file
    with open(input_file, 'r') as f:
        asm_lines = [line.rstrip('\n') for line in f]

    # Parse instructions
    parsed = [parse_instr(line, i, isa) for i, line in enumerate(asm_lines)]

    # Split into blocks
    blocks = split_blocks(parsed, isa, asm_lines)

    # Schedule each block
    final_output = []
    for block in blocks:
        final_output.extend(schedule_block(block, isa))
        final_output.append('')  # empty line between blocks

    # Write to output file
    with open(output_file, 'w') as f:
        f.write('\n'.join(final_output))

    print(f"Scheduled assembly written to '{output_file}'")
