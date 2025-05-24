import os
import zipfile
import rarfile
import threading
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor


def extract_zip(zip_path, extract_to):
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        os.remove(zip_path)
        return True
    except Exception as e:
        print(f"Error extracting {zip_path}: {e}")
        return False


def extract_rar(rar_path, extract_to):
    try:
        with rarfile.RarFile(rar_path, 'r') as rar_ref:
            rar_ref.extractall(extract_to)
        os.remove(rar_path)
        return True
    except Exception as e:
        print(f"Error extracting {rar_path}: {e}")
        return False


def process_archive(archive_path):
    dir_path = os.path.dirname(archive_path)
    if archive_path.lower().endswith('.zip'):
        return extract_zip(archive_path, dir_path)
    elif archive_path.lower().endswith('.rar'):
        return extract_rar(archive_path, dir_path)
    return False


def find_archives(root_dir):
    archives = []
    for root, _, files in os.walk(root_dir):
        for file in files:
            if file.lower().endswith(('.zip', '.rar')):
                archives.append(os.path.join(root, file))
    return archives


def main(root_dir):

    if not os.path.isdir(root_dir):
        print("无效的目录路径!")
        return

    archives = find_archives(root_dir)
    if not archives:
        print("没有找到任何压缩文件!")
        return

    print(f"找到 {len(archives)} 个压缩文件，开始解压...")

    # 使用多线程处理
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(tqdm(executor.map(process_archive, archives), total=len(archives), desc="解压进度"))

    success_count = sum(results)
    print(f"处理完成! 成功解压 {success_count}/{len(archives)} 个文件")


if __name__ == "__main__":
    root_dir = 'NAKK'
    main(root_dir)