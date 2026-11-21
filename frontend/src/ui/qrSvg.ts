/**
 * Minimal self-contained ISO/IEC 18004 QR Code (Byte mode, ECC Level L, Versions 1..4)
 * SVG generator for the END CARD repository link. Zero external dependencies, zero CDN.
 */

const GF_EXP = new Uint8Array(512);
const GF_LOG = new Uint8Array(256);
(() => {
  let x = 1;
  for (let i = 0; i < 255; i++) {
    GF_EXP[i] = x;
    GF_LOG[x] = i;
    x <<= 1;
    if (x & 0x100) x ^= 0x11d;
  }
  for (let i = 255; i < 512; i++) {
    GF_EXP[i] = GF_EXP[i - 255];
  }
})();

function gfMul(a: number, b: number): number {
  if (a === 0 || b === 0) return 0;
  return GF_EXP[GF_LOG[a] + GF_LOG[b]];
}

function rsGeneratorPoly(ecLen: number): Uint8Array {
  let poly = new Uint8Array([1]);
  for (let i = 0; i < ecLen; i++) {
    const next = new Uint8Array(poly.length + 1);
    const factor = GF_EXP[i];
    for (let j = 0; j < poly.length; j++) {
      next[j] ^= poly[j];
      next[j + 1] ^= gfMul(poly[j], factor);
    }
    poly = next;
  }
  return poly;
}

function rsEncode(data: Uint8Array, ecLen: number): Uint8Array {
  const gen = rsGeneratorPoly(ecLen);
  const rem = new Uint8Array(ecLen);
  for (let i = 0; i < data.length; i++) {
    const factor = data[i] ^ rem[0];
    rem.copyWithin(0, 1);
    rem[ecLen - 1] = 0;
    for (let j = 0; j < ecLen; j++) {
      rem[j] ^= gfMul(gen[j + 1], factor);
    }
  }
  return rem;
}

interface VersionSpec {
  version: number;
  size: number;
  dataCodewords: number;
  ecCodewords: number;
  align: number[];
}

// Single-block ECC-L specs for Versions 1..4 (supports up to 78 ASCII bytes)
const VERSIONS: VersionSpec[] = [
  { version: 1, size: 21, dataCodewords: 19, ecCodewords: 7, align: [] },
  { version: 2, size: 25, dataCodewords: 34, ecCodewords: 10, align: [6, 18] },
  { version: 3, size: 29, dataCodewords: 55, ecCodewords: 15, align: [6, 22] },
  { version: 4, size: 33, dataCodewords: 80, ecCodewords: 20, align: [6, 26] },
];

