import os
import struct
import sys

class PAKPackager:
    def __init__(self):
        self.signature = b'PAK0'

    def build_directory_tree_sorted(self, root_dir):
        root_abs = os.path.abspath(root_dir)
        all_dirs = []
        all_files = []

        def walk(current_rel_path, current_abs_path):
            try:
                entries = sorted(os.listdir(current_abs_path))
            except OSError:
                return
            dirs = []
            files = []
            for name in entries:
                full = os.path.join(current_abs_path, name)
                if os.path.islink(full):
                    continue
                if os.path.isdir(full):
                    dirs.append(name)
                else:
                    files.append(name)
            for d in dirs:
                sub_rel = os.path.join(current_rel_path, d) if current_rel_path else d
                all_dirs.append((current_rel_path, d))
                walk(sub_rel, os.path.join(current_abs_path, d))
            for f in files:
                all_files.append((current_rel_path, f, os.path.join(current_abs_path, f)))

        walk('', root_abs)

        dir_index_map = {'': 0}
        dirs = [(0xFFFFFFFF, "")]
        for parent_rel, dir_name in all_dirs:
            parent_idx = dir_index_map[parent_rel]
            dirs.append((parent_idx, dir_name))
            cur_rel = os.path.join(parent_rel, dir_name) if parent_rel else dir_name
            dir_index_map[cur_rel] = len(dirs) - 1

        files = []
        for parent_rel, file_name, full_path in all_files:
            dir_index = dir_index_map[parent_rel]
            files.append((dir_index, file_name, full_path))

        return dirs, files

    def calculate_directory_file_ranges(self, dirs, files):
        file_counts = [0] * len(dirs)
        for dir_idx, _, _ in files:
            file_counts[dir_idx] += 1

        dir_last_index = [0] * len(dirs)
        cur_idx = 0
        for i in range(len(dirs)):
            cur_idx += file_counts[i]
            dir_last_index[i] = cur_idx
        return dir_last_index

    def pack(self, input_dir, output_file, verbose=True):
        print(f"Packing directory: {input_dir} -> {output_file}")
        dirs, files = self.build_directory_tree_sorted(input_dir)
        dir_last_index = self.calculate_directory_file_ranges(dirs, files)

        print(f"Found {len(dirs)} directories, {len(files)} files")
        if verbose:
            print("\nDirectory list (index, parent, name, last_file_idx):")
            for i, (parent, name) in enumerate(dirs):
                print(f"  [{i}] parent={parent}, name='{name}', last_file_idx={dir_last_index[i]}")
            print("\nFile list (dir_index, file_name):")
            for i, (dir_idx, fname, _) in enumerate(files):
                print(f"  [{i}] dir={dir_idx}, file='{fname}'")

        name_data = bytearray()
        for parent_idx, dir_name in dirs[1:]:
            encoded = dir_name.encode('utf-8')
            if len(encoded) > 255:
                raise ValueError(f"Directory name too long: {dir_name}")
            name_data.append(len(encoded))
            name_data.extend(encoded)
        for dir_idx, file_name, _ in files:
            encoded = file_name.encode('utf-8')
            if len(encoded) > 255:
                raise ValueError(f"File name too long: {file_name}")
            name_data.append(len(encoded))
            name_data.extend(encoded)
        name_data.append(0x00)

        header_size = 0x10
        dir_section_size = len(dirs) * 8
        file_section_size = len(files) * 0x10
        name_section_size = len(name_data)
        data_offset = header_size + dir_section_size + file_section_size + name_section_size

        file_entries = []
        cur_offset = data_offset
        for dir_idx, fname, path in files:
            size = os.path.getsize(path)
            file_entries.append({
                'path': path,
                'offset': cur_offset,
                'size': size,
                'dir_idx': dir_idx,
                'name': fname
            })
            cur_offset += size

        with open(output_file, 'wb') as f:
            f.write(self.signature)
            f.write(struct.pack('<I', data_offset))
            f.write(struct.pack('<I', len(dirs)))
            f.write(struct.pack('<I', len(files)))

            for i, (parent, _) in enumerate(dirs):
                f.write(struct.pack('<I', parent))
                f.write(struct.pack('<I', dir_last_index[i]))

            for entry in file_entries:
                f.write(struct.pack('<I', entry['offset']))
                f.write(struct.pack('<I', entry['size']))
                f.write(b'\x00' * 8)

            f.write(name_data)

            for entry in file_entries:
                with open(entry['path'], 'rb') as src:
                    f.write(src.read())
                print(f"Packed: {entry['path']} (size: {entry['size']} bytes)")

        print(f"\nPacking completed! Output: {output_file}")
        print(f"Data offset: 0x{data_offset:08X}")
        print(f"Directories: {len(dirs)}, Files: {len(files)}")

def main():
    if len(sys.argv) != 3:
        print("Usage: python packer.py <input_directory> <output.dat>")
        sys.exit(1)

    input_dir = sys.argv[1]
    output_file = sys.argv[2]

    if not output_file.lower().endswith('.dat'):
        print("Error: Output file must have .dat extension!")
        sys.exit(1)

    if not os.path.isdir(input_dir):
        print(f"Error: Directory '{input_dir}' does not exist!")
        sys.exit(1)

    packer = PAKPackager()
    packer.pack(input_dir, output_file, verbose=True)

if __name__ == "__main__":
    main()
