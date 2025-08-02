import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime
import re

# 카카오 API 키
KAKAO_API_KEY = '883c83743371e851ef54b213c1728657'

st.title("Power Outage Navigator (Streamlit GUI)")

# --- 매핑 함수들 ---
def normalize_colname(col):
    return col.replace(' ', '').replace('\t', '').replace('\n', '')

def read_csv_auto_encoding(file, skiprows=0):
    for enc in ['utf-8', 'euc-kr', 'cp949']:
        try:
            file.seek(0)
            return pd.read_csv(file, encoding=enc, skiprows=skiprows)
        except Exception:
            file.seek(0)
    st.error("CSV 파일을 읽을 수 없습니다. 인코딩을 확인하세요.")
    return None

def search_kakao_api_region(customer_name):
    region_keywords = ["부산", "울산", "경남"]
    search_patterns = [f"{customer_name} {region}" for region in region_keywords]
    for pattern in search_patterns:
        url = "https://dapi.kakao.com/v2/local/search/keyword.json"
        headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
        params = {"query": pattern, "size": 5}
        try:
            response = requests.get(url, headers=headers, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data['documents']:
                    for place in data['documents']:
                        address = place.get('address_name') or place.get('road_address_name') or "정보없음"
                        phone = place.get('phone', '') or "정보없음"
                        if any(region in address for region in region_keywords):
                            return address, phone, f"카카오 API({pattern})"
            elif response.status_code == 429:
                time.sleep(2)
                break
        except Exception:
            continue
    return "정보없음", "정보없음", "검색 실패"

def normalize_city(addr):
    addr = addr.replace('부산 ', '부산광역시 ').replace('울산 ', '울산광역시 ').replace('경남 ', '경상남도 ')
    addr = addr.replace('부산광역시광역시', '부산광역시').replace('울산광역시광역시', '울산광역시').replace('경상남도상남도', '경상남도')
    return addr.strip()

def extract_gudongbunji(addr):
    m = re.search(r'(\w+구)\s(\w+동)\s([0-9\-]+)', addr)
    if m:
        bunji = m.group(3)
        if bunji.endswith('-0'):
            bunji = bunji[:-2]
        return m.group(1), m.group(2), bunji
    m = re.search(r'(\w+구)\s(\w+동)', addr)
    if m:
        return m.group(1), m.group(2), ''
    return '', '', ''

def find_equipment_by_real_address(address, equipment_df):
    if equipment_df is None:
        return "정보없음", "매칭 실패"
    try:
        gu, dong, bunji = extract_gudongbunji(normalize_city(address))
        if not gu or not dong or not bunji:
            return "정보없음", "구/동/번지 불완전"
        def row_match(row):
            eq_addr = normalize_city(str(row['주소']))
            eq_gu, eq_dong, eq_bunji = extract_gudongbunji(eq_addr)
            # 구/동/번지 모두 일치해야만 매칭
            return gu == eq_gu and dong == eq_dong and bunji == eq_bunji
        matches = equipment_df[equipment_df.apply(row_match, axis=1)]
        if not matches.empty:
            total_equipment = matches['장비수'].fillna(0).astype(int).sum()
            return total_equipment, "정확 일치"
    except Exception:
        return "정보없음", "매칭 오류"
    return "정보없음", "정확 일치 없음"

# --- Streamlit 인터페이스 ---
outage_file = st.file_uploader("정전대상 CSV 업로드", type=["csv"])
equipment_file = st.file_uploader("l2샘플(장비DB) CSV 업로드", type=["csv"])

skiprows = 0
if outage_file is not None:
    preview = None
    for enc in ['utf-8', 'euc-kr', 'cp949']:
        try:
            outage_file.seek(0)
            preview = outage_file.getvalue().decode(enc)
            break
        except Exception:
            continue
    if preview is not None:
        st.write("CSV 미리보기 (상위 10줄):")
        lines = preview.splitlines()
        for i, line in enumerate(lines[:10]):
            st.write(f"{i}: {line}")
    else:
        st.write("미리보기 불가: 인코딩 문제")
    skiprows = st.number_input("데이터 시작 전 건너뛸 줄 수", min_value=0, max_value=20, value=0)

if st.button("주소 매핑 실행"):
    if outage_file and equipment_file:
        outage_df = read_csv_auto_encoding(outage_file, skiprows=skiprows)
        equipment_df = read_csv_auto_encoding(equipment_file)
        if outage_df is None or equipment_df is None:
            st.stop()
        # 컬럼명 정규화 및 표준화
        outage_df.columns = [normalize_colname(c) for c in outage_df.columns]
        equipment_df.columns = [normalize_colname(c) for c in equipment_df.columns]
        for col in equipment_df.columns:
            if col in ['주소', '사업장주소']:
                equipment_df = equipment_df.rename(columns={col: '주소'})
            if '수' in col:
                equipment_df = equipment_df.rename(columns={col: '장비수'})
        # 필수 컬럼 체크
        st.write("정전대상 CSV 실제 컬럼명:", list(outage_df.columns))
        required_cols = ['일자', '요일', '시간', '고객명']
        missing_cols = [col for col in required_cols if col not in outage_df.columns]
        if missing_cols:
            st.error(f"정전대상 CSV에 다음 컬럼이 필요합니다: {missing_cols}")
            st.stop()
        # 매핑 처리
        results = []
        for idx, row in outage_df.iterrows():
            date = str(row['일자']).strip()
            weekday = str(row['요일']).strip()
            time_ = str(row['시간']).strip()
            customer_name = str(row['고객명']).strip()
            address, phone, _ = search_kakao_api_region(customer_name)
            equipment_count, match_method = find_equipment_by_real_address(address, equipment_df)
            results.append({
                '일자': date,
                '요일': weekday,
                '시간': time_,
                '고객명': customer_name,
                '실제주소': address,
                '전화번호': phone,
                '총장비수': equipment_count,
                '매칭방법': match_method
            })
        result_df = pd.DataFrame(results)
        
        # 데이터 타입 변환으로 PyArrow 오류 방지
        try:
            # 총장비수 컬럼을 숫자로 변환 (문자열은 NaN으로 처리)
            result_df['총장비수'] = pd.to_numeric(result_df['총장비수'], errors='coerce')
            # NaN 값을 '정보없음'으로 다시 변환
            result_df['총장비수'] = result_df['총장비수'].fillna('정보없음')
        except Exception as e:
            st.warning(f"데이터 타입 변환 중 오류: {e}")
        
        # 표 행 간격/텍스트 크기 조정 CSS
        st.markdown(
            """
            <style>
            .stDataFrame tbody tr {
                height: 24px !important;
            }
            .stDataFrame td {
                padding-top: 2px !important;
                padding-bottom: 2px !important;
                font-size: 14px !important;
            }
            </style>
            """,
            unsafe_allow_html=True
        )
        st.dataframe(result_df)
        # 간단한 통계만 출력
        total = len(result_df)
        address_success = len(result_df[result_df['실제주소'] != '정보없음'])
        equipment_success = len(result_df[result_df['총장비수'] != '정보없음'])
        st.markdown(f"**전체:** {total}건 | **실제 주소 성공:** {address_success}건 | **장비 매칭 성공:** {equipment_success}건")
        # 결과 다운로드
        csv = result_df.to_csv(index=False, encoding='utf-8-sig')
        st.download_button("결과 CSV 다운로드", csv, file_name="진짜스마트매핑_결과.csv", mime="text/csv")
    else:
        st.warning("두 개의 CSV 파일을 모두 업로드하세요.") 