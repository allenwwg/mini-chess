"""下载 Felicity Xiangqi EGTB 残局数据 (108 个 .znb, 约 5MB)

数据源: https://github.com/leedavid/FelicityEgtb  (MIT License)
逐文件下载 + 重试 + 断点续传 (已存在且大小正确则跳过)。
"""
import json
import os
import sys
import time
import urllib.request

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')

API = 'https://api.github.com/repos/leedavid/FelicityEgtb/contents/egtb/1?ref=master'
DEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'egtb')


def fetch_json(url, timeout=20):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode('utf-8'))


def download(url, path, expected, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            data = urllib.request.urlopen(req, timeout=30).read()
            if len(data) != expected:
                print(f'  size mismatch {len(data)} != {expected}, retry {attempt+1}')
                continue
            with open(path, 'wb') as f:
                f.write(data)
            return True
        except Exception as exc:
            print(f'  attempt {attempt+1} failed: {type(exc).__name__} {exc}')
            time.sleep(1)
    return False


def main():
    os.makedirs(DEST, exist_ok=True)
    print(f'Fetching file list from {API}')
    items = fetch_json(API)
    znb = [x for x in items if x['name'].endswith('.znb')]
    print(f'Found {len(znb)} .znb files, total {sum(x["size"] for x in znb)} bytes')

    ok = skip = fail = 0
    for i, item in enumerate(znb):
        name = item['name']
        path = os.path.join(DEST, name)
        if os.path.exists(path) and os.path.getsize(path) == item['size']:
            skip += 1
            continue
        print(f'[{i+1:3d}/{len(znb)}] {name} ({item["size"]} bytes)')
        if download(item['download_url'], path, item['size']):
            ok += 1
        else:
            fail += 1

    total_bytes = sum(os.path.getsize(os.path.join(DEST, x['name']))
                      for x in znb if os.path.exists(os.path.join(DEST, x['name'])))
    print(f'\nDone: downloaded={ok} skipped={skip} failed={fail}')
    print(f'Local: {len(znb)-fail}/{len(znb)} files, {total_bytes} bytes in {DEST}')
    return 0 if fail == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
