#!/usr/bin/env python3
import argparse
import struct
from pathlib import Path


def align_up(value, alignment):
    return (value + alignment - 1) & ~(alignment - 1)


def read_g4tx_info(g4tx):
    if g4tx[:4] != b"G4TX":
        raise ValueError("Not a G4TX file.")

    header_size = struct.unpack_from("<H", g4tx, 0x04)[0]
    table_size = struct.unpack_from("<I", g4tx, 0x0C)[0]
    texture_data_size = struct.unpack_from("<I", g4tx, 0x2C)[0]

    data_base = align_up(header_size + table_size, 0x10)

    gnf_offset = g4tx.find(b"GNF ", data_base)
    if gnf_offset < 0:
        raise ValueError("Could not find GNF header inside G4TX.")

    gnf_internal_header_size = struct.unpack_from("<I", g4tx, gnf_offset + 4)[0]
    gnf_stub_size = gnf_internal_header_size + 8

    if gnf_offset + gnf_stub_size > len(g4tx):
        raise ValueError("Detected GNF stub size runs past end of G4TX.")

    return {
        "header_size": header_size,
        "table_size": table_size,
        "texture_data_size": texture_data_size,
        "data_base": data_base,
        "gnf_offset": gnf_offset,
        "gnf_stub_size": gnf_stub_size,
    }


def extract_gnf(g4tx_path, g4tg_path, out_path):
    g4tx = Path(g4tx_path).read_bytes()
    g4tg = Path(g4tg_path).read_bytes()

    info = read_g4tx_info(g4tx)

    stub = g4tx[info["gnf_offset"]:info["gnf_offset"] + info["gnf_stub_size"]]
    gnf = stub + g4tg

    Path(out_path).write_bytes(gnf)

    print(f"[OK] Extracted: {out_path}")


def rebuild_pair(original_g4tx_path, edited_gnf_path, out_g4tx_path, out_g4tg_path):
    g4tx = bytearray(Path(original_g4tx_path).read_bytes())
    gnf = Path(edited_gnf_path).read_bytes()

    if gnf[:4] != b"GNF ":
        raise ValueError("Input edited file is not a GNF file.")

    info = read_g4tx_info(g4tx)

    new_stub_size = struct.unpack_from("<I", gnf, 4)[0] + 8
    old_stub_size = info["gnf_stub_size"]

    if new_stub_size != old_stub_size:
        raise ValueError(
            f"Edited GNF stub size changed: old 0x{old_stub_size:X}, new 0x{new_stub_size:X}."
        )

    stub = gnf[:new_stub_size]
    body = gnf[new_stub_size:]

    g4tx[info["gnf_offset"]:info["gnf_offset"] + old_stub_size] = stub

    Path(out_g4tx_path).write_bytes(g4tx)
    Path(out_g4tg_path).write_bytes(body)

    print(f"[OK] Rebuilt: {out_g4tx_path} + {out_g4tg_path}")


def batch_extract(root_dir):
    root = Path(root_dir)

    g4tx_files = list(root.rglob("*.g4tx"))

    if not g4tx_files:
        print("No .g4tx files found.")
        return

    count = 0

    for g4tx_path in g4tx_files:
        base = g4tx_path.with_suffix("")
        g4tg_path = base.with_suffix(".g4tg")

        if not g4tg_path.exists():
            print(f"[SKIP] Missing .g4tg for: {g4tx_path}")
            continue

        out_path = base.with_suffix(".gnf")

        try:
            extract_gnf(g4tx_path, g4tg_path, out_path)
            count += 1
        except Exception as e:
            print(f"[ERROR] {g4tx_path}: {e}")

    print(f"\nDone. Extracted {count} file(s).")


def main():
    parser = argparse.ArgumentParser(
        description="PS4 G4TX/G4TG extract/rebuild"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    ex = sub.add_parser("extract", help="Extract a .gnf from a .g4tx/.g4tg pair.")
    ex.add_argument("g4tx")
    ex.add_argument("g4tg")
    ex.add_argument("out_gnf")

    rb = sub.add_parser("rebuild", help="Split an edited .gnf back into .g4tx/.g4tg.")
    rb.add_argument("original_g4tx")
    rb.add_argument("edited_gnf")
    rb.add_argument("out_g4tx")
    rb.add_argument("out_g4tg")

    bx = sub.add_parser("batch_extract", help="Batch extracts GNF from current directory/subdirectories.")
    bx.add_argument("folder", nargs="?", default=".", help="Root folder (default: current directory)")

    args = parser.parse_args()

    if args.cmd == "extract":
        extract_gnf(args.g4tx, args.g4tg, args.out_gnf)
    elif args.cmd == "rebuild":
        rebuild_pair(args.original_g4tx, args.edited_gnf, args.out_g4tx, args.out_g4tg)
    elif args.cmd == "batch_extract":
        batch_extract(args.folder)


if __name__ == "__main__":
    main()
