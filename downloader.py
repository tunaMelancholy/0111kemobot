import os
import re
import requests
import time
import shutil
import zipfile
from datetime import datetime
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor

# cst_post_url为爬取单个帖子的URL
#   例如 https://kemono.su/fanbox/user/22601389/post/7664922
# cst_user_url为爬取当前用户所有帖子的URL
#   例如 https://kemono.su/fanbox/user/22601389

# 任选其一，虽然填写两个也可以正常工作，但是不便于分类
# 下载指定帖子内容
cst_post_url = ""
# 下载指定用户所有帖子
cst_user_url = "https://kemono.su/fanbox/user/34151526"
# https://kemono.su/fanbox/user/26068055
# 当前下载页数，配合cst_user_url使用
pages = 3

api_pages = (pages -1) *50
# 安装依赖 pip install -r requirements.txt
# 或者 pip install requests tqdm

# 程序的调用了Kemono的API
# 更新时间：2025年1月12日
# 从Kemo_bot迁移主要功能至Kemo_Downloader

# 更新时间：2025年3月28日
# 修复了download_user的部分Bug和Json解析错误
# 优化了Downloader下载逻辑，新加了超时重试机制
# 删除了create_zip_file代码

# 更新时间：2025年3月29日
# 新加了Windows新建文件夹特殊字符剔除

# 设置线程池最大线程数，请设置合理数值，最好不要过大(64个线程)
# 因为目前不知道Kemono的API有没有限制....
# 如果下载的图片很多很大的情况下，可以调整大一些
THREAD_POOL_SIZE = 24
executor = ThreadPoolExecutor(max_workers=THREAD_POOL_SIZE)

# 辅助函数，其实没用到，可以注释掉
def generate_random_string(length=8):
    import random, string
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

# 设置UA和请求头，避免Pot，理论上Kemono没有反爬虫程序，不会做检测
def get_headers():
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }


def download_file(url, output_dir, index, progress_bar):
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            response = requests.get(url, headers=get_headers(), stream=True)
            response.raise_for_status()
            ext = url.split(".")[-1].split("?")[0]  # 提取文件扩展名
            filename = f"{str(index).zfill(5)}.{ext}"
            file_path = os.path.join(output_dir, filename)

            # 弃用，太耗费时间
            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0

            with open(file_path, "wb") as file:
                for data in response.iter_content(chunk_size=1024):
                    file.write(data)
                    downloaded_size += len(data)
                    progress_bar.update(len(data))

            return file_path
        except Exception as e:
            retry_count += 1
            if retry_count < max_retries:
                print(f"下载失败，正在重试({retry_count}/{max_retries}): {url}")
            else:
                print(f"下载失败，已达到最大重试次数({max_retries}): {url}: {e}")
            time.sleep(1)  # 每次重试前等待1秒

    return None

def create_zip_file(files, output_dir, base_name):
    zip_files = []
    current_zip = None
    current_size = 0
    max_zip_size = 2000 * 1024 * 1024  #限制压缩包大小为2000MB
    zip_index = 1

    for file in files:
        file_size = os.path.getsize(file)
        if current_zip is None or (current_size + file_size) > max_zip_size:
            if current_zip:
                current_zip.close()
            zip_name = os.path.join(output_dir, f"{base_name}_{zip_index}.zip")
            current_zip = zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED)
            zip_files.append(zip_name)
            current_size = 0
            zip_index += 1
        current_zip.write(file, os.path.basename(file))
        current_size += file_size

    if current_zip:
        current_zip.close()

    return zip_files

def download_file_threaded(url, output_dir, index, downloaded_files, progress_bar):
    file_path = download_file(url, output_dir, index, progress_bar)
    if file_path:
        downloaded_files.append(file_path)

def clean_filename(filename):
    """清理 Windows 文件名中的非法字符"""
    return re.sub(r'[\\/:*?"<>|]', '', filename)

def download_post(url):
    # 验证 提取URL
    match = re.search(r"(fanbox|fantia|patreon)/user/\d+/post/\d+", url)
    if not match:
        print("无效的URL格式，请检查后重试。")
        return

    api_url = f"https://kemono.su/api/v1/{match.group(0)}"
    response = requests.get(api_url, headers=get_headers())
    response.raise_for_status()
    json_data = response.json()
    # print(url)
    # print(match)
    # print(api_url)
    # print(json_data)
    # 提取标题
    title = json_data.get("post", {}).get("published")
    title1 = itle = json_data.get("post", {}).get("title")
    print(f"\n正在处理帖子: {title}")

    # 创建输出目录
    data_str = title[:10] +"-"+ title1
    clean_str = clean_filename(data_str)
    output_dir = f"./kemono/{clean_str}"
    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        print(e)
    # 提取图片和文件链接
    previews = json_data.get("previews", [])
    image_links = [
        f"{preview['server']}/data{preview['path']}"
        for preview in previews
    ]

    attachments = json_data.get("attachments", [])
    file_links = [
        f"{attachment['server']}/data{attachment['path']}"
        for attachment in attachments
    ]

    all_links = image_links + file_links

    if not all_links:
        print("没有发现任何图片或文件。")
        return

    print(f"发现 {len(image_links)} 张图片和 {len(file_links)} 个文件，开始下载...")


    # 下载文件
    downloaded_files = []

    # 网速影响很大，如果网速慢的话注释掉以下的代码
    # total_size = sum(
    #     int(requests.head(link, headers=get_headers()).headers.get('content-length', 0))
    #     for link in all_links
    # )
    # with tqdm(total=total_size, unit="B", unit_scale=True, unit_divisor=1, desc="下载进度") as progress_bar:

    with tqdm(total=len(image_links), unit="B", unit_scale=True, unit_divisor=1024, desc="下载速度") as progress_bar:
        futures = []
        for index, file_url in enumerate(all_links, start=1):
            futures.append(executor.submit(download_file_threaded, file_url, output_dir, index, downloaded_files, progress_bar))
        for future in futures:
            future.result()

    # 打包文件
    base_name = f"Kemono_{data_str}"
    # zip_files = create_zip_file(downloaded_files, output_dir, base_name)

    # 输出压缩包信息
    # print("下载完成，以下是生成的压缩包文件:")
    # for zip_file in zip_files:
    #     print(zip_file)

def download_user(url):
    # 提取API链接
    match = re.search(r"(fanbox|fantia|patreon)/user/\d+", url)
    if not match:
        print("无效的URL格式，请检查后重试。")
        return

    api_url = f"https://kemono.su/api/v1/{match.group(0)}/posts-legacy?o={api_pages}"
    response = requests.get(api_url, headers=get_headers())
    response.raise_for_status()
    json_data = response.json()

    # 提取用户信息
    props = json_data.get("props", {})
    user_name = props.get("name", "未知作者")
    service = props.get("service", "未知平台")
    user_id = props.get("id", "未知ID")

    print(f"开始处理用户: {user_name} ({service})")

    # 提取帖子ID
    results = json_data.get("results", [])
    post_ids = [result.get("id") for result in results if result.get("id")]

    if not post_ids:
        print("未找到任何帖子。")
        return

    print(f"共找到 {len(post_ids)} 个帖子，开始下载...")

    # 构造URL
    for post_id in post_ids:
        post_url = f"https://kemono.su/{service}/user/{user_id}/post/{post_id}"
        download_post(post_url)

    print("全部帖子已下载完成！")


if __name__ == "__main__":
    # 下载单个帖子
    if(cst_post_url!=""):
        download_post(cst_post_url)

    # 下载全部帖子
    if(cst_user_url!=""):
        download_user(cst_user_url)
