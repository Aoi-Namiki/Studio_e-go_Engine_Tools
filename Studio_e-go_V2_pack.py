import os
import struct
import sys
from collections import OrderedDict

class PAKPackager:
    def __init__(self):
        self.signature = b'PAK0'

    def build_directory_tree_sorted(self, root_dir):
        """
        构建目录树，保证：
        1. 所有目录和文件按名称排序（字母顺序）
        2. 跳过符号链接（防止打包外部文件）
        3. 返回的 dirs 和 files 顺序严格一致
        """
        # 收集所有路径的绝对路径，便于排序
        root_abs = os.path.abspath(root_dir)
        all_dirs = []      # (parent_rel_path, dir_name)
        all_files = []     # (parent_rel_path, file_name, full_path)

        # 递归遍历，手动控制顺序（按名称排序）
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
                    continue   # 跳过符号链接
                if os.path.isdir(full):
                    dirs.append(name)
                else:
                    files.append(name)
            # 按名称排序（已经 sorted 过）
            for d in dirs:
                sub_rel = os.path.join(current_rel_path, d) if current_rel_path else d
                all_dirs.append((current_rel_path, d))
                walk(sub_rel, os.path.join(current_abs_path, d))
            for f in files:
                all_files.append((current_rel_path, f, os.path.join(current_abs_path, f)))

        walk('', root_abs)

        # 构建 dirs 列表：每个元素为 (parent_index, dir_name)
        # 我们需要先将所有目录分配索引，根目录索引为 0，名称为空
        dir_index_map = {'': 0}          # 相对路径 -> 索引
        dirs = [(0xFFFFFFFF, "")]        # 根目录
        for parent_rel, dir_name in all_dirs:
            # 父目录的索引
            parent_idx = dir_index_map[parent_rel]
            dirs.append((parent_idx, dir_name))
            # 当前目录的相对路径（用于子目录查找）
            cur_rel = os.path.join(parent_rel, dir_name) if parent_rel else dir_name
            dir_index_map[cur_rel] = len(dirs) - 1

        # 构建 files 列表：每个元素为 (dir_index, file_name, file_path)
        files = []
        for parent_rel, file_name, full_path in all_files:
            dir_index = dir_index_map[parent_rel]
            files.append((dir_index, file_name, full_path))

        return dirs, files

    def calculate_directory_file_ranges(self, dirs, files):
        """计算每个目录包含的文件结束索引（右边界）"""
        # 统计每个目录下的文件数量（按 files 顺序）
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
        print(f"正在打包目录: {input_dir} -> {output_file}")
        dirs, files = self.build_directory_tree_sorted(input_dir)
        dir_last_index = self.calculate_directory_file_ranges(dirs, files)

        print(f"找到 {len(dirs)} 个目录, {len(files)} 个文件")
        if verbose:
            # 打印目录结构用于调试
            print("\n目录列表 (索引, 父索引, 名称, 文件结束索引):")
            for i, (parent, name) in enumerate(dirs):
                print(f"  [{i}] parent={parent}, name='{name}', last_file_idx={dir_last_index[i]}")
            print("\n文件列表 (所属目录索引, 文件名):")
            for i, (dir_idx, fname, _) in enumerate(files):
                print(f"  [{i}] dir={dir_idx}, file='{fname}'")

        # ---- 构建名字块 (UTF-8) ----
        name_data = bytearray()
        # 写入所有目录名（跳过根目录）
        for parent_idx, dir_name in dirs[1:]:
            encoded = dir_name.encode('utf-8')
            if len(encoded) > 255:
                raise ValueError(f"目录名过长: {dir_name}")
            name_data.append(len(encoded))
            name_data.extend(encoded)
        # 写入所有文件名
        for dir_idx, file_name, _ in files:
            encoded = file_name.encode('utf-8')
            if len(encoded) > 255:
                raise ValueError(f"文件名过长: {file_name}")
            name_data.append(len(encoded))
            name_data.extend(encoded)
        name_data.append(0x00)   # 终止符

        # ---- 计算偏移 ----
        header_size = 0x10
        dir_section_size = len(dirs) * 8
        file_section_size = len(files) * 0x10
        name_section_size = len(name_data)
        data_offset = header_size + dir_section_size + file_section_size + name_section_size

        # ---- 计算每个文件的数据偏移 ----
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

        # ---- 写入文件 ----
        with open(output_file, 'wb') as f:
            # 文件头
            f.write(self.signature)
            f.write(struct.pack('<I', data_offset))
            f.write(struct.pack('<I', len(dirs)))
            f.write(struct.pack('<I', len(files)))

            # 目录表
            for i, (parent, _) in enumerate(dirs):
                f.write(struct.pack('<I', parent))
                f.write(struct.pack('<I', dir_last_index[i]))

            # 文件表
            for entry in file_entries:
                f.write(struct.pack('<I', entry['offset']))
                f.write(struct.pack('<I', entry['size']))
                f.write(b'\x00' * 8)

            # 名字块
            f.write(name_data)

            # 文件数据
            for entry in file_entries:
                with open(entry['path'], 'rb') as src:
                    f.write(src.read())
                print(f"已打包: {entry['path']} (大小: {entry['size']} 字节)")

        print(f"\n打包完成! 输出: {output_file}")
        print(f"数据偏移: 0x{data_offset:08X}")
        print(f"目录数: {len(dirs)}  文件数: {len(files)}")

