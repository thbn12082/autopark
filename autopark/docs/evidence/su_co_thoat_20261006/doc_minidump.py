"""Đọc nhanh một minidump của WER (%LOCALAPPDATA%\\CrashDumps\\*.dmp) KHÔNG cần WinDbg/cdb (máy chưa có) — Việc 8, 06/10/2026.

In: mã ngoại lệ, địa chỉ lỗi = module + offset, hàm export gần nhất phía trước (đọc bảng export của DLL trên đĩa; chỉ
gợi ý, hàm nội bộ không có tên), luồng gây lỗi, các luồng khác, module đã gỡ (unloaded — có ích khi chết lúc tắt), và
"quét ngăn xếp" của luồng lỗi: các giá trị 8 byte rơi vào vùng mã của một module (gợi ý khung gọi, có thể lẫn rác).
Chỉ đọc tệp. Dùng: python doc_minidump.py <tệp.dmp> [--quet 40]
"""
import argparse
import struct
from pathlib import Path

ST_THREAD, ST_MODULE, ST_EXCEPTION, ST_SYSINFO, ST_MEMLIST, ST_MEM64, ST_MISC, ST_UNLOADED, ST_THREADNAMES = \
    3, 4, 6, 7, 5, 9, 15, 14, 24


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def u64(b, o):
    return struct.unpack_from("<Q", b, o)[0]


def mdstring(b, rva):
    n = u32(b, rva)
    return b[rva + 4: rva + 4 + n].decode("utf-16-le", "replace")


def exports(path):
    """(rva, tên) của bảng export trong DLL trên đĩa; [] nếu không đọc được."""
    try:
        d = Path(path).read_bytes()
        pe = u32(d, 0x3C)
        opt = pe + 24
        magic = struct.unpack_from("<H", d, opt)[0]
        dd = opt + (112 if magic == 0x20B else 96)
        exp_rva, exp_size = u32(d, dd), u32(d, dd + 4)
        nsec = struct.unpack_from("<H", d, pe + 6)[0]
        sopt = struct.unpack_from("<H", d, pe + 20)[0]
        secs = []
        for i in range(nsec):
            s = pe + 24 + sopt + 40 * i
            secs.append((u32(d, s + 12), u32(d, s + 8), u32(d, s + 20)))      # va, vsize, rawptr

        def off(rva):
            for va, vs, raw in secs:
                if va <= rva < va + max(vs, 1):
                    return raw + rva - va
            return None
        e = off(exp_rva)
        if e is None:
            return []
        nfun, nname = u32(d, e + 20), u32(d, e + 24)
        afun, aname, aord = off(u32(d, e + 28)), off(u32(d, e + 32)), off(u32(d, e + 36))
        out = []
        for i in range(nname):
            name_rva = u32(d, aname + 4 * i)
            o = off(name_rva)
            name = d[o: d.index(b"\0", o)].decode("ascii", "replace")
            ordi = struct.unpack_from("<H", d, aord + 2 * i)[0]
            frva = u32(d, afun + 4 * ordi)
            if not (exp_rva <= frva < exp_rva + exp_size):          # bỏ forwarder
                out.append((frva, name))
        return sorted(out)
    except Exception:  # noqa: BLE001
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("--quet", type=int, default=40, help="số giá trị trỏ vào module in ra khi quét ngăn xếp")
    a = ap.parse_args()
    b = Path(a.dump).read_bytes()
    assert b[:4] == b"MDMP", "không phải minidump"
    nstreams, dir_rva = u32(b, 8), u32(b, 12)
    streams = {}
    for i in range(nstreams):
        t, size, rva = struct.unpack_from("<III", b, dir_rva + 12 * i)
        streams[t] = (rva, size)
    mods = []
    if ST_MODULE in streams:
        rva, _ = streams[ST_MODULE]
        for i in range(u32(b, rva)):
            m = rva + 4 + 108 * i
            mods.append((u64(b, m), u32(b, m + 8), mdstring(b, u32(b, m + 20))))

    def where(addr):
        for base, size, name in mods:
            if base <= addr < base + size:
                return name, addr - base
        return None, None
    print(f"tệp: {a.dump} ({len(b)} B), {nstreams} luồng dữ liệu, {len(mods)} module")
    if ST_MISC in streams:
        rva, _ = streams[ST_MISC]
        print(f"pid {u32(b, rva + 8)}")
    names = {}
    if ST_THREADNAMES in streams:
        rva, _ = streams[ST_THREADNAMES]
        for i in range(u32(b, rva)):
            tid, nrva = struct.unpack_from("<IQ", b, rva + 4 + 12 * i)
            names[tid] = mdstring(b, nrva)
    threads = {}
    if ST_THREAD in streams:
        rva, _ = streams[ST_THREAD]
        for i in range(u32(b, rva)):
            t = rva + 4 + 48 * i
            tid = u32(b, t)
            threads[tid] = (u64(b, t + 24), u32(b, t + 32), u32(b, t + 36))   # stack start, size, rva
    if ST_EXCEPTION in streams:
        rva, _ = streams[ST_EXCEPTION]
        tid = u32(b, rva)
        code, flags = u32(b, rva + 8), u32(b, rva + 12)
        addr = u64(b, rva + 24)
        nparam = u32(b, rva + 32)
        params = [u64(b, rva + 40 + 8 * k) for k in range(min(nparam, 15))]
        mod, offs = where(addr)
        hint = ""
        if mod:
            ex = exports(mod)
            prev = [e for e in ex if e[0] <= offs]
            if prev:
                hint = f" (export gần nhất phía trước: {prev[-1][1]}+0x{offs - prev[-1][0]:X})"
        print(f"NGOẠI LỆ 0x{code:08X} cờ 0x{flags:X} ở 0x{addr:X} = {mod or '?'}+0x{(offs or 0):X}{hint}")
        if code == 0xC0000005 and len(params) >= 2:
            print(f"  access violation: {'ghi' if params[0] == 1 else 'đọc' if params[0] == 0 else 'thực thi'} "
                  f"địa chỉ 0x{params[1]:X}")
        if code == 0xC0000409 and params:
            print(f"  fail-fast mã con {params[0]} (7 = FAST_FAIL_FATAL_APP_EXIT, tức abort())")
        print(f"luồng lỗi {tid} {names.get(tid, '')}; tổng {len(threads)} luồng: "
              + ", ".join(f"{t}{'(' + names[t] + ')' if t in names else ''}" for t in threads))
        if tid in threads and a.quet > 0:
            start, size, srva = threads[tid]
            stack = b[srva: srva + size]
            hits = []
            for k in range(0, len(stack) - 7, 8):
                v = u64(stack, k)
                m, o = where(v)
                if m and o > 0x1000:
                    hits.append(f"{Path(m).name}+0x{o:X}")
                    if len(hits) >= a.quet:
                        break
            print(f"quét ngăn xếp luồng lỗi ({size} B): " + " | ".join(hits))
    else:
        print("không có luồng dữ liệu ngoại lệ")
    if ST_UNLOADED in streams:
        rva, _ = streams[ST_UNLOADED]
        hdr, ent, n = u32(b, rva), u32(b, rva + 4), u32(b, rva + 8)
        un = [mdstring(b, u32(b, rva + hdr + ent * i + 20)) for i in range(n)]
        print(f"module đã gỡ ({n}): " + ", ".join(Path(x).name for x in un[:30]))
    tops = sorted({Path(n).name for _, _, n in mods})
    print("module nạp (" + str(len(tops)) + "): " + ", ".join(tops[:200]))


if __name__ == "__main__":
    main()
