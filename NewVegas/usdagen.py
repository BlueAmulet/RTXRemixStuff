import os
import sys
import math
import argparse
import xxhash
import difflib
import json
import contextlib

# PyFFI required to process NIF

# Version of PyFFI on pypi is old, work around time.clock() removal
import time
time.clock = time.time

try:
    from pyffi.formats.nif import NifFormat
    from concurrent.futures import ProcessPoolExecutor, as_completed
    have_PyFFI = True
except:
    print('Warning: PyFFI not installed, NIF parsing disabled')
    have_PyFFI = False

# Prevent import warnings for sub processes
if __name__ == '__main__':
    try:
        from tqdm import tqdm
        pbprint = tqdm.write
        have_tqdm = True
    except:
        print('Warning: tqdm not installed, no progress bars will be shown')
        pbprint = print
        have_tqdm = False

    # PIL required to process DDS
    try:
        from PIL import Image, ImageChops
        have_PIL = True
    except:
        print('Warning: Pillow not installed, normal map reflectivity disabled')
        have_PIL = False


# Map suffix to asset inputs
extensions = {
'_n': 'normalmap_texture',
'_em': 'metallic_texture',
'_m': 'metallic_texture',
'_g': 'emissive_mask_texture'
}

# The suffixes are not always consistent
overrides = {
'textures/architecture/chandelier/chandelier.dds': {'_g': '_m'},
'textures/architecture/freeside/atomicwranglersign.dds': {'_g': '_m'},
'textures/architecture/goodsprings/nv_storeglass.dds': {'_g': '_e'},
'textures/architecture/mccarran/mcglass.dds': {'_m': '_g'},
'textures/architecture/strip/l38glass.dds': {'_m': '_g'},
'textures/architecture/strip/l38metal01.dds': {'_m': '_g'},
'textures/architecture/strip/lucky38sign.dds': {'_g': '_m'},
'textures/architecture/strip/newvegassign01.dds': {'_g': '_m'},
'textures/architecture/strip/newvegassign02.dds': {'_g': '_m'},
'textures/architecture/strip/nv_thetops-metal01.dds': {'_m': '_e'},
'textures/architecture/strip/nv_thetops-metal02.dds': {'_m': '_e'},
'textures/architecture/strip/nv_thetops-sign01.dds': {'_g': '_m'},
'textures/architecture/strip/nv_thetops-sign03.dds': {'_g': '_m'},
'textures/architecture/strip/nv_thetopswl02.dds': {'_m': '_e'},
'textures/architecture/strip/nv_vault21-sign02.dds': {'_g': '_m'},
'textures/architecture/strip/nv_vault21_sign03.dds': {'_g': '_m'},
'textures/architecture/strip/nv_vault21_sign04.dds': {'_g': '_m'},
'textures/architecture/strip/silverrushsign.dds': {'_g': '_m'},
'textures/armor/headgear/vaultsecurityhelmetm.dds': {'_e': '_m'},
'textures/clutter/graves/gravelantern01.dds': {'_m': '_g'},
'textures/clutter/lights/gomorrahhanginglanternglass.dds': {'_g': '_e'},
'textures/clutter/open_24hours_sign/nv_24-sign.dds': {'_g': '_e'},
'textures/dlc03/architecture/andrewsbase/dlc03aircontroldetails01.dds': {'_m': '_e'},
'textures/dungeons/caves/caverockwall03.dds': {'_g': '_p'},
'textures/dungeons/nvgamorrah/nvgamorrahkit.dds': {'_m': '_g'},
'textures/dungeons/nvgamorrah/nvgamorrahkit02.dds': {'_m': '_g'},
'textures/dungeons/nvhooverdam/generator01.dds': {'_g': '_m', '_m': '_e'},
'textures/dungeons/nvlucky38/nvpenthouse01.dds': {'_m': '_s'},
'textures/weapons/2handrifle/rechargerrifle.dds': {'_g': '_m'}
}

# These normals are just flat normals
blacklist = [
'textures/shared/flat_n.dds',
'textures/shared/shadefade01_n.dds',
'textures/shared/shadefade01lod_n.dds',
'textures/shared/shadefade03_n.dds',
]


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

