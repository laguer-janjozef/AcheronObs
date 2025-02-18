import json
from typing import List
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import cv2
from .hp_logic import get_healthpercent
from .schemas import Match
from .spike_logic import is_spike_planted
from .ultimate_logic import is_ultimate_up
from .score_logic import get_score
from .side_logic import is_side


with open('ressource/config.json') as config_file:
    settings = json.load(config_file)

with open('ressource/match.json') as matchconfig:
    match = json.load(matchconfig)

middleware = [
    Middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])
]

app = FastAPI(middleware=middleware)
cap = cv2.VideoCapture(settings['camera_index'], cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

ispreround = 0
roundwinner = None

match = Match(id=ispreround, spike_status=False,
              teams=[{'id': i,
                      'full_name': f'{match[f"team{i}"]["full_name"]}',
                      'short_name': f'{match[f"team{i}"]["short_name"]}',
                      'logo': f'{match[f"team{i}"]["logo"]}',
                      'players': [{'id': x,
                                   'real_name': f'Player {x}',
                                   'agent': f'{match[f"team{i}"][f"player{x}"]["agent"]}',
                                   'display_name': f'{match[f"team{i}"][f"player{x}"]["gamename"]}'} for x in range(0, 5)]
                      } for i in range(0, 2)]
              )


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message):
        for connection in self.active_connections:
            await connection.send_json(message)


manager = ConnectionManager()


@app.post("/api/match/edit_match")
async def edit_match(new_match: Match):
    global match
    match = new_match
    return new_match


@app.get("/api/match/get_match/")
async def get_match():
    match.id = ispreround
    match.spike_status = await is_spike_planted(cap)
    match.teams[0].game_score = await get_score(settings['score_left_position'], cap)
    match.teams[0].id = await is_side(cap)
    match.teams[1].game_score = await get_score(settings['score_right_position'], cap)
    if match.teams[0].id == 0:
        match.teams[1].id = 1
    else:
        match.teams[1].id = 0
    for i in range(0, 5):
        match.teams[0].players[i].hp = await get_healthpercent(settings['team_1'][f'player_{i}_position'], cap)
        match.teams[0].players[i].ultimate_up = await is_ultimate_up(settings['team_1'][f'player_{i}_position'], cap)
    for i in range(0, 5):
        match.teams[1].players[i].ultimate_up = await is_ultimate_up(settings['team_2'][f'player_{i}_position'], cap)
        match.teams[1].players[i].hp = await get_healthpercent(settings['team_2'][f'player_{i}_position'], cap)
    return match

@app.websocket("/ws/{client}")
async def websocket_endpoint(websocket: WebSocket, client: str):
    global ispreround
    global roundwinner
    global match
    await manager.connect(websocket)
    if client == "controller":
        await websocket.send_json({"preround":f"{ispreround}", "Teams": [match.teams[0].short_name, match.teams[1].short_name]})
    try:
        while True:
            event = await websocket.receive_text() #button is pressed from controller
            event = json.loads(event)

            if event['event'] == 'togglePreround':
                if ispreround == 0:
                    ispreround = 1
                else:
                    ispreround = 0

                await websocket.send_json({"preround":f"{ispreround}"})

            elif event['event'] == 'winEvent':
                roundwinner = event['winner']

            if roundwinner != None:
                await manager.broadcast({'winner':roundwinner, 'round': match.teams[0].game_score + match.teams[1].game_score})
                roundwinner = None

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print("disconnected")