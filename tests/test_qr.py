"""The QR encoder, checked against published reference values and an independent reader."""
import random

import pytest

from app import qr


def test_reed_solomon_matches_the_published_hello_world_example():
    # "HELLO WORLD", version 1-M (alphanumeric); data and error-correction codewords from the standard's walk-through.
    data = [32, 91, 11, 120, 209, 114, 220, 77, 67, 64, 236, 17, 236, 17, 236, 17]
    assert qr.rs_remainder(data, 10) == [196, 35, 39, 119, 235, 215, 231, 226, 93, 23]


@pytest.mark.parametrize('level,mask,expected', [
    ('L', 0, '111011111000100'), ('M', 0, '101010000010010'),
    ('Q', 0, '011010101011111'), ('H', 0, '001011010001001'),
    ('L', 4, '110011000101111'), ('M', 7, '100101010100000'), ('M', 3, '101101101001011'),
])
def test_format_information_matches_the_standard_table(level, mask, expected):
    assert format(qr.format_bits(level, mask), '015b') == expected


def test_version_information_matches_the_standard_table():
    assert format(qr.version_bits(7), '018b') == '000111110010010100'
    assert format(qr.version_bits(10), '018b') == '001010010011010011'


def test_capacities_match_the_standard():
    # data codewords for level M, versions 1-10
    assert [qr.data_codewords(v, 'M') for v in range(1, 11)] == [16, 28, 44, 64, 86, 108, 124, 154, 182, 216]
    assert [qr.data_codewords(v, 'L') for v in range(1, 5)] == [19, 34, 55, 80]


# ---------------------------------------------------------------- an independent reader for generated matrices
def _read(modules):
    n = len(modules)
    version = (n - 17) // 4
    bit = lambda x, y: 1 if modules[y][x] else 0
    first = [bit(8, i) for i in range(6)] + [bit(8, 7), bit(8, 8), bit(7, 8)] + [bit(14 - i, 8) for i in range(9, 15)]
    second = [bit(n - 1 - i, 8) for i in range(8)] + [bit(8, n - 15 + i) for i in range(8, 15)]
    value = sum(b << i for i, b in enumerate(first))
    assert value == sum(b << i for i, b in enumerate(second)), 'the two format copies disagree'
    assert bit(8, n - 8) == 1, 'dark module missing'
    match = [(lvl, m) for lvl in 'LMQH' for m in range(8) if qr.format_bits(lvl, m) == value]
    assert len(match) == 1, 'format information is not a valid code word'
    level, mask = match[0]
    # which modules carry data: everything except function patterns
    reserved = [[False] * n for _ in range(n)]
    def box(x0, y0, x1, y1):
        for y in range(max(0, y0), min(n, y1)):
            for x in range(max(0, x0), min(n, x1)):
                reserved[y][x] = True
    box(0, 0, 9, 9); box(n - 8, 0, n, 9); box(0, n - 8, 9, n)
    for i in range(n):
        reserved[6][i] = reserved[i][6] = True
    pos = qr._alignment_positions(version)
    for i, ay in enumerate(pos):
        for j, ax in enumerate(pos):
            if (i, j) not in ((0, 0), (0, len(pos) - 1), (len(pos) - 1, 0)):
                box(ax - 2, ay - 2, ax + 3, ay + 3)
    if version >= 7:
        box(n - 11, 0, n - 8, 6); box(0, n - 11, 6, n - 8)
    masks = {0: lambda x, y: (x + y) % 2 == 0, 1: lambda x, y: y % 2 == 0, 2: lambda x, y: x % 3 == 0,
             3: lambda x, y: (x + y) % 3 == 0, 4: lambda x, y: (y // 2 + x // 3) % 2 == 0,
             5: lambda x, y: (x * y) % 2 + (x * y) % 3 == 0, 6: lambda x, y: ((x * y) % 2 + (x * y) % 3) % 2 == 0,
             7: lambda x, y: ((x + y) % 2 + (x * y) % 3) % 2 == 0}
    bits = []
    col, upward = n - 1, True
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(n - 1, -1, -1) if upward else range(n)
        for y in rows:
            for x in (col, col - 1):
                if not reserved[y][x]:
                    bits.append(bit(x, y) ^ (1 if masks[mask](x, y) else 0))
        upward = not upward
        col -= 2
    codewords = [int(''.join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits) - 7, 8)]
    # de-interleave
    blocks_n, ecc = qr._BLOCKS[level][version], qr._ECC_PER_BLOCK[level][version]
    total = qr._raw_modules(version) // 8
    codewords = codewords[:total]
    short = blocks_n - total % blocks_n
    short_data = total // blocks_n - ecc
    data_lens = [short_data + (0 if b < short else 1) for b in range(blocks_n)]
    blocks = [[] for _ in range(blocks_n)]
    k = 0
    for i in range(max(data_lens)):
        for b in range(blocks_n):
            if i < data_lens[b]:
                blocks[b].append(codewords[k]); k += 1
    for i in range(ecc):
        for b in range(blocks_n):
            blocks[b].append(codewords[k]); k += 1
    for block in blocks:                              # every block must have zero syndromes
        alpha = 1
        for _ in range(ecc):
            acc = 0
            for c in block:
                acc = qr._gf_mul(acc, alpha) ^ c
            assert acc == 0, 'error-correction check failed'
            alpha = qr._gf_mul(alpha, 2)
    data = [c for b, block in enumerate(blocks) for c in block[:data_lens[b]]]
    stream = ''.join(format(c, '08b') for c in data)
    assert stream[:4] == '0100'
    count_bits = 8 if version <= 9 else 16
    length = int(stream[4:4 + count_bits], 2)
    payload = bytes(int(stream[4 + count_bits + 8 * i:4 + count_bits + 8 * i + 8], 2) for i in range(length))
    return payload.decode('utf-8'), level, version


def test_finder_patterns_sit_in_three_corners():
    m = qr.matrix('hello')
    n = len(m)
    for x0, y0 in ((0, 0), (n - 7, 0), (0, n - 7)):
        ring = [m[y0][x0 + i] for i in range(7)] + [m[y0 + 6][x0 + i] for i in range(7)]
        assert all(ring)
        assert m[y0 + 3][x0 + 3] and not m[y0 + 1][x0 + 1]


@pytest.mark.parametrize('text', [
    'http://192.168.1.23:17330/#pair=K7QX2M9A',
    'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
    'a', 'DropDL ✓ العربية',
])
def test_generated_codes_read_back(text):
    decoded, level, _ = _read(qr.matrix(text))
    assert decoded == text and level == 'M'


def test_every_version_and_level_reads_back():
    rnd = random.Random(7)
    for level in 'LMQH':
        for version in range(1, 11):
            capacity = qr.data_codewords(version, level) - (2 if version <= 9 else 3)
            text = ''.join(rnd.choice('abcdefghijklmnopqrstuvwxyz0123456789') for _ in range(capacity))
            decoded, got_level, got_version = _read(qr.matrix(text, level))
            assert (decoded, got_level, got_version) == (text, level, version)


def test_too_long_is_refused_and_svg_is_well_formed():
    with pytest.raises(ValueError):
        qr.matrix('x' * 400)
    out = qr.svg('http://10.0.0.2:17330/')
    assert out.startswith('<svg') and out.endswith('</svg>') and 'viewBox="0 0 33 33"' in out
