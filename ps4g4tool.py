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
    texture_data_size = struct.unpack_from("<I", g4tx, 0x30)[0]

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

    print(f"Extracted: {out_path}")
    print(f"G4TX GNF offset: 0x{info['gnf_offset']:X}")
    print(f"GNF stub size:   0x{info['gnf_stub_size']:X}")
    print(f"G4TG body size:  0x{len(g4tg):X}")
    print(f"Output GNF size: 0x{len(gnf):X}")


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
            f"Edited GNF stub size changed: old 0x{old_stub_size:X}, new 0x{new_stub_size:X}. "
        )

    stub = gnf[:new_stub_size]
    body = gnf[new_stub_size:]

    g4tx[info["gnf_offset"]:info["gnf_offset"] + old_stub_size] = stub

    Path(out_g4tx_path).write_bytes(g4tx)
    Path(out_g4tg_path).write_bytes(body)

    print(f"Rebuilt G4TX: {out_g4tx_path}")
    print(f"Rebuilt G4TG: {out_g4tg_path}")
    print(f"GNF stub size: 0x{new_stub_size:X}")
    print(f"G4TG body size: 0x{len(body):X}")
    print(f"Full GNF size:  0x{len(gnf):X}")


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

    args = parser.parse_args()

    if args.cmd == "extract":
        extract_gnf(args.g4tx, args.g4tg, args.out_gnf)
    elif args.cmd == "rebuild":
        rebuild_pair(args.original_g4tx, args.edited_gnf, args.out_g4tx, args.out_g4tg)


if __name__ == "__main__":
    main()