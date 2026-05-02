import struct
import sys
import re
from pathlib import Path

def u32(data, off):
    return struct.unpack_from("<I", data, off)[0]

def u16(data, off):
    return struct.unpack_from("<H", data, off)[0]

def u8(data, off):
    return data[off]

def align_up(value, align):
    return (value + align - 1) & ~(align - 1)

DXGI_FORMAT = {
    "RGBA8": 28,
    "BC1": 70,
    "BC3": 77,
    "BC7": 98,
}

BC_BLOCK_SIZE = {
    "BC1": 8,
    "BC3": 16,
    "BC7": 16,
    "BC7_UNKNOWN": 16,
}

GNM_SURFACE_FORMAT = {
    0x0A: ("RGBA8", DXGI_FORMAT["RGBA8"]),
    0x23: ("BC1", DXGI_FORMAT["BC1"]),
    0x25: ("BC3", DXGI_FORMAT["BC3"]),
    0x29: ("BC7", DXGI_FORMAT["BC7"]),
}

def safe_filename(name):
    name = name.strip().replace("\x00", "")
    name = re.sub(r'[<>:"/\\\\|?*]', "_", name)
    name = re.sub(r"\s+", "_", name)
    return name or None

def map_gnm_format(reg1):
    surfacefmt = (reg1 >> 20) & 0x3F
    if surfacefmt in GNM_SURFACE_FORMAT:
        label, dxgi = GNM_SURFACE_FORMAT[surfacefmt]
        return dxgi, label
    return DXGI_FORMAT["BC7"], "BC7_UNKNOWN"

def write_dds_dx10(filename, width, height, mipcount, raw_data, dxgi_format):
    header = bytearray(128)
    header[0:4] = b"DDS "
    struct.pack_into("<I", header, 4, 124)
    struct.pack_into("<I", header, 8, 0x00021007)
    struct.pack_into("<I", header, 12, height)
    struct.pack_into("<I", header, 16, width)
    struct.pack_into("<I", header, 20, len(raw_data))
    struct.pack_into("<I", header, 24, 1)
    struct.pack_into("<I", header, 28, mipcount)
    struct.pack_into("<I", header, 76, 32)
    struct.pack_into("<I", header, 80, 0x4)
    header[84:88] = b"DX10"
    struct.pack_into("<I", header, 108, 0x1000)

    dx10 = bytearray(20)
    struct.pack_into("<I", dx10, 0, dxgi_format)
    struct.pack_into("<I", dx10, 4, 3)
    struct.pack_into("<I", dx10, 8, 0)
    struct.pack_into("<I", dx10, 12, 1)
    struct.pack_into("<I", dx10, 16, 0)

    with open(filename, "wb") as f:
        f.write(header)
        f.write(dx10)
        f.write(raw_data)

def write_dds_rgba8(filename, width, height, mipcount, raw_data):
    header = bytearray(128)

    header[0:4] = b"DDS "
    struct.pack_into("<I", header, 4, 124)

    # DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PITCH | DDSD_PIXELFORMAT
    struct.pack_into("<I", header, 8, 0x0000100F)

    struct.pack_into("<I", header, 12, height)
    struct.pack_into("<I", header, 16, width)
    struct.pack_into("<I", header, 20, width * 4)
    struct.pack_into("<I", header, 24, 1)
    struct.pack_into("<I", header, 28, mipcount)

    # DDS_PIXELFORMAT
    struct.pack_into("<I", header, 76, 32)
    struct.pack_into("<I", header, 80, 0x41)  # DDPF_RGB | DDPF_ALPHAPIXELS
    struct.pack_into("<I", header, 88, 32)

    # Raw data layout is RGBA8.
    struct.pack_into("<I", header, 92, 0x000000FF)
    struct.pack_into("<I", header, 96, 0x0000FF00)
    struct.pack_into("<I", header, 100, 0x00FF0000)
    struct.pack_into("<I", header, 104, 0xFF000000)

    struct.pack_into("<I", header, 108, 0x1000)

    with open(filename, "wb") as f:
        f.write(header)
        f.write(raw_data)

