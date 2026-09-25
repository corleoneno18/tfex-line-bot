import os
import time
import requests
from google import genai

def get_tfex_data():
    # ยิง API ตรงไปที่ Settrade เพื่อรับข้อมูลตารางราคา SET50 Futures
    url = "https://www.settrade.com/api/settrade/derivatives/market-data/trading-quotation-by-series?underlying=SET50"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.settrade.com/th/derivatives/market-data/trading-quotation-by-series"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.text
    except Exception as e:
        print(f"ดึงข้อมูล API ไม่สำเร็จ: {e}")
    
    # หาก API ดึงไม่ได้ ให้ fallback ไปดึงหน้า html
    url_fallback = "https://www.settrade.com/th/derivatives/market-data/trading-quotation-by-series"
    res = requests.get(url_fallback, headers=headers)
    return res.text[:15000]

def summarize_with_gemini(raw_data):
    api_key = os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
    จากข้อมูล JSON ตลาด TFEX ด้านล่างนี้ ให้สกัดข้อมูลของ SET50 Futures ทุก Series ทั้งหมดที่มีในข้อมูล
    แล้วจัดรูปแบบสรุปเป็นข้อความอ่านง่ายสำหรับอ่านใน LINE โดยให้แสดงข้อมูลของแต่ละ Series ดังนี้:

    📌 [ชื่อย่อสัญญา]
    • ราคาล่าสุด: 
    • เปลี่ยนแปลง: (พร้อม %)
    • สูงสุด / ต่ำสุด: 
    • ปริมาณ (สัญญา): 
    • สถานะคงค้าง: 
    • ราคาเปิด / ราคาเฉลี่ย: 

    พร้อมสรุปผลรวม ปริมาณสัญญา และ สถานะคงค้าง ทั้งหมดท้ายข้อความด้วย

    ข้อมูลดิบ:
    {raw_data}
    """
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"กำลังเรียก Gemini API (ครั้งที่ {attempt + 1})...")
            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt
            )
            return response.text
        except Exception as e:
            if "503" in str(e) and attempt < max_retries - 1:
                print("เซิร์ฟเวอร์หนาแน่น (503) กำลังลองใหม่อีกครั้งใน 3 วินาที...")
                time.sleep(3)
            else:
                raise e

def send_line_message(message):
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = os.environ.get("LINE_USER_ID")
    
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    payload = {
        "to": user_id,
        "messages": [
            {
                "type": "text",
                "text": f"📊 สรุป SET50 Futures วันนี้:\n\n{message}"
            }
        ]
    }
    response = requests.post(url, headers=headers, json=payload)
    print(f"--- LINE API RESULT ---")
    print(f"Status Code: {response.status_code}")
    print(f"Response Text: {response.text}")
    print(f"----------------------")

if __name__ == "__main__":
    try:
        raw = get_tfex_data()
        summary = summarize_with_gemini(raw)
        print("Gemini Summary Success!")
        send_line_message(summary)
        print("ทำงานสำเร็จ!")
    except Exception as e:
        print(f"เกิดข้อผิดพลาด: {e}")
