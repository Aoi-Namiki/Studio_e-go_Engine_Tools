import os
import sys

def ReadName(data, name_pos):
    length = data[name_pos]
    name_pos += 1
    name = data[name_pos : name_pos+length].decode('ascii')
    name_pos += length
    return name_pos, name

def GetPath(dirs, dir_index):
    path = []
    i = dir_index
    while dirs[i][0] != 0xFFFFFFFF:
        path.append(dirs[i][2])
        i = dirs[i][0]
    path.reverse()
    res = ''
    for _ in path:
        res += '/' + _
    return res

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python unpacker.py <input.dat> <output_dir>")
        sys.exit(1)

    input_file = sys.argv[1]
    output_dir = sys.argv[2]

    if not input_file.lower().endswith('.dat'):
        print("Error: Input file must have .dat extension")
        sys.exit(1)

    try:
        with open(input_file, 'rb') as f:
            data = f.read()
    except FileNotFoundError:
        print(f"Error: File {input_file} not found")
        sys.exit(1)

    data_offset = int.from_bytes(data[4:8], byteorder='little')
    dir_count = int.from_bytes(data[8:12], byteorder='little')
    count = int.from_bytes(data[12:16], byteorder='little')

    dirs = []
    index_offset = 0x10
    name_pos = 0x10 + dir_count * 0x8 + count * 0x10

    for i in range(dir_count):
        parent = int.from_bytes(data[index_offset:index_offset+4], byteorder='little')
        lastIndex = int.from_bytes(data[index_offset+4:index_offset+8], byteorder='little')
        name = ''

        if parent != 0xFFFFFFFF:
            name_pos, name = ReadName(data, name_pos)

        dirs.append((parent, lastIndex, name))
        index_offset += 8

    file_count = 0
    current = 0
    files = []
    for i in range(dir_count):
        while current < dirs[i][1]:
            name_pos, name = ReadName(data, name_pos)
            path = GetPath(dirs, i) + '/' + name
            file_offset = int.from_bytes(data[index_offset:index_offset+4], byteorder='little')
            file_size = int.from_bytes(data[index_offset+4:index_offset+8], byteorder='little')
            index_offset += 0x10
            current += 1
            file_count += 1
            files.append((path, file_offset, file_size))

    assert file_count == count

    for file in files:
        file_data = data[file[1] : file[1]+file[2]]
        rel_path = file[0][1:] if file[0].startswith('/') else file[0]
        out_path = os.path.join(output_dir, rel_path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, 'wb') as f:
            f.write(file_data)

    print(f"Successfully unpacked {file_count} files to {output_dir}")
