import os
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai

def get_tfex_data():
    url = "https://www.settrade.com/th/derivatives/market-data/trading-quotation-by-series"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")
    
    text_content = soup.get_text(separator=' ', strip=True)
    return text_content[:15000]

def summarize_with_gemini(raw_data):
    api_key = os.environ.get("GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    
    # ใช้ SDK ตัวมาตรฐาน gemini-2.5-flash
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    prompt = f"""
    จากข้อมูลตลาด TFEX ด้านล่างนี้ ให้สกัดข้อมูลของ SET50 Futures ทุก Series ที่พบ 
    แล้วสรุปเป็นข้อความสั้นๆ สำหรับอ่านใน LINE โดยต้องมีข้อมูลหัวข้อดังนี้ต่อ 1 Series:
    - ชื่อย่อสัญญา, ราคาล่าสุด, เปลี่ยนแปลง (และ %), ราคาสูงสุด, ราคาต่ำสุด, ปริมาณ (สัญญา), สถานะคงค้าง, ราคาชำระราคา, ราคาเปิด, ราคาเฉลี่ย
    
    ข้อมูลดิบ:
    {raw_data}
    """
    
    response = model.generate_content(prompt)
    return response.text

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
