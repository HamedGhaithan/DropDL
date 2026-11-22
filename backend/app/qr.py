"""A small, dependency-free QR code encoder (ISO/IEC 18004, byte mode, versions 1-10).

Used to show the Phone Link pairing address. Only what that needs is implemented:
byte-mode data, error-correction levels L/M/Q/H, automatic version and mask choice.
"""
from __future__ import annotations

# Error-correction codewords per block, and number of blocks, indexed [level][version] (index 0 unused).
_ECC_PER_BLOCK = {
    'L': (None, 7, 10, 15, 20, 26, 18, 20, 24, 30, 18),
    'M': (None, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26),
    'Q': (None, 13, 22, 18, 26, 18, 24, 18, 22, 20, 24),
    'H': (None, 17, 28, 22, 16, 22, 28, 26, 26, 24, 28),
}
_BLOCKS = {
    'L': (None, 1, 1, 1, 1, 1, 2, 2, 2, 2, 4),
    'M': (None, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5),
    'Q': (None, 1, 1, 2, 2, 4, 4, 6, 6, 8, 8),
    'H': (None, 1, 1, 2, 4, 4, 4, 5, 6, 8, 8),
}
_FORMAT_BITS = {'L': 1, 'M': 0, 'Q': 3, 'H': 2}
MAX_VERSION = 10