def calculate_hash(file_path):
    if not os.path.exists(file_path):
        return None
    with open(file_path, 'rb') as file:
        data = file.read()

    # Extract info from the DDS header
    dwHeight = int.from_bytes(data[12:16], 'little')
    dwWidth  = int.from_bytes(data[16:20], 'little')
    pfFlags  = int.from_bytes(data[80:84], 'little')
    pfFourCC = data[84:88]
    bitCount = int.from_bytes(data[88:92], 'little')

    # Calculate mipmap size
    mipsize = dwWidth*dwHeight
    if pfFlags & 0x4: # DDPF_FOURCC
        if pfFourCC == b'DXT1': # DXT1 is 4bpp
            mipsize //= 2
    elif pfFlags & 0x20242: # DDPF_ALPHA | DDPF_RGB | DDPF_YUV | DDPF_LUMINANCE
        mipsize = mipsize*bitCount//8

    # Calculate hash of the first mipmap
    return xxhash.xxh3_64(data[128:128+mipsize]).hexdigest().upper()

def u32(num):
    return num.to_bytes(4, 'little')

def write_dds(file_name, img):
    width, height = img.size
    channels = len(img.getbands())
    mipmaps = int(math.log2(min(width, height)))+1
    if channels != 1 and channels != 4:
        raise NotImplementedError(f'Writing {channels} channel DDS unsupported')
    with open(file_name, 'wb') as f:
        # Header
        f.write(b'DDS ') # ID
        f.write(u32(124)) # Header size
        f.write(b'\x0F\x10\x02\x00') # Flags (Caps, Height, Width, Pitch, PixelFormat, MipMaps)
        f.write(u32(height)) # Height
        f.write(u32(width)) # Width
        f.write(u32(width * channels)) # Pitch
        f.write(u32(1)) # Depth
        f.write(u32(mipmaps)) # MipMaps
        f.write(b'\0' * 44) # Reserved
        # Pixel format
        f.write(u32(32)) # Format header size
        f.write(b'\x04\x00\x00\x00') # Format flags (Single channel uncompressed)
        f.write(b'DX10') # FourCC
        f.write(b'\0' * 20) # Bit count and R G B A masks
        f.write(b'\x08\x10\x40\x00') # Caps (Complex, Texture, MipMaps)
        f.write(b'\0' * 16) # Extra caps and reserved
        # DX10 Header
        if channels == 1:
            f.write(u32(61)) # R8_UNORM
        elif channels == 4:
            f.write(u32(28)) # R8G8B8A8_UNORM
        f.write(u32(3)) # Texture2D resource
        f.write(u32(0)) # Misc flags
        f.write(u32(1)) # Array size
        f.write(u32(0)) # Misc flags 2
        # Write image data
        for i in range(1, mipmaps+1):
            f.write(img.tobytes('raw'))
            if i != mipmaps:
                img = img.resize((img.size[0] // 2, img.size[1] // 2), resample=Image.BILINEAR)

def clean_path(path):
    path = os.path.normpath(path.decode('utf-8')).lower().replace('\\', '/')
    if path.startswith('data/'):
        path = path[5:]
    return path

def process_nif(fname):
    input_names = ['_d', '_n', '_g', '_p', '_e', '_m']
    result = []
    try:
        with open(fname, 'rb') as f:
            data = NifFormat.Data()
            data.read(f)
            for nifroot in data.roots:
                for block in nifroot.tree():
                    if isinstance(block, NifFormat.BSShaderTextureSet):
                        inputs = {}
                        for i in range(1, 6):
                            if block.textures[i] != b'':
                                texture = clean_path(block.textures[i])
                                if texture not in blacklist:
                                    inputs[input_names[i]] = texture
                        result.append((clean_path(block.textures[0]), inputs))
    except:
        pass
    return result

def relpathstd(path, start=''):
    return os.path.relpath(path, start).lower().replace('\\', '/')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Generates a USDA to load the game's various textures.")
    parser.add_argument('-t', '--textures', help='The textures folder to search through', required=True)
    parser.add_argument('-m', '--meshes', help='The meshes folder to search through')
    parser.add_argument('-hm', '--hashes', help='Texture hash mapping list')
    parser.add_argument('-o', '--output', help='The USDA file to write', required=True)
    parser.add_argument('-nc', '--no-use-cache', help="Don't use nifmap.json if present", action='store_true')
    parser.add_argument('-ng', '--no-generate', help="Don't generate additional textures", action='store_true')
    args = parser.parse_args()

    # Validate inputs
    if not os.path.isdir(args.textures):
        eprint(f'Error: {args.textures}: No such directory')
        sys.exit(1)

    if args.meshes is not None:
        if not os.path.isdir(args.meshes):
            eprint(f'Error: {args.meshes}: No such directory')
            sys.exit(1)
        if not have_PyFFI:
            print('Warning: meshes folder given but PyFFI not installed')

    hashfiles = []
    if args.hashes is not None:
        hashfiles = [x.strip() for x in args.hashes.split(',')]
        for hashfile in hashfiles:
            if not os.path.isfile(hashfile):
                eprint(f'Error: {hashfile}: No such file')
                sys.exit(1)

    if os.path.basename(args.textures).lower() == 'textures':
        txrdir = args.textures
        rootdir = os.path.dirname(args.textures)
    elif os.path.isdir(os.path.join(args.textures, 'textures')):
        txrdir = os.path.join(args.textures, 'textures')
        rootdir = args.textures
    else:
        eprint(f'Error: Failed to locate a folder named "textures"')
        sys.exit(1)

    # Nif parsing is slow, use a cache if present
    if os.path.exists('nifmap.json') and not args.no_use_cache:
        with open('nifmap.json') as f:
            nifmap = json.load(f)
        print('Loaded nif texture mapping from nifmap.json')
    else:
        nifmap = {}
        if have_PyFFI and args.meshes is not None:
            # Gather a list of all .nif files
            niflist = []
            for root, _, files in os.walk(args.meshes):
                for file in files:
                    fname = os.path.join(root, file)
                    if fname.lower().endswith('.nif'):
                        niflist.append(fname)

            # Process all .nif using multiple cores
            print('Processing .nif files')
            with tqdm(total=len(niflist)) if have_tqdm else contextlib.nullcontext() as pbar:
                with ProcessPoolExecutor() as ex:
                    for future in as_completed([ex.submit(process_nif, fname) for fname in niflist]):
                        try:
                            for diffuse, inputs in future.result():
                                if diffuse in nifmap:
                                    current = nifmap[diffuse]
                                    if any(k not in current or current[k] != inputs[k] for k in inputs):
                                        # Merge the sets together
                                        pbprint(f'Warning: {diffuse} has multiple texture sets')
                                        for input in inputs:
                                            if input not in current:
                                                current[input] = inputs[input]
                                            else:
                                                # Use whatever texture is closest to the diffuse
                                                current[input] = difflib.get_close_matches(diffuse, [current[input], inputs[input]], n=1, cutoff=0)[0]
                                else:
                                    nifmap[diffuse] = inputs
                        except:
                            pass
                        if pbar is not None:
                            pbar.update(1)

            # Write map as json cache
            print('Saving nif texture mapping to nifmap.json')
            with open('nifmap.json', 'w') as f:
                json.dump(nifmap, f, indent='\t')

    # Load texture hash map if given
    hashmap = {}
    for hashfile in hashfiles:
        print(f'Loading hash map {hashfile}')
        with open(hashfile) as f:
            for line in f:
                parts = line.split(' ', 1)
                if len(parts) != 2 or len(parts[0]) != 18 or not parts[0].lower().startswith('0x'):
                    eprint(f'Error: Malform texture hash line: {line}')
                    sys.exit(1)
                hashmap[relpathstd(parts[1].rstrip())] = parts[0][2:].upper()

    # Write USDA
    materials = 0
    textures = 0
    generated = 0
    print(f'Writing {args.output}')
    with open(args.output, 'w') as f:
        # Write USDA header
        f.write('#usda 1.0\nover "RootNode"\n{\n\tover "Looks"\n\t{\n')

        # Gather a list of all .dds files
        ddslist = []
        for root, _, files in os.walk(txrdir):
            for file in files:
                fname = os.path.join(root, file)
                if fname.lower().endswith('.dds'):
                    ddslist.append(fname)

        # Search through the textures folder
        if ddslist:
            used_hashes = {}
            for fname in (tqdm if have_tqdm else lambda x: x)(ddslist):
                diffuse_path = relpathstd(fname, rootdir)
                fname_noext = os.path.splitext(fname)[0].removesuffix('_d') # Some diffuse end in _d

                # Look for extra inputs
                if diffuse_path in nifmap:
                    inputs = nifmap[diffuse_path]
                else:
                    inputs = {}
                    for ext in extensions:
                        file_ext = ext
                        if fname in overrides and ext in overrides[fname]:
                            file_ext = overrides[fname][ext]
                        extra_file = fname_noext + file_ext + '.dds'
                        if os.path.exists(extra_file):
                            input_path = relpathstd(extra_file, rootdir)
                            if input_path not in blacklist:
                                inputs[ext] = input_path
                textures += len(inputs)

                if inputs:
                    # Calculate hashes of textures
                    if diffuse_path in hashmap:
                        diffuse_hash = hashmap[diffuse_path]
                    else:
                        diffuse_hash = calculate_hash(fname)
                    hashes = {}
                    paths = {}
                    for ext in inputs:
                        paths[ext] = os.path.join(rootdir, inputs[ext])
                        if inputs[ext] in hashmap:
                            hashes[ext] = hashmap[inputs[ext]]
                        else:
                            hashes[ext] = calculate_hash(paths[ext])

                    # Check for duplicates
                    input_set = tuple(inputs.values())
                    hash_set = tuple(hashes.values())
                    if diffuse_hash in used_hashes:
                        # Check if duplicate is different
                        if used_hashes[diffuse_hash][1] != hash_set:
                            pbprint(f'Warning: Conflicting hash {diffuse_hash}: {used_hashes[diffuse_hash]} != {input_set, hash_set}')
                    else:
                        # No duplicate, write to usda
                        materials += 1
                        used_hashes[diffuse_hash] = (input_set, hash_set)

                        # Split alpha off of normal map and invert as roughness map
                        if not args.no_generate and have_PIL and '_n' in inputs and os.path.exists(paths['_n']):
                            # DXT1 has 1 bit alpha, which is unsuitable for a specular map, ignore
                            with open(paths['_n'], 'rb') as dds:
                                dds.seek(84)
                                not_dxt1 = dds.read(4) != b'DXT1'
                            if not_dxt1:
                                with Image.open(paths['_n']) as img:
                                    if 'A' in img.mode:
                                        normal_noext = os.path.splitext(inputs['_n'])[0].removesuffix('_n')
                                        fname_reflect = os.path.join('generated', normal_noext + '_r.dds').replace('\\', '/')
                                        inputs['reflect'] = fname_reflect
                                        os.makedirs(os.path.dirname(fname_reflect), exist_ok=True)
                                        write_dds(fname_reflect, ImageChops.invert(img.getchannel('A')))
                                        generated += 1
                                    else:
                                        pbprint(f'Warning: {inputs["_n"]}: expected alpha in mode, found {img.mode}')

                        # Convert masked emission to additive emission
                        if not args.no_generate and have_PIL and '_g' in inputs and os.path.exists(paths['_g']):
                            with Image.open(fname) as img_d:
                                with Image.open(paths['_g']) as img_g:
                                    if 'A' not in img_d.mode:
                                        img_d.putalpha(255)
                                    if 'A' not in img_g.mode:
                                        img_g.putalpha(255)
                                    if img_d.size != img_g.size:
                                        img_d = img_d.resize(img_g.size, resample=Image.BILINEAR)
                                    fname_glow = os.path.join('generated', inputs['_g']).replace('\\', '/')
                                    inputs['_g'] = fname_glow
                                    os.makedirs(os.path.dirname(fname_glow), exist_ok=True)
                                    write_dds(fname_glow, ImageChops.multiply(img_d, img_g))
                                    generated += 1

                        # Write material to USDA
                        f.write('\t\tover "mat_' + diffuse_hash + '"\n\t\t{\n\t\t\tover "Shader"\n\t\t\t{\n')
                        if '_n' in inputs:
                            # Force DX normals
                            f.write('\t\t\t\tint inputs:encoding = 2 \n')
                        if '_g' in inputs:
                            # Set up emission
                            f.write('\t\t\t\tbool inputs:enable_emission = 1 \n')
                            f.write('\t\t\t\tfloat inputs:emissive_intensity = 10 \n')
                        # Write texture inputs
                        f.write('\t\t\t\tasset inputs:diffuse_texture = @' + diffuse_path + '@ \n')
                        for ext in inputs:
                            if ext == 'reflect':
                                f.write(f'\t\t\t\tasset inputs:reflectionroughness_texture = @' + inputs[ext] + '@ \n')
                            elif ext in extensions:
                                f.write(f'\t\t\t\tasset inputs:{extensions[ext]} = @' + inputs[ext] + '@ \n')
                        f.write('\t\t\t}\n\t\t}\n')
        else:
            print('Warning: No textures found')
        # Write USDA footer
        f.write('\t}\n}\n')
    print(f'Wrote {materials} materials')
    print(f'Wrote {generated} textures')
    print(f'Used {textures} textures')