# ----------------------------------------------------------------------
# 可选：配套解包函数（用于验证打包是否正确）
# 取消注释即可使用
# ----------------------------------------------------------------------
def unpack(pak_file, output_dir):
    """解包并还原目录结构（与打包格式严格对称）"""
    os.makedirs(output_dir, exist_ok=True)
    with open(pak_file, 'rb') as f:
        sig = f.read(4)
        if sig != b'PAK0':
            raise ValueError("无效的签名")
        data_off = struct.unpack('<I', f.read(4))[0]
        num_dirs = struct.unpack('<I', f.read(4))[0]
        num_files = struct.unpack('<I', f.read(4))[0]

        # 读取目录表
        dir_parent = []
        dir_last = []
        for _ in range(num_dirs):
            parent = struct.unpack('<I', f.read(4))[0]
            last = struct.unpack('<I', f.read(4))[0]
            dir_parent.append(parent)
            dir_last.append(last)

        # 读取文件表
        file_offsets = []
        file_sizes = []
        for _ in range(num_files):
            off = struct.unpack('<I', f.read(4))[0]
            sz = struct.unpack('<I', f.read(4))[0]
            file_offsets.append(off)
            file_sizes.append(sz)
            f.seek(8, 1)  # 跳过保留

        # 读取名字块
        name_data = bytearray()
        while True:
            ch = f.read(1)
            if not ch or ch == b'\x00':
                break
            name_data.extend(ch)
        # 解析名字
        names = []
        pos = 0
        while pos < len(name_data):
            length = name_data[pos]
            pos += 1
            names.append(name_data[pos:pos+length].decode('utf-8'))
            pos += length
        # 名字顺序：先所有目录名（除根目录），后所有文件名
        num_name_dirs = num_dirs - 1
        dir_names = names[:num_name_dirs] if num_name_dirs > 0 else []
        file_names = names[num_name_dirs:] if num_name_dirs < len(names) else []

        # 构建目录路径
        dir_paths = ['']  # 根目录
        for i in range(1, num_dirs):
            parent = dir_parent[i]
            dir_paths.append(os.path.join(dir_paths[parent], dir_names[i-1]))

        # 还原文件
        for i in range(num_files):
            # 找到所属目录
            dir_idx = None
            for d in range(num_dirs):
                if i < dir_last[d]:
                    dir_idx = d
                    break
            if dir_idx is None:
                raise ValueError(f"文件索引 {i} 无归属目录")
            full_path = os.path.join(output_dir, dir_paths[dir_idx], file_names[i])
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            f.seek(file_offsets[i])
            data = f.read(file_sizes[i])
            with open(full_path, 'wb') as out:
                out.write(data)
            print(f"解包: {full_path}")
    print("解包完成!")

def main():
    if len(sys.argv) != 3:
        print("用法: python packer.py <输入目录> <输出.dat>")
        sys.exit(1)

    input_dir = sys.argv[1]
    output_file = sys.argv[2]

    if not output_file.lower().endswith('.dat'):
        print("错误: 输出文件必须是 .dat 后缀!")
        sys.exit(1)

    if not os.path.isdir(input_dir):
        print(f"错误: 目录 '{input_dir}' 不存在!")
        sys.exit(1)

    packer = PAKPackager()
    packer.pack(input_dir, output_file, verbose=True)

    # 如果想自动验证，取消下面注释（需要先定义 unpack 函数）
    # print("\n开始验证解包...")
    # unpack(output_file, "验证输出目录")

if __name__ == "__main__":
    main()