def read_dds(path):
    data = Path(path).read_bytes()

    if data[:4] != b"DDS ":
        raise ValueError("Not a DDS file")

    height = u32(data, 12)
    width = u32(data, 16)
    mipcount = u32(data, 28)

    fourcc = data[84:88]

    if fourcc == b"DX10":
        dxgi = u32(data, 128)
        payload = data[148:]
        return width, height, mipcount, dxgi, payload

    pf_flags = u32(data, 80)
    rgb_bit_count = u32(data, 88)
    r_mask = u32(data, 92)
    g_mask = u32(data, 96)
    b_mask = u32(data, 100)
    a_mask = u32(data, 104)

    if (
        (pf_flags & 0x40)
        and rgb_bit_count == 32
        and r_mask == 0x000000FF
        and g_mask == 0x0000FF00
        and b_mask == 0x00FF0000
        and a_mask == 0xFF000000
    ):
        return width, height, mipcount, DXGI_FORMAT["RGBA8"], data[128:]

    raise ValueError("Unsupported DDS format. Expected DX10 BC DDS or legacy RGBA8 DDS.")

def compute_pixel_index_thin_micro(x, y):
    x0 = (x >> 0) & 1
    x1 = (x >> 1) & 1
    x2 = (x >> 2) & 1
    y0 = (y >> 0) & 1
    y1 = (y >> 1) & 1
    y2 = (y >> 2) & 1

    return x0 | (y0 << 1) | (x1 << 2) | (y1 << 3) | (x2 << 4) | (y2 << 5)

def compute_microtiled_addr_1d_thin(x, y, bpp, pitch, height):
    micro_tile_width = 8
    micro_tile_pixels = 64

    micro_tile_bytes = (micro_tile_pixels * bpp + 7) // 8
    micro_tiles_per_row = pitch // micro_tile_width

    micro_tile_index_x = x // micro_tile_width
    micro_tile_index_y = y // micro_tile_width

    micro_tile_offset = (
        (micro_tile_index_y * micro_tiles_per_row + micro_tile_index_x)
        * micro_tile_bytes
    )

    pixel_index = compute_pixel_index_thin_micro(x, y)
    elem_offset = (pixel_index * bpp) // 8

    return micro_tile_offset + elem_offset