# ---------------------------------------------------------------- Reed-Solomon over GF(256), polynomial 0x11D
def _gf_mul(x: int, y: int) -> int:
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree: int) -> list[int]:
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = _gf_mul(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = _gf_mul(root, 0x02)
    return result


def rs_remainder(data: list[int], degree: int) -> list[int]:
    divisor = _rs_divisor(degree)
    result = [0] * degree
    for byte in data:
        factor = byte ^ result.pop(0)
        result.append(0)
        for i, coefficient in enumerate(divisor):
            result[i] ^= _gf_mul(coefficient, factor)
    return result


# ---------------------------------------------------------------- sizes
def _raw_modules(version: int) -> int:
    result = (16 * version + 128) * version + 64
    if version >= 2:
        count = version // 7 + 2
        result -= (25 * count - 10) * count - 55
        if version >= 7:
            result -= 36
    return result


def data_codewords(version: int, level: str) -> int:
    return _raw_modules(version) // 8 - _ECC_PER_BLOCK[level][version] * _BLOCKS[level][version]


def _alignment_positions(version: int) -> list[int]:
    if version == 1:
        return []
    count = version // 7 + 2
    step = (version * 4 + count * 2 + 1) // (count * 2 - 2) * 2
    size = version * 4 + 17
    result = [6] + [0] * (count - 1)
    pos = size - 7
    for i in range(count - 1, 0, -1):
        result[i] = pos
        pos -= step
    return result


def format_bits(level: str, mask: int) -> int:
    data = _FORMAT_BITS[level] << 3 | mask
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    return (data << 10 | rem) ^ 0x5412


def version_bits(version: int) -> int:
    rem = version
    for _ in range(12):
        rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
    return version << 12 | rem


# ---------------------------------------------------------------- encoding
def _codewords(data: bytes, version: int, level: str) -> list[int]:
    bits: list[int] = []
    def put(value: int, length: int):
        bits.extend((value >> i) & 1 for i in range(length - 1, -1, -1))
    put(0b0100, 4)                                   # byte mode
    put(len(data), 8 if version <= 9 else 16)
    for byte in data:
        put(byte, 8)
    capacity = data_codewords(version, level) * 8
    put(0, min(4, capacity - len(bits)))             # terminator
    put(0, (-len(bits)) % 8)
    pad = 0xEC
    while len(bits) < capacity:
        put(pad, 8)
        pad ^= 0xEC ^ 0x11
    codewords = [int(''.join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    # split into blocks, add error correction, interleave
    blocks_n, ecc = _BLOCKS[level][version], _ECC_PER_BLOCK[level][version]
    raw = _raw_modules(version) // 8
    short_count = blocks_n - raw % blocks_n
    short_len = raw // blocks_n
    blocks, k = [], 0
    for i in range(blocks_n):
        length = short_len - ecc + (0 if i < short_count else 1)
        block = codewords[k:k + length]
        k += length
        tail = rs_remainder(block, ecc)
        if i < short_count:
            block = block + [None]                   # placeholder so all blocks line up
        blocks.append(block + tail)
    out = []
    for i in range(len(blocks[0])):
        for block in blocks:
            if block[i] is not None:
                out.append(block[i])
    return out


class _Grid:
    def __init__(self, version: int):
        self.size = version * 4 + 17
        self.dark = [[False] * self.size for _ in range(self.size)]
        self.fixed = [[False] * self.size for _ in range(self.size)]

    def set(self, x: int, y: int, dark: bool):
        self.dark[y][x] = dark
        self.fixed[y][x] = True


def _function_patterns(grid: _Grid, version: int):
    n = grid.size
    for i in range(n):                                # timing
        grid.set(6, i, i % 2 == 0)
        grid.set(i, 6, i % 2 == 0)
    for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):   # finders + separators
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < n and 0 <= y < n:
                    distance = max(abs(dx), abs(dy))
                    grid.set(x, y, distance not in (2, 4))
    positions = _alignment_positions(version)
    last = len(positions) - 1
    for i, ay in enumerate(positions):
        for j, ax in enumerate(positions):
            if (i, j) in ((0, 0), (0, last), (last, 0)):
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    grid.set(ax + dx, ay + dy, max(abs(dx), abs(dy)) != 1)
    _draw_format(grid, format_bits('M', 0))           # reserve; redrawn with the real mask
    if version >= 7:
        bits = version_bits(version)
        for i in range(18):
            bit = (bits >> i) & 1 == 1
            a, b = n - 11 + i % 3, i // 3
            grid.set(a, b, bit)
            grid.set(b, a, bit)


def _draw_format(grid: _Grid, bits: int):
    n = grid.size
    bit = lambda i: (bits >> i) & 1 == 1
    for i in range(6):
        grid.set(8, i, bit(i))
    grid.set(8, 7, bit(6))
    grid.set(8, 8, bit(7))
    grid.set(7, 8, bit(8))
    for i in range(9, 15):
        grid.set(14 - i, 8, bit(i))
    for i in range(8):
        grid.set(n - 1 - i, 8, bit(i))
    for i in range(8, 15):
        grid.set(8, n - 15 + i, bit(i))
    grid.set(8, n - 8, True)                         # the dark module


def _place_data(grid: _Grid, codewords: list[int]):
    n, i, total = grid.size, 0, len(codewords) * 8
    right = n - 1
    while right >= 1:
        if right == 6:
            right = 5
        for vert in range(n):
            for j in range(2):
                x = right - j
                upward = ((right + 1) & 2) == 0
                y = n - 1 - vert if upward else vert
                if not grid.fixed[y][x] and i < total:
                    grid.dark[y][x] = (codewords[i >> 3] >> (7 - (i & 7))) & 1 == 1
                    i += 1
        right -= 2


_MASKS = (
    lambda x, y: (x + y) % 2 == 0,
    lambda x, y: y % 2 == 0,
    lambda x, y: x % 3 == 0,
    lambda x, y: (x + y) % 3 == 0,
    lambda x, y: (x // 3 + y // 2) % 2 == 0,
    lambda x, y: x * y % 2 + x * y % 3 == 0,
    lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
    lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0,
)


def _apply_mask(grid: _Grid, mask: int):
    test = _MASKS[mask]
    for y in range(grid.size):
        for x in range(grid.size):
            if not grid.fixed[y][x] and test(x, y):
                grid.dark[y][x] = not grid.dark[y][x]


def _penalty(dark: list[list[bool]]) -> int:
    n, score = len(dark), 0
    lines = dark + [list(col) for col in zip(*dark)]
    for line in lines:                                # runs of 5+ and finder-like patterns
        run, colour = 1, line[0]
        for value in line[1:]:
            if value == colour:
                run += 1
            else:
                if run >= 5:
                    score += run - 2
                run, colour = 1, value
        if run >= 5:
            score += run - 2
        text = ''.join('1' if v else '0' for v in line)
        score += 40 * (text.count('10111010000') + text.count('00001011101'))
    for y in range(n - 1):                            # 2x2 blocks
        for x in range(n - 1):
            if dark[y][x] == dark[y][x + 1] == dark[y + 1][x] == dark[y + 1][x + 1]:
                score += 3
    total = sum(map(sum, dark))
    score += 10 * (abs(total * 20 - n * n * 10) // (n * n))
    return score


def matrix(text: str | bytes, level: str = 'M') -> list[list[bool]]:
    """Return the QR modules (True = dark) for `text`, without the quiet zone."""
    data = text.encode('utf-8') if isinstance(text, str) else bytes(text)
    for version in range(1, MAX_VERSION + 1):
        header = 4 + (8 if version <= 9 else 16)
        if header + 8 * len(data) <= data_codewords(version, level) * 8:
            break
    else:
        raise ValueError('Too much data for a QR code of version 10.')
    codewords = _codewords(data, version, level)
    best, best_score = None, None
    for mask in range(8):
        grid = _Grid(version)
        _function_patterns(grid, version)
        _place_data(grid, codewords)
        _apply_mask(grid, mask)
        _draw_format(grid, format_bits(level, mask))
        score = _penalty(grid.dark)
        if best_score is None or score < best_score:
            best, best_score = grid.dark, score
    return best


def svg(text: str, level: str = 'M', border: int = 4, dark: str = '#0b0f19', light: str = '#ffffff') -> str:
    """An SVG drawing of the QR code (one path, crisp at any size)."""
    modules = matrix(text, level)
    n = len(modules) + border * 2
    parts = []
    for y, row in enumerate(modules):
        x = 0
        while x < len(row):
            if row[x]:
                start = x
                while x < len(row) and row[x]:
                    x += 1
                parts.append(f'M{start + border},{y + border}h{x - start}v1h-{x - start}z')
            else:
                x += 1
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" shape-rendering="crispEdges">'
            f'<rect width="{n}" height="{n}" fill="{light}"/><path fill="{dark}" d="{"".join(parts)}"/></svg>')
