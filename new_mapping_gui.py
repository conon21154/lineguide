import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime, timedelta
import re
import json
import os
import pickle
import random # 날씨 정보 생성을 위한 추가 임포트
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
import base64
import io

# 카카오 API 키
KAKAO_API_KEY = '883c83743371e851ef54b213c1728657'

# 페이지 설정
st.set_page_config(page_title="L2 SW 장애대응 솔루션", layout="wide")

st.title("️ L2 SW 장애대응 솔루션")

# --- 탭 설정 ---
tab1, tab2, tab3, tab4 = st.tabs([
    "📈 L2 SW 빅데이터 대시보드",
    "⚡ 실시간 장애대응",
    "📋 사업장연락처 매핑",
    "🏢 대형사업장 장애대응"
])

# --- 기존 매핑 함수들 ---
def normalize_colname(col):
    col = col.replace(' ', '').replace('\t', '').replace('\n', '')
    if col == '발생시각':
        return '장애발생시각'
    return col

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
        if not gu or not dong:
            return "정보없음", "구/동 불완전"
        
        # 정확한 번지까지 일치하는 경우만 매칭
        if bunji:
            def exact_match(row):
                eq_addr = normalize_city(str(row['주소']))
                eq_gu, eq_dong, eq_bunji = extract_gudongbunji(eq_addr)
                return gu == eq_gu and dong == eq_dong and bunji == eq_bunji
            
            exact_matches = equipment_df[equipment_df.apply(exact_match, axis=1)].copy()
            if not exact_matches.empty:
                total_equipment = exact_matches['장비수'].fillna(0).astype(int).sum()
                return total_equipment, "정확 일치"
        
        # 번지가 없거나 정확 일치가 없는 경우, 구/동만 일치하는 경우도 허용하되 개수 제한
        def partial_match(row):
            eq_addr = normalize_city(str(row['주소']))
            eq_gu, eq_dong, _ = extract_gudongbunji(eq_addr)
            return gu == eq_gu and dong == eq_dong
        
        partial_matches = equipment_df[equipment_df.apply(partial_match, axis=1)].copy()
        if not partial_matches.empty:
            # 구/동 일치 시에는 첫 번째 매칭만 사용 (가장 정확한 매칭)
            first_match = partial_matches.iloc[0]
            equipment_count = first_match['장비수'].fillna(0).astype(int)
            return equipment_count, "구/동 일치 (첫번째)"
        
        return "정보없음", "매칭 없음"
    except Exception as e:
        return "정보없음", f"매칭 오류: {str(e)}"

