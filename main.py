from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional, Dict
from PIL import Image, ImageDraw
from datetime import datetime
import base64
import os
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

@app.get("/api/config")
def get_config():
    # 카카오 키가 있어도 이제 안 씀 (빈 값 반환)
    return {"kakao_key": None}

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
    if room_id not in rooms_db: return {"error": "존재하지 않는 방입니다."}
    room = rooms_db[room_id]
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    is_open = now >= room.open_time 
    return { "is_open": is_open, "open_time": room.open_time, "slots": room.slots, "columns": room.columns }

@app.get("/")
def read_root(): return FileResponse("index.html")
@app.get("/host")
def read_host(): return FileResponse("create.html")

@app.get("/img/{room_id}/{position}")
def get_image(room_id: str, position: int):
    file_path = f"img_{room_id}_{position}.png"
    if os.path.exists(file_path): return FileResponse(file_path)
    return {"error": "Image not found"}

@app.get("/result_card/{room_id}")
def get_result_card(room_id: str):
    file_path = f"result_{room_id}.jpg"
    if os.path.exists(file_path): return FileResponse(file_path)
    return {"error": "Not generated yet"}

@app.post("/reserve/{room_id}")
def reserve_slot(room_id: str, request: JoinRequest):
    if room_id not in rooms_db: return {"status": "ERROR", "message": "방이 없습니다."}
    room = rooms_db[room_id]
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    if now >= room.open_time: return {"status": "TIME_OVER", "message": "⏰ 마감되었습니다."}
    
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
    if now >= room.open_time: return {"status": "TIME_OVER", "message": "⏰ 마감되었습니다."}
    
    target_slot = None
    for slot in room.slots:
        if slot.reserved_by == request.user_name and not slot.is_filled:
            target_slot = slot; break
    if not target_slot:
        for slot in room.slots:
            if not slot.is_filled and slot.reserved_by is None:
                target_slot = slot; break

    if target_slot:
        target_slot.user = request.user_name
        target_slot.message = request.message
        target_slot.is_filled = True
        try:
            header, encoded = request.image_data.split(",", 1)
            data = base64.b64decode(encoded)
            file_name = f"img_{room_id}_{target_slot.position}.png"
            with open(file_name, "wb") as f: f.write(data)
        except Exception as e: print(f"저장 실패: {e}")
        return {"status": "SUCCESS"}
            
    return {"status": "FULL", "message": "자리 없음"}

@app.post("/make-card/{room_id}")
def make_card(room_id: str):
    if room_id not in rooms_db: return {"error": "No Room"}
    room = rooms_db[room_id]
    
    cols = room.columns
    total_slots = len(room.slots)
    rows = (total_slots // cols) + (1 if total_slots % cols else 0)
    
    slot_size = 120    
    margin = 40  # 외곽 여백 (이 부분도 빨간 니트로 채워짐)
    
    # 전체 캔버스 크기
    width = (cols * slot_size) + (margin * 2)
    height = (rows * slot_size) + (margin * 2)
    
    # [핵심] 배경: 크리스마스 레드 (#b71c1c)
    bg_color = (183, 28, 28) 
    dot_color = (160, 20, 20) # 배경 패턴용 더 진한 빨강
    
    canvas = Image.new('RGB', (width, height), color=bg_color)
    draw = ImageDraw.Draw(canvas)

    # [디자인] 배경 전체에 니트 구멍 패턴 그리기 (자동 채움 효과)
    # 픽셀 사이즈 16px 기준 (HTML과 동일 비율) -> 120px 안에 약 7.5개... 
    # 여기서는 단순화를 위해 20px 간격으로 점을 찍습니다.
    for py in range(0, height, 15):
        for px in range(0, width, 15):
            draw.ellipse([px, py, px+2, py+2], fill=dot_color)
    
    start_x = margin
    start_y = margin

    for slot in room.slots:
        col_idx = slot.position % cols
        row_idx = slot.position // cols
        
        x = start_x + (col_idx * slot_size)
        y = start_y + (row_idx * slot_size)
        
        # 공백(Space)인 경우에도 빨간 배경이 유지되므로 자연스러움
        if slot.char == " ": continue 
        
        try:
            if slot.is_filled and slot.user:
                img_path = f"img_{room_id}_{slot.position}.png"
                if os.path.exists(img_path):
                    user_img = Image.open(img_path).convert("RGBA")
                    user_img = user_img.resize((slot_size, slot_size), Image.Resampling.LANCZOS)
                    # 붙여넣기
                    canvas.paste(user_img, (x, y), mask=user_img)
            else:
                # [선택] 아직 안 채워진 글자 자리 처리 (약하게 표시할지 말지)
                # 여기서는 비워둡니다 (빨간 배경이 보임)
                pass

        except Exception as e: 
            print(f"이미지 병합 오류: {e}")
            
    out_file = f"result_{room_id}.jpg"
    canvas.save(out_file, quality=95)
    return {"message": "완료"}
