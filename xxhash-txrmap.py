import os
import sys
import xxhash

def calculate_DDS_hash(file_path):
    with open(file_path, 'rb') as file:
        data = file.read()

    # Extract info from the DDS header
    if data[0:4] != b'DDS ':
        print(f'Warning: {file_path}: Missing DDS header')
        return None
    dwHeight = int.from_bytes(data[12:16], "little")
    dwWidth  = int.from_bytes(data[16:20], "little")
    pfFlags  = int.from_bytes(data[80:84], "little")
    pfFourCC = data[84:88]
    bitCount = int.from_bytes(data[88:92], "little")

    # Calculate mipmap size
    mipsize = dwWidth*dwHeight
    if pfFlags & 0x4: # DDPF_FOURCC
        if pfFourCC == b'DXT1': # DXT1 is 4bpp
            mipsize //= 2
    elif pfFlags & 0x20242: # DDPF_ALPHA | DDPF_RGB | DDPF_YUV | DDPF_LUMINANCE
        mipsize = mipsize*bitCount//8

    # Calculate hash of the first mipmap
    return "0x" + xxhash.xxh3_64(data[128:128+mipsize]).hexdigest().upper()

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(f'Usage: {sys.argv[0]} textures_folder output_hashes')
        sys.exit(1)

    folder_path = sys.argv[1]
    output_file_path = sys.argv[2]

    with open(output_file_path, 'w') as output_file:
        # Recursively iterate over all files in the folder
        for root, dirs, files in os.walk(folder_path):
            for file_name in files:
                file_path = os.path.join(root, file_name)

                # Check if the file is a DDS file
                if file_name.lower().endswith('.dds') and os.path.isfile(file_path):
                    # Generate the hash for the DDS file
                    hash_value = calculate_DDS_hash(file_path)
                    if hash_value is not None:
                        output_file.write(f"{hash_value} {file_path}\n")