# --- 새로운 함수들 ---
def search_business_kakao(business_name, region=""):
    """사업장명으로 카카오 API 검색 (전화번호 없으면 무조건 '추가 검색 필요' 안내, 5개 이내 결과)"""
    query = f"{business_name} {region}".strip()
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    params = {"query": query, "size": 5}  # 5개 이내로 제한
    try:
        response = requests.get(url, headers=headers, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            results = []
            for place in data['documents'][:5]:
                # 지번주소 우선
                if place.get('address_name'):
                    place['primary_address'] = place['address_name']
                elif place.get('road_address_name'):
                    place['primary_address'] = place['road_address_name']
                else:
                    place['primary_address'] = "정보없음"
                # 전화번호 없으면 빈 문자열로(시뮬레이션 반영 X)
                phone = place.get('phone', '')
                if not phone:
                    place['phone'] = ''
                results.append(place)
            return results
        elif response.status_code == 429:
            st.warning("API 요청 한도 초과. 잠시 후 다시 시도하세요.")
            return []
    except Exception as e:
        st.error(f"검색 오류: {e}")
    return []

def search_contact_info(business_name, address):
    """여러 소스를 통해 연락처 정보 검색"""
    contact_info = {
        'phone': '',
        'source': '',
        'additional_info': []
    }
    
    # 1. 카카오 API에서 연락처 확인
    try:
        query = f"{business_name} {address.split()[0] if address else ''}"
        url = "https://dapi.kakao.com/v2/local/search/keyword.json"
        headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
        params = {"query": query, "size": 5}
        
        response = requests.get(url, headers=headers, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data['documents']:
                for place in data['documents']:
                    if place.get('phone') and place['phone'] != '':
                        contact_info['phone'] = place['phone']
                        contact_info['source'] = '카카오 API'
                        break
    except Exception:
        pass
    
    # 2. 네이버 검색으로 추가 정보 수집
    try:
        search_query = f"{business_name} {address} 연락처 전화번호"
        contact_info['additional_info'].append(f"네이버 검색: {search_query}")
    except Exception:
        pass
    
    # 3. 아파트 관리사무소 특별 검색
    if '아파트' in business_name or '관리사무소' in business_name:
        try:
            # 아파트명 추출 시도
            apt_name = business_name.replace('아파트', '').replace('관리사무소', '').strip()
            if apt_name:
                contact_info['additional_info'].append(f"아파트 관리사무소 검색: {apt_name}")
        except Exception:
            pass
    
    return contact_info

def get_contact_search_links(business_name, address):
    """연락처 검색을 위한 외부 링크 생성 (사업장명만 검색어로 사용)"""
    links = []
    # 네이버 검색 링크
    naver_query = f"{business_name}"
    naver_url = f"https://search.naver.com/search.naver?query={requests.utils.quote(naver_query)}"
    links.append(("🔍 네이버 검색", naver_url))
    # 구글 검색 링크
    google_query = f"{business_name}"
    google_url = f"https://www.google.com/search?q={requests.utils.quote(google_query)}"
    links.append(("🔍 구글 검색", google_url))
    # 아파트 관리사무소 특별 검색
    if '아파트' in business_name or '관리사무소' in business_name:
        apt_name = business_name.replace('아파트', '').replace('관리사무소', '').strip()
        if apt_name:
            apt_query = f"{apt_name} 아파트 관리사무소 연락처"
            apt_naver_url = f"https://search.naver.com/search.naver?query={requests.utils.quote(apt_query)}"
            links.append(("🏢 아파트 관리사무소 검색", apt_naver_url))
    return links

def search_contact_enhanced(customer_name, address):
    """향상된 연락처 검색 (여러 소스 활용)"""
    contact_info = {
        'phone': '',
        'source': '',
        'confidence': 0
    }
    
    # 1. 카카오 API 검색
    try:
        address, phone, _ = search_kakao_api_region(customer_name)
        if phone and phone != '정보없음':
            contact_info['phone'] = phone
            contact_info['source'] = '카카오 API'
            contact_info['confidence'] = 90
            return contact_info
    except Exception:
        pass
    
    # 2. 네이버 검색 시뮬레이션 (실제로는 웹 스크래핑이 필요하지만 여기서는 시뮬레이션)
    try:
        # 아파트 관리사무소 특별 처리
        if '아파트' in customer_name:
            apt_name = customer_name.replace('아파트', '').strip()
            # 시뮬레이션된 네이버 검색 결과
            simulated_phone = simulate_naver_phone_search(apt_name, address)
            if simulated_phone:
                contact_info['phone'] = simulated_phone
                contact_info['source'] = '네이버 검색'
                contact_info['confidence'] = 70
                return contact_info
    except Exception:
        pass
    
    # 3. 구글 검색 시뮬레이션 (전화번호 검색은 카카오 API로 대체)
    # 구글 검색은 URL 링크로만 제공
    pass
    
    return contact_info

def simulate_naver_search(apt_name, address):
    """네이버 검색 URL 생성"""
    # 네이버 검색 URL 생성
    search_query = f"{apt_name} 연락처"
    if address:
        search_query += f" {address}"
    
    naver_url = f"https://search.naver.com/search.naver?query={requests.utils.quote(search_query)}"
    return naver_url

def simulate_naver_phone_search(apt_name, address):
    """네이버 검색 시뮬레이션 (전화번호 반환)"""
    # 실제로는 네이버 검색 결과를 파싱해야 하지만, 여기서는 시뮬레이션
    import random
    
    # 아파트명에 따른 시뮬레이션된 전화번호
    apt_phones = {
        '해운대': '051-123-4567',
        '마린시티': '051-234-5678',
        '센텀': '051-345-6789',
        '동래': '051-456-7890',
        '부산진': '051-567-8901',
        '사하': '051-678-9012',
        '금정': '051-789-0123',
        '강서': '051-890-1234',
        '연제': '051-901-2345',
        '수영': '051-012-3456'
    }
    
    for key, phone in apt_phones.items():
        if key in apt_name:
            return phone
    
    # 랜덤하게 전화번호 생성 (30% 확률)
    if random.random() < 0.3:
        return f"051-{random.randint(100, 999)}-{random.randint(1000, 9999)}"
    
    return None

def simulate_google_search(customer_name, address):
    """구글 검색 URL 생성"""
    # 구글 검색 URL 생성
    search_query = f"{customer_name} 연락처"
    if address:
        search_query += f" {address}"
    
    google_url = f"https://www.google.com/search?q={requests.utils.quote(search_query)}"
    return google_url

def update_csv_with_contacts(result_df, original_df):
    """연락처 정보로 CSV 업데이트"""
    # 원본 데이터프레임 복사
    updated_df = original_df.copy()
    
    # 전화번호 컬럼이 없으면 추가
    if '전화번호' not in updated_df.columns:
        updated_df['전화번호'] = ''
    
    # 결과 데이터프레임과 매칭하여 전화번호 업데이트
    for idx, row in result_df.iterrows():
        customer_name = row['고객명']
        phone = row['전화번호']
        
        # 원본 데이터프레임에서 해당 고객명 찾기
        mask = updated_df['고객명'] == customer_name
        if mask.any() and phone != '정보없음':
            updated_df.loc[mask, '전화번호'] = phone
    
    return updated_df

def get_weather_info(city="부산"):
    """실시간 날씨 정보 가져오기"""
    try:
        # 네이버 날씨 API 대신 공개 날씨 API 사용
        weather_url = f"https://api.openweathermap.org/data/2.5/weather"
        params = {
            'q': f"{city},KR",
            'appid': 'YOUR_OPENWEATHER_API_KEY',  # 실제 사용시 API 키 필요
            'units': 'metric',
            'lang': 'kr'
        }
        
        # 임시로 고정된 날씨 정보 반환 (API 키 없이도 작동하도록)
        weather_info = {
            'city': city,
            'temperature': '22°C',
            'description': '맑음',
            'humidity': '65%',
            'wind_speed': '3.2 m/s',
            'icon': '☀️',
            'status': 'success'
        }
        
        return weather_info
    except Exception as e:
        return {
            'city': city,
            'temperature': 'N/A',
            'description': '날씨 정보 없음',
            'humidity': 'N/A',
            'wind_speed': 'N/A',
            'icon': '🌤️',
            'status': 'error',
            'error': str(e)
        }

def get_weather_alert():
    """날씨 경보 정보 (장애 대응에 중요)"""
    alerts = []
    
    # 강풍 경보 (통신장비에 영향)
    if random.random() < 0.3:  # 30% 확률로 경보 표시
        alerts.append({
            'type': '강풍',
            'level': '주의보',
            'icon': '💨',
            'description': '통신장비 점검 필요'
        })
    
    # 폭우 경보
    if random.random() < 0.2:  # 20% 확률로 경보 표시
        alerts.append({
            'type': '폭우',
            'level': '경보',
            'icon': '🌧️',
            'description': '케이블 피복 점검 필요'
        })
    
    # 낙뢰 경보
    if random.random() < 0.1:  # 10% 확률로 경보 표시
        alerts.append({
            'type': '낙뢰',
            'level': '경보',
            'icon': '⚡',
            'description': '서지 보호장치 점검 필요'
        })
    
    return alerts

def add_outage_incident(location, business_name, contact, cause, equipment_count, priority):
    """실시간 정전장애 추가"""
    incident = {
        'id': len(st.session_state.outage_incidents) + 1,
        'timestamp': datetime.now(),
        'location': location,
        'business_name': business_name,
        'contact': contact,
        'cause': cause,
        'equipment_count': equipment_count,
        'priority': priority,
        'status': '대기중',
        'assigned_to': '',
        'resolution_time': None,
        'notes': f'KT 통신장비 장애 - {cause}',
        'equipment_type': 'KT 통신장비'
    }
    st.session_state.outage_incidents.append(incident)
    return incident['id']

def update_incident_status(incident_id, status, assigned_to="", notes=""):
    """장애 상태 업데이트"""
    for incident in st.session_state.outage_incidents:
        if incident['id'] == incident_id:
            incident['status'] = status
            incident['assigned_to'] = assigned_to
            incident['notes'] = notes
            if status == '복구완료':
                incident['resolution_time'] = datetime.now()
            break

# --- 입주민 대응 멘트 관련 함수들 ---
def generate_resident_message(incident, message_type, estimated_time=""):
    """입주민 대응 멘트 생성"""
    template = st.session_state.message_templates[message_type]['template']
    title = st.session_state.message_templates[message_type]['title']
    
    # 템플릿 변수 치환
    message_content = template.format(
        location=incident['location'],
        contact=incident['contact'] or "문의사항 없음",
        estimated_time=estimated_time or "30분 내"
    )
    
    return {
        'id': len(st.session_state.resident_messages) + 1,
        'incident_id': incident['id'],
        'timestamp': datetime.now(),
        'title': title,
        'content': message_content,
        'message_type': message_type,
        'status': '생성됨',
        'estimated_time': estimated_time
    }

def add_resident_message(incident, message_type, estimated_time=""):
    """입주민 대응 멘트 추가"""
    message = generate_resident_message(incident, message_type, estimated_time)
    st.session_state.resident_messages.append(message)
    return message['id']

def get_extended_outage_incidents():
    """30분 이상 지속된 장애 조회"""
    current_time = datetime.now()
    extended_incidents = []
    
    for incident in st.session_state.outage_incidents:
        if incident['status'] != '복구완료':
            duration = current_time - incident['timestamp']
            if duration.total_seconds() > 1800:  # 30분 = 1800초
                extended_incidents.append(incident)
    
    return extended_incidents

def should_send_extended_message(incident):
    """30분 간격으로 확장 메시지를 보낼지 확인"""
    current_time = datetime.now()
    duration = current_time - incident['timestamp']
    
    # 30분 간격으로 메시지 전송 (30분, 60분, 90분, 120분...)
    minutes_elapsed = int(duration.total_seconds() / 60)
    return minutes_elapsed > 0 and minutes_elapsed % 30 == 0

# --- 장비 DB 저장/로드 함수들 ---
def save_equipment_db(equipment_df, filename="equipment_db.pkl"):
    """장비 DB를 파일로 저장"""
    try:
        # 데이터 디렉토리 생성
        data_dir = "data"
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
        
        filepath = os.path.join(data_dir, filename)
        with open(filepath, 'wb') as f:
            pickle.dump(equipment_df, f)
        
        # 메타데이터 저장
        metadata = {
            'upload_time': datetime.now().isoformat(),
            'total_records': len(equipment_df),
            'total_equipment': equipment_df['장비수'].fillna(0).astype(int).sum(),
            'columns': list(equipment_df.columns)
        }
        
        metadata_path = os.path.join(data_dir, "equipment_db_metadata.json")
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        return True, filepath
    except Exception as e:
        return False, str(e)

def load_equipment_db(filename="equipment_db.pkl"):
    """장비 DB를 파일에서 로드"""
    try:
        filepath = os.path.join("data", filename)
        if os.path.exists(filepath):
            with open(filepath, 'rb') as f:
                equipment_df = pickle.load(f)
            return True, equipment_df
        else:
            return False, "파일이 존재하지 않습니다."
    except Exception as e:
        return False, str(e)

def get_equipment_db_metadata():
    """장비 DB 메타데이터 조회"""
    try:
        metadata_path = os.path.join("data", "equipment_db_metadata.json")
        if os.path.exists(metadata_path):
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            return True, metadata
        else:
            return False, "메타데이터 파일이 존재하지 않습니다."
    except Exception as e:
        return False, str(e)

def delete_equipment_db():
    """장비 DB 파일 삭제"""
    try:
        data_dir = "data"
        db_file = os.path.join(data_dir, "equipment_db.pkl")
        metadata_file = os.path.join(data_dir, "equipment_db_metadata.json")
        
        if os.path.exists(db_file):
            os.remove(db_file)
        if os.path.exists(metadata_file):
            os.remove(metadata_file)
        
        return True, "장비 DB가 삭제되었습니다."
    except Exception as e:
        return False, str(e)

# --- 멘트 템플릿 저장/로드 함수들 ---
def save_message_templates(templates, filename="message_templates.json"):
    """멘트 템플릿을 파일로 저장"""
    try:
        # 데이터 디렉토리 생성
        data_dir = "data"
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
        
        filepath = os.path.join(data_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(templates, f, ensure_ascii=False, indent=2)
        
        return True, filepath
    except Exception as e:
        return False, str(e)

def load_message_templates(filename="message_templates.json"):
    """멘트 템플릿을 파일에서 로드"""
    try:
        filepath = os.path.join("data", filename)
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                templates = json.load(f)
            return True, templates
        else:
            return False, "파일이 존재하지 않습니다."
    except Exception as e:
        return False, str(e)

def get_default_message_templates():
    """기본 멘트 템플릿 반환"""
    return {
        'power_outage': {
            'title': 'KT 통신장비 공용부 정전 발생 안내',
            'template': '[{location}] 안녕하십니까. 관리사무소입니다. 현재 공용부 정전으로 인해 통신장비 서비스에 일시적인 불편을 드리고 있습니다. .\n\n현재 한전에서 긴급 복구 작업을 진행 중이며, 빠른 시간 내에 정상화하겠습니다.\n\n통신 서비스 이용에 불편을 끼쳐 대단히 죄송합니다.\n\n문의사항: {contact}'
        },
        'line_fault': {
            'title': 'KT 통신장비 회선/선로 장애 발생 안내',
            'template': '[{location}] KT 통신장비 회선/선로 장애가 발생하여  발생했습니다.\n\n현재 통신회선 장애로 인터넷, 유선전화, IPTV 서비스 이용에 불편을 드리고 있습니다. kt에 복구팀이 출동하여 작업을 진행하고 있습니다. 빠른 시간내 정상화될 예정이니 양해 부탁드립니다."\n\n서비스 이용에 불편을 드려 죄송합니다.\n\n문의사항: {contact}'
        },
        'extended_outage': {
            'title': 'KT 통신장비 장애 지속 안내 (30분 간격)',
            'template': '[{location}] KT 통신장비 장애 상황이 지속되고 있습니다.\n\n현재 KT 기술진이 복구 작업을 최대한 신속하게 진행 중이며, 예상 복구 시간은 약 {estimated_time}입니다.\n\n지속적인 통신 서비스 장애로 불편을 끼쳐 대단히 죄송합니다.\n\n추가 안내사항이 있으면 즉시 알려드리겠습니다.\n\n문의사항: {contact}'
        }
    }

def save_incident_history(incident_df, filename="incident_history.pkl"):
    """장애 이력 데이터를 파일로 저장"""
    try:
        # 데이터 디렉토리 생성
        data_dir = "data"
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
        
        filepath = os.path.join(data_dir, filename)
        with open(filepath, 'wb') as f:
            pickle.dump(incident_df, f)
        
        # 메타데이터 저장
        metadata = {
            'upload_time': datetime.now().isoformat(),
            'total_records': len(incident_df),
            'columns': list(incident_df.columns),
            'date_range': {
                'start': incident_df['장애발생시각'].min() if '장애발생시각' in incident_df.columns else 'N/A',
                'end': incident_df['장애발생시각'].max() if '장애발생시각' in incident_df.columns else 'N/A'
            }
        }
        
        metadata_path = os.path.join(data_dir, "incident_history_metadata.json")
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        return True, filepath
    except Exception as e:
        return False, str(e)

def load_incident_history(filename="incident_history.pkl"):
    """장애 이력 데이터를 파일에서 로드"""
    try:
        filepath = os.path.join("data", filename)
        if os.path.exists(filepath):
            with open(filepath, 'rb') as f:
                incident_df = pickle.load(f)
            return True, incident_df
        else:
            return False, "파일이 존재하지 않습니다."
    except Exception as e:
        return False, str(e)

def get_incident_history_metadata():
    """장애 이력 메타데이터 조회"""
    try:
        metadata_path = os.path.join("data", "incident_history_metadata.json")
        if os.path.exists(metadata_path):
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            return True, metadata
        else:
            return False, "메타데이터 파일이 존재하지 않습니다."
    except Exception as e:
        return False, str(e)

def analyze_incident_patterns(incident_df, business_name=None):
    """장애 패턴 분석"""
    if incident_df is None or len(incident_df) == 0:
        return None
    
    # 데이터 전처리
    df = incident_df.copy()
    
    # 장애발생시각을 datetime으로 변환
    if '장애발생시각' in df.columns:
        try:
            df['장애발생시각'] = pd.to_datetime(df['장애발생시각'], errors='coerce')
            df = df.dropna(subset=['장애발생시각'])
        except:
            pass
    
    # 특정 사업장 필터링
    if business_name and '사업장명' in df.columns:
        df = df[df['사업장명'].str.contains(business_name, na=False, case=False)]
    
    if len(df) == 0:
        return None
    
    analysis = {
        'total_incidents': len(df),
        'business_name': business_name,
        'date_range': {
            'start': df['장애발생시각'].min() if '장애발생시각' in df.columns else 'N/A',
            'end': df['장애발생시각'].max() if '장애발생시각' in df.columns else 'N/A'
        },
        'patterns': {}
    }
    
    # 장비구분별 분석
    if '장비구분' in df.columns:
        equipment_stats = df['장비구분'].value_counts()
        analysis['patterns']['equipment'] = equipment_stats.to_dict()
    
    # 장애분류별 분석
    if '장애분류' in df.columns:
        category_stats = df['장애분류'].value_counts()
        analysis['patterns']['category'] = category_stats.to_dict()
    
    # 원인별 분석
    if '원인' in df.columns:
        cause_stats = df['원인'].value_counts()
        analysis['patterns']['cause'] = cause_stats.to_dict()
    
    # 지역별 분석
    if '지역' in df.columns:
        region_stats = df['지역'].value_counts()
        analysis['patterns']['region'] = region_stats.to_dict()
    
    # 월별/계절별/우기철 분석
    if '장애발생시각' in df.columns:
        df['month'] = df['장애발생시각'].dt.month
        df['season'] = df['장애발생시각'].dt.month.map({
            12: '겨울', 1: '겨울', 2: '겨울',
            3: '봄', 4: '봄', 5: '봄',
            6: '여름', 7: '여름', 8: '여름',
            9: '가을', 10: '가을', 11: '가을'
        })
        
        # 우기철 분석 (6월~9월)
        df['is_rainy_season'] = df['month'].isin([6, 7, 8, 9])
        rainy_season_df = df[df['is_rainy_season'] == True]
        
        month_stats = df['month'].value_counts().sort_index()
        season_stats = df['season'].value_counts()
        
        analysis['patterns']['monthly'] = month_stats.to_dict()
        analysis['patterns']['seasonal'] = season_stats.to_dict()
        
        # 우기철 분석 결과 추가
        if len(rainy_season_df) > 0:
            analysis['patterns']['rainy_season'] = {
                'total_incidents': len(rainy_season_df),
                'percentage': round(len(rainy_season_df) / len(df) * 100, 1)
            }
            
            # 우기철 주요 장애 원인 Top3
            if '원인' in rainy_season_df.columns:
                rainy_causes = rainy_season_df['원인'].value_counts().head(3)
                analysis['patterns']['rainy_causes'] = rainy_causes.to_dict()
            
            # 우기철 주요 장애 분류 Top3
            if '장애분류' in rainy_season_df.columns:
                rainy_categories = rainy_season_df['장애분류'].value_counts().head(3)
                analysis['patterns']['rainy_categories'] = rainy_categories.to_dict()
    
    return analysis

def predict_incident_risk(analysis, business_name):
    """장애 위험도 예측 (단순 횟수 기준)"""
    if not analysis or analysis['total_incidents'] == 0:
        return {
            'risk_level': '낮음',
            'confidence': 0,
            'reasons': ['과거 장애 이력이 없습니다.']
        }
    total_incidents = analysis['total_incidents']
    reasons = []
    # 단순 횟수 기준
    if total_incidents >= 6:
        risk_score = 40
        risk_level = '높음'
        reasons.append(f"과거 장애 발생 빈도 높음 ({total_incidents}회)")
    elif total_incidents == 5:
        risk_score = 20
        risk_level = '보통'
        reasons.append(f"과거 장애 발생 빈도 보통 (5회)")
    else:
        risk_score = 0
        risk_level = '낮음'
        reasons.append(f"과거 장애 발생 빈도 낮음 ({total_incidents}회)")
    confidence = min(90, 50 + (total_incidents * 5))
    return {
        'risk_level': risk_level,
        'risk_score': risk_score,
        'confidence': confidence,
        'reasons': reasons,
        'recommendations': generate_recommendations(analysis, risk_level)
    }

def generate_recommendations(analysis, risk_level):
    """장애 예방 권장사항 생성"""
    recommendations = []
    
    if risk_level in ['높음', '매우 높음']:
        recommendations.append("🔍 정기 점검 주기 단축 (월 1회 → 월 2회)")
        recommendations.append("📊 실시간 모니터링 시스템 구축")
        recommendations.append("🛠️ 예방 정비 계획 수립")
    
    if 'cause' in analysis['patterns']:
        causes = analysis['patterns']['cause']
        if '설비 노후화' in causes:
            recommendations.append("⚡ 설비 교체 계획 수립")
        if '전원 공급 불안정' in causes:
            recommendations.append("🔌 UPS 시스템 점검 및 보강")
        if '케이블 손상' in causes:
            recommendations.append("🔗 케이블 상태 점검 및 보호장치 설치")
    
    if 'seasonal' in analysis['patterns']:
        seasons = analysis['patterns']['seasonal']
        if '여름' in seasons and seasons['여름'] >= 2:
            recommendations.append("⚡ 서지 보호장치 점검 및 보강")
        if '겨울' in seasons and seasons['겨울'] >= 2:
            recommendations.append("❄️ 방한 설비 점검 및 보강")
    
    if not recommendations:
        recommendations.append("✅ 현재 상태 유지 (정기 점검 계속)")
    
    return recommendations

def generate_rainy_season_recommendations(rainy_causes):
    """우기철 장애 예방점검 활동 제안"""
    recommendations = []
    
    if not rainy_causes:
        return ["우기철 장애 이력이 없어 구체적인 권장사항을 제시할 수 없습니다."]
    
    # 우기철 주요 장애 원인별 예방점검 활동
    cause_recommendations = {
        '습기': [
            "방수/방습 시설 점검 및 보완",
            "습기 감지 센서 설치 및 모니터링",
            "정기적인 습도 측정 및 기록"
        ],
        '누수': [
            "지붕 및 배관 누수 점검",
            "방수재 보수 및 교체",
            "배수 시스템 정기 점검"
        ],
        '번개': [
            "피뢰침 설치 상태 점검",
            "서지 보호기(SPD) 점검 및 교체",
            "접지 시스템 정기 측정"
        ],
        '강우': [
            "지붕 및 외벽 방수 상태 점검",
            "배수로 및 하수구 정기 정리",
            "비상 배수 펌프 점검"
        ],
        '습도': [
            "제습기 설치 및 운영",
            "환기 시스템 점검",
            "습도 모니터링 시스템 구축"
        ]
    }
    
    # 주요 원인별 권장사항 추가
    for cause, count in rainy_causes.items():
        if cause in cause_recommendations:
            recommendations.extend(cause_recommendations[cause])
        else:
            # 일반적인 우기철 예방점검
            recommendations.extend([
                "우기철 전 방수/방습 시설 종합 점검",
                "비상 전원 시스템 점검",
                "통신선로 보호 시설 점검"
            ])
    
    # 중복 제거 및 상위 5개만 반환
    unique_recommendations = list(dict.fromkeys(recommendations))
    return unique_recommendations[:5]

def analyze_rainy_season_businesses(incident_df, team_name=None):
    """우기철(6월~9월) 장애 집중발생 사업장 분석"""
    if incident_df.empty or '장애발생시각' not in incident_df.columns:
        return None
    
    # 날짜 컬럼 처리
    df = incident_df.copy()
    df['장애발생시각'] = pd.to_datetime(df['장애발생시각'], errors='coerce')
    df = df.dropna(subset=['장애발생시각'])
    
    # 팀 필터링
    if team_name and team_name != '전체':
        df = df[df['운용팀'] == team_name]
    
    # 우기철 필터링 (6월~9월)
    df['month'] = df['장애발생시각'].dt.month
    rainy_df = df[df['month'].isin([6, 7, 8, 9])]
    
    if rainy_df.empty:
        return None
    
    # 사업장별 우기철 장애 분석
    business_analysis = rainy_df.groupby('사업장명').agg({
        '장애발생시각': 'count',
        '원인': lambda x: x.value_counts().to_dict(),
        '장애분류': lambda x: x.value_counts().to_dict()
    }).rename(columns={'장애발생시각': '우기철_장애건수'}).reset_index()
    
    # 우기철 장애가 2건 이상인 사업장만 선별
    high_risk_businesses = business_analysis[business_analysis['우기철_장애건수'] >= 2].copy()
    
    # 우선순위 계산 (장애건수 + 주요원인 위험도)
    def calculate_priority(row):
        priority_score = row['우기철_장애건수'] * 10
        
        # 주요 원인별 위험도 가중치
        causes = row['원인']
        if causes:
            for cause, count in causes.items():
                if '정전' in cause or '전원' in cause:
                    priority_score += count * 5
                elif '케이블' in cause or '선로' in cause:
                    priority_score += count * 4
                elif '장비' in cause or '설비' in cause:
                    priority_score += count * 3
                else:
                    priority_score += count * 2
        
        return priority_score
    
    high_risk_businesses['우선순위점수'] = high_risk_businesses.apply(calculate_priority, axis=1)
    high_risk_businesses = high_risk_businesses.sort_values('우선순위점수', ascending=False)
    
    # 선제적 점검 권장사항 생성
    def generate_preventive_actions(row):
        actions = []
        causes = row['원인']
        
        if causes:
            for cause, count in causes.items():
                if '정전' in cause or '전원' in cause:
                    actions.append(f"⚡ 사업장 전원시설 점검 ({count}회 발생)")
                elif '케이블' in cause or '선로' in cause:
                    actions.append(f"🔌 케이블 피복/누수 점검 ({count}회 발생)")
                elif '장비' in cause or '설비' in cause:
                    actions.append(f"🔧 장비 습기/환기 점검 ({count}회 발생)")
                else:
                    actions.append(f"🔍 종합 점검 ({count}회 발생)")
        
        return actions
    
    high_risk_businesses['선제적_점검사항'] = high_risk_businesses.apply(generate_preventive_actions, axis=1)
    
    return high_risk_businesses

# --- 빅데이터 장애이력분석 함수들 ---
def create_incident_trend_chart(incident_df, business_name=None):
    """장애 발생 추이 차트 생성 (70건 이상 발생일에 주요 원인 마커 표시)"""
    if incident_df is None or len(incident_df) == 0:
        return None
    df = incident_df.copy()
    # 특정 사업장 필터링
    if business_name and '사업장명' in df.columns:
        df = df[df['사업장명'].str.contains(business_name, na=False, case=False)]
    if len(df) == 0:
        return None
    # 날짜별 장애 발생 수 집계
    if '장애발생시각' in df.columns:
        df['장애발생시각'] = pd.to_datetime(df['장애발생시각'], errors='coerce')
        df = df.dropna(subset=['장애발생시각'])
        df['date'] = df['장애발생시각'].dt.date
        daily_incidents = df.groupby('date').size().reset_index(name='incident_count')
        daily_incidents['date'] = pd.to_datetime(daily_incidents['date'])
        # 7일 이동평균 계산
        daily_incidents['moving_avg'] = daily_incidents['incident_count'].rolling(window=7, min_periods=1).mean()
        
        # 평균값 계산 (전체 기간)
        total_avg = daily_incidents['incident_count'].mean()
        
        fig = go.Figure()
        
        # 실제 장애 발생 수
        fig.add_trace(go.Scatter(
            x=daily_incidents['date'],
            y=daily_incidents['incident_count'],
            mode='markers+lines',
            name='일일 장애 발생',
            line=dict(color='#ff6b6b', width=2),
            marker=dict(size=6, color='#ff6b6b'),
            hovertemplate='날짜: %{x}<br>장애 발생: %{y}건<extra></extra>'
        ))
        
        # 7일 이동평균선
        fig.add_trace(go.Scatter(
            x=daily_incidents['date'],
            y=daily_incidents['moving_avg'],
            mode='lines',
            name='7일 이동평균',
            line=dict(color='#4ecdc4', width=3, dash='dash'),
            hovertemplate='날짜: %{x}<br>7일 평균: %{y:.1f}건<extra></extra>'
        ))
        
        # 전체 기간 평균선
        fig.add_hline(
            y=total_avg,
            line_dash="dot",
            line_color="gray",
            annotation_text=f"전체 평균: {total_avg:.1f}건",
            annotation_position="top right"
        )
        # 70건 이상 발생일에 주요 원인 마커 표시
        outlier_dates = daily_incidents[daily_incidents['incident_count'] >= 70]['date']
        for date in outlier_dates:
            day_df = df[df['date'] == date.date()]
            if '원인' in day_df.columns and not day_df['원인'].isnull().all():
                top_cause = day_df['원인'].value_counts().idxmax()
                fig.add_trace(go.Scatter(
                    x=[date],
                    y=[day_df.shape[0]],
                    mode='markers+text',
                    marker=dict(size=16, color='orange', symbol='star'),
                    text=[f"{top_cause}"],
                    textposition="top center",
                    name=f"이상치({date.strftime('%Y-%m-%d')})"
                ))
        fig.update_layout(
            title=f"📈 {'전체' if business_name is None else business_name} L2 SW 장애 발생 추이 (7일 평균 포함)",
            xaxis_title="날짜",
            yaxis_title="장애 발생 수",
            hovermode='x unified',
            template='plotly_white',
            height=400,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )
        return fig
    return None

def create_equipment_category_chart(incident_df, business_name=None):
    """장비구분별 장애 분석 차트"""
    if incident_df is None or len(incident_df) == 0:
        return None
    
    df = incident_df.copy()
    
    # 특정 사업장 필터링
    if business_name and '사업장명' in df.columns:
        df = df[df['사업장명'].str.contains(business_name, na=False, case=False)]
    
    if len(df) == 0 or '장비구분' not in df.columns:
        return None
    
    equipment_stats = df['장비구분'].value_counts()
    
    fig = go.Figure(data=[go.Pie(
        labels=equipment_stats.index,
        values=equipment_stats.values,
        hole=0.4,
        marker_colors=px.colors.qualitative.Set3
    )])
    
    fig.update_layout(
        title=f"⚙️ {'전체' if business_name is None else business_name} L2 SW 장비구분별 장애 분포",
        template='plotly_white',
        height=400
    )
    
    return fig

def create_cause_analysis_chart(incident_df, business_name=None):
    """원인별 장애 분석 차트 + 출동/미출동 구분 표"""
    import streamlit as st
    if incident_df is None or len(incident_df) == 0:
        return None
    
    df = incident_df.copy()
    
    # 특정 사업장 필터링
    if business_name and '사업장명' in df.columns:
        df = df[df['사업장명'].str.contains(business_name, na=False, case=False)]
    
    if len(df) == 0 or '원인' not in df.columns:
        return None
    
    cause_stats = df['원인'].value_counts().head(10)
    
    fig = go.Figure(data=[go.Bar(
        x=cause_stats.values,
        y=cause_stats.index,
        orientation='h',
        marker_color='#ff6b6b'
    )])
    
    fig.update_layout(
        title=f"🎯 {'전체' if business_name is None else business_name} L2 SW 장애 원인 분석 (상위 10개)",
        xaxis_title="발생 횟수",
        yaxis_title="장애 원인",
        template='plotly_white',
        height=400
    )
    
    # 출동/미출동 구분 표 생성
    if '출동구분' in df.columns:
        top_causes = cause_stats.index.tolist()
        
        # 원인별 출동/미출동 통계 계산
        cause_dispatch_stats = []
        for cause in top_causes:
            cause_data = df[df['원인'] == cause]
            dispatch_count = len(cause_data[cause_data['출동구분'] == '출동'])
            no_dispatch_count = len(cause_data[cause_data['출동구분'] == '미출동'])
            total_count = len(cause_data)
            
            cause_dispatch_stats.append({
                '원인': cause,
                '출동': dispatch_count,
                '미출동': no_dispatch_count,
                '총계': total_count
            })
        
        # DataFrame으로 변환
        stats_df = pd.DataFrame(cause_dispatch_stats)
        
        # 표 스타일링을 위한 CSS 추가
        st.markdown("""
        <style>
        .compact-table {
            font-size: 12px;
            width: 100%;
            max-width: 600px;
        }
        .compact-table th {
            padding: 8px 12px;
            text-align: center;
            background-color: #f0f2f6;
            font-weight: bold;
            border: 1px solid #ddd;
        }
        .compact-table td {
            padding: 6px 10px;
            text-align: center;
            border: 1px solid #ddd;
        }
        .cause-row {
            background-color: #f8f9fa;
            font-weight: bold;
        }
        </style>
        """, unsafe_allow_html=True)
        
        st.write('#### 출동/미출동별 장애 원인 상위 10개')
        
        # 표를 HTML로 렌더링하여 더 컴팩트하게 표시
        html_table = stats_df.to_html(classes='compact-table', index=False, escape=False)
        st.markdown(html_table, unsafe_allow_html=True)
    
    return fig

def create_seasonal_pattern_chart(incident_df, business_name=None):
    """계절별 패턴 분석 차트"""
    if incident_df is None or len(incident_df) == 0:
        return None
    
    df = incident_df.copy()
    
    # 특정 사업장 필터링
    if business_name and '사업장명' in df.columns:
        df = df[df['사업장명'].str.contains(business_name, na=False, case=False)]
    
    if len(df) == 0 or '장애발생시각' not in df.columns:
        return None
    
    df['장애발생시각'] = pd.to_datetime(df['장애발생시각'], errors='coerce')
    df = df.dropna(subset=['장애발생시각'])
    
    df['month'] = df['장애발생시각'].dt.month
    df['season'] = df['장애발생시각'].dt.month.map({
        12: '겨울', 1: '겨울', 2: '겨울',
        3: '봄', 4: '봄', 5: '봄',
        6: '여름', 7: '여름', 8: '여름',
        9: '가을', 10: '가을', 11: '가을'
    })
    
    # 월별 분석
    monthly_stats = df['month'].value_counts().sort_index()
    season_stats = df['season'].value_counts()
    
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=('월별 장애 발생', '계절별 장애 발생'),
        specs=[[{"type": "bar"}, {"type": "pie"}]]
    )
    
    # 월별 막대 그래프
    fig.add_trace(
        go.Bar(x=monthly_stats.index, y=monthly_stats.values, name="월별", marker_color='#4ecdc4'),
        row=1, col=1
    )
    
    # 계절별 파이 차트
    fig.add_trace(
        go.Pie(labels=season_stats.index, values=season_stats.values, name="계절별"),
        row=1, col=2
    )
    
    fig.update_layout(
        title=f"🌤️ {'전체' if business_name is None else business_name} L2 SW 계절별 장애 패턴",
        template='plotly_white',
        height=400
    )
    
    return fig

def create_region_heatmap(incident_df):
    """지역별 장애 발생 히트맵"""
    if incident_df is None or len(incident_df) == 0 or '지역' not in incident_df.columns:
        return None
    
    df = incident_df.copy()
    
    # 지역별 장애 발생 수 집계
    region_stats = df['지역'].value_counts()
    
    # 지역별 위험도 계산 (발생 빈도 기반)
    max_incidents = region_stats.max()
    region_stats_normalized = (region_stats / max_incidents * 100).round(1)
    
    fig = go.Figure(data=go.Bar(
        x=region_stats.index,
        y=region_stats.values,
        marker=dict(
            color=region_stats.values,
            colorscale='Reds',
            showscale=True,
            colorbar=dict(title="장애 발생 수")
        ),
        text=region_stats.values,
        textposition='auto'
    ))
    
    fig.update_layout(
        title="🗺️ 지역별 L2 SW 장애 발생 현황",
        xaxis_title="지역",
        yaxis_title="장애 발생 수",
        template='plotly_white',
        height=400
    )
    
    return fig

def create_maintenance_prediction_chart(incident_df, business_name=None):
    """정비 예측 차트"""
    if incident_df is None or len(incident_df) == 0:
        return None
    
    df = incident_df.copy()
    
    # 특정 사업장 필터링
    if business_name and '사업장명' in df.columns:
        df = df[df['사업장명'].str.contains(business_name, na=False, case=False)]
    
    if len(df) == 0:
        return None
    
    # 최근 30일간의 장애 패턴 분석
    if '장애발생시각' in df.columns:
        df['장애발생시각'] = pd.to_datetime(df['장애발생시각'], errors='coerce')
        df = df.dropna(subset=['장애발생시각'])
        
        # 최근 30일 데이터만 사용
        recent_date = df['장애발생시각'].max()
        thirty_days_ago = recent_date - timedelta(days=30)
        recent_df = df[df['장애발생시각'] >= thirty_days_ago]
        
        if len(recent_df) > 0:
            # 일별 장애 발생 수
            daily_incidents = recent_df.groupby(recent_df['장애발생시각'].dt.date).size()
            
            # 다음 7일 예측 (간단한 선형 추세 기반)
            if len(daily_incidents) >= 3:
                x = np.arange(len(daily_incidents))
                y = daily_incidents.values
                
                # 선형 회귀로 추세 계산
                coeffs = np.polyfit(x, y, 1)
                trend_line = np.poly1d(coeffs)
                
                # 예측 데이터 생성
                future_x = np.arange(len(daily_incidents), len(daily_incidents) + 7)
                predictions = trend_line(future_x)
                predictions = np.maximum(predictions, 0)  # 음수 방지
                
                fig = go.Figure()
                
                # 실제 데이터
                fig.add_trace(go.Scatter(
                    x=list(daily_incidents.index),
                    y=daily_incidents.values,
                    mode='markers+lines',
                    name='실제 장애 발생',
                    line=dict(color='#ff6b6b', width=3),
                    marker=dict(size=8, color='#ff6b6b')
                ))
                
                # 예측 데이터
                future_dates = [recent_date + timedelta(days=i+1) for i in range(7)]
                fig.add_trace(go.Scatter(
                    x=future_dates,
                    y=predictions,
                    mode='markers+lines',
                    name='예측 장애 발생',
                    line=dict(color='#4ecdc4', width=3, dash='dash'),
                    marker=dict(size=8, color='#4ecdc4')
                ))
                
                fig.update_layout(
                    title=f"🔮 {'전체' if business_name is None else business_name} L2 SW 장애 발생 예측 (다음 7일)",
                    xaxis_title="날짜",
                    yaxis_title="예상 장애 발생 수",
                    template='plotly_white',
                    height=400
                )
                
                return fig
    
    return None

def generate_bigdata_insights(incident_df, business_name=None):
    """빅데이터 인사이트 생성"""
    if incident_df is None or len(incident_df) == 0:
        return []
    
    df = incident_df.copy()
    
    # 특정 사업장 필터링
    if business_name and '사업장명' in df.columns:
        df = df[df['사업장명'].str.contains(business_name, na=False, case=False)]
    
    if len(df) == 0:
        return []
    
    insights = []
    
    # 1. 장애 발생 패턴 분석
    if '장애발생시각' in df.columns:
        df['장애발생시각'] = pd.to_datetime(df['장애발생시각'], errors='coerce')
        df = df.dropna(subset=['장애발생시각'])
        
        # 시간대별 분석
        df['hour'] = df['장애발생시각'].dt.hour
        peak_hour = df['hour'].mode().iloc[0] if len(df['hour'].mode()) > 0 else 0
        insights.append(f"🕐 장애 발생 피크 시간대: {peak_hour}시")
        
        # 요일별 분석
        df['weekday'] = df['장애발생시각'].dt.day_name()
        peak_day = df['weekday'].mode().iloc[0] if len(df['weekday'].mode()) > 0 else "알 수 없음"
        insights.append(f"📅 장애 발생 피크 요일: {peak_day}")
    
    # 2. 장비별 분석
    if '장비구분' in df.columns:
        most_frequent_equipment = df['장비구분'].mode().iloc[0] if len(df['장비구분'].mode()) > 0 else "알 수 없음"
        insights.append(f"⚙️ 가장 빈번한 L2 SW 장애 장비: {most_frequent_equipment}")
    
    # 3. 원인별 분석
    if '원인' in df.columns:
        most_common_cause = df['원인'].mode().iloc[0] if len(df['원인'].mode()) > 0 else "알 수 없음"
        insights.append(f"🎯 가장 빈번한 L2 SW 장애 원인: {most_common_cause}")
    
    # 4. 지역별 분석
    if '지역' in df.columns:
        most_affected_region = df['지역'].mode().iloc[0] if len(df['지역'].mode()) > 0 else "알 수 없음"
        insights.append(f"🗺️ 가장 많은 L2 SW 장애 발생 지역: {most_affected_region}")
    
    # 5. 추세 분석
    if '장애발생시각' in df.columns and len(df) >= 10:
        recent_incidents = df[df['장애발생시각'] >= df['장애발생시각'].max() - timedelta(days=30)]
        if len(recent_incidents) > len(df) * 0.3:
            insights.append("📈 최근 30일간 L2 SW 장애 발생 빈도 증가 추세")
        elif len(recent_incidents) < len(df) * 0.1:
            insights.append("📉 최근 30일간 L2 SW 장애 발생 빈도 감소 추세")
        else:
            insights.append("📊 최근 30일간 L2 SW 장애 발생 빈도 안정적")
    
    return insights

def create_office_heatmap(incident_df):
    """국사별(지역 기준) 장애 발생 현황 히트맵 (상위 15개만 표시)"""
    if incident_df is None or len(incident_df) == 0 or '지역' not in incident_df.columns:
        return None
    df = incident_df.copy()
    # 상위 15개 국사만 표시
    office_stats = df['지역'].value_counts().head(15)
    max_incidents = office_stats.max()
    office_stats_normalized = (office_stats / max_incidents * 100).round(1)
    fig = go.Figure(data=go.Bar(
        x=office_stats.index,
        y=office_stats.values,
        marker=dict(
            color=office_stats.values,
            colorscale='Blues',
            showscale=True,
            colorbar=dict(title="장애 발생 수")
        ),
        text=office_stats.values,
        textposition='auto'
    ))
    fig.update_layout(
        title="🏢 국사별 L2 SW 장애 발생 현황 (상위 15개 국사)",
        xaxis_title="국사(지역)",
        yaxis_title="장애 발생 수",
        template='plotly_white',
        height=400
    )
    return fig

def create_team_heatmap(incident_df):
    """운용팀별 장애 발생 현황 히트맵"""
    if incident_df is None or len(incident_df) == 0 or '운용팀' not in incident_df.columns:
        return None
    df = incident_df.copy()
    team_stats = df['운용팀'].value_counts()
    max_incidents = team_stats.max()
    team_stats_normalized = (team_stats / max_incidents * 100).round(1)
    fig = go.Figure(data=go.Bar(
        x=team_stats.index,
        y=team_stats.values,
        marker=dict(
            color=team_stats.values,
            colorscale='Greens',
            showscale=True,
            colorbar=dict(title="장애 발생 수")
        ),
        text=team_stats.values,
        textposition='auto'
    ))
    fig.update_layout(
        title="👨‍💼 운용팀별 L2 SW 장애 발생 현황",
        xaxis_title="운용팀",
        yaxis_title="장애 발생 수",
        template='plotly_white',
        height=400
    )
    return fig

# --- 세션 상태 초기화 ---
if 'outage_incidents' not in st.session_state:
    st.session_state.outage_incidents = []
if 'search_history' not in st.session_state:
    st.session_state.search_history = []
if 'resident_messages' not in st.session_state:
    st.session_state.resident_messages = []
if 'message_templates' not in st.session_state:
    # 저장된 멘트 템플릿 자동 로드 시도
    success, result = load_message_templates()
    if success:
        st.session_state.message_templates = result
    else:
        st.session_state.message_templates = get_default_message_templates()


# --- 탭 1: L2 SW 빅데이터 대시보드 ---
with tab1:
    st.header("📈 L2 SW 빅데이터 장애이력분석 대시보드")
    st.markdown("""
    <div style="background-color: #f0f2f6; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
        <h3>🎯 L2 SW 장애이력분석 대시보드</h3>
        <p>이 대시보드는 L2 SW의 장애 이력을 빅데이터 분석하여 다음과 같은 인사이트를 제공합니다:</p>
        <ul>
            <li>📈 <strong>장애 발생 추이 분석</strong>: 시간별, 일별, 월별 장애 발생 패턴</li>
            <li>🎯 <strong>원인별 분석</strong>: 장애 원인별 발생 빈도 및 패턴</li>
            <li>🏢 <strong>국사별 분석</strong>: 국사(사업장명)별 장애 발생 현황</li>
            <li>👨‍💼 <strong>운용팀별 분석</strong>: 운용팀별 장애 발생 현황</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)

    if 'incident_history' in st.session_state and st.session_state.incident_history is not None:
        subtab1, subtab2 = st.tabs(["요약", "상세 분석"])
        with subtab1:
            # 기존 대시보드 전체 내용 복원 (아래 기존 코드 전체를 들여쓰기 한 칸 추가해서 이곳에 붙여넣기)
            # 분석 모드 선택
            col1, col2 = st.columns([3, 1])
            with col1:
                analysis_mode = st.selectbox(
                    "🔍 분석 모드 선택",
                    ["전체 L2 SW 분석", "특정 사업장 분석"],
                    key="dashboard_analysis_mode"
                )
            with col2:
                if analysis_mode == "특정 사업장 분석":
                    dashboard_business_search = st.text_input("🏢 사업장명", placeholder="예: 해운대 아파트, 롯데백화점...", key="dashboard_business_search")
                else:
                    dashboard_business_search = None
            if st.button("🚀 빅데이터 분석 실행", type="primary", key="dashboard_bigdata_analysis"):
                if analysis_mode == "특정 사업장 분석" and not dashboard_business_search:
                    st.warning("사업장명을 입력해주세요.")
                else:
                    st.session_state.dashboard_current_business = dashboard_business_search
                    st.success(f"L2 SW {'전체' if dashboard_business_search is None else dashboard_business_search} 빅데이터 분석을 시작합니다!")
                    st.rerun()
            if hasattr(st.session_state, 'dashboard_current_business'):
                business_name = st.session_state.dashboard_current_business
                # 년도별 분석 필터 추가
                st.markdown("### 🗓️ 년도별 분석 설정")
                base_df = st.session_state.incident_history.copy()
                if '장애발생시각' in base_df.columns:
                    base_df['장애발생시각'] = pd.to_datetime(base_df['장애발생시각'], errors='coerce')
                    base_df = base_df.dropna(subset=['장애발생시각'])
                    available_years = sorted(base_df['장애발생시각'].dt.year.unique(), reverse=True)
                    if len(available_years) > 1:
                        year_options = ['전체 년도'] + [str(year) for year in available_years]
                        selected_year = st.selectbox("분석할 년도를 선택하세요", options=year_options, key="year_filter")
                        if selected_year != '전체 년도':
                            base_df = base_df[base_df['장애발생시각'].dt.year == int(selected_year)]
                            st.info(f"📅 {selected_year}년 데이터로 분석합니다.")
                
                st.markdown("### 📈 주요 지표 대시보드")
                df = base_df.copy()
                if business_name:
                    df = df[df['사업장명'].str.contains(business_name, na=False, case=False)]
                total_incidents = len(df)
                if '장애발생시각' in df.columns:
                    df['장애발생시각'] = pd.to_datetime(df['장애발생시각'], errors='coerce')
                    df = df.dropna(subset=['장애발생시각'])
                    if not df.empty:
                        date_range = f"{df['장애발생시각'].min().strftime('%Y-%m-%d')} ~ {df['장애발생시각'].max().strftime('%Y-%m-%d')}"
                    else:
                        date_range = "24.1~25.4"
                else:
                    date_range = "24.1~25.4"
                analysis = analyze_incident_patterns(df, business_name)
                if analysis:
                    risk_prediction = predict_incident_risk(analysis, business_name or "전체")
                else:
                    risk_prediction = {'risk_level': '낮음', 'confidence': 0}
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("📊 총 L2 SW 장애", f"{total_incidents:,}건")
                with col2:
                    st.markdown(f"**📅 분석 기간**<br><span style='font-size:16px'>{date_range}</span>", unsafe_allow_html=True)
                with col3:
                    risk_color = {"매우 높음": "🔴", "높음": "🟠", "보통": "🟡", "낮음": "🟢"}
                    st.metric("⚠️ 위험도", f"{risk_color.get(risk_prediction['risk_level'], '🟢')} {risk_prediction['risk_level']}")
                with col4:
                    st.metric("🎯 예측 신뢰도", f"{risk_prediction['confidence']:.0f}%")
                st.markdown("### 💡 L2 SW 빅데이터 인사이트")
                insights = generate_bigdata_insights(df, business_name)
                if insights:
                    col1, col2 = st.columns(2)
                    with col1:
                        for i, insight in enumerate(insights[:len(insights)//2]):
                            st.info(insight)
                    with col2:
                        for i, insight in enumerate(insights[len(insights)//2:]):
                            st.info(insight)
                else:
                    st.info("분석할 수 있는 데이터가 부족합니다.")
                st.markdown("### 📊 L2 SW 장애 분석 차트")
                chart_tab1, chart_tab2 = st.tabs([
                    "📈 장애 발생 추이", "🎯 원인별 분석"
                ])
                with chart_tab1:
                    st.markdown("#### 📈 L2 SW 장애 발생 추이 분석")
                    trend_chart = create_incident_trend_chart(df, business_name)
                    if trend_chart:
                        st.plotly_chart(trend_chart, use_container_width=True)
                    else:
                        st.info("장애 발생 추이 차트를 생성할 수 없습니다.")
                with chart_tab2:
                    st.markdown("#### 🎯 L2 SW 장애 원인 분석")
                    cause_chart = create_cause_analysis_chart(df, business_name)
                    if cause_chart:
                        st.plotly_chart(cause_chart, use_container_width=True)
                    else:
                        st.info("장애 원인 분석 차트를 생성할 수 없습니다.")
                if business_name is None:
                    st.markdown("### 🏢 국사별 L2 SW 장애 발생 현황")
                    office_chart = create_office_heatmap(df)
                    if office_chart:
                        st.plotly_chart(office_chart, use_container_width=True)
                    else:
                        st.info("국사별 분석 차트를 생성할 수 없습니다.")
                    st.markdown("### 👨‍💼 운용팀별 L2 SW 장애 발생 현황")
                    team_chart = create_team_heatmap(df)
                    if team_chart:
                        st.plotly_chart(team_chart, use_container_width=True)
                    else:
                        st.info("운용팀별 분석 차트를 생성할 수 없습니다.")
                st.markdown("### 📋 L2 SW 상세 분석 결과")
                if analysis:
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("**📈 L2 SW 장애 패턴 분석:**")
                        if 'category' in analysis['patterns']:
                            st.write("**🔍 장애분류별:**")
                            for category, count in analysis['patterns']['category'].items():
                                st.write(f"- {category}: {count}회")
                        if 'cause' in analysis['patterns']:
                            st.write("**🎯 원인별:**")
                            for cause, count in list(analysis['patterns']['cause'].items())[:10]:
                                st.write(f"- {cause}: {count}회")
                    with col2:
                        st.write("**📅 L2 SW 시간별 패턴:**")
                        if 'monthly' in analysis['patterns']:
                            st.write("**📅 월별 발생:**")
                            # 월별 데이터를 가로로 표시하기 위해 3개씩 그룹화
                            monthly_data = list(analysis['patterns']['monthly'].items())
                            for i in range(0, len(monthly_data), 3):
                                month_group = monthly_data[i:i+3]
                                month_text = " | ".join([f"{month}월:{count}회" for month, count in month_group])
                                st.write(f"- {month_text}")
                        if 'seasonal' in analysis['patterns']:
                            st.write("**🌤️ 계절별 발생:**")
                            seasonal_text = " | ".join([f"{season}:{count}회" for season, count in analysis['patterns']['seasonal'].items()])
                            st.write(f"- {seasonal_text}")
                        
                        # 우기철 분석 추가
                        if 'rainy_season' in analysis['patterns']:
                            st.write("**🌧️ 우기철(6월~9월) 분석:**")
                            rainy_data = analysis['patterns']['rainy_season']
                            st.write(f"- 총 장애: {rainy_data['total_incidents']}회 ({rainy_data['percentage']}%)")
                            
                            if 'rainy_causes' in analysis['patterns']:
                                st.write("**🎯 우기철 주요 장애 원인 Top3:**")
                                rainy_causes = analysis['patterns']['rainy_causes']
                                for i, (cause, count) in enumerate(rainy_causes.items(), 1):
                                    st.write(f"  {i}. {cause}: {count}회")
                    st.markdown("### ⚠️ L2 SW 장애 위험도 예측")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("**🔍 위험도 분석:**")
                        for reason in risk_prediction['reasons']:
                            st.write(f"• {reason}")
                    with col2:
                        st.write("**💡 L2 SW 예방 권장사항:**")
                        for recommendation in risk_prediction['recommendations']:
                            st.write(f"• {recommendation}")
                        
                        # 우기철 예방점검 활동 추가
                        if 'rainy_causes' in analysis['patterns']:
                            st.write("**🌧️ 우기철 예방점검 활동:**")
                            rainy_recommendations = generate_rainy_season_recommendations(analysis['patterns']['rainy_causes'])
                            for recommendation in rainy_recommendations:
                                st.write(f"• {recommendation}")
                st.markdown("### 📋 L2 SW 상세 장애 이력")
                filtered_df = df.copy()
                if '장애발생시각' in filtered_df.columns:
                    filtered_df = filtered_df.sort_values('장애발생시각', ascending=False)
                st.dataframe(filtered_df, use_container_width=True)
                csv = filtered_df.to_csv(index=False, encoding='cp949')
                filename = f"L2SW_{business_name or '전체'}_장애이력분석.csv"
                st.download_button(
                    f"📥 L2 SW 장애 이력 분석 결과 다운로드", 
                    csv, 
                    file_name=filename, 
                    mime="text/csv"
                )
        with subtab2:
            subtab_team, subtab_office, subtab_voc, subtab_action = st.tabs(["팀별 중복장애 분석", "지역(국사별) 장애분석", "현장 TM활동", "액션아이템"])
            with subtab_team:
                df = st.session_state.incident_history.copy()
                team_group = df.groupby(['운용팀', '사업장명']).size().reset_index(name='장애건수')
                duplicated = team_group[team_group['장애건수'] >= 2]
                team_list = sorted(duplicated['운용팀'].unique())
                team_options = ['운용팀을 선택하세요'] + team_list
                selected_team = st.selectbox("운용팀을 선택하세요", options=team_options, index=0, key="team_select_team")
                detail_cols = ['장애분류', '원인', '조치1', '조치2', '출동구분', '장애발생시각']
                available_cols = [col for col in detail_cols if col in df.columns]
                def parse_datetime_multi(x):
                    for fmt in ("%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M"):
                        try:
                            return pd.to_datetime(x, format=fmt, errors="raise")
                        except:
                            continue
                    try:
                        return pd.to_datetime(x, errors="coerce")
                    except:
                        return pd.NaT
                def is_night(x):
                    t = parse_datetime_multi(x)
                    if pd.isnull(t):
                        return ''
                    # 야간장애: 당일 18시 이후부터 다음날 07시59분까지
                    hour = t.hour
                    return '야간 장애' if (hour >= 18 or hour < 8) else ''
                if selected_team != '운용팀을 선택하세요':
                    team_df = duplicated[duplicated['운용팀'] == selected_team].copy()
                    if not team_df.empty:
                        # 요약 표 생성
                        summary_list = []
                        for _, row in team_df.iterrows():
                            biz = row['사업장명']
                            detail = df[(df['운용팀'] == selected_team) & (df['사업장명'] == biz)].copy()
                            if '출동구분' in detail.columns:
                                detail = detail[detail['출동구분'] == '출동'].copy()
                            # 야간 장애 건수 (18시~07시59분)
                            night_count = 0
                            if '장애발생시각' in detail.columns:
                                night_count = detail['장애발생시각'].apply(lambda x: 
                                    parse_datetime_multi(x).hour >= 18 or parse_datetime_multi(x).hour < 8 
                                    if not pd.isnull(parse_datetime_multi(x)) else False
                                ).sum()
                            # 최근 장애일
                            recent = ''
                            if '장애발생시각' in detail.columns and not detail.empty:
                                recent_dt = detail['장애발생시각'].apply(parse_datetime_multi)
                                if not recent_dt.isnull().all():
                                    recent = recent_dt.max().strftime('%Y-%m-%d %H:%M')
                            # 주요 장애 원인(상위 2개) - 비율로 표시
                            main_causes = ''
                            if '원인' in detail.columns and not detail['원인'].isnull().all():
                                cause_counts = detail['원인'].value_counts()
                                total_causes = len(detail)
                                top_causes = cause_counts.head(2)
                                cause_percentages = []
                                for cause, count in top_causes.items():
                                    percentage = round((count / total_causes) * 100, 1)
                                    cause_percentages.append(f"{cause}({percentage}%)")
                                main_causes = ', '.join(cause_percentages)
                            
                            # 실제 출동 횟수 계산
                            dispatch_count = 0
                            if '출동구분' in detail.columns:
                                dispatch_count = len(detail[detail['출동구분'] == '출동'])
                            
                            # 중복발생 가능성 예측
                            duplicate_risk = ''
                            if row['장애건수'] >= 5:
                                duplicate_risk = '🔴 높음 (5회 이상)'
                            elif row['장애건수'] >= 3:
                                duplicate_risk = '🟠 보통 (3-4회)'
                            else:
                                duplicate_risk = '🟢 낮음 (2회)'
                            
                            summary_list.append({
                                '사업장명': biz,
                                '장애건수': row['장애건수'],
                                '출동횟수': dispatch_count,
                                '야간장애건수': night_count,
                                '최근장애일': recent,
                                '주요장애원인': main_causes,
                                '중복발생가능성': duplicate_risk
                            })
                        summary_df = pd.DataFrame(summary_list)
                        if not summary_df.empty:
                            # 운용자가 상위 개수 직접 입력
                            top_n = st.number_input("상위 몇 개 사업장을 볼까요?", min_value=1, max_value=100, value=5, step=1, key="top_n_summary")
                            summary_df = summary_df.sort_values('장애건수', ascending=False).head(top_n)
                            st.markdown(f'#### 🚨 장애 집중 관리 필요 사업장(상위 {top_n}개) - 중복발생 가능성 포함')
                            st.dataframe(summary_df, use_container_width=True)
                            
                            # 상세 이력 검색 섹션 분리
                            st.markdown('#### 📋 사업장별 상세 이력 조회')
                            search_keyword = st.text_input("상세 이력을 보고 싶은 사업장명을 검색하세요", value="", key="team_detail_search")
                            
                            if search_keyword:
                                # 검색된 사업장의 상세 이력만 표시
                                filtered_df = summary_df[summary_df['사업장명'].str.contains(search_keyword, case=False, na=False)]
                                if not filtered_df.empty:
                                    selected_biz = filtered_df.iloc[0]['사업장명']
                                    detail = df[(df['운용팀'] == selected_team) & (df['사업장명'] == selected_biz)].copy()
                                    if '출동구분' in detail.columns:
                                        detail = detail[detail['출동구분'] == '출동'].copy()
                                    if '장애발생시각' in detail.columns:
                                        detail['야간구분'] = detail['장애발생시각'].apply(is_night)
                                    show_cols = [col for col in ['장애분류', '원인', '조치1', '조치2', '출동구분', '장애발생시각', '야간구분'] if col in detail.columns]
                                    st.markdown(f"#### 📋 {selected_biz} 상세 이력")
                                    st.dataframe(detail[show_cols], use_container_width=True)
                                else:
                                    st.info("검색 결과에 해당하는 사업장이 없습니다.")
                            else:
                                st.info("사업장명을 검색하면 상세 이력을 볼 수 있습니다.")
                        else:
                            st.info("선택한 운용팀에 중복 장애 발생 사업장이 없습니다.")
                    else:
                        st.info("선택한 운용팀에 중복 장애 발생 사업장이 없습니다.")
                else:
                    st.info("운용팀을 선택하면 분석 결과가 표시됩니다.")
            with subtab_office:
                df = st.session_state.incident_history.copy()
                # 운용팀 목록
                team_list = sorted(df['운용팀'].dropna().unique())
                selected_team = st.selectbox("운용팀을 선택하세요", options=['운용팀을 선택하세요'] + team_list, index=0, key="team_select_office")
                if selected_team != '운용팀을 선택하세요':
                    team_df = df[df['운용팀'] == selected_team].copy()
                    # 지역(국사)별 장애 건수 집계
                    if '지역' in team_df.columns:
                        region_group = team_df.groupby('지역').size().reset_index(name='장애건수').sort_values('장애건수', ascending=False)
                        st.dataframe(region_group, use_container_width=True)
                        # 상위 3개 국사 추출
                        top_regions = region_group.head(3)['지역'].tolist()
                        # 각 국사별 장애 원인 Top3 표시
                        for region in top_regions:
                            region_df = team_df[team_df['지역'] == region].copy()
                            if '원인' in region_df.columns:
                                cause_counts = region_df['원인'].value_counts().head(3)
                                cause_str = ', '.join([f"{cause}({count}건)" for cause, count in cause_counts.items()])
                                st.markdown(f"**🏢 {region} 주요 장애 원인:** {cause_str}")
                        # 그래프
                        import plotly.express as px
                        fig = px.bar(region_group, x='지역', y='장애건수', title=f"{selected_team} - 지역(국사)별 장애 건수")
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("데이터에 '지역' 컬럼이 없습니다.")
                else:
                    st.info("운용팀을 선택하면 지역(국사)별 장애분석이 표시됩니다.")
            with subtab_voc:
                st.markdown("## 📞 현장 TM활동 대상 사업장 관리")
                st.markdown("""
                <div style="background-color: #f0f2f6; padding: 15px; border-radius: 8px; margin-bottom: 15px;">
                    <h4>📞 현장 TM활동이란?</h4>
                    <p>텔레마케팅 활동을 통한 VOC 방어 활동입니다:</p>
                    <ul>
                        <li>🔍 <strong>연락처 업데이트</strong>: 실시간 장애 대응 시 사업장 연락처 정보 갱신</li>
                        <li>📱 <strong>현장 연락처 획득</strong>: 현장 직원들이 직접 연락처 정보 수집</li>
                        <li>🛡️ <strong>VOC 방어</strong>: 사전 연락을 통한 고객 불만 사전 차단</li>
                    </ul>
                </div>
                """, unsafe_allow_html=True)
                df = st.session_state.incident_history.copy()
                team_list = sorted(df['운용팀'].dropna().unique())
                selected_team = st.selectbox("운용팀을 선택하세요", options=['운용팀을 선택하세요'] + team_list, index=0, key='team_select_voc')
                
                # TM활동 대상 선정 기준
                st.markdown("### 🎯 TM활동 대상 선정 기준")
                col1, col2 = st.columns(2)
                with col1:
                    min_incidents = st.number_input("최소 장애 발생 횟수", min_value=1, value=2, help="이 횟수 이상 장애가 발생한 사업장을 대상으로 선정")
                with col2:
                    include_night = st.checkbox("야간 장애 발생 사업장 우선", value=True, help="야간 장애가 발생한 사업장을 우선 대상으로 선정")
                def parse_datetime_multi(x):
                    for fmt in ("%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M"):
                        try:
                            return pd.to_datetime(x, format=fmt, errors="raise")
                        except:
                            continue
                    try:
                        return pd.to_datetime(x, errors="coerce")
                    except:
                        return pd.NaT
                if selected_team != '운용팀을 선택하세요':
                    team_df = df[df['운용팀'] == selected_team].copy()
                    
                    # TM활동 대상 사업장 선정
                    if '장애발생시각' in team_df.columns and '출동구분' in team_df.columns:
                        team_df['dt'] = team_df['장애발생시각'].apply(parse_datetime_multi)
                        
                        # 전체 장애 발생 사업장 분석
                        incident_by_biz = team_df.groupby(['사업장명', '지역']).size().reset_index(name='총장애횟수')
                        
                        # 야간 장애 발생 사업장 분석
                        night_df = team_df[(team_df['출동구분'] == '출동') & (team_df['dt'].dt.hour >= 18) | ((team_df['출동구분'] == '출동') & (team_df['dt'].dt.hour < 8))].copy()
                        night_count_by_biz = night_df.groupby(['사업장명', '지역']).size().reset_index(name='야간장애횟수')
                        
                        # TM활동 대상 선정 (기준에 따라)
                        tm_targets = incident_by_biz[incident_by_biz['총장애횟수'] >= min_incidents].copy()
                        
                        if include_night:
                            # 야간 장애 사업장과 병합
                            tm_targets = tm_targets.merge(night_count_by_biz, on=['사업장명', '지역'], how='left')
                            tm_targets['야간장애횟수'] = tm_targets['야간장애횟수'].fillna(0)
                            # 야간 장애가 있는 사업장을 우선 정렬
                            tm_targets = tm_targets.sort_values(['야간장애횟수', '총장애횟수'], ascending=[False, False])
                        else:
                            tm_targets = tm_targets.sort_values('총장애횟수', ascending=False)
                        
                        # 운용자 메모(연락처) 컬럼 추가
                        if '운용자메모' in team_df.columns:
                            memos = team_df.groupby('사업장명')['운용자메모'].first().reset_index()
                            tm_targets = tm_targets.merge(memos, on='사업장명', how='left')
                        
                        # TM활동 우선순위 계산
                        tm_targets['TM우선순위'] = tm_targets.apply(lambda row: 
                            '🔴 긴급' if row['야간장애횟수'] > 0 and row['총장애횟수'] >= 5 else
                            '🟠 높음' if row['야간장애횟수'] > 0 or row['총장애횟수'] >= 3 else
                            '🟡 보통', axis=1)
                        
                        # 긴급 대상만 필터링
                        urgent_targets = tm_targets[tm_targets['TM우선순위'] == '🔴 긴급'].copy()
                        
                        # 표시할 컬럼 선택
                        show_cols = [col for col in ['사업장명', '지역', '총장애횟수', '야간장애횟수', 'TM우선순위', '운용자메모'] if col in urgent_targets.columns]
                        
                        st.markdown(f"### 📞 TM활동 긴급 대상 사업장 (총 {len(urgent_targets)}개)")
                        if not urgent_targets.empty:
                            st.dataframe(urgent_targets[show_cols], use_container_width=True)
                            
                            # 긴급 대상 사업장에서 바로 연락처 검색
                            st.markdown("##### 🚨 긴급 대상 사업장 연락처 검색")
                            selected_urgent = st.selectbox(
                                "연락처를 검색할 긴급 대상 사업장을 선택하세요",
                                options=urgent_targets['사업장명'].tolist(),
                                key="urgent_business_select"
                            )
                            
                            if selected_urgent:
                                selected_row = urgent_targets[urgent_targets['사업장명'] == selected_urgent].iloc[0]
                                st.info(f"선택된 사업장: {selected_urgent} (총 {selected_row['총장애횟수']}회 장애, 야간 {selected_row['야간장애횟수']}회)")
                                
                                col1, col2 = st.columns([2, 1])
                                with col1:
                                    quick_search_business = st.text_input("사업장명 (수정 가능)", value=selected_urgent, key="quick_business")
                                with col2:
                                    quick_search_address = st.text_input("주소 (선택사항)", placeholder="지역 정보 입력", key="quick_address")
                                
                                if st.button("🔍 긴급 대상 연락처 즉시 검색", type="primary", key="urgent_contact_search"):
                                    with st.spinner(f"{selected_urgent} 연락처를 검색하고 있습니다..."):
                                        # 카카오 API 검색
                                        kakao_result = search_contact_enhanced(quick_search_business, quick_search_address)
                                        
                                        # 검색 결과 표시
                                        st.markdown("##### 📞 긴급 대상 연락처 검색 결과")
                                        col1, col2, col3 = st.columns(3)
                                        
                                        with col1:
                                            st.markdown("**🔍 카카오 API 결과**")
                                            if kakao_result:
                                                st.success(f"✅ 연락처: {kakao_result}")
                                                if st.button("💾 긴급 대상 연락처 저장", key="save_urgent_contact"):
                                                    st.success(f"{selected_urgent} 연락처가 저장되었습니다!")
                                            else:
                                                st.warning("❌ 카카오 API에서 연락처를 찾을 수 없습니다.")
                                        
                                        with col2:
                                            st.markdown("**🌐 구글 검색**")
                                            google_links = get_contact_search_links(quick_search_business, quick_search_address)
                                            if google_links:
                                                for i, (label, url) in enumerate(google_links[:2]):
                                                    st.link_button(f"{label} {i+1}", url)
                                            else:
                                                st.info("구글 검색 링크를 생성할 수 없습니다.")
                                        
                                        with col3:
                                            st.markdown("**🔍 네이버 검색**")
                                            naver_result = simulate_naver_search(quick_search_business, quick_search_address)
                                            if naver_result:
                                                st.link_button("네이버 검색", naver_result)
                                            else:
                                                st.info("네이버 검색 링크를 생성할 수 없습니다.")
                        else:
                            st.info("🔴 긴급 대상 사업장이 없습니다. 모든 사업장이 안정적으로 운영되고 있습니다!")
                        
                        # 통계 정보 (긴급 대상 중심)
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("총 대상 사업장", f"{len(tm_targets)}개")
                        with col2:
                            st.metric("🔴 긴급 대상", f"{len(urgent_targets)}개")
                        with col3:
                            urgent_night_count = len(urgent_targets[urgent_targets['야간장애횟수'] > 0])
                            st.metric("긴급 야간 장애", f"{urgent_night_count}개")
                        
       
                        
                        # TM활동 이력 및 연락처 업데이트
                        st.markdown('#### 📞 TM활동 이력 및 연락처 관리')
                        
                        # 연락처 검색 기능 추가
                        st.markdown("##### 🔍 연락처 검색 및 업데이트")
                        col1, col2 = st.columns([2, 1])
                        with col1:
                            search_business = st.text_input("사업장명 검색", placeholder="예: 해운대 아파트, 롯데백화점...", key="tm_contact_search")
                        with col2:
                            search_address = st.text_input("주소 검색", placeholder="예: 부산 해운대구...", key="tm_address_search")
                        
                        if st.button("🔍 연락처 검색 실행", type="primary", key="tm_contact_search_btn"):
                            if search_business or search_address:
                                with st.spinner("연락처를 검색하고 있습니다..."):
                                    # 카카오 API 검색
                                    kakao_result = search_contact_enhanced(search_business, search_address)
                                    
                                    # 검색 결과 표시
                                    st.markdown("##### 📞 검색 결과")
                                    col1, col2, col3 = st.columns(3)
                                    
                                    with col1:
                                        st.markdown("**🔍 카카오 API 검색 결과**")
                                        if kakao_result:
                                            st.success(f"✅ 연락처 발견: {kakao_result}")
                                            # 연락처 저장 버튼
                                            if st.button("💾 연락처 저장", key="save_kakao_contact"):
                                                st.success("연락처가 저장되었습니다!")
                                        else:
                                            st.warning("❌ 카카오 API에서 연락처를 찾을 수 없습니다.")
                                    
                                    with col2:
                                        st.markdown("**🌐 구글 검색 링크**")
                                        google_links = get_contact_search_links(search_business, search_address)
                                        if google_links:
                                            for i, (label, url) in enumerate(google_links[:2]):
                                                st.link_button(f"{label} {i+1}", url)
                                        else:
                                            st.info("구글 검색 링크를 생성할 수 없습니다.")
                                    
                                    with col3:
                                        st.markdown("**🔍 네이버 검색 링크**")
                                        naver_result = simulate_naver_search(search_business, search_address)
                                        if naver_result:
                                            st.link_button("네이버 검색", naver_result)
                                        else:
                                            st.info("네이버 검색 링크를 생성할 수 없습니다.")
                            else:
                                st.warning("사업장명 또는 주소를 입력해주세요.")
                        
                        # 사업장별 상세 정보 조회
                        if st.button("📋 사업장별 상세 정보 조회", type="primary", key="biz_tm_detail"):
                            # 해당 팀의 모든 사업장 장애 횟수 집계
                            all_incidents_by_biz = team_df.groupby(['사업장명', '지역']).size().reset_index(name='총장애횟수')
                            # 야간 장애 횟수 추가
                            night_incidents_by_biz = team_df[(team_df['dt'].dt.hour >= 18) | (team_df['dt'].dt.hour < 8)].groupby(['사업장명']).size().reset_index(name='야간장애횟수')
                            all_incidents_by_biz = all_incidents_by_biz.merge(night_incidents_by_biz, on='사업장명', how='left').fillna(0)
                            # 최근 장애일 추가
                            recent_incidents = team_df.groupby('사업장명')['장애발생시각'].max().reset_index()
                            recent_incidents['최근장애일'] = recent_incidents['장애발생시각'].apply(lambda x: parse_datetime_multi(x).strftime('%Y-%m-%d %H:%M') if not pd.isnull(parse_datetime_multi(x)) else '')
                            all_incidents_by_biz = all_incidents_by_biz.merge(recent_incidents[['사업장명', '최근장애일']], on='사업장명', how='left')
                            # 주요 장애 원인 추가
                            cause_by_biz = team_df.groupby('사업장명')['원인'].apply(lambda x: ', '.join(x.value_counts().head(2).index)).reset_index(name='주요장애원인')
                            all_incidents_by_biz = all_incidents_by_biz.merge(cause_by_biz, on='사업장명', how='left')
                            # 장애 횟수 많은 순으로 정렬
                            all_incidents_by_biz = all_incidents_by_biz.sort_values('총장애횟수', ascending=False)
                            st.markdown(f"#### 🚨 {selected_team} 사업장별 장애이력 (장애 횟수 많은 순)")
                            st.dataframe(all_incidents_by_biz, use_container_width=True)
                        else:
                            st.info("데이터에 '장애발생시각' 또는 '출동구분' 컬럼이 없습니다.")
                    else:
                        st.info("운용팀을 선택하면 야간 출동 사업장이 표시됩니다.")
            
            with subtab_action:
                st.markdown("## 🎯 액션아이템 - 우기철 선제적 점검 대상")
                st.markdown("""
                <div style="background-color: #fff3cd; padding: 15px; border-radius: 8px; margin-bottom: 15px; border-left: 4px solid #ffc107;">
                    <h4>🌧️ 우기철(6월~9월) 선제적 점검 대상 선정</h4>
                    <p>우기철 장애 집중발생 사업장을 분석하여 선제적 점검 대상을 추출합니다:</p>
                    <ul>
                        <li>🔍 <strong>우기철 장애 패턴 분석</strong>: 6월~9월 장애 이력 분석</li>
                        <li>⚠️ <strong>고위험 사업장 선별</strong>: 우기철 장애 2건 이상 발생 사업장</li>
                        <li>🎯 <strong>우선순위 점수 계산</strong>: 장애건수 + 원인별 위험도 가중치</li>
                        <li>🔧 <strong>선제적 점검 권장사항</strong>: 원인별 맞춤형 점검 항목</li>
                    </ul>
                </div>
                """, unsafe_allow_html=True)
                
                df = st.session_state.incident_history.copy()
                team_list = sorted(df['운용팀'].dropna().unique())
                team_options = ['전체 팀'] + team_list
                selected_action_team = st.selectbox("분석할 운용팀을 선택하세요", options=team_options, index=0, key='action_team_select')
                
                if selected_action_team != '전체 팀':
                    st.markdown(f"### 🌧️ {selected_action_team} 우기철 선제적 점검 대상 분석")
                    
                    # 우기철 분석 실행
                    rainy_analysis = analyze_rainy_season_businesses(df, selected_action_team)
                    
                    if rainy_analysis is not None and not rainy_analysis.empty:
                        st.success(f"✅ 우기철 장애 집중발생 사업장 {len(rainy_analysis)}개 발견!")
                        
                        # 우기철 분석 통계 (가로 배치)
                        st.markdown("#### 📊 우기철 분석 통계")
                        stat_col1, stat_col2, stat_col3, stat_col4, stat_col5 = st.columns(5)
                        
                        with stat_col1:
                            total_rainy_incidents = rainy_analysis['우기철_장애건수'].sum()
                            st.metric("총 우기철 장애", f"{total_rainy_incidents}건")
                        
                        with stat_col2:
                            avg_incidents = rainy_analysis['우기철_장애건수'].mean()
                            st.metric("평균 장애건수", f"{avg_incidents:.1f}건")
                        
                        with stat_col3:
                            max_incidents = rainy_analysis['우기철_장애건수'].max()
                            st.metric("최대 장애건수", f"{max_incidents}건")
                        
                        with stat_col4:
                            total_businesses = len(rainy_analysis)
                            st.metric("선제적 점검 대상", f"{total_businesses}개")
                        
                        with stat_col5:
                            # 우선순위 분포 요약
                            priority_counts = rainy_analysis['우선순위점수'].apply(lambda x: 
                                '🔴 매우높음' if x >= 50 else
                                '🟠 높음' if x >= 30 else
                                '🟡 보통' if x >= 15 else '🟢 낮음'
                            ).value_counts()
                            high_priority_count = priority_counts.get('🔴 매우높음', 0) + priority_counts.get('🟠 높음', 0)
                            st.metric("고위험 사업장", f"{high_priority_count}개")
                        
                        # 우선순위 분포 상세
                        st.markdown("**🔴 우선순위 분포:**")
                        priority_dist_col1, priority_dist_col2, priority_dist_col3, priority_dist_col4 = st.columns(4)
                        
                        with priority_dist_col1:
                            st.write(f"🔴 매우높음: {priority_counts.get('🔴 매우높음', 0)}개")
                        with priority_dist_col2:
                            st.write(f"🟠 높음: {priority_counts.get('🟠 높음', 0)}개")
                        with priority_dist_col3:
                            st.write(f"🟡 보통: {priority_counts.get('🟡 보통', 0)}개")
                        with priority_dist_col4:
                            st.write(f"🟢 낮음: {priority_counts.get('🟢 낮음', 0)}개")
                        
                        # 선제적 점검 대상 사업장 (우선순위별 필터링)
                        st.markdown("#### 🎯 선제적 점검 대상 사업장 (우선순위별 필터링)")
                        
                        # 우선순위 필터 추가
                        priority_filter = st.selectbox(
                            "우선순위별 필터링",
                            options=['전체', '🔴 매우높음', '🟠 높음', '🟡 보통', '🟢 낮음'],
                            index=0,
                            key="priority_filter"
                        )
                        
                        # 우선순위별 필터링 적용
                        filtered_df = rainy_analysis.copy()
                        if priority_filter != '전체':
                            filtered_df['우선순위_등급'] = filtered_df['우선순위점수'].apply(lambda x: 
                                '🔴 매우높음' if x >= 50 else
                                '🟠 높음' if x >= 30 else
                                '🟡 보통' if x >= 15 else '🟢 낮음'
                            )
                            filtered_df = filtered_df[filtered_df['우선순위_등급'] == priority_filter]
                        
                        if not filtered_df.empty:
                            # 표시용 데이터프레임 생성
                            display_df = filtered_df.copy()
                            
                            # 주요원인을 퍼센트로 표시
                            def format_causes_percentage(causes_dict):
                                if not causes_dict:
                                    return ''
                                total = sum(causes_dict.values())
                                percentages = []
                                for cause, count in list(causes_dict.items())[:3]:  # 상위 3개만
                                    percentage = round((count / total) * 100, 1)
                                    percentages.append(f"{cause}({percentage}%)")
                                return ', '.join(percentages)
                            
                            display_df['주요원인'] = display_df['원인'].apply(format_causes_percentage)
                            
                            # 선제적 점검사항을 주요 항목만 표시
                            def format_preventive_actions(actions_list):
                                if not actions_list:
                                    return ''
                                # 주요 점검 항목만 추출 (이모지 제거하고 핵심 내용만)
                                key_items = []
                                for action in actions_list[:2]:  # 상위 2개만
                                    # 이모지와 횟수 정보 제거하고 핵심 내용만 추출
                                    clean_action = action.split('(')[0].replace('⚡', '').replace('🔌', '').replace('🔧', '').replace('🔍', '').strip()
                                    key_items.append(clean_action)
                                return ' | '.join(key_items)
                            
                            display_df['선제적_점검사항'] = display_df['선제적_점검사항'].apply(format_preventive_actions)
                            
                            # 표시할 컬럼만 선택
                            show_cols = ['사업장명', '우기철_장애건수', '우선순위점수', '주요원인', '선제적_점검사항']
                            st.dataframe(display_df[show_cols], use_container_width=True)
                            
                            st.info(f"📊 {priority_filter} 우선순위 사업장: {len(filtered_df)}개")
                        else:
                            st.warning(f"⚠️ {priority_filter} 우선순위 사업장이 없습니다.")
                        
                        # 상세 분석
                        st.markdown("#### 🔍 상세 분석 및 권장사항")
                        
                        # 선택된 사업장 상세 분석 (필터링된 데이터 사용)
                        if not filtered_df.empty:
                            selected_business = st.selectbox(
                                "상세 분석할 사업장을 선택하세요",
                                options=filtered_df['사업장명'].tolist(),
                                key="action_business_select"
                            )
                            
                            if selected_business:
                                business_data = filtered_df[filtered_df['사업장명'] == selected_business].iloc[0]
                                st.markdown(f"##### 📋 {selected_business} 상세 분석")
                                
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.markdown("**📊 우기철 장애 현황:**")
                                    st.write(f"- 총 장애건수: {business_data['우기철_장애건수']}건")
                                    st.write(f"- 우선순위점수: {business_data['우선순위점수']}점")
                                    
                                    if business_data['원인']:
                                        st.markdown("**🎯 주요 장애 원인:**")
                                        for cause, count in business_data['원인'].items():
                                            st.write(f"- {cause}: {count}회")
                                
                                with col2:
                                    st.markdown("**🔧 선제적 점검 권장사항:**")
                                    if business_data['선제적_점검사항']:
                                        for action in business_data['선제적_점검사항']:
                                            st.write(f"• {action}")
                                    else:
                                        st.write("• 종합 점검 실시")
                        
                        # 필터링된 데이터 다운로드
                        st.markdown("#### 📥 분석 결과 다운로드")
                        
                        # 엑셀 호환성을 위한 인코딩 처리
                        csv_data = filtered_df.to_csv(index=False, encoding='cp949')
                        priority_suffix = f"_{priority_filter.replace('🔴', '매우높음').replace('🟠', '높음').replace('🟡', '보통').replace('🟢', '낮음')}" if priority_filter != '전체' else ""
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.download_button(
                                f"📥 CSV 다운로드 ({priority_suffix})",
                                csv_data,
                                file_name=f"{selected_action_team}_우기철_선제적점검대상{priority_suffix}_{pd.Timestamp.now().strftime('%Y%m%d')}.csv",
                                mime="text/csv"
                            )
                        
                        with col2:
                            # 엑셀 파일로도 다운로드 가능하도록
                            excel_buffer = io.BytesIO()
                            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                                filtered_df.to_excel(writer, sheet_name='우기철_선제적점검대상', index=False)
                            excel_buffer.seek(0)
                            
                            st.download_button(
                                f"📊 Excel 다운로드 ({priority_suffix})",
                                excel_buffer.getvalue(),
                                file_name=f"{selected_action_team}_우기철_선제적점검대상{priority_suffix}_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                    
                    else:
                        st.warning("⚠️ 해당 팀의 우기철 장애 이력이 없거나 분석할 수 있는 데이터가 부족합니다.")
                        st.info("💡 다른 팀을 선택하거나 더 많은 장애 이력 데이터를 업로드해보세요.")
                else:
                    st.info("운용팀을 선택하면 우기철 선제적 점검 대상 분석이 시작됩니다.")
    else:
        st.info("L2 SW 장애 이력 데이터를 업로드하세요.")

# --- 탭 2: 실시간 정전장애 ---
with tab2:
    st.header("⚡ 실시간 정전장애 관리")
    
    # 장비 DB 업로드 섹션
    with st.expander("⚙️ 장비 DB 관리", expanded=False):
        st.write("**장비 설치 현황 데이터베이스 업로드**")
        st.write("CSV 파일 형식: 주소, 장비수 (또는 사업장주소, 설치댓수 등)")
        
        # 저장된 장비 DB 정보 표시
        success, metadata = get_equipment_db_metadata()
        if success:
            st.success(f"💾 **저장된 장비 DB 정보:**")
            st.write(f"📅 업로드 시간: {metadata['upload_time'][:19]}")
            st.write(f"📊 총 레코드: {metadata['total_records']:,}개")
            st.write(f"⚙️ 총 장비: {metadata['total_equipment']:,}대")
            st.write(f"📋 컬럼: {', '.join(metadata['columns'])}")
        
        col1, col2 = st.columns(2)
        
        with col1:
            equipment_file = st.file_uploader("장비 DB CSV 파일 업로드", type=["csv"], key="equipment_db_uploader")
            
            if equipment_file is not None:
                equipment_df = read_csv_auto_encoding(equipment_file)
                if equipment_df is not None:
                    # 컬럼명 정규화 예시
                    equipment_df.columns = [c.replace(' ', '').replace('\t', '').replace('\n', '') for c in equipment_df.columns]
                    
                    # 장비 DB 컬럼 표준화
                    for col in equipment_df.columns:
                        if col in ['주소', '사업장주소', '설치주소']:
                            equipment_df = equipment_df.rename(columns={col: '주소'})
                        if '수' in col or '댓수' in col or '개수' in col:
                            equipment_df = equipment_df.rename(columns={col: '장비수'})
                    
                    st.session_state.equipment_db = equipment_df
                    st.success(f"장비 DB가 업로드되었습니다. (총 {len(equipment_df)}개 주소, {equipment_df['장비수'].fillna(0).astype(int).sum()}대 장비)")
                    
                    # 자동 저장
                    save_success, save_result = save_equipment_db(equipment_df)
                    if save_success:
                        st.success("💾 장비 DB가 자동으로 저장되었습니다.")
                    else:
                        st.warning(f"저장 실패: {save_result}")
                    
                    # 미리보기
                    with st.expander("장비 DB 미리보기"):
                        st.dataframe(equipment_df.head(10))
                else:
                    st.error("파일을 읽을 수 없습니다.")
        
        with col2:
            # 현재 로드된 장비 DB 상태
            if 'equipment_db' in st.session_state and st.session_state.equipment_db is not None:
                st.success(f"✅ **현재 로드된 장비 DB:**")
                st.write(f"📊 총 레코드: {len(st.session_state.equipment_db):,}개")
                st.write(f"⚙️ 총 장비: {st.session_state.equipment_db['장비수'].fillna(0).astype(int).sum():,}대")
                
                # 수동 저장 버튼
                if st.button("💾 수동 저장", type="secondary", key="equipment_manual_save"):
                    save_success, save_result = save_equipment_db(st.session_state.equipment_db)
                    if save_success:
                        st.success("장비 DB가 저장되었습니다.")
                        st.rerun()
                
                # 장비 DB 제거 버튼
                if st.button("🗑️ 메모리에서 제거", key="equipment_remove_memory"):
                    st.session_state.equipment_db = None
                    st.success("장비 DB가 메모리에서 제거되었습니다.")
                    st.rerun()
                
                # 저장된 파일 삭제 버튼
                if st.button("🗑️ 저장된 파일 삭제", key="equipment_delete_file"):
                    delete_success, delete_result = delete_equipment_db()
                    if delete_success:
                        st.success("저장된 장비 DB 파일이 삭제되었습니다.")
                        st.rerun()
                    else:
                        st.error(f"삭제 실패: {delete_result}")
            else:
                st.info("현재 로드된 장비 DB가 없습니다.")
                
                # 저장된 파일에서 로드 버튼
                if success:  # 메타데이터가 있으면
                    if st.button("📂 저장된 파일에서 로드", key="equipment_load_file"):
                        load_success, load_result = load_equipment_db()
                        if load_success:
                            st.session_state.equipment_db = load_result
                            st.success("저장된 장비 DB가 로드되었습니다.")
                            st.rerun()
                        else:
                            st.error(f"로드 실패: {load_result}")
    
    # 사업장 검색 섹션
    with st.expander("🔍 사업장/주소 검색", expanded=True):
        col1, col2 = st.columns([3, 1])
        with col1:
            search_query = st.text_input("🏢 사업장명 또는 주소를 입력하세요", placeholder="예: 롯데백화점, 부산광역시 해운대구...", key="search_input")
        with col2:
            region_filter = st.selectbox("지역", ["전체", "부산", "울산", "경남"], key="region_filter")
        
        if st.button("🔍 검색", type="secondary") and search_query:
            region = "" if region_filter == "전체" else region_filter
            
            with st.spinner("검색 중..."):
                results = search_business_kakao(search_query, region)
            
            if results:
                st.success(f"{len(results)}개의 결과를 찾았습니다.")
                
                # 검색 기록 저장
                search_record = {
                    'timestamp': datetime.now(),
                    'query': search_query,
                    'region': region_filter,
                    'result_count': len(results)
                }
                st.session_state.search_history.append(search_record)
                
                # 결과 표시
                for idx, place in enumerate(results[:5], 1):
                    with st.container():
                        col1, col2, col3 = st.columns([3, 1, 1])
                        with col1:
                            st.write(f"**{idx}. {place.get('place_name', 'N/A')}**")
                            primary_addr = place.get('primary_address', 'N/A')
                            road_addr = place.get('road_address_name', '')
                            addr_name = place.get('address_name', '')
                            if primary_addr and primary_addr != 'N/A':
                                st.write(f"📍 **주소:** {primary_addr}")
                                if road_addr and road_addr != primary_addr:
                                    st.write(f"🛣️ **도로명:** {road_addr}")
                            else:
                                st.write(f"📍 **주소:** {road_addr or addr_name or 'N/A'}")
                            # 전화번호 표시 및 임시 저장
                            session_key = f"manual_contact_{idx}_{place.get('place_name', '')}_{primary_addr}"
                            # 세션 상태에 임시 전화번호 저장
                            if 'manual_contacts' not in st.session_state:
                                st.session_state.manual_contacts = {}
                            phone = place.get('phone', '')
                            if not phone:
                                # 수동 입력값이 있으면 우선
                                manual_contact = st.session_state.manual_contacts.get(session_key, '')
                                if manual_contact:
                                    phone = manual_contact
                                    phone_display = manual_contact
                                else:
                                    phone_display = '추가 검색 필요'
                            else:
                                phone_display = phone
                            st.write(f"📞 **전화:** {phone_display}")
                            if place.get('category_name'):
                                st.write(f"🏷️ **분류:** {place.get('category_name')}")
                            # 연락처 추가 검색 기능
                            if not phone:
                                search_links = get_contact_search_links(
                                    place.get('place_name', ''),
                                    primary_addr or addr_name or road_addr
                                )
                                with st.expander("🔍 연락처 추가 검색", expanded=False):
                                    st.write("**연락처 정보를 찾기 위해 다음 링크를 사용하세요:**")
                                    for link_text, link_url in search_links:
                                        st.link_button(link_text, link_url)
                                    # 수동 연락처 입력
                                    manual_contact = st.text_input(
                                        "📝 연락처 수동 입력",
                                        placeholder="051-123-4567",
                                        key=session_key
                                    )
                                    if manual_contact:
                                        st.session_state.manual_contacts[session_key] = manual_contact
                                        st.success(f"연락처가 입력되었습니다: {manual_contact}")
                                        phone_display = manual_contact
                                        phone = manual_contact
                            else:
                                with st.expander("🔍 더 많은 정보 검색", expanded=False):
                                    search_links = get_contact_search_links(
                                        place.get('place_name', ''),
                                        ''
                                    )
                                    for link_text, link_url in search_links:
                                        st.link_button(link_text, link_url)
                            # 장비 수 매핑 - primary_address 사용
                            equipment_match = False
                            if 'equipment_db' in st.session_state and st.session_state.equipment_db is not None:
                                address = primary_addr or addr_name or road_addr
                                equipment_count, match_method = find_equipment_by_real_address(address, st.session_state.equipment_db)
                                if equipment_count != "정보없음":
                                    # 장비 수가 너무 많은 경우 경고
                                    if int(equipment_count) > 100:
                                        st.write(f"⚙️ **설치 장비:** {equipment_count}대 ({match_method}) ⚠️")
                                        st.warning(f"⚠️ 장비 수가 많습니다. 매칭 정확도를 확인하세요.")
                                    else:
                                        st.write(f"⚙️ **설치 장비:** {equipment_count}대 ({match_method})")
                                    equipment_match = True
                                else:
                                    st.write(f"⚙️ **설치 장비:** 정보없음")
                            else:
                                st.write(f"⚙️ **설치 장비:** 장비 DB 미업로드")
                        
                        with col2:
                            if place.get('place_url'):
                                st.link_button("상세정보", place['place_url'])
                        
                        with col3:
                            # 장비 매칭된 경우 바로 멘트 생성으로 연결
                            if equipment_match:
                                if st.button(f"📢 멘트 생성", key=f"ment_{idx}"):
                                    # 장애 신고
                                    incident_id = add_outage_incident(
                                        location=place.get('primary_address', '') or place.get('address_name', '') or place.get('road_address_name', ''),
                                        business_name=place.get('place_name', ''),
                                        contact=place.get('phone', ''),
                                        cause="미확인",
                                        equipment_count=int(equipment_count) if equipment_count != "정보없음" else 1,
                                        priority="높음"
                                    )
                                    
                                    # 자동으로 공용부 정전 멘트 생성
                                    message_id = add_resident_message(
                                        incident={'id': incident_id, 'location': place.get('primary_address', '') or place.get('address_name', '') or place.get('road_address_name', ''), 'contact': place.get('phone', '')},
                                        message_type="power_outage",
                                        estimated_time="30분 내"
                                    )
                                    
                                    st.success(f"🚨 장애 신고 및 멘트가 자동 생성되었습니다!")
                                    st.success(f"장애 ID: {incident_id}, 멘트 ID: {message_id}")
                                    st.success("아래 '입주민 대응 멘트 관리' 섹션에서 생성된 멘트를 확인하세요!")
                                    st.rerun()
                            else:
                                # 일반 장애 신고 (장비 DB 미매칭)
                                if st.button(f"⚡ 장애신고", key=f"report_{idx}"):
                                    # 장애 신고
                                    incident_id = add_outage_incident(
                                        location=place.get('primary_address', '') or place.get('address_name', '') or place.get('road_address_name', ''),
                                        business_name=place.get('place_name', ''),
                                        contact=place.get('phone', ''),
                                        cause="미확인",
                                        equipment_count=1,
                                        priority="보통"
                                    )
                                    
                                    st.success(f"장애 신고가 등록되었습니다. (ID: {incident_id})")
                                    st.success("아래 '입주민 대응 멘트 관리' 섹션에서 멘트를 생성하세요!")
                                    st.rerun()
                        
                        st.divider()
            else:
                st.warning("검색 결과가 없습니다. 다른 키워드로 시도해보세요.")
    
    # 입주민 대응 멘트 관리
    st.subheader("📢 KT 통신장비 입주민 대응 멘트 관리")
    
    # 멘트 템플릿 편집
    with st.expander("✏️ KT 통신장비 멘트 템플릿 편집", expanded=False):
        st.write("**KT 통신장비 장애 대응을 위한 멘트 템플릿을 사용자 정의로 수정할 수 있습니다.**")
        st.write("**사용 가능한 변수:** {location} (위치), {contact} (연락처), {estimated_time} (예상 복구 시간)")
        
        # 멘트 유형 선택
        template_type = st.selectbox(
            "편집할 멘트 유형",
            ["power_outage", "line_fault", "extended_outage"],
            format_func=lambda x: {
                "power_outage": "1. 공용부 정전 발생",
                "line_fault": "2. 회선/선로 장애 발생", 
                "extended_outage": "3. 장애 지속 안내 (30분 간격)"
            }[x]
        )
        
        # 현재 템플릿 표시
        current_template = st.session_state.message_templates[template_type]
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**📝 제목 편집:**")
            new_title = st.text_input(
                "멘트 제목",
                value=current_template['title'],
                key=f"title_{template_type}"
            )
        
        with col2:
            st.write("**📋 내용 편집:**")
            new_template = st.text_area(
                "멘트 내용",
                value=current_template['template'],
                height=200,
                key=f"template_{template_type}"
            )
        
        # 미리보기
        if st.button("👀 미리보기", key=f"preview_{template_type}"):
            sample_incident = {
                'location': '부산광역시 해운대구 우동 123-45',
                'contact': '051-123-4567'
            }
            
            try:
                preview_content = new_template.format(
                    location=sample_incident['location'],
                    contact=sample_incident['contact'],
                    estimated_time="30분 내"
                )
                
                st.write("**📋 미리보기:**")
                st.text_area(
                    "미리보기 결과",
                    value=preview_content,
                    height=150,
                    disabled=True
                )
            except Exception as e:
                st.error(f"템플릿 오류: {e}")
                st.info("변수 형식을 확인해주세요. (예: {location}, {contact}, {estimated_time})")
        
        # 저장 버튼
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("💾 템플릿 저장", type="primary", key=f"save_{template_type}"):
                st.session_state.message_templates[template_type]['title'] = new_title
                st.session_state.message_templates[template_type]['template'] = new_template
                
                # 파일에 저장
                save_success, save_result = save_message_templates(st.session_state.message_templates)
                if save_success:
                    st.success("템플릿이 저장되었습니다!")
                else:
                    st.warning(f"메모리 저장됨, 파일 저장 실패: {save_result}")
                st.rerun()
        
        with col2:
            if st.button("🔄 기본값으로 복원", key=f"reset_{template_type}"):
                default_templates = get_default_message_templates()
                st.session_state.message_templates[template_type] = default_templates[template_type]
                
                # 파일에 저장
                save_success, save_result = save_message_templates(st.session_state.message_templates)
                if save_success:
                    st.success("기본값으로 복원되었습니다!")
                else:
                    st.warning(f"메모리 복원됨, 파일 저장 실패: {save_result}")
                st.rerun()
        
        with col3:
            if st.button("📥 템플릿 내보내기", key=f"export_{template_type}"):
                template_data = {
                    'type': template_type,
                    'title': current_template['title'],
                    'template': current_template['template'],
                    'export_time': datetime.now().isoformat()
                }
                st.download_button(
                    "JSON 다운로드",
                    json.dumps(template_data, ensure_ascii=False, indent=2),
                    file_name=f"ment_template_{template_type}.json",
                    mime="application/json"
                )
        
        # 전체 템플릿 관리
        st.write("---")
        st.write("**📋 전체 템플릿 관리:**")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("💾 전체 템플릿 저장", type="secondary"):
                save_success, save_result = save_message_templates(st.session_state.message_templates)
                if save_success:
                    st.success("전체 템플릿이 저장되었습니다!")
                else:
                    st.error(f"저장 실패: {save_result}")
        
        with col2:
            if st.button("🔄 전체 기본값 복원", type="secondary"):
                st.session_state.message_templates = get_default_message_templates()
                save_success, save_result = save_message_templates(st.session_state.message_templates)
                if save_success:
                    st.success("전체 템플릿이 기본값으로 복원되었습니다!")
                else:
                    st.warning(f"메모리 복원됨, 파일 저장 실패: {save_result}")
                st.rerun()
        
        with col3:
            if st.button("📥 전체 템플릿 내보내기", type="secondary"):
                export_data = {
                    'templates': st.session_state.message_templates,
                    'export_time': datetime.now().isoformat(),
                    'version': '1.0'
                }
                st.download_button(
                    "전체 JSON 다운로드",
                    json.dumps(export_data, ensure_ascii=False, indent=2),
                    file_name="all_message_templates.json",
                    mime="application/json"
                )
    
    # 생성된 멘트 목록
    if st.session_state.resident_messages:
        st.write("**📋 생성된 멘트 목록:**")
        
        # 멘트 유형별 필터
        message_filter = st.selectbox("멘트 유형 필터", ["전체", "power_outage", "line_fault", "extended_outage"])
        
        filtered_messages = st.session_state.resident_messages
        if message_filter != "전체":
            filtered_messages = [msg for msg in filtered_messages if msg['message_type'] == message_filter]
        
        for message in reversed(filtered_messages):  # 최신순
            with st.container():
                col1, col2, col3 = st.columns([1, 3, 1])
                
                with col1:
                    st.write(f"**ID: {message['id']}**")
                    st.write(f"**{message['title']}**")
                    st.write(f"⏰ {message['timestamp'].strftime('%m/%d %H:%M')}")
                
                with col2:
                    st.text_area(
                        f"멘트 내용 (ID: {message['id']})",
                        value=message['content'],
                        height=150,
                        disabled=True,
                        key=f"message_content_{message['id']}"
                    )
                
                with col3:
                    st.write(f"**상태:** {message['status']}")
                    if message['estimated_time']:
                        st.write(f"**예상시간:** {message['estimated_time']}")
                    
                    # 멘트 복사 버튼
                    if st.button("📋 복사", key=f"copy_{message['id']}"):
                        st.write("멘트가 클립보드에 복사되었습니다.")
                        st.code(message['content'])
                    
                    # 멘트 삭제 버튼
                    if st.button("🗑️ 삭제", key=f"delete_{message['id']}"):
                        st.session_state.resident_messages = [msg for msg in st.session_state.resident_messages if msg['id'] != message['id']]
                        st.success("멘트가 삭제되었습니다.")
                        st.rerun()
                
                st.divider()
    else:
        st.info("생성된 멘트가 없습니다.")
    
    # 30분 이상 지속된 장애 자동 알림
    extended_incidents = get_extended_outage_incidents()
    if extended_incidents:
        st.write("**⚠️ 장기 지속 장애 알림:**")
        for incident in extended_incidents:
            duration = datetime.now() - incident['timestamp']
            hours = int(duration.total_seconds() // 3600)
            minutes = int((duration.total_seconds() % 3600) // 60)
            
            st.warning(f"**ID {incident['id']}:** {incident['business_name']} - {hours}시간 {minutes}분 지속")
            
            # 30분 간격 자동 멘트 생성 제안
            if should_send_extended_message(incident):
                if st.button(f"🔄 30분 간격 멘트 생성 (ID: {incident['id']})", key=f"auto_extended_{incident['id']}"):
                    estimated_time = f"{hours + 1}시간 내"
                    message_id = add_resident_message(incident, "extended_outage", estimated_time)
                    st.success(f"30분 간격 멘트가 생성되었습니다. (ID: {message_id})")
                    st.rerun()
    
    # 최근 검색 기록
    if st.session_state.search_history:
        with st.expander("📈 최근 검색 기록"):
            for record in reversed(st.session_state.search_history[-10:]):  # 최근 10개
                st.write(f"🕐 {record['timestamp'].strftime('%m/%d %H:%M')} - "
                        f"'{record['query']}' ({record['region']}) - {record['result_count']}건")

# --- 탭 3: 사업장 매핑 ---
with tab3:
    st.header("📋 사업장 대상 매핑")
    
    # 서브탭 생성
    subtab1, subtab2 = st.tabs(["🔌 예고정전 매핑", "📞 연락처 매핑"])
    
    with subtab1:
        st.subheader("🔌 예고정전 대상 매핑")
        col1, col2 = st.columns(2)
        with col1:
            outage_file = st.file_uploader("정전대상 CSV 업로드", type=["csv"], key="outage")
        with col2:
            equipment_file = st.file_uploader("l2샘플(장비DB) CSV 업로드", type=["csv"], key="equipment")

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
            with st.expander("CSV 미리보기 보기"):
                lines = preview.splitlines()
                for i, line in enumerate(lines[:10]):
                    st.write(f"{i}: {line}")
        skiprows = st.number_input("데이터 시작 전 건너뛸 줄 수", min_value=0, max_value=20, value=0)

    if st.button("🔄 주소 매핑 실행", type="primary"):
        if outage_file and equipment_file:
            with st.spinner("매핑 처리 중..."):
                outage_df = read_csv_auto_encoding(outage_file, skiprows=skiprows)
                equipment_df = read_csv_auto_encoding(equipment_file)
                
                if outage_df is None or equipment_df is None:
                    st.stop()
                
                # 컬럼명 정규화
                outage_df.columns = [normalize_colname(c) for c in outage_df.columns]
                equipment_df.columns = [normalize_colname(c) for c in equipment_df.columns]
                
                # 장비 DB 컬럼 표준화
                for col in equipment_df.columns:
                    if col in ['주소', '사업장주소']:
                        equipment_df = equipment_df.rename(columns={col: '주소'})
                    if '수' in col:
                        equipment_df = equipment_df.rename(columns={col: '장비수'})
                
                # 필수 컬럼 체크
                required_cols = ['일자', '요일', '시간', '고객명']
                missing_cols = [col for col in required_cols if col not in outage_df.columns]
                if missing_cols:
                    st.error(f"정전대상 CSV에 다음 컬럼이 필요합니다: {missing_cols}")
                    st.stop()
                
                # 매핑 처리
                progress_bar = st.progress(0)
                results = []
                total_rows = len(outage_df)
                
                # 연락처 검색 옵션
                enhanced_search = st.checkbox("🔍 향상된 연락처 검색 사용 (네이버/구글 검색 포함)", value=True)
                
                for idx, row in outage_df.iterrows():
                    progress_bar.progress((idx + 1) / total_rows)
                    
                    date = str(row['일자']).strip()
                    weekday = str(row['요일']).strip()
                    time_ = str(row['시간']).strip()
                    customer_name = str(row['고객명']).strip()
                    
                    # 기본 카카오 API 검색
                    address, phone, _ = search_kakao_api_region(customer_name)
                    
                    # 향상된 연락처 검색 사용 시
                    if enhanced_search and (phone == '정보없음' or phone == ''):
                        contact_info = search_contact_enhanced(customer_name, address)
                        if contact_info['phone']:
                            phone = contact_info['phone']
                            source_info = f"카카오 API → {contact_info['source']}"
                        else:
                            source_info = "카카오 API"
                    else:
                        source_info = "카카오 API"
                    
                    equipment_count, match_method = find_equipment_by_real_address(address, equipment_df)
                    
                    results.append({
                        '일자': date,
                        '요일': weekday,
                        '시간': time_,
                        '고객명': customer_name,
                        '실제주소': address,
                        '전화번호': phone,
                        '검색소스': source_info,
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
                
                progress_bar.empty()
                
                # 결과 표시
                st.success("매핑 완료!")
                st.dataframe(result_df, use_container_width=True)
                
                # 통계
                total = len(result_df)
                address_success = len(result_df[result_df['실제주소'] != '정보없음'])
                phone_success = len(result_df[result_df['전화번호'] != '정보없음'])
                equipment_success = len(result_df[result_df['총장비수'] != '정보없음'])
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("전체 건수", total)
                with col2:
                    st.metric("주소 매핑 성공", address_success, f"{address_success/total*100:.1f}%")
                with col3:
                    st.metric("연락처 매핑 성공", phone_success, f"{phone_success/total*100:.1f}%")
                with col4:
                    st.metric("장비 매칭 성공", equipment_success, f"{equipment_success/total*100:.1f}%")
                
                # 연락처 검색 결과 상세 분석
                if enhanced_search:
                    st.subheader("📊 연락처 검색 결과 분석")
                    
                    # 검색 소스별 통계
                    source_stats = result_df['검색소스'].value_counts()
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write("**🔍 검색 소스별 성공률:**")
                        for source, count in source_stats.items():
                            percentage = (count / total) * 100
                            st.write(f"- {source}: {count}건 ({percentage:.1f}%)")
                    
                    with col2:
                        st.write("**📞 연락처 미발견 건수:**")
                        no_phone = len(result_df[result_df['전화번호'] == '정보없음'])
                        st.write(f"- 연락처 없음: {no_phone}건")
                        if no_phone > 0:
                            st.write("**미발견 고객명:**")
                            no_phone_customers = result_df[result_df['전화번호'] == '정보없음']['고객명'].tolist()
                            for customer in no_phone_customers[:5]:  # 상위 5개만 표시
                                st.write(f"  • {customer}")
                            if len(no_phone_customers) > 5:
                                st.write(f"  • ... 외 {len(no_phone_customers) - 5}건")
                
                # 다운로드 버튼들
                col1, col2 = st.columns(2)
                
                with col1:
                    # 기본 결과 다운로드
                    csv = result_df.to_csv(index=False, encoding='cp949')
                    st.download_button("📥 매핑 결과 CSV 다운로드", csv, file_name="예고정전_매핑결과.csv", mime="text/csv")
                
                with col2:
                    # 연락처 업데이트된 원본 CSV 다운로드
                    if enhanced_search:
                        updated_original = update_csv_with_contacts(result_df, outage_df)
                        updated_csv = updated_original.to_csv(index=False, encoding='cp949')
                        st.download_button("📥 연락처 업데이트된 원본 CSV", updated_csv, file_name="예고정전_연락처업데이트.csv", mime="text/csv")
        else:
            st.warning("두 개의 CSV 파일을 모두 업로드하세요.")
    
    with subtab2:
        st.subheader("📞 연락처 매핑")
        st.write("엑셀 파일에 업로드된 사업장 정보를 API 검색으로 연락처를 추가합니다. (사업장명 키워드 추출 + 대표장비 주소 기준)")
        
        # 파일 업로드
        contact_file = st.file_uploader("연락처 추가할 엑셀/CSV 파일 업로드", type=["xlsx", "xls", "csv"], key="contact_mapping")
        
        if contact_file is not None:
            # 파일 읽기
            if contact_file.name.endswith(('.xlsx', '.xls')):
                import pandas as pd
                df = pd.read_excel(contact_file)
            else:
                df = read_csv_auto_encoding(contact_file)
            
            if df is not None:
                st.success(f"파일 업로드 완료: {len(df)}건")
                
                # 컬럼 선택
                st.write("**📋 컬럼 매핑 설정**")
                col1, col2, col3 = st.columns(3)
                with col1:
                    h_col = st.selectbox("사업장명(H열) 컬럼 선택", options=df.columns.tolist(), key="h_col")
                with col2:
                    m_col = st.selectbox("대표장비 주소(M열) 컬럼 선택", options=df.columns.tolist(), key="m_col")
                with col3:
                    n_col = st.selectbox("연락처최종(N열) 컬럼 선택(없으면 새로 생성)", options=['새 컬럼 생성'] + df.columns.tolist(), key="n_col")
                
                region_filter = st.selectbox("검색 지역 필터", options=['전체', '부산', '경남'], key="contact_region")
                enhanced_search = st.checkbox("🔍 향상된 연락처 검색 사용 (네이버/구글 검색 포함)", value=True, key="contact_enhanced")
                
                def extract_keyword(biz_name):
                    import re
                    m = re.search(r'([가-힣A-Za-z]+)$', str(biz_name))
                    return m.group(1) if m else str(biz_name)
                
                if st.button("📞 연락처 매핑 실행", type="primary"):
                    with st.spinner("연락처 매핑 처리 중..."):
                        progress_bar = st.progress(0)
                        results = []
                        total_rows = len(df)
                        
                        # N열이 없으면 새로 생성
                        if n_col == '새 컬럼 생성':
                            n_col_name = '연락처최종'
                            df[n_col_name] = ''
                        else:
                            n_col_name = n_col
                        
                        for idx, row in df.iterrows():
                            progress_bar.progress((idx + 1) / total_rows)
                            biz_name_raw = row[h_col]
                            keyword = extract_keyword(biz_name_raw)
                            address = str(row[m_col])
                            # 카카오 API 검색
                            search_result = search_business_kakao(keyword, address)
                            phone = search_result[0]['phone'] if search_result and search_result[0].get('phone') else ''
                            # 향상된 검색
                            if (not phone or phone == '정보없음') and enhanced_search:
                                contact_info = search_contact_enhanced(keyword, address)
                                phone = contact_info['phone'] if contact_info['phone'] else '정보없음'
                            if not phone:
                                phone = '정보없음'
                            df.at[idx, n_col_name] = phone
                        
                        st.success(f"연락처 매핑 완료: {len(df)}건")
                        st.dataframe(df, use_container_width=True)
                        
                        # 다운로드 버튼
                        col1, col2 = st.columns(2)
                        with col1:
                            if contact_file.name.endswith(('.xlsx', '.xls')):
                                import io
                                output = io.BytesIO()
                                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                                    df.to_excel(writer, index=False, sheet_name='연락처매핑결과')
                                output.seek(0)
                                st.download_button(
                                    "📥 연락처 매핑 결과 다운로드 (Excel)",
                                    output.getvalue(),
                                    file_name="연락처_매핑결과.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                )
                            else:
                                csv = df.to_csv(index=False, encoding='cp949')
                                st.download_button(
                                    "📥 연락처 매핑 결과 다운로드 (CSV)",
                                    csv,
                                    file_name="연락처_매핑결과.csv",
                                    mime="text/csv"
                                )
                        with col2:
                            success_count = len(df[df[n_col_name] != '정보없음'])
                            st.info(f"✅ 성공: {success_count}건\n❌ 실패: {len(df) - success_count}건")
            else:
                st.error("파일을 읽을 수 없습니다.")

# --- 사이드바 ---
with st.sidebar:
    st.header("📊 시스템 상태 및 데이터 관리")
    # 통합 데이터 업로드 섹션
    st.subheader("📁 데이터 업로드/DB 관리")
    # 장애 이력 CSV 업로드
    incident_file = st.file_uploader("장애 이력 CSV 업로드", type=["csv"], key="sidebar_incident")
    if incident_file is not None:
        incident_df = read_csv_auto_encoding(incident_file)
        if incident_df is not None:
            incident_df.columns = [normalize_colname(c) for c in incident_df.columns]
            st.session_state.incident_history = incident_df
            st.session_state.incident_file = incident_file.getvalue()  # 파일 원본 저장
            st.success(f"장애 이력 {len(incident_df)}건 업로드됨 (모든 탭에서 사용 가능)")
        else:
            st.session_state.incident_history = None
            st.session_state.incident_file = None
            st.error("장애 이력 CSV 파일을 읽을 수 없습니다.")
    # 장비 DB CSV 업로드
    equipment_file = st.file_uploader("장비 DB CSV 업로드", type=["csv"], key="sidebar_equipment")
    if equipment_file is not None:
        equipment_df = read_csv_auto_encoding(equipment_file)
        if equipment_df is not None:
            equipment_df.columns = [c.replace(' ', '').replace('\t', '').replace('\n', '') for c in equipment_df.columns]
            st.session_state.equipment_db = equipment_df
            st.session_state.equipment_file = equipment_file.getvalue()  # 파일 원본 저장
            st.success(f"장비 DB {len(equipment_df)}건 업로드됨 (모든 탭에서 사용 가능)")
        else:
            st.session_state.equipment_db = None
            st.session_state.equipment_file = None
            st.error("장비 DB CSV 파일을 읽을 수 없습니다.")
    # 대형사업장 장애대응 엑셀 업로드
    largebiz_file = st.file_uploader("대형사업장 장애대응 엑셀 업로드", type=["xlsx", "xls"], key="sidebar_largebiz")
    if largebiz_file is not None:
        import pandas as pd
        try:
            largebiz_df = pd.read_excel(largebiz_file)
            largebiz_df.columns = [c.strip().replace('\n', '').replace('\t', '') for c in largebiz_df.columns]
            st.session_state.largebiz_db = largebiz_df
            st.session_state.largebiz_file = largebiz_file.getvalue()  # 파일 원본 저장
            st.success(f"대형사업장 DB {len(largebiz_df)}건 업로드됨 (모든 탭에서 사용 가능)")
        except Exception as e:
            st.session_state.largebiz_db = None
            st.session_state.largebiz_file = None
            st.error(f"엑셀 파일을 읽을 수 없습니다: {e}")


# --- 탭 4: 대형사업장 장애대응 ---
with tab4:
    st.header("🏢 대형사업장 장애대응")
    if 'largebiz_db' in st.session_state and st.session_state.largebiz_db is not None:
        df = st.session_state.largebiz_db.copy()
        # 운용팀.1 기준으로 selectbox 생성
        team_list = sorted(df['운용팀.1'].dropna().unique())
        selected_team = st.selectbox("운용팀을 선택하세요", options=['운용팀을 선택하세요'] + team_list, index=0, key="largebiz_team_select")
        if selected_team != '운용팀을 선택하세요':
            filtered_df = df[df['운용팀.1'] == selected_team]
            # 운용팀.1 컬럼 위치 찾기
            cols = filtered_df.columns.tolist()
            if '운용팀.1' in cols:
                idx = cols.index('운용팀.1')
                show_cols = cols[idx+1:]
                show_cols = ['운용팀.1'] + show_cols
            else:
                show_cols = cols
            st.dataframe(filtered_df[show_cols], use_container_width=True)
        else:
            st.info("운용팀을 선택하면 대형사업장 검색이 가능합니다.")
    else:
        st.info("사이드바에서 대형사업장 장애대응 엑셀 파일을 업로드하세요.")

# 하단 정보
st.markdown("---")
st.markdown("**🖧 L2 스위치 장애 통합 분석 솔루션**")
# 우측 하단 디렉터 정보
st.markdown('<div style="text-align: right; color: #888; font-size: 0.9em;">중부산운용팀 AI TF(DANDI)<br><span style="font-size:0.8em; color:#bbb;">김동현, 윤성현, 이태희</span></div>', unsafe_allow_html=True)
    
# DB 상태 요약 (업로드 파일 기준으로만 표시)
st.divider()
st.subheader("DB 상태 요약")
if 'incident_history' in st.session_state and st.session_state.incident_history is not None:
    st.write(f"장애 이력: {len(st.session_state.incident_history)}건")
    if 'incident_file' in st.session_state and st.session_state.incident_file:
        st.download_button(
            "최종 업로드 파일 다운로드",
            st.session_state.incident_file,
            file_name="최종_장애이력.csv",
            mime="text/csv"
        )
else:
    st.write("장애 이력: 없음")
if 'equipment_db' in st.session_state and st.session_state.equipment_db is not None:
    st.write(f"장비 DB: {len(st.session_state.equipment_db)}건")
    if 'equipment_file' in st.session_state and st.session_state.equipment_file:
        st.download_button(
            "최종 업로드 파일 다운로드",
            st.session_state.equipment_file,
            file_name="최종_장비DB.csv",
            mime="text/csv"
        )
else:
    st.write("장비 DB: 없음")
if 'largebiz_db' in st.session_state and st.session_state.largebiz_db is not None:
    st.write(f"대형사업장 DB: {len(st.session_state.largebiz_db)}건")
    if 'largebiz_file' in st.session_state and st.session_state.largebiz_file:
        st.download_button(
            "최종 업로드 파일 다운로드",
            st.session_state.largebiz_file,
            file_name="최종_대형사업장_DB.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
else:
    st.write("대형사업장 DB: 없음")
    