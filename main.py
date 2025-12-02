from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional, Dict
from PIL import Image
from datetime import datetime
import base64
import io
import os
import glob
import uuid

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CreateRequest(BaseModel):
    text: str
    columns: int 
    open_time: str

class JoinRequest(BaseModel):
    user_name: str
    message: str = ""
    image_data: str = ""

class Slot(BaseModel):
    position: int
    char: str
    user: Optional[str] = None
    message: Optional[str] = None
    is_filled: bool = False
    reserved_by: Optional[str] = None

class RoomData(BaseModel):
    slots: List[Slot]
    columns: int
    open_time: str

rooms_db: Dict[str, RoomData] = {}

# ---- API ----

@app.post("/create")
def create_room(request: CreateRequest):
    room_id = str(uuid.uuid4())[:8] 
    new_slots = []
    for i, char in enumerate(request.text.upper()):
        is_blocked = (char == " ")
        new_slots.append(Slot(position=i, char=char, is_filled=is_blocked))
    
    rooms_db[room_id] = RoomData(
        slots=new_slots,
        columns=request.columns,
        open_time=request.open_time
    )
    return {"message": "방 생성 완료!", "room_id": room_id}

@app.get("/status/{room_id}")
def check_status(room_id: str):
    if room_id not in rooms_db:
        return {"error": "존재하지 않는 방입니다."}
    
    room = rooms_db[room_id]
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    is_open = now >= room.open_time 
    
    return {
        "is_open": is_open, 
        "open_time": room.open_time, 
        "slots": room.slots,
        "columns": room.columns 
    }

@app.get("/")
def read_root(): return FileResponse("index.html")
@app.get("/host")
def read_host(): return FileResponse("create.html")

@app.get("/img/{room_id}/{position}")
def get_image(room_id: str, position: int):
    file_path = f"img_{room_id}_{position}.png"
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return {"error": "Image not found"}

@app.get("/result_card/{room_id}")
def get_result_card(room_id: str):
    file_path = f"result_{room_id}.jpg"
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return {"error": "Not generated yet"}

@app.post("/reserve/{room_id}")
def reserve_slot(room_id: str, request: JoinRequest):
    if room_id not in rooms_db: return {"status": "ERROR", "message": "방이 없습니다."}
    room = rooms_db[room_id]

    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    if now >= room.open_time:
        return {"status": "TIME_OVER", "message": "⏰ 마감되었습니다."}
    
    for slot in room.slots:
        if slot.reserved_by == request.user_name and not slot.is_filled:
             return {"status": "SUCCESS", "assigned_char": slot.char}
    for slot in room.slots:
        if not slot.is_filled and slot.reserved_by is None:
            slot.reserved_by = request.user_name
            return {"status": "SUCCESS", "assigned_char": slot.char}
            
    return {"status": "FULL", "message": "자리가 꽉 찼습니다."}

@app.post("/join/{room_id}")
def join_room(room_id: str, request: JoinRequest):
    if room_id not in rooms_db: return {"status": "ERROR", "message": "방이 없습니다."}
    room = rooms_db[room_id]

    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    if now >= room.open_time:
        return {"status": "TIME_OVER", "message": "⏰ 마감되었습니다."}
    
    target_slot = None
    for slot in room.slots:
        if slot.reserved_by == request.user_name and not slot.is_filled:
            target_slot = slot
            break
    
    if not target_slot:
        for slot in room.slots:
            if not slot.is_filled and slot.reserved_by is None:
                target_slot = slot
                break

    if target_slot:
        target_slot.user = request.user_name
        target_slot.message = request.message
        target_slot.is_filled = True
        try:
            header, encoded = request.image_data.split(",", 1)
            data = base64.b64decode(encoded)
            file_name = f"img_{room_id}_{target_slot.position}.png"
            with open(file_name, "wb") as f:
                f.write(data)
        except Exception as e:
            print(f"저장 실패: {e}")
        return {"status": "SUCCESS"}
            
    return {"status": "FULL", "message": "자리 없음"}

# [수정] 결과 카드 크기 축소 버전
@app.post("/make-card/{room_id}")
def make_card(room_id: str):
    if room_id not in rooms_db: return {"error": "No Room"}
    room = rooms_db[room_id]
    
    total_slots = len(room.slots)
    cols = room.columns
    rows = (total_slots // cols) + (1 if total_slots % cols else 0)
    
    # 1. 필요한 너비/높이 계산 (수치 대폭 축소)
    # 간격 120px, 전체 여백 50px
    required_width = cols * 120 + 50
    required_height = rows * 120 + 50
    
    # 2. 정사각형 캔버스 만들기 (최소 크기도 500으로 줄임)
    canvas_size = max(500, required_width, required_height)
    width = canvas_size
    height = canvas_size
    
    try:
        bg_img = Image.open("bg.png").convert("RGB")
        canvas = bg_img.resize((width, height))
    except:
        canvas = Image.new('RGB', (width, height), color='white')
    
    for slot in room.slots:
        if slot.char == " ": continue
        col_idx = slot.position % cols
        row_idx = slot.position // cols
        
        # 좌표 계산 (시작점 25px, 간격 120px)
        x = 25 + (col_idx * 120)
        y = 25 + (row_idx * 120)
        try:
            if slot.is_filled and slot.user:
                img = Image.open(f"img_{room_id}_{slot.position}.png").convert("RGBA")
                # 이미지 크기 축소 (100x100)
                img = img.resize((100, 100))
                canvas.paste(img, (x, y), mask=img)
        except: pass
            
    out_file = f"result_{room_id}.jpg"
    canvas.save(out_file)
    return {"message": "완료"}
