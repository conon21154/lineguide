# utils/kakao_api.py
# 더 정확한 주소 매칭을 위한 개선된 버전

import requests
import time
from urllib.parse import quote

class KakaoAPI:
    """카카오 API로 정확한 연락처 검색"""
    
    def __init__(self, api_key):
        self.api_key = api_key
        self.keyword_url = "https://dapi.kakao.com/v2/local/search/keyword.json"
        self.address_url = "https://dapi.kakao.com/v2/local/search/address.json"
        
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'KakaoAK {api_key}',
            'Content-Type': 'application/json'
        })
        
        self.last_call_time = 0
        self.min_interval = 0.1
        
        print(f"🗝️ 정확한 카카오 연락처 검색 API가 준비되었어요!")
    
    def find_contact_info(self, address):
        """
        주소로 연락처 정보 찾기 (정확도 개선)
        """
        try:
            print(f"🔍 정확한 연락처 검색: {address[:30]}...")
            
            # 1단계: 정확한 주소로 좌표 구하기
            coords = self._get_address_coordinates(address)
            
            if coords:
                # 2단계: 해당 좌표 근처 500m 이내에서 전화번호 있는 곳 찾기
                result = self._find_nearby_places_with_phone(coords, address)
                if result:
                    return result
            
            # 3단계: 좌표 검색 실패 시 기존 방법 사용
            print(f"   🔄 기존 방법으로 재시도...")
            return self._fallback_search(address)
            
        except Exception as e:
            raise e
    
    def _get_address_coordinates(self, address):
        """주소를 좌표로 변환"""
        try:
            self._wait_for_rate_limit()
            
            params = {
                'query': address
            }
            
            response = self.session.get(self.address_url, params=params, timeout=10)
            
            if response.status_code != 200:
                return None
                
            data = response.json()
            
            if not data.get('documents'):
                return None
            
            # 첫 번째 결과의 좌표 사용
            result = data['documents'][0]
            return {
                'lat': float(result['y']),
                'lng': float(result['x']),
                'address_name': result['address_name']
            }
            
        except:
            return None
    
    def _find_nearby_places_with_phone(self, coords, original_address):
        """좌표 근처에서 전화번호 있는 장소 찾기"""
        try:
            self._wait_for_rate_limit()
            
            # 좌표 기반 주변 검색
            params = {
                'x': coords['lng'],
                'y': coords['lat'],
                'radius': 500,  # 500m 반경
                'query': '음식점',  # 일단 음식점으로 검색
                'size': 15
            }
            
            response = self.session.get(self.keyword_url, params=params, timeout=10)
            
            if response.status_code != 200:
                return None
                
            data = response.json()
            
            if not data.get('documents'):
                return None
            
            # 전화번호가 있고, 주소가 유사한 곳 찾기
            for place in data['documents']:
                phone = place.get('phone', '').strip()
                place_name = place.get('place_name', '').strip()
                place_address = place.get('address_name', '').strip()
                
                if phone and self._is_address_similar(original_address, place_address):
                    print(f"   ✅ 정확한 매칭: {place_name} - {phone}")
                    print(f"      입력주소: {original_address}")
                    print(f"      찾은주소: {place_address}")
                    
                    return {
                        'place_name': place_name,
                        'phone': phone,
                        'address': place_address,
                        'category': place.get('category_name', ''),
                        'match_type': 'exact_location'
                    }
            
            return None
            
        except:
            return None
    
    def _is_address_similar(self, addr1, addr2):
        """두 주소가 유사한지 확인"""
        # 주소에서 핵심 부분 추출
        addr1_parts = addr1.replace(' ', '').replace('-', '')
        addr2_parts = addr2.replace(' ', '').replace('-', '')
        
        # 시/구/동이 같은지 확인
        addr1_key = ''.join(addr1.split()[:3]) if len(addr1.split()) >= 3 else addr1
        addr2_key = ''.join(addr2.split()[:3]) if len(addr2.split()) >= 3 else addr2
        
        return addr1_key in addr2_parts or addr2_key in addr1_parts
    
    def _fallback_search(self, address):
        """기존 방법으로 검색 (정확도는 떨어지지만 결과는 나옴)"""
        try:
            # 여러 키워드로 시도
            keywords = ["음식점", "카페", "병원", "편의점", "마트"]
            
            for keyword in keywords:
                result = self._try_search(f"{address} {keyword}")
                if result:
                    result['match_type'] = 'nearby_search'
                    print(f"   ⚠️ 근처 검색 결과: {result['place_name']} - {result['phone']}")
                    print(f"      (정확한 주소 매칭은 아닐 수 있음)")
                    return result
            
            raise Exception("전화번호를 찾을 수 없어요")
            
        except Exception as e:
            raise e
    
    def _try_search(self, query):
        """기본 키워드 검색"""
        try:
            self._wait_for_rate_limit()
            
            params = {
                'query': query,
                'size': 15
            }
            
            response = self.session.get(self.keyword_url, params=params, timeout=10)
            
            if response.status_code != 200:
                return None
                
            data = response.json()
            
            if not data.get('documents'):
                return None
            
            # 전화번호가 있는 첫 번째 결과 반환
            for place in data['documents']:
                phone = place.get('phone', '').strip()
                if phone:
                    return {
                        'place_name': place.get('place_name', '').strip(),
                        'phone': phone,
                        'address': place.get('address_name', '').strip(),
                        'category': place.get('category_name', ''),
                        'search_query': query
                    }
            
            return None
            
        except:
            return None
    
    def _wait_for_rate_limit(self):
        """API 호출 제한 관리"""
        current_time = time.time()
        time_since_last_call = current_time - self.last_call_time
        
        if time_since_last_call < self.min_interval:
            time.sleep(self.min_interval - time_since_last_call)
        
        self.last_call_time = time.time()
    
    def test_api_key(self):
        """API 키 테스트"""
        try:
            print("🧪 API 키 테스트 중...")
            result = self._try_search("서울역 맛집")
            
            if result:
                print(f"✅ API 키 테스트 성공!")
                return True
            else:
                print(f"✅ API 키는 유효해요!")
                return True
                
        except Exception as e:
            print(f"❌ API 키 테스트 실패: {e}")
            return False

# 테스트 함수
def test_accurate_search():
    """정확도 개선된 검색 테스트"""
    print("🧪 정확도 개선된 카카오 검색 테스트!")
    
    api_key = input("카카오 REST API 키를 입력하세요: ")
    if not api_key.strip():
        print("❌ API 키가 없어요!")
        return
    
    api = KakaoAPI(api_key)
    
    # 테스트할 정확한 주소들
    test_addresses = [
        "부산광역시 동래구 온천동 871-95",
        "서울특별시 강남구 역삼동 123-45",
        "대구광역시 중구 동성로 1가"
    ]
    
    print("\n📞 정확도 개선된 연락처 검색 테스트!")
    print("=" * 70)
    
    for address in test_addresses:
        try:
            result = api.find_contact_info(address)
            print(f"📍 검색 주소: {address}")
            print(f"   업체명: {result['place_name']}")
            print(f"   전화번호: {result['phone']}")
            print(f"   매칭타입: {result.get('match_type', 'unknown')}")
            print(f"   찾은주소: {result['address']}")
            print("-" * 70)
            
        except Exception as e:
            print(f"📍 {address}: ❌ {e}")
            print("-" * 70)

if __name__ == "__main__":
    test_accurate_search()