def deswizzle_bc_1d_thin(data, width, height, pitch_pixels, block_bytes):
    elem_w = (width + 3) // 4
    elem_h = (height + 3) // 4
    bpp = block_bytes * 8

    src_pitch_elems = align_up(max((pitch_pixels + 3) // 4, 1), 8)
    src_height_elems = align_up(max((align_up(height, 8) + 3) // 4, 1), 8)

    out = bytearray(elem_w * elem_h * block_bytes)

    for y in range(elem_h):
        for x in range(elem_w):
            src_off = compute_microtiled_addr_1d_thin(
                x, y, bpp, src_pitch_elems, src_height_elems
            )
            dst_off = (y * elem_w + x) * block_bytes

            if src_off + block_bytes <= len(data):
                out[dst_off:dst_off + block_bytes] = data[src_off:src_off + block_bytes]

    return bytes(out)

def swizzle_bc_1d_thin(linear_data, width, height, pitch_pixels, block_bytes, swizzled_size):
    elem_w = (width + 3) // 4
    elem_h = (height + 3) // 4
    bpp = block_bytes * 8

    dst_pitch_elems = align_up(max((pitch_pixels + 3) // 4, 1), 8)
    dst_height_elems = align_up(max((align_up(height, 8) + 3) // 4, 1), 8)

    out = bytearray(swizzled_size)

    for y in range(elem_h):
        for x in range(elem_w):
            src_off = (y * elem_w + x) * block_bytes
            dst_off = compute_microtiled_addr_1d_thin(
                x, y, bpp, dst_pitch_elems, dst_height_elems
            )

            if src_off + block_bytes <= len(linear_data) and dst_off + block_bytes <= len(out):
                out[dst_off:dst_off + block_bytes] = linear_data[src_off:src_off + block_bytes]

    return bytes(out)

def deswizzle_rgba8_1d_thin(data, width, height, pitch_pixels):
    bpp = 32
    bytes_per_pixel = 4

    src_pitch = align_up(pitch_pixels, 8)
    src_height = align_up(height, 8)

    out = bytearray(width * height * bytes_per_pixel)

    for y in range(height):
        for x in range(width):
            src_off = compute_microtiled_addr_1d_thin(x, y, bpp, src_pitch, src_height)
            dst_off = (y * width + x) * bytes_per_pixel

            if src_off + bytes_per_pixel <= len(data):
                out[dst_off:dst_off + bytes_per_pixel] = data[src_off:src_off + bytes_per_pixel]

    return bytes(out)

def swizzle_rgba8_1d_thin(linear_data, width, height, pitch_pixels, swizzled_size):
    bpp = 32
    bytes_per_pixel = 4

    dst_pitch = align_up(pitch_pixels, 8)
    dst_height = align_up(height, 8)

    out = bytearray(swizzled_size)

    for y in range(height):
        for x in range(width):
            src_off = (y * width + x) * bytes_per_pixel
            dst_off = compute_microtiled_addr_1d_thin(x, y, bpp, dst_pitch, dst_height)

            if src_off + bytes_per_pixel <= len(linear_data) and dst_off + bytes_per_pixel <= len(out):
                out[dst_off:dst_off + bytes_per_pixel] = linear_data[src_off:src_off + bytes_per_pixel]

    return bytes(out)

def parse_gnm_texture(data, off):
    data_offset = u32(data, off + 0)
    reg1 = u32(data, off + 4)
    reg2 = u32(data, off + 8)

    width = ((reg2 >> 0) & 0x3FFF) + 1
    height = ((reg2 >> 14) & 0x3FFF) + 1

    reg3 = u32(data, off + 12)
    lastlevel = (reg3 >> 16) & 0xF
    tiling = (reg3 >> 20) & 0x1F
    pow2pad = (reg3 >> 25) & 0x1
    tex_type = (reg3 >> 28) & 0xF

    reg4 = u32(data, off + 16)
    depth = ((reg4 >> 0) & 0x1FFF) + 1
    pitch = ((reg4 >> 13) & 0x3FFF) + 1

    texture_size = u32(data, off + 28)

    return {
        "width": width,
        "height": height,
        "depth": depth,
        "pitch": pitch,
        "mips": lastlevel + 1,
        "tiling": tiling,
        "pow2pad": pow2pad,
        "type": tex_type,
        "data_offset": data_offset,
        "texture_size": texture_size,
        "reg1": reg1,
    }

def parse_gnf_header(data):
    if data[:4] != b"GNF ":
        raise ValueError("Internal data is not a GNF file")

    content_size = u32(data, 4)
    version = u8(data, 8)
    tex_count = u8(data, 9)
    alignment = u8(data, 10)
    data_start = 8 + content_size

    return content_size, version, tex_count, alignment, data_start

def read_g4tx_info(g4tx):
    if g4tx[:4] != b"G4TX":
        raise ValueError("Not a G4TX file")

    header_size = u16(g4tx, 0x04)
    table_size = u32(g4tx, 0x0C)
    texture_count = u16(g4tx, 0x20)
    texture_data_size = u32(g4tx, 0x2C)

    data_base = align_up(header_size + table_size, 0x10)
    gnf_offset = g4tx.find(b"GNF ", data_base)

    if gnf_offset < 0:
        raise ValueError("Could not find GNF header inside G4TX")

    gnf_internal_header_size = u32(g4tx, gnf_offset + 4)
    gnf_stub_size = gnf_internal_header_size + 8

    if gnf_offset + gnf_stub_size > len(g4tx):
        raise ValueError("Detected GNF stub runs past end of G4TX")

    return {
        "header_size": header_size,
        "table_size": table_size,
        "texture_count": texture_count,
        "texture_data_size": texture_data_size,
        "data_base": data_base,
        "gnf_offset": gnf_offset,
        "gnf_stub_size": gnf_stub_size,
    }

def read_g4tx_names(g4tx):
    info = read_g4tx_info(g4tx)
    count = info["texture_count"]

    scan_start = info["header_size"]
    scan_end = info["gnf_offset"]
    blob = g4tx[scan_start:scan_end]

    names = []

    for m in re.finditer(rb"[A-Za-z0-9_]{3,}\x00", blob):
        raw = m.group()[:-1]

        try:
            name = raw.decode("ascii")
        except UnicodeDecodeError:
            continue

        if "_" not in name:
            continue

        clean = safe_filename(name)

        if clean and clean not in names:
            names.append(clean)

    return names[:count]

def build_gnf_from_g4tx_pair(g4tx_path):
    g4tx_path = Path(g4tx_path)
    g4tg_path = g4tx_path.with_suffix(".g4tg")

    if not g4tg_path.exists():
        raise FileNotFoundError(f"Missing matching G4TG file: {g4tg_path}")

    g4tx = g4tx_path.read_bytes()
    g4tg = g4tg_path.read_bytes()

    info = read_g4tx_info(g4tx)
    stub = g4tx[info["gnf_offset"]:info["gnf_offset"] + info["gnf_stub_size"]]
    names = read_g4tx_names(g4tx)

    return stub + g4tg, names, g4tx, info

def output_dds_name(g4tx_path, index, label, names, used_names):
    file_stem = Path(g4tx_path).stem
    tex_name = names[index] if index < len(names) and names[index] else None

    if tex_name:
        stem = tex_name
    else:
        stem = file_stem

    if not stem.startswith(file_stem):
        stem = f"{file_stem}_{stem}"

    if stem in used_names:
        stem = f"{stem}_{index}"

    used_names.add(stem)
    return f"{index}_{stem}.dds"

def find_replacement_dds(g4tx_path, index, label):
    folder = Path(g4tx_path).parent
    stem = Path(g4tx_path).stem

    preferred_patterns = [
        f"{index}_{stem}.dds",
        f"{index}_{stem}_*.dds",
        f"{index:02d}_{stem}.dds",
        f"{index:02d}_{stem}_*.dds",
    ]

    for pattern in preferred_patterns:
        matches = sorted(folder.glob(pattern))
        if matches:
            return matches[0]

    fallback_patterns = [
        f"{index}_*.dds",
        f"{index:02d}_*.dds",
    ]

    fallback_matches = []
    for pattern in fallback_patterns:
        fallback_matches.extend(sorted(folder.glob(pattern)))

    fallback_matches = sorted(set(fallback_matches))

    if len(fallback_matches) == 1:
        return fallback_matches[0]

    if len(fallback_matches) > 1:
        print(
            f"Texture {index}: multiple possible DDS files found; "
            f"expected one matching '{index}_{stem}.dds'"
        )

    return None

def extract_g4tx_pair(path):
    path = Path(path)

    gnf, names, _g4tx, _info = build_gnf_from_g4tx_pair(path)

    content_size, version, tex_count, alignment, data_start = parse_gnf_header(gnf)

    print(f"Version: {version}")
    print(f"Textures: {tex_count}")
    print(f"Output folder: {path.parent}")
    print("-" * 40)

    used_names = set()

    for i in range(tex_count):
        tex = parse_gnm_texture(gnf, 0x10 + i * 0x20)
        dxgi, label = map_gnm_format(tex["reg1"])

        offset = data_start + tex["data_offset"]
        raw = gnf[offset:offset + tex["texture_size"]]

        print(f"Texture {i}: {tex['width']}x{tex['height']} {label}")

        if label in BC_BLOCK_SIZE and tex["tiling"] == 13:
            raw_out = deswizzle_bc_1d_thin(
                raw,
                tex["width"],
                tex["height"],
                tex["pitch"],
                BC_BLOCK_SIZE[label],
            )
        elif label == "RGBA8" and tex["tiling"] == 13:
            raw_out = deswizzle_rgba8_1d_thin(
                raw,
                tex["width"],
                tex["height"],
                tex["pitch"],
            )
        else:
            raw_out = raw

        filename = output_dds_name(path, i, label, names, used_names)
        out_path = path.parent / filename

        if label == "RGBA8":
            write_dds_rgba8(out_path, tex["width"], tex["height"], tex["mips"], raw_out)
        else:
            write_dds_dx10(out_path, tex["width"], tex["height"], tex["mips"], raw_out, dxgi)

        print(f"  -> {out_path}")

def validate_dds_for_texture(g4tx_path, tex, index):
    dxgi, label = map_gnm_format(tex["reg1"])
    dds_path = find_replacement_dds(g4tx_path, index, label)

    errors = []
    warnings = []

    if not dds_path:
        warnings.append("No replacement DDS found")
        return False, warnings, errors

    try:
        width, height, mipcount, dds_dxgi, linear_payload = read_dds(dds_path)
    except Exception as e:
        errors.append(f"Could not read DDS: {e}")
        return True, warnings, errors

    if width != tex["width"] or height != tex["height"]:
        errors.append(
            f"Dimensions mismatch: DDS {width}x{height}, expected {tex['width']}x{tex['height']}"
        )

    if dds_dxgi != dxgi:
        errors.append(f"DXGI mismatch: DDS {dds_dxgi}, expected {dxgi} ({label})")

    if mipcount != tex["mips"]:
        errors.append(f"Mip count mismatch: DDS {mipcount}, expected {tex['mips']}")

    if label not in BC_BLOCK_SIZE and label != "RGBA8":
        errors.append(f"Unsupported import format: {label}")

    if tex["tiling"] != 13:
        errors.append(f"Unsupported tiling mode: {tex['tiling']}")

    if label in BC_BLOCK_SIZE:
        block_bytes = BC_BLOCK_SIZE[label]
        expected_linear_size = (
            ((tex["width"] + 3) // 4) *
            ((tex["height"] + 3) // 4) *
            block_bytes
        )

        if len(linear_payload) != expected_linear_size:
            errors.append(
                f"Payload size mismatch: DDS 0x{len(linear_payload):X}, expected 0x{expected_linear_size:X}"
            )

    elif label == "RGBA8":
        expected_linear_size = tex["width"] * tex["height"] * 4

        if len(linear_payload) != expected_linear_size:
            errors.append(
                f"Payload size mismatch: DDS 0x{len(linear_payload):X}, expected 0x{expected_linear_size:X}"
            )

    return True, warnings, errors

def validate_g4tx_pair(path):
    path = Path(path)
    gnf, _names, _original_g4tx, _info = build_gnf_from_g4tx_pair(path)

    _content_size, _version, tex_count, _alignment, _data_start = parse_gnf_header(gnf)

    print(f"Validating: {path}")
    print(f"Textures: {tex_count}")
    print("-" * 40)

    found = 0
    warnings_total = 0
    errors_total = 0

    for i in range(tex_count):
        tex = parse_gnm_texture(gnf, 0x10 + i * 0x20)
        _dxgi, label = map_gnm_format(tex["reg1"])
        dds_path = find_replacement_dds(path, i, label)

        print(f"Texture {i}: {tex['width']}x{tex['height']} {label}")

        exists, warnings, errors = validate_dds_for_texture(path, tex, i)

        if dds_path:
            print(f"  DDS: {dds_path.name}")

        if exists:
            found += 1

        for warning in warnings:
            warnings_total += 1
            print(f"  [WARN] {warning}")

        for error in errors:
            errors_total += 1
            print(f"  [ERROR] {error}")

        if exists and not warnings and not errors:
            print("  [OK] Valid")

    print("-" * 40)
    print(f"DDS files found: {found}/{tex_count}")
    print(f"Warnings: {warnings_total}")
    print(f"Errors: {errors_total}")

    if errors_total:
        print("Result: FAILED")
        return False

    print("Result: OK")
    return True

def import_textures_into_gnf_bytes(g4tx_path, gnf_bytes):
    data = bytearray(gnf_bytes)
    _content_size, _version, tex_count, _alignment, data_start = parse_gnf_header(data)

    replaced = 0

    for i in range(tex_count):
        tex = parse_gnm_texture(data, 0x10 + i * 0x20)
        dxgi, label = map_gnm_format(tex["reg1"])

        dds_path = find_replacement_dds(g4tx_path, i, label)

        if not dds_path:
            print(f"Texture {i}: no replacement DDS found, skipping")
            continue

        exists, warnings, errors = validate_dds_for_texture(g4tx_path, tex, i)
        if errors:
            raise ValueError(f"Texture {i}: validation failed: {'; '.join(errors)}")

        width, height, mipcount, dds_dxgi, linear_payload = read_dds(dds_path)

        if label in BC_BLOCK_SIZE:
            block_bytes = BC_BLOCK_SIZE[label]

            swizzled = swizzle_bc_1d_thin(
                linear_payload,
                tex["width"],
                tex["height"],
                tex["pitch"],
                block_bytes,
                tex["texture_size"],
            )
        elif label == "RGBA8":
            swizzled = swizzle_rgba8_1d_thin(
                linear_payload,
                tex["width"],
                tex["height"],
                tex["pitch"],
                tex["texture_size"],
            )
        else:
            raise ValueError(f"Texture {i}: unsupported import format {label}")

        file_offset = data_start + tex["data_offset"]

        if file_offset + tex["texture_size"] > len(data):
            raise ValueError(f"Texture {i}: target write exceeds internal GNF size")

        data[file_offset:file_offset + tex["texture_size"]] = swizzled

        replaced += 1
        print(f"Texture {i}: replaced from {dds_path}")

    return bytes(data), replaced, tex_count

def import_g4tx_pair(path):
    path = Path(path)
    g4tg_path = path.with_suffix(".g4tg")

    gnf, _names, original_g4tx, info = build_gnf_from_g4tx_pair(path)

    edited_gnf, replaced, tex_count = import_textures_into_gnf_bytes(path, gnf)

    new_stub_size = u32(edited_gnf, 4) + 8
    old_stub_size = info["gnf_stub_size"]

    if new_stub_size != old_stub_size:
        raise ValueError(
            f"Internal GNF stub size changed: old 0x{old_stub_size:X}, new 0x{new_stub_size:X}"
        )

    stub = edited_gnf[:new_stub_size]
    body = edited_gnf[new_stub_size:]

    rebuilt_g4tx = bytearray(original_g4tx)
    rebuilt_g4tx[info["gnf_offset"]:info["gnf_offset"] + old_stub_size] = stub

    out_g4tx = path.with_name(f"{path.stem}_repacked.g4tx")
    out_g4tg = g4tg_path.with_name(f"{g4tg_path.stem}_repacked.g4tg")

    out_g4tx.write_bytes(rebuilt_g4tx)
    out_g4tg.write_bytes(body)

    print("-" * 40)
    print(f"Done. Replaced {replaced}/{tex_count} textures.")
    print(f"Output G4TX: {out_g4tx}")
    print(f"Output G4TG: {out_g4tg}")

def batch_extract(root):
    root = Path(root)
    g4tx_files = sorted(root.rglob("*.g4tx"))
    g4tx_files = [p for p in g4tx_files if not p.stem.endswith("_repacked")]

    processed = 0

    for g4tx_path in g4tx_files:
        g4tg_path = g4tx_path.with_suffix(".g4tg")

        if not g4tg_path.exists():
            print(f"[SKIP] Missing G4TG: {g4tx_path}")
            continue

        try:
            print(f"\n[EXTRACT] {g4tx_path}")
            extract_g4tx_pair(g4tx_path)
            processed += 1
        except Exception as e:
            print(f"[ERROR] {g4tx_path}: {e}")

    print("-" * 40)
    print(f"Batch extract complete. Processed {processed}/{len(g4tx_files)} G4TX file(s).")

def batch_import(root):
    root = Path(root)
    g4tx_files = sorted(root.rglob("*.g4tx"))
    g4tx_files = [p for p in g4tx_files if not p.stem.endswith("_repacked")]

    processed = 0

    for g4tx_path in g4tx_files:
        g4tg_path = g4tx_path.with_suffix(".g4tg")

        if not g4tg_path.exists():
            print(f"[SKIP] Missing G4TG: {g4tx_path}")
            continue

        try:
            print(f"\n[IMPORT] {g4tx_path}")
            import_g4tx_pair(g4tx_path)
            processed += 1
        except Exception as e:
            print(f"[ERROR] {g4tx_path}: {e}")

    print("-" * 40)
    print(f"Batch import complete. Processed {processed}/{len(g4tx_files)} G4TX file(s).")

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python ykps4tool.py extract file.g4tx")
        print("  python ykps4tool.py validate file.g4tx")
        print("  python ykps4tool.py import file.g4tx")
        print("  python ykps4tool.py batch_extract [folder]")
        print("  python ykps4tool.py batch_import [folder]")
        sys.exit(1)

    mode = sys.argv[1].lower()

    if mode in ("batch_extract", "batch_import"):
        root = sys.argv[2] if len(sys.argv) >= 3 else "."
        if mode == "batch_extract":
            batch_extract(root)
        else:
            batch_import(root)
        return

    if len(sys.argv) < 3:
        print("Missing input .g4tx file.")
        sys.exit(1)

    path = sys.argv[2]

    if not path.lower().endswith(".g4tx"):
        print("Input must be a .g4tx file. Matching .g4tg must be beside it.")
        sys.exit(1)

    if mode == "extract":
        extract_g4tx_pair(path)
    elif mode == "validate":
        ok = validate_g4tx_pair(path)
        if not ok:
            sys.exit(1)
    elif mode == "import":
        import_g4tx_pair(path)
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)

if __name__ == "__main__":
    main()