export function renderQrSvg(text: string, pixelSize = 112): string {
  const bytes = new TextEncoder().encode(text.slice(0, 76));
  const spec =
    VERSIONS.find((v) => bytes.length + 2 <= v.dataCodewords) ?? VERSIONS[3];
  const n = spec.size;

  // 1. Pack Byte-mode bit stream
  const bits: number[] = [];
  const pushBits = (val: number, len: number) => {
    for (let i = len - 1; i >= 0; i--) bits.push((val >>> i) & 1);
  };
  pushBits(0b0100, 4); // Byte mode
  pushBits(bytes.length, 8);
  for (const b of bytes) pushBits(b, 8);
  const maxBits = spec.dataCodewords * 8;
  pushBits(0, Math.min(4, maxBits - bits.length));
  while (bits.length % 8 !== 0) bits.push(0);

  const data = new Uint8Array(spec.dataCodewords);
  for (let i = 0; i < bits.length / 8; i++) {
    let v = 0;
    for (let b = 0; b < 8; b++) v = (v << 1) | bits[i * 8 + b];
    data[i] = v;
  }
  const pads = [0xec, 0x11];
  for (let i = bits.length / 8, p = 0; i < spec.dataCodewords; i++, p ^= 1) {
    data[i] = pads[p];
  }

  const ec = rsEncode(data, spec.ecCodewords);
  const codewords = new Uint8Array(data.length + ec.length);
  codewords.set(data, 0);
  codewords.set(ec, data.length);

  // 2. Build module matrix
  const grid = Array.from({ length: n }, () => new Uint8Array(n));
  const reserved = Array.from({ length: n }, () => new Uint8Array(n));

  const setMod = (r: number, c: number, dark: boolean) => {
    if (r >= 0 && r < n && c >= 0 && c < n) {
      grid[r][c] = dark ? 1 : 0;
      reserved[r][c] = 1;
    }
  };

  const drawFinder = (r0: number, c0: number) => {
    for (let dr = -1; dr <= 7; dr++) {
      for (let dc = -1; dc <= 7; dc++) {
        const inOuter = dr >= 0 && dr <= 6 && dc >= 0 && dc <= 6;
        const onBorder = dr === 0 || dr === 6 || dc === 0 || dc === 6;
        const inCore = dr >= 2 && dr <= 4 && dc >= 2 && dc <= 4;
        setMod(r0 + dr, c0 + dc, inOuter && (onBorder || inCore));
      }
    }
  };

  drawFinder(0, 0);
  drawFinder(0, n - 7);
  drawFinder(n - 7, 0);

  // Timing patterns
  for (let i = 8; i < n - 8; i++) {
    setMod(6, i, i % 2 === 0);
    setMod(i, 6, i % 2 === 0);
  }

  // Alignment pattern (Versions 2..4)
  if (spec.align.length === 2) {
    const [a0, a1] = spec.align;
    const coords = [
      [a0, a0],
      [a0, a1],
      [a1, a0],
      [a1, a1],
    ];
    for (const [cr, cc] of coords) {
      if (reserved[cr][cc]) continue;
      for (let dr = -2; dr <= 2; dr++) {
        for (let dc = -2; dc <= 2; dc++) {
          const dark =
            Math.max(Math.abs(dr), Math.abs(dc)) === 2 || (dr === 0 && dc === 0);
          setMod(cr + dr, cc + dc, dark);
        }
      }
    }
  }

  // Reserve format info + dark module
  for (let i = 0; i < 9; i++) {
    if (!reserved[8][i]) reserved[8][i] = 1;
    if (!reserved[i][8]) reserved[i][8] = 1;
  }
  for (let i = 0; i < 8; i++) {
    reserved[8][n - 1 - i] = 1;
    reserved[n - 1 - i][8] = 1;
  }
  setMod(n - 8, 8, true);

  // 3. Place data bits upward/downward in 2-col strips with mask 0 ((r + c) % 2 === 0)
  let bitIdx = 0;
  const totalBits = codewords.length * 8;
  let upward = true;
  for (let right = n - 1; right >= 1; right -= 2) {
    if (right === 6) right = 5;
    for (let vert = 0; vert < n; vert++) {
      const r = upward ? n - 1 - vert : vert;
      for (let j = 0; j < 2; j++) {
        const c = right - j;
        if (reserved[r][c]) continue;
        const bit =
          bitIdx < totalBits
            ? (codewords[bitIdx >>> 3] >>> (7 - (bitIdx & 7))) & 1
            : 0;
        bitIdx++;
        const masked = bit ^ ((r + c) % 2 === 0 ? 1 : 0);
        grid[r][c] = masked;
      }
    }
    upward = !upward;
  }

  // 4. Format bits for ECC Level L (01) + Mask 0 (000) => precomputed BCH = 0x77c4
  const fmt = 0x77c4;
  const fmtBit = (i: number) => ((fmt >>> i) & 1) === 1;
  const r8Cols = [0, 1, 2, 3, 4, 5, 7, 8, n - 8, n - 7, n - 6, n - 5, n - 4, n - 3, n - 2];
  for (let i = 0; i < 15; i++) {
    const b = fmtBit(14 - i);
    if (i < 8) grid[8][r8Cols[i]] = b ? 1 : 0;
    else grid[8][r8Cols[i]] = b ? 1 : 0;
  }
  // Exact standard placement around finders
  const topLeftR = [8, 8, 8, 8, 8, 8, 8, 8, 7, 5, 4, 3, 2, 1, 0];
  const topLeftC = [0, 1, 2, 3, 4, 5, 7, 8, 8, 8, 8, 8, 8, 8, 8];
  for (let i = 0; i < 15; i++) {
    const b = fmtBit(14 - i) ? 1 : 0;
    grid[topLeftR[i]][topLeftC[i]] = b;
    if (i < 7) grid[n - 1 - i][8] = b;
    else grid[8][n - 15 + i] = b;
  }

  // 5. Render crisp SVG with 2-module quiet zone
  const quiet = 2;
  const view = n + quiet * 2;
  let paths = "";
  for (let r = 0; r < n; r++) {
    for (let c = 0; c < n; c++) {
      if (grid[r][c]) {
        paths += `M${c + quiet},${r + quiet}h1v1h-1z`;
      }
    }
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${pixelSize}" height="${pixelSize}" viewBox="0 0 ${view} ${view}" shape-rendering="crispEdges" role="img" aria-label="Repository QR code"><rect width="${view}" height="${view}" fill="#FFFFFF"/><path d="${paths}" fill="#07090C"/></svg>`;
}
