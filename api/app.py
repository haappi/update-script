import hashlib
import json
import os
import time
from contextlib import asynccontextmanager
from typing import Dict, List
from fastapi.responses import FileResponse
from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from datetime import datetime, timedelta
from pydantic import BaseModel

cache = {}

def calculate_md5(file_path):
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        while chunk := f.read(4096):
            hasher.update(chunk)
    return hasher.hexdigest()


async def rename_stuff() -> list[str]:
    return_list = []
    for file_name in os.listdir('mods'):
        file_path = os.path.join('mods', file_name)
        if os.path.isfile(file_path):
            md5_hash = calculate_md5(file_path)
            try:
                os.rename(file_path, os.path.join('hashed_mods', f"{md5_hash}-{file_name}"))
                return_list.append(md5_hash)
            except FileExistsError:
                os.remove(file_path)

    return return_list


async def get_delete_stuff() -> list[str]:
    return_list = []
    for file_name in os.listdir('deleted'):
        print("aaaa")
        file_path = os.path.join('deleted', file_name)
        if os.path.isfile(file_path):
            md5_hash = calculate_md5(file_path)
            try:
                os.rename(file_path, os.path.join('hashed_mods', f"{md5_hash}-{file_name}"))
                return_list.append(md5_hash)
            except FileExistsError:
                os.remove(file_path)

    return return_list


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        os.makedirs("mods")
    except FileExistsError:
        pass
    try:
        os.makedirs("hashed_mods")
    except FileExistsError:
        pass

    await rename_stuff()

    yield


app = FastAPI(lifespan=lifespan)


class History(BaseModel):
    timestamp: int
    added: List[str]
    removed: List[str]


def read_history_file(file_path: str) -> Dict[str, History]:
    with open(file_path, 'r') as file:
        data = json.load(file)

    history_data = {}
    for key, value in data.items():
        history_obj = History(**value)
        history_data[key] = history_obj

    return history_data


def write_to_history(file_path: str, data: Dict[str, History]):
    _json = {}
    for key, value in data.items():
        _json[key] = value.dict()
    print(_json)
    with open(file_path, 'w') as file:
        json.dump(_json, file, indent=4)


history: Dict[str, History] = read_history_file('history.json')

password = "password"


@app.get("/gami/reload/")
async def reload_history(key: str):
    if key != password:
        return HTTPException(status_code=403, detail="Invalid key")
    global history
    history = read_history_file('history.json')
    added = await rename_stuff()
    removed = await get_delete_stuff()
    random_hash = hashlib.md5(os.urandom(32)).hexdigest()

    history[random_hash] = History(timestamp=int(time.time()), added=added, removed=removed)

    write_to_history('history.json', history)

    return {"message": f"History reloaded. {len(added)} new mods added. {len(removed)} mods removed."}


def get_latest_hash():
    latest_timestamp = max(history.values(), key=lambda x: x.timestamp).timestamp
    latest_hashes = [key for key, value in history.items() if value.timestamp == latest_timestamp]
    return latest_hashes[0] if latest_hashes else None


def get_history(current_hash: str) -> List[str]:
    current_timestamp = history.get(current_hash, {}).timestamp if current_hash in history else 0
    filtered_hashes = [key for key, value in history.items() if value.timestamp > current_timestamp]
    return filtered_hashes


@app.get("/gami/latest_hash", response_class=PlainTextResponse)
async def get_latest_hash_route():
    return get_latest_hash()


@app.get("/gami/update/")
async def get_update_without_hash():
    return await get_update(None)


def get_hash_count_behind(current_hash: str):
    current_timestamp = history.get(current_hash, {}).timestamp if current_hash in history else 0
    return len([key for key, value in history.items() if value.timestamp > current_timestamp])


@app.get("/gami/update/{current_hash}")
async def get_update(current_hash: str | None = None):
    if current_hash:
        if current_hash not in history:
            return HTTPException(status_code=404, detail="Hash not found. Try deleting the hash.txt file.")

    hashes = get_history(current_hash)
    added: set = set()
    removed: set = set()
    for _hash in hashes:
        added.update(history[_hash].added)
        removed.update(history[_hash].removed)

    if not current_hash:
        for item in removed:
            if item in added:
                added.remove(item)
        removed = set()

    return {"added": added, "removed": removed, "latest_hash": get_latest_hash(),
            "message": f"Update fetched. {len(added)} mods added, {len(removed)} mods removed. "
                       f"You were {get_hash_count_behind(current_hash)} updates behind."}


@app.get("/gami/download/{md5_hash}")
async def download_mod(md5_hash: str):
    if len(md5_hash) != 32:
        return HTTPException(status_code=400, detail="Invalid hash")
    for file_name in os.listdir('hashed_mods'):
        if file_name.startswith(md5_hash):
            return FileResponse(
                os.path.join('hashed_mods', file_name),
                media_type='application/octet-stream',
                filename=file_name.split('-',
                                         1)[1]
            )

    return HTTPException(status_code=404, detail="File not found. Contact haappi")


@app.get("/gami/update_updater/{current_hash}")
async def get_updater_update(current_hash: str):
    if current_hash == calculate_md5('updater.exe'):
        return {"message": "No update available"}

    return FileResponse(
        'updater.exe',
        media_type='application/octet-stream',
        filename='updater.exe'
    )


"""
todo


automatically create a max 7z archive of the mods directory
when downloading, check if its more perforamnt to
- install each by hand
- install and decompress the archive
"""


@app.get("/gami/friendly_name/{md5_hash}")
async def get_friendly_name(md5_hash: str):
    if md5_hash in cache:
        cached_data, cached_timestamp = cache[md5_hash]
        if datetime.utcnow() - cached_timestamp <= timedelta(minutes=60):
            return cached_data

    for file_name in os.listdir('hashed_mods'):
        if file_name.startswith(md5_hash):
            friendly_name = file_name.split('-', 1)[1]
            response = PlainTextResponse(friendly_name)
            response.headers["Cache-Control"] = "max-age=3600"
            cache[md5_hash] = (response, datetime.utcnow())
            return response

    raise HTTPException(status_code=404, detail="File not found. Contact haappi")