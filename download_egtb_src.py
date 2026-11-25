"""下载 Felicity Egtb C++ 源码 (MIT) 用于本地编译探测程序"""
import json
import os
import sys
import urllib.request

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')

API = 'https://api.github.com/repos/leedavid/FelicityEgtb/contents/'
DEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'egtb_src')


def api(path):
    return json.loads(urllib.request.urlopen(
        urllib.request.Request(API + path, headers={'User-Agent': 'Mozilla/5.0'}),
        timeout=20).read().decode('utf-8'))


def download(url, path):
    data = urllib.request.urlopen(
        urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}),
        timeout=30).read()
    with open(path, 'wb') as f:
        f.write(data)
    return len(data)


def walk(folder, rel):
    for item in api(folder):
        if item['type'] == 'dir':
            os.makedirs(os.path.join(DEST, rel, item['name']), exist_ok=True)
            walk(folder + '/' + item['name'], os.path.join(rel, item['name']))
        elif item['name'].endswith(('.cpp', '.h', '.c')):
            path = os.path.join(DEST, rel, item['name'])
            download(item['download_url'], path)
            print(f'  {os.path.join(rel, item["name"])}')


os.makedirs(DEST, exist_ok=True)
print('Downloading source/ ...')
walk('source', '')
print('Done')
