# timetable_check.py
import requests
import json
from datetime import datetime

r = requests.get('http://localhost:8000/api/yamanote/positions')
data = r.json()

print('=== 時刻表ベースの列車位置 ===')
print(f'列車数: {data["count"]}')
print(f'タイムスタンプ: {data["timestamp"]}')
print()

# 最初の3件を詳細表示
for i, p in enumerate(data['positions'][:3]):
    print(f'--- 列車 {i+1} ---')
    print(f'  train_id: {p["train_id"]}')
    print(f'  number: {p["number"]}')
    print(f'  direction: {p["direction"]}')
    print(f'  from_station_id: {p["from_station_id"]}')
    print(f'  to_station_id: {p["to_station_id"]}')
    print(f'  progress: {p["progress"]:.2f}')
    print(f'  is_stopped: {p["is_stopped"]}')
    print(f'  current_time_sec: {p["current_time_sec"]} ({p["current_time_sec"]//3600}:{(p["current_time_sec"]%3600)//60:02d})')
    print()

# 駅リストも確認
print('=== 山手線の駅一覧 ===')
r2 = requests.get('http://localhost:8000/api/stations?lineId=JR-East.Yamanote')
stations = r2.json()['stations']
for i, st in enumerate(stations):
    print(f'{i+1:2d}. {st["id"]} ({st["name_ja"]})')