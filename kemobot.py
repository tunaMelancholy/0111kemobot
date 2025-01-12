import os
import re
import requests
import shutil
import zipfile
import random
import string
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from asyncio import Semaphore, create_task, gather

# 设置你的BotToken，如果没有Token的话请@BotFather申请机器人
cstBot_token = "TOKEN_HERE"

# Python运行 <= 3.9.21
# 安装依赖 pip install -r requirements.txt
# 或者 pip install requests python-telegram-bot asyncio

# 并发控制,防止不同用户的频繁请求
semaphore = Semaphore(3)

# 辅助函数，生成随机字符串文件夹
def generate_random_string(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

# 设置UA和请求头，理论上来讲，Kemono没有验证策略，不设置也是OK的
def get_headers():
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }

# 下载函数
def download_file(url, output_dir, index):
    try:
        response = requests.get(url, headers=get_headers(), stream=True)
        response.raise_for_status()
        ext = url.split(".")[-1].split("?")[0]  # 提取文件扩展名
        filename = f"{str(index).zfill(5)}.{ext}"
        file_path = os.path.join(output_dir, filename)
        with open(file_path, "wb") as file:
            shutil.copyfileobj(response.raw, file)
        return file_path
    except Exception as e:
        print(f"下载失败: {url}: {e}")
        return None

# 打包函数
def create_zip_file(files, output_dir, base_name):
    zip_files = []
    current_zip = None
    current_size = 0
    max_zip_size = 80 * 1024 * 1024  # 80MB
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

# 异步处理，发送压缩包
async def send_zip_files(context, chat_id, zip_files):
    for zip_file in zip_files:
        try:
            await context.bot.send_document(chat_id=chat_id, document=open(zip_file, "rb"))
        except Exception as e:
            print(f"发送失败: {zip_file}: {e}")

# 删除函数
def clean_up_dir(dir_path):
    try:
        if os.path.exists(dir_path):
            shutil.rmtree(dir_path)
    except Exception as e:
        print(f"清理文件时出错: {dir_path}: {e}")

# 指令处理函数
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = (
        "欢迎使用TunasKemoBot喵!\n\n"
        "一个用来爬取Kemono.su的Bot喵!\n"
        "目前Bot还在测试阶段\n"
        "-----------------------------\n"
        "指令:\n"
        "/start - 显示Bot信息\n"
        "/d <URL> - 下载对应帖子的文件和图片\n"
        "/u <URL> - 下载对应作者的全部帖子\n"
        "-----------------------------\n"
        "当前版本V1.0.4\n"
        "如果有问题请联系 @tunaloli\n"
        "不经常维护.....\n"
        "由于机器性能原因，Bot仅能处理一位用户的需求，在此期间其他的请求将会无响应\n"
        "上次更新：2025年1月11日21:54:01"
    )
    await update.message.reply_text(message)

# 处理JSON，转化URL，提取图片和文件链接
async def download_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with semaphore:
        if len(context.args) != 1:
            await update.message.reply_text("用法错误，请使用: /d <URL>")
            return

        url = context.args[0]
        chat_id = update.message.chat_id

        # 创建输出目录
        date_str = datetime.now().strftime("%Y%m%d")
        random_str = generate_random_string()
        output_dir = f"./kemono/{date_str}/{random_str}"
        os.makedirs(output_dir, exist_ok=True)

        try:
            # 验证并提取URL
            match = re.search(r"(fanbox|fantia|patreon)/user/\d+/post/\d+", url)
            if not match:
                await update.message.reply_text("无效的URL格式，请检查后重试。")
                return

            api_url = f"https://kemono.su/api/v1/{match.group(0)}"
            response = requests.get(api_url, headers=get_headers())
            response.raise_for_status()
            json_data = response.json()

            # 提取标题
            title = json_data.get("post", {}).get("title", "无标题")
            await update.message.reply_text(f"正在处理帖子: {title}")

            # 提取图片和文件链接
            # 图片
            previews = json_data.get("previews", [])
            image_links = [
                f"{preview['server']}/data{preview['path']}"
                for preview in previews
            ]

            # 文件
            attachments = json_data.get("attachments", [])
            file_links = [
                f"{attachment['server']}/data{attachment['path']}"
                for attachment in attachments
            ]

            all_links = image_links + file_links

            if not all_links:
                await update.message.reply_text("没有发现任何图片或文件。")
                return

            await update.message.reply_text(
                f"发现 {len(image_links)} 张图片和 {len(file_links)} 个文件，开始下载..."
            )

            # 下载文件
            downloaded_files = []
            for index, file_url in enumerate(all_links, start=1):
                file_path = download_file(file_url, output_dir, index)
                if file_path:
                    downloaded_files.append(file_path)

            # 打包文件
            base_name = f"Kemono{datetime.now().strftime('%H%M%S')}{generate_random_string(6)}"
            zip_files = create_zip_file(downloaded_files, output_dir, base_name)

            # 发送打包文件
            # 去掉异步处理，或者手动加一个阻塞
            await update.message.reply_text("下载完成，正在打包文件...")
            await send_zip_files(context, chat_id, zip_files)

            await update.message.reply_text("所有文件已发送，开始清理临时文件...")

        except Exception as e:
            await update.message.reply_text(f"处理时发生错误: {e}")
        finally:
            clean_up_dir(output_dir)

# 爬取作者全部帖子
async def download_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with semaphore:
        if len(context.args) != 1:
            await update.message.reply_text("用法错误，请使用: /u <URL>")
            return

        url = context.args[0]
        chat_id = update.message.chat_id

        try:
            # 提取API链接
            # 正则匹配，URL规则，可以自己修改
            match = re.search(r"(fanbox|fantia|patreon)/user/\d+", url)
            if not match:
                await update.message.reply_text("无效的URL格式，请检查后重试。")
                return

            api_url = f"https://kemono.su/api/v1/{match.group(0)}/posts-legacy"
            response = requests.get(api_url, headers=get_headers())
            response.raise_for_status()
            json_data = response.json()

            # 提取用户信息
            props = json_data.get("props", {})
            user_name = props.get("name", "未知作者")
            service = props.get("service", "未知平台")
            user_id = props.get("id", "未知ID")

            await update.message.reply_text(f"开始处理用户: {user_name} ({service})")

            # 提取帖子ID
            results = json_data.get("results", [])
            post_ids = [result.get("id") for result in results if result.get("id")]

            if not post_ids:
                await update.message.reply_text("未找到任何帖子。")
                return

            await update.message.reply_text(f"共找到 {len(post_ids)} 个帖子，开始下载...")

            # 构造帖子URL并调用 download_post 下载
            for post_id in post_ids:
                post_url = f"https://kemono.su/{service}/user/{user_id}/post/{post_id}"
                context.args = [post_url]
                await download_post(update, context)

            await update.message.reply_text("全部帖子已下载完成！")

        except Exception as e:
            await update.message.reply_text(f"处理用户时发生错误: {e}")

# 主函数
if __name__ == "__main__":
    app = ApplicationBuilder().token(cstBot_token).build()

    # 这里注释掉了 download_user 对应的指令，因为还有点小Bug，在download_post中应该串行处理，先发送再删除，懒得修了，可以自己修一修
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("d", download_post))
    # app.add_handler(CommandHandler("u", download_user))

    print("Bot is running...")
    app.run_polling()
