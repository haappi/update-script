import cgi
import sys
from typing import Final

import aiohttp
import asyncio
import hashlib
import os
import aiofiles

API_URL: Final[str] = "https://chicago.quack.boo/gami/"


def print_fail(message, end='\n'):
    sys.stderr.write('\x1b[1;31m' + message.strip() + '\x1b[0m' + end)


def print_pass(message, end='\n'):
    sys.stdout.write('\x1b[1;32m' + message.strip() + '\x1b[0m' + end)


def print_warn(message, end='\n'):
    sys.stderr.write('\x1b[1;33m' + message.strip() + '\x1b[0m' + end)


def print_info(message, end='\n'):
    sys.stdout.write('\x1b[1;34m' + message.strip() + '\x1b[0m' + end)


def print_bold(message, end='\n'):
    sys.stdout.write('\x1b[1;37m' + message.strip() + '\x1b[0m' + end)




def calculate_md5(file_path):
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        while chunk := f.read(4096):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_files_and_md5(directory):
    files_and_md5 = {}
    for file_name in os.listdir(directory):
        file_path = os.path.join(directory, file_name)
        if os.path.isfile(file_path):
            md5_hash = calculate_md5(file_path)
            files_and_md5[file_name] = md5_hash
    return files_and_md5


def get_hashed_files(directory):
    files = []
    for file_name in os.listdir(directory):
        file_path = os.path.join(directory, file_name)
        if os.path.isfile(file_path):
            files.append(calculate_md5(file_path))
    return files


def save_string_to_file(file_path, data):
    with open(file_path, 'w') as file:
        file.write(data)


def load_string_from_file(file_path):
    with open(file_path, 'r') as file:
        return file.read()


async def fetch_latest_hash(session):
    async with session.get(API_URL + "latest_hash") as response:
        if response.status == 200:
            return await response.text()
        else:
            _json = await response.json()
            if "detail" in _json:
                print_fail("Error: ", _json["detail"])
                exit(1)


async def get_friendly_name(session, file_name):
    async with session.get(API_URL + file_name) as response:
        if response.status == 200:
            return await response.text()
        else:
            return file_name


async def fetch_affected_files(session, current_hash):
    async with session.get(API_URL + current_hash) as response:
        if response.status == 200:
            _json = await response.json()
            print_warn(_json["message"])
            return _json
        else:
            return None


async def download_file(session, file_name):
    async with session.get(API_URL + file_name) as response:
        if response.status == 200:
            content_disposition = response.headers.get('Content-Disposition')
            if content_disposition:
                _, params = cgi.parse_header(content_disposition)
                server_file_name = params.get('filename')
                if server_file_name:
                    file_name = server_file_name

            file_size = int(response.headers.get('Content-Length', 0))
            downloaded = 0
            async with aiofiles.open(file_name, 'wb') as f:
                async for chunk in response.content.iter_chunked(1024):
                    await f.write(chunk)
                    downloaded += len(chunk)
                    print(f"Downloading {file_name}: {downloaded}/{file_size} bytes", end='\r')
            print(f"Downloading {file_name}: Done")
        else:
            print(f"Failed to download {file_name}")


def update_current_hash(latest_hash):
    save_string_to_file('hash.txt', latest_hash)


async def main():
    deletedDirectory = "deletedModsByHappy"

    try:
        os.makedirs(deletedDirectory)
        print_info(f"Directory '{deletedDirectory}' created successfully.")
    except FileExistsError:
        print_info(f"Directory '{deletedDirectory}' already exists. Skipping creation.")

    current_hash = load_string_from_file('hash.txt') if os.path.exists('hash.txt') else ""

    async with aiohttp.ClientSession() as session:
        latest_hash = await fetch_latest_hash(session)

        if latest_hash != current_hash:
            affected_files = await fetch_affected_files(session, current_hash)
            already_existing = get_hashed_files('.')

            if affected_files:
                tasks = []
                for file_name in affected_files['added']:
                    if file_name in already_existing:
                        print_warn(f"File '{file_name}' already exists. Skipping download.")
                        continue
                    tasks.append(download_file(session, file_name))
                await asyncio.gather(*tasks)

                for file_name in affected_files['removed']:
                    file_name = await get_friendly_name(session, file_name)
                    try:
                        os.rename(file_name, os.path.join(deletedDirectory, file_name))
                        print_pass(f"File '{file_name}' moved to '{deletedDirectory}'.")
                    except FileNotFoundError or FileExistsError:
                        print_fail(f"File '{file_name}' not found. Skipping deletion.")

                update_current_hash(latest_hash)
                print_pass("Update successful!")
            else:
                print_pass("Failed to fetch affected files.")
        else:
            print_pass("No update available.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print_fail(f"An error occurred: {e}\nTry deleting the hash.txt file.")

    input("Press Enter to exit...")
