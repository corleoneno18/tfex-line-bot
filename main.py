import os
import json
import time
import requests
from google import genai

def get_tfex_data():
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
    
    url_fallback = "https://www.settrade.com/th/derivatives/market-data/trading-quotation-by-series"
    res = requests.get(url_fallback, headers=headers)
    return res.text[:15000]

def build_direct_summary(raw_json_str):
    """กรณี Gemini ไม่พร้อมทำงาน สรุปข้อมูลตารางตรงจาก JSON"""
    try:
        data = json.loads(raw_json_str)
        series_list = data.get("derivativesTradingQuotationBySeries", {}).get("seriesList", [])
        
        lines = []
        total_vol = 0
        total_oi = 0
        
        for item in series_list:
            symbol = item.get("symbol", "-")
            last = item.get("lastPrice", "-")
            change = item.get("change", "-")
            pct_change = item.get("percentChange", "-")
            high = item.get("high", "-")
            low = item.get("low", "-")
            volume = item.get("volume", 0)
            oi = item.get("openInterest", 0)
            open_p = item.get("openPrice", "-")
            avg_p = item.get("averagePrice", "-")
            
            if isinstance(volume, (int, float)): total_vol += volume
            if isinstance(oi, (int, float)): total_oi += oi
            
            lines.append(
                f"📌 [{symbol}]\n"
                f"• ราคาล่าสุด: {last}\n"
                f"• เปลี่ยนแปลง: {change} ({pct_change}%)\n"
                f"• สูงสุด / ต่ำสุด: {high} / {low}\n"
                f"• ปริมาณ (สัญญา): {volume:,} \n"
                f"• สถานะคงค้าง: {oi:,}\n"
                f"• ราคาเปิด / ราคาเฉลี่ย: {open_p} / {avg_p}\n"
            )
            
        summary_text = "\n".join(lines)
        summary_text += f"\n📊 รวม SET50 Futures\n• ปริมาณรวม: {total_vol:,} สัญญา\n• สถานะคงค้างรวม: {total_oi:,} สัญญา"
        return summary_text
    except Exception as e:
        print(f"ไม่สามารถแปลงข้อมูลแบบ Direct สรุปได้: {e}")
        return "ไม่สามารถประมวลผลข้อมูล SET50 Futures ได้ในขณะนี้"

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
    
    max_retries = 5
    for attempt in range(max_retries):
        try:
            print(f"กำลังเรียก Gemini API (gemini-3.8-flash) ครั้งที่ {attempt + 1}...")
            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt
            )
            print("Gemini Summary Success!")
            return response.text
        except Exception as e:
            err_msg = str(e)
            if "503" in err_msg or "UNAVAILABLE" in err_msg:
                wait_time = (attempt + 1) * 5
                print(f"เซิร์ฟเวอร์หนาแน่น (503) รอ {wait_time} วินาทีก่อนลองใหม่...")
                time.sleep(wait_time)
            else:
                print(f"เกิดข้อผิดพลาด: {err_msg}")
                break
                
    print("Gemini API ไม่พร้อมใช้งานเนื่องจากเซิร์ฟเวอร์หนาแน่น สลับไปใช้การจัดรูปแบบข้อความโดยตรง...")
    return build_direct_summary(raw_data)

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
        send_line_message(summary)
        print("ทำงานสำเร็จ!")
    except Exception as e:
        print(f"เกิดข้อผิดพลาด: {e}")
