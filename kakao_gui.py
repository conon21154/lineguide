import pandas as pd
import requests
import time

# 🔐 네이버 API 키 입력
client_id = "I3REcW_cSNoPq4X68CNj"
client_secret = "LqfNB7lRi6ENjyt1D3nbU35PbwH4ZSYoPTLg6IMR"

headers = {
    "X-Naver-Client-Id": client_id,
    "X-Naver-Client-Secret": client_secret
}

# 📄 엑셀 불러오기
df = pd.read_excel("매핑요청.xlsx")
df.columns = df.columns.str.strip().str.replace(r"\s+", "", regex=True)

# 🧭 '대표장비주소' 기준으로 검색
df["업체명"] = ""
df["전화번호"] = ""

for i, row in df.iterrows():
    query = row["대표장비주소"]
    url = f"https://openapi.naver.com/v1/search/local.json?query={query}&display=1"

    try:
        response = requests.get(url, headers=headers)
        result = response.json()

        if result["items"]:
            item = result["items"][0]
            df.at[i, "업체명"] = item["title"].replace("<b>", "").replace("</b>", "")
            df.at[i, "전화번호"] = item["telephone"] or "전화번호 없음"
        else:
            df.at[i, "업체명"] = "검색결과 없음"
            df.at[i, "전화번호"] = "검색결과 없음"

        time.sleep(0.3)  # API 요청 간격 제한
    except Exception as e:
        print(f"{i}행 처리 중 오류:", e)

# 📁 결과 저장
