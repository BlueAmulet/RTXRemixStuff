import os
import sys
import math
import argparse
import xxhash

try:
    from PIL import Image
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
'textures/clutter/open_24hours_sign/nv_24-sign.dds': {'_g': '_e'}
}


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def calculate_hash(file_path):
    # Read the file and extract the raw data. Thanks @BlueAmulet!
    with open(file_path, 'rb') as file:
        data = file.read()

    dwHeight = int.from_bytes(data[12:16], 'little')
    dwWidth  = int.from_bytes(data[16:20], 'little')
    pfFlags  = int.from_bytes(data[80:84], 'little')
    pfFourCC = data[84:88]
    bitCount = int.from_bytes(data[88:92], 'little')

    mipsize = dwWidth*dwHeight
    if pfFlags & 0x4: # DDPF_FOURCC
        if pfFourCC == b'DXT1': # DXT1 is 4bpp
            mipsize //= 2
    elif pfFlags & 0x20242: # DDPF_ALPHA | DDPF_RGB | DDPF_YUV | DDPF_LUMINANCE
        mipsize = mipsize*bitCount//8

    return xxhash.xxh3_64(data[128:128+mipsize]).hexdigest()


def write_dds(file_name, img):
    width, height = img.size
    mipmaps = int(math.log2(min(width, height)))+1
    with open(file_name, 'wb') as f:
        # Header
        f.write(b'DDS ') # ID
        f.write((124).to_bytes(4, 'little')) # Header size
        f.write(b'\x0F\x10\x02\x00') # Flags (Caps, Height, Width, Pitch, PixelFormat, MipMaps)
        f.write(height.to_bytes(4, 'little')) # Height
        f.write(width.to_bytes(4, 'little')) # Width
        f.write(width.to_bytes(4, 'little')) # Pitch
        f.write((1).to_bytes(4, 'little')) # Depth
        f.write(mipmaps.to_bytes(4, 'little')) # MipMaps
        f.write(b'\0' * 44) # Reserved
        # Pixel format
        f.write((32).to_bytes(4, 'little')) # Format header size
        f.write(b'\x00\x00\x02\x00') # Format flags (Single channel uncompressed)
        f.write(b'\0\0\0\0') # FourCC
        f.write((8).to_bytes(4, 'little')) # Bit Count
        f.write((255).to_bytes(4, 'little')) # R mask
        f.write(b'\0' * 12) # G B A masks
        f.write(b'\x08\x10\x40\x00') # Caps (Complex, Texture, MipMaps)
        f.write(b'\0' * 16) # Extra caps and reserved
        # Write image data
        for i in range(1, mipmaps+1):
            f.write(img.tobytes('raw', 'A'))
            if i != mipmaps:
                img = img.resize((img.size[0] // 2, img.size[1] // 2), resample=Image.BILINEAR)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Generates a USDA to load the game's various textures.")
    parser.add_argument('-t', '--textures', help='The textures folder to search through', required=True)
    parser.add_argument('-o', '--output', help='The USDA file to write', required=True)
    parser.add_argument('-nr', '--no-reflection', help='Skip writing reflection DDS', action='store_true')
    args = parser.parse_args()

    # Validate inputs
    if not os.path.isdir(args.textures):
        eprint(f'Error: {args.texture}: No such directory')
        sys.exit(1)

    # Write USDA
    materials = 0
    textures = 0
    with open(args.output, 'w') as f:
        # Write USDA header
        f.write('#usda 1.0\nover "RootNode"\n{\n\tover "Looks"\n\t{\n')

        # Search through the textures folder
        used_hashes = {}
        for root, _, files in os.walk(args.textures):
            for file in files:
                fname = os.path.join(root, file).replace('\\', '/')
                fname_noext = os.path.splitext(fname)[0]
                if fname_noext.endswith('_d'): # Some diffuse end in _d
                    fname_noext = fname_noext[:-2]

                # Look for extra inputs
                inputs = {}
                for ext in extensions:
                    file_ext = ext
                    if fname in overrides and ext in overrides[fname]:
                        file_ext = overrides[fname][ext]
                    extra_file = fname_noext + file_ext + '.dds'
                    if os.path.exists(extra_file):
                        inputs[ext] = extra_file
                        textures += 1

                if inputs:
                    # Calculate hashes of textures
                    diffuse_hash = calculate_hash(fname)
                    hashes = {}
                    for ext in inputs:
                        hashes[ext] = calculate_hash(inputs[ext])

                    # Check for duplicates
                    input_set = tuple(inputs.values())
                    hash_set = tuple(hashes.values())
                    if diffuse_hash in used_hashes:
                        # Check if duplicate is different
                        if used_hashes[diffuse_hash][1] != hash_set:
                            print(f'Warning: Conflicting hash {diffuse_hash}: {used_hashes[diffuse_hash]} != {input_set, hash_set}')
                    else:
                        # No duplicate, write to usda
                        materials += 1
                        used_hashes[diffuse_hash] = (input_set, hash_set)
                        if have_PIL and '_n' in inputs and not args.no_reflection:
                            # Split alpha off of normal map
                            with Image.open(inputs['_n']) as img:
                                if 'A' in img.mode:
                                    os.makedirs(os.path.join('generated', os.path.dirname(fname)), exist_ok=True)
                                    fname_reflect = os.path.join('generated', fname_noext + '_r.dds')
                                    inputs['reflect'] = fname_reflect
                                    write_dds(fname_reflect, img)
                                else:
                                    print(f'Warning: {inputs["_n"]}: expected alpha in mode, found {img.mode}')

                        # Write material to USDA
                        f.write('\t\tover "mat_' + diffuse_hash + '"\n\t\t{\n\t\t\tover "Shader"\n\t\t\t{\n')
                        if '_n' in inputs:
                            # Force DX normals
                            f.write('\t\t\t\tint inputs:encoding = 2 \n')
                        if '_g' in inputs:
                            # Set up emission
                            f.write('\t\t\t\tfloat inputs:emissive_intensity = 10 \n')
                        # Write texture inputs
                        f.write('\t\t\t\tasset inputs:diffuse_texture = @./' + fname + '@ \n')
                        for ext in inputs:
                            if ext == 'reflect':
                                f.write(f'\t\t\t\tasset inputs:inputs:reflectionroughness_texture = @./' + inputs[ext] + '@ \n')
                            else:
                                f.write(f'\t\t\t\tasset inputs:{extensions[ext]} = @./' + inputs[ext] + '@ \n')
                        f.write('\t\t\t}\n\t\t}\n')
        # Write USDA footer
        f.write('\t}\n}\n')
    print(f'Wrote {materials} materials')
    print(f'Used {textures} textures')
