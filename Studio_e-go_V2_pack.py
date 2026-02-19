import os
import struct
import sys
from collections import defaultdict

class PAKPackager:
    def __init__(self):
        self.signature = b'PAK0'
        
    def build_directory_tree(self, root_dir):
        """构建目录树结构"""
        dirs = [(0xFFFFFFFF, "")]  # 根目录
        files = []
        dir_map = {root_dir: 0}
        
        for current_dir, subdirs, filenames in os.walk(root_dir):
            current_index = dir_map[current_dir]
            for subdir in subdirs:
                subdir_path = os.path.join(current_dir, subdir)
                dirs.append((current_index, subdir))
                dir_map[subdir_path] = len(dirs) - 1
            for filename in filenames:
                file_path = os.path.join(current_dir, filename)
                files.append((current_index, filename, file_path))
        
        return dirs, files
    
    def calculate_directory_file_ranges(self, dirs, files):
        dir_files = defaultdict(list)
        for file_index, (dir_index, _, _) in enumerate(files):
            dir_files[dir_index].append(file_index)
        
        dir_last_index = [0] * len(dirs)
        current_index = 0
        for dir_index in range(len(dirs)):
            if dir_index in dir_files:
                file_count = len(dir_files[dir_index])
                dir_last_index[dir_index] = current_index + file_count
                current_index += file_count
            else:
                dir_last_index[dir_index] = current_index
        
        return dir_last_index
    
    def pack(self, input_dir, output_file):
        print(f"正在打包目录: {input_dir} -> {output_file}")
        dirs, files = self.build_directory_tree(input_dir)
        dir_last_index = self.calculate_directory_file_ranges(dirs, files)
        print(f"找到 {len(dirs)} 个目录, {len(files)} 个文件")
        
        name_data = bytearray()
        for parent_index, dir_name in dirs[1:]:
            name_data.append(len(dir_name))
            name_data.extend(dir_name.encode('ascii'))
        
        file_name_positions = []
        for dir_index, file_name, file_path in files:
            name_data.append(len(file_name))
            start_pos = len(name_data)
            name_data.extend(file_name.encode('ascii'))
            file_name_positions.append((start_pos, len(file_name)))
        
        name_data.append(0x00)
        
        header_size = 0x10
        dir_section_size = len(dirs) * 8
        file_section_size = len(files) * 0x10
        name_section_size = len(name_data)
        data_offset = header_size + dir_section_size + file_section_size + name_section_size
        
        file_entries = []
        current_offset = data_offset
        for dir_index, file_name, file_path in files:
            file_size = os.path.getsize(file_path)
            file_entries.append({
                'path': file_path,
                'offset': current_offset,
                'size': file_size
            })
            current_offset += file_size
        
        with open(output_file, 'wb') as f:
            f.write(self.signature)
            f.write(struct.pack('<I', data_offset))
            f.write(struct.pack('<I', len(dirs)))
            f.write(struct.pack('<I', len(files)))
            
            for i, (parent_index, dir_name) in enumerate(dirs):
                f.write(struct.pack('<I', parent_index))
                f.write(struct.pack('<I', dir_last_index[i]))
            
            for entry in file_entries:
                f.write(struct.pack('<I', entry['offset']))
                f.write(struct.pack('<I', entry['size']))
                f.write(b'\x00' * 8)
            
            f.write(name_data)
            
            for entry in file_entries:
                with open(entry['path'], 'rb') as src_file:
                    f.write(src_file.read())
                print(f"已打包: {entry['path']} (大小: {entry['size']} 字节)")
        
        print(f"打包完成! 输出文件: {output_file}")
        print(f"数据偏移: 0x{data_offset:08X}")
        print(f"目录数量: {len(dirs)}")
        print(f"文件数量: {len(files)}")

def main():
    if len(sys.argv) != 3:
        print("用法: python Studio_e-go_V2_pack.py <输入目录> <输出文件>")
        sys.exit(1)
    
    input_directory = sys.argv[1]
    output_file = sys.argv[2]
    
    # 限制输出文件必须为 .dat 后缀（不区分大小写）
    if not output_file.lower().endswith('.dat'):
        print("错误: 输出文件必须是 .dat 后缀!")
        sys.exit(1)
    
    if not os.path.exists(input_directory):
        print(f"错误: 目录 '{input_directory}' 不存在!")
        sys.exit(1)
    
    packager = PAKPackager()
    packager.pack(input_directory, output_file)

if __name__ == "__main__":
    main()