import os
import json
import time
import requests
from google import genai

def get_tfex_data():
    # ใช้ Endpoint API ตรงของ Settrade สำหรับดึงข้อมูล Equity Index Futures (SET50)
    url = "https://www.settrade.com/api/settrade/derivatives/market-data/trading-quotation-by-series?underlying=SET50"
    
    # ส่ง Headers จำลองเป็น Browser จริง เพื่อไม่ให้ระบบ Anti-bot ของ Settrade บล็อก
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.settrade.com/th/derivatives/market-data/trading-quotation-by-series",
        "Origin": "https://www.settrade.com"
    }
    
    try:
        session = requests.Session()
        # เรียกหน้าเว็บหลักก่อน 1 รอบเพื่อให้ได้ Cookie
        session.get("https://www.settrade.com/th/derivatives/market-data/trading-quotation-by-series", headers=headers, timeout=10)
        
        # ยิง API เพื่อขอข้อมูล JSON จริง
        response = session.get(url, headers=headers, timeout=10)
        if response.status_code == 200 and "seriesList" in response.text:
            print("ดึงข้อมูล JSON จาก Settrade API สำเร็จ!")
            return response.text
        else:
            print(f"API ตอบกลับ Status Code: {response.status_code}")
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการเรียก API: {e}")
    
    return None

def build_direct_summary(raw_json_str):
    """ฟังก์ชันจัดข้อความโดยตรงจาก JSON (ในกรณี Gemini API ไม่ตอบกลับ)"""
    try:
        data = json.loads(raw_json_str)
        series_list = data.get("derivativesTradingQuotationBySeries", {}).get("seriesList", [])
        
        if not series_list:
            return "ไม่พบข้อมูล Series ของ SET50 Futures"

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
                f"🔷 **{symbol}**\n"
                f"• ล่าสุด: {last}\n"
                f"• เปลี่ยนแปลง: {change} ({pct_change}%)\n"
                f"• สูงสุด / ต่ำสุด: {high} / {low}\n"
                f"• ราคาเปิด / เฉลี่ย: {open_p} / {avg_p}\n"
                f"• ปริมาณ: {volume:,} สัญญา\n"
                f"• สถานะคงค้าง (OI): {oi:,} สัญญา\n"
            )
            
        summary_text = "\n".join(lines)
        summary_text += f"\n📊 **รวม SET50 Futures**\n• ปริมาณรวม: {total_vol:,} สัญญา\n• สถานะคงค้างรวม: {total_oi:,} สัญญา"
        return summary_text
    except Exception as e:
        print(f"Error Direct Formatting: {e}")
        return "เกิดข้อผิดพลาดในการประมวลผลตารางตัวเลข"

def summarize_with_gemini(raw_data):
    api_key = os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
    จากข้อมูล JSON ตลาด TFEX ด้านล่างนี้ ให้สกัดข้อมูลของ SET50 Futures ทุก Series ทั้งหมดที่มี
    จัดรูปแบบเป็นข้อความสำหรับส่งเข้า LINE โดยให้แสดงข้อมูลของแต่ละ Series ดังนี้:

    🔷 [ชื่อย่อสัญญา]
    • ล่าสุด: 
    • เปลี่ยนแปลง: (พร้อม %)
    • สูงสุด / ต่ำสุด: 
    • ราคาเปิด / เฉลี่ย: 
    • ปริมาณ: (สัญญา)
    • สถานะคงค้าง (OI): (สัญญา)

    พร้อมสรุปผลรวม ปริมาณสัญญา และ สถานะคงค้าง รวมทั้งหมดท้ายข้อความด้วย

    ข้อมูลดิบ:
    {raw_data}
    """
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"กำลังเรียก Gemini API ครั้งที่ {attempt + 1}...")
            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt
            )
            print("Gemini ประมวลผลสำเร็จ!")
            return response.text
        except Exception as e:
            err_msg = str(e)
            if "503" in err_msg or "UNAVAILABLE" in err_msg:
                wait_time = (attempt + 1) * 4
                print(f"เซิร์ฟเวอร์หนาแน่น (503) รอ {wait_time} วินาที...")
                time.sleep(wait_time)
            else:
                print(f"เกิดข้อผิดพลาดกับ Gemini: {err_msg}")
                break
                
    print("Gemini API เซิร์ฟเวอร์ไม่พร้อม สลับไปใช้ระบบ Direct Formatter...")
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
        if raw:
            summary = summarize_with_gemini(raw)
            send_line_message(summary)
            print("ทำงานสำเร็จ!")
        else:
            print("ไม่สามารถดึงข้อมูล JSON จาก Settrade ได้")
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการทำงาน: {e}")
