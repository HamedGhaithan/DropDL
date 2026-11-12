// Regenerate installer/dropdl.ico from frontend/public/dropdl.svg.
// Usage (from frontend/): node ../scripts/build-icons.mjs
// Windows Forms (the native window/tray) needs classic 32-bit DIB frames, so
// every size is written as a bitmap, not PNG-compressed.
import {readFileSync, writeFileSync} from 'node:fs'
import {dirname, join} from 'node:path'
import {fileURLToPath} from 'node:url'
import {createRequire} from 'node:module'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const require = createRequire(join(root, 'frontend', 'package.json'))
const {Resvg} = require('@resvg/resvg-js')
const svg = readFileSync(join(root, 'frontend', 'public', 'dropdl.svg'), 'utf8')
// Small sizes use a tighter tile so the drop and arrow stay readable.
const small = svg.replace('rx="15"', 'rx="13"').replace('rx="15"', 'rx="13"').replace('rx="14.5"', 'rx="12.5"')
const sizes = [16, 24, 32, 48, 64, 128, 256]

function rgba(size) {
  const source = size <= 24 ? small : svg
  const image = new Resvg(source, {fitTo: {mode: 'width', value: size}, shapeRendering: 2}).render()
  return image.pixels // RGBA, top-down
}

function dib(size, pixels) {
  const header = Buffer.alloc(40)
  header.writeUInt32LE(40, 0); header.writeInt32LE(size, 4); header.writeInt32LE(size * 2, 8)
  header.writeUInt16LE(1, 12); header.writeUInt16LE(32, 14); header.writeUInt32LE(0, 16)
  const color = Buffer.alloc(size * size * 4)
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const from = (y * size + x) * 4, to = ((size - 1 - y) * size + x) * 4 // bottom-up BGRA
    color[to] = pixels[from + 2]; color[to + 1] = pixels[from + 1]; color[to + 2] = pixels[from]; color[to + 3] = pixels[from + 3]
  }
  const stride = Math.ceil(size / 32) * 4
  const mask = Buffer.alloc(stride * size) // all zero: alpha channel decides transparency
  return Buffer.concat([header, color, mask])
}

const frames = sizes.map(size => ({size, data: dib(size, rgba(size))}))
const directory = Buffer.alloc(6 + 16 * frames.length)
directory.writeUInt16LE(0, 0); directory.writeUInt16LE(1, 2); directory.writeUInt16LE(frames.length, 4)
let offset = directory.length
frames.forEach(({size, data}, index) => {
  const at = 6 + index * 16
  directory.writeUInt8(size >= 256 ? 0 : size, at); directory.writeUInt8(size >= 256 ? 0 : size, at + 1)
  directory.writeUInt8(0, at + 2); directory.writeUInt8(0, at + 3)
  directory.writeUInt16LE(1, at + 4); directory.writeUInt16LE(32, at + 6)
  directory.writeUInt32LE(data.length, at + 8); directory.writeUInt32LE(offset, at + 12)
  offset += data.length
})
writeFileSync(join(root, 'installer', 'dropdl.ico'), Buffer.concat([directory, ...frames.map(f => f.data)]))
writeFileSync(join(root, 'frontend', 'public', 'dropdl-256.png'), new Resvg(svg, {fitTo: {mode: 'width', value: 256}}).render().asPng())
console.log(`installer/dropdl.ico: ${sizes.join(', ')} px bitmap frames; frontend/public/dropdl-256.png`)
