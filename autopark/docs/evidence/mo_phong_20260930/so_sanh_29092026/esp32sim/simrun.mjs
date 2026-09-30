// Run a firmware in esp32sim's WebAssembly build under Node (Windows, no Rust toolchain).
// node simrun.mjs <bootloader.bin> <partitions.bin> <app.bin> <seconds> <log> [inputs.json] [--nojit]
// inputs.json: [{"at": 2.5, "json": {"t":"key","src":"uart0","data":"P"}}, ...]  (at = emulated seconds)
import { readFileSync, writeFileSync, appendFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createJitHost } from './jit.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const [boot, ptable, app, secondsArg, log, inputsFile] = process.argv.slice(2);
const noJit = process.argv.includes('--nojit');
const seconds = Number(secondsArg);
const inputs = inputsFile && !inputsFile.startsWith('--') ? JSON.parse(readFileSync(inputsFile, 'utf8')) : [];
inputs.sort((a, b) => a.at - b.at);
const enc = new TextEncoder(), dec = new TextDecoder();
const logs = [];
let w;
const blockJit = createJitHost(() => w);
const wasmBytes = readFileSync(join(here, 'esp32sim.wasm'));
const { instance } = await WebAssembly.instantiate(wasmBytes, { env: { ...blockJit.imports, host_profile_now: () => performance.now(), host_log: (p, n) => logs.push(dec.decode(new Uint8Array(w.memory.buffer).subarray(p, p + n))) } });
w = instance.exports;
const mem = () => new Uint8Array(w.memory.buffer);
const withBytes = (bytes, f) => { const p = w.esp32sim_alloc(bytes.length); mem().set(bytes, p); try { return f(p, bytes.length); } finally { w.esp32sim_free(p, bytes.length); } };
const emu = withBytes(enc.encode('none'), (p, n) => w.esp32sim_new(p, n, 8, 0));
if (!emu) throw new Error('esp32sim_new failed: ' + logs.join(' | '));
const files = [[0, join(here, 'esp32s3_rev0_rom.elf')], [1, boot], [2, ptable], [3, app]];
for (const [kind, f] of files) {
  const rc = withBytes(new Uint8Array(readFileSync(f)), (p, n) => w.esp32sim_load(emu, kind, p, n));
  if (rc !== 0) throw new Error(`load kind ${kind} ${f}: ` + logs.join(' | '));
}
w.esp32sim_set_jit(emu, noJit ? 0 : 1);
if (w.esp32sim_boot(emu, 0) !== 0) throw new Error('boot failed: ' + logs.join(' | '));
const hz = w.esp32sim_cpu_hz(emu);
writeFileSync(log, `# esp32sim.wasm cpu_hz=${hz} jit=${!noJit}\n`);
const partial = { usb: '', uart0: '', uart1: '' };
const usbBytes = [];
const t0 = Date.now();
let nextInput = 0;
const step = Math.round(hz / 100); // 10 ms of emulated time per call
const target = hz * seconds;
const emit = (src, text) => {
  partial[src] = (partial[src] || '') + text;
  let i;
  while ((i = partial[src].indexOf('\n')) >= 0) {
    const line = partial[src].slice(0, i).replace(/\r$/, '');
    partial[src] = partial[src].slice(i + 1);
    const tEmu = w.esp32sim_cycles(emu) / hz;
    appendFileSync(log, `${tEmu.toFixed(3).padStart(8)} emu | ${((Date.now() - t0) / 1000).toFixed(3).padStart(8)} wall | ${src.padEnd(5)} | ${line}\n`);
  }
};
while (w.esp32sim_cycles(emu) < target) {
  const now = w.esp32sim_cycles(emu) / hz;
  while (nextInput < inputs.length && inputs[nextInput].at <= now) {
    const js = JSON.stringify(inputs[nextInput].json);
    appendFileSync(log, `${now.toFixed(3).padStart(8)} emu | >> ${js}\n`);
    withBytes(enc.encode(js), (p, n) => w.esp32sim_in_text(emu, p, n));
    nextInput++;
  }
  const rc = w.esp32sim_run(emu, step, Date.now());
  if (rc !== 0) { appendFileSync(log, `# esp32sim_run stopped rc=${rc} at ${now.toFixed(3)} s: ${logs.slice(-3).join(' | ')}\n`); break; }
  const n = w.esp32sim_out_take(emu);
  for (let i = 0; i < n; i++) {
    if (w.esp32sim_out_kind(emu, i) !== 1) continue;
    const p = w.esp32sim_out_ptr(emu, i), len = w.esp32sim_out_len(emu, i);
    const msg = JSON.parse(dec.decode(mem().subarray(p, p + len)));
    if (msg.t === 'serial') {
      if (msg.src === 'usb') for (const ch of msg.data) usbBytes.push([ch.codePointAt(0), w.esp32sim_cycles(emu) / hz]);
      emit(msg.src, msg.data);
    }
  }
}
for (const [src, rest] of Object.entries(partial)) if (rest) appendFileSync(log, `# unterminated ${src}: ${JSON.stringify(rest)}\n`);
const wall = (Date.now() - t0) / 1000;
const emuS = w.esp32sim_cycles(emu) / hz;
appendFileSync(log, `# emulated ${emuS.toFixed(2)} s in ${wall.toFixed(2)} s wall = ${(emuS / wall).toFixed(3)}x real time; insns ${(w.esp32sim_insns(emu) / 1e6).toFixed(1)} M (${(w.esp32sim_insns(emu) / 1e6 / wall).toFixed(1)} Minsn/s); jit compiled ${blockJit.stats.compiled}\n`);
appendFileSync(log, `# usb code points received: ${usbBytes.length}\n`);
writeFileSync(log + '.usb.json', JSON.stringify(usbBytes));
appendFileSync(log, `# host_log tail: ${logs.slice(-5).join(' | ')}\n`);
w.esp32sim_delete(emu);
