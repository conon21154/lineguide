import requests
import time
import re
from urllib.parse import quote
from html import unescape

class NaverAPI:
    def __init__(self, client_id, client_secret, min_interval=0.15):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = "https://openapi.naver.com/v1/search/local.json"
        self.session = requests.Session()
        self.session.headers.update({
            'X-Naver-Client-Id': client_id,
            'X-Naver-Client-Secret': client_secret,
            'Content-Type': 'application/json'
        })
        self.last_call_time = 0
        self.min_interval = min_interval

    def find_contact_info(self, address, keywords=None):
        """주소와 키워드 리스트로 연락처 검색. 실패 시 None 반환."""
        if not keywords:
            keywords = ["맛집", "음식점", "카페", "병원", "편의점", "마트", "상가"]
        try:
            for keyword in keywords:
                result = self._try_search_with_keyword(address, keyword)
                if result:
                    return result
            # 동네 이름만으로도 시도
            parts = address.split()
            if len(parts) > 0:
                last_part = parts[-1]
                if "동" in last_part or "구" in last_part:
                    for keyword in ["맛집", "카페"]:
                        result = self._try_search_with_keyword(last_part, keyword)
                        if result:
                            return result
            return None
        except Exception as e:
            return None

    def _try_search_with_keyword(self, address, keyword):
        search_query = f"{address} {keyword}"
        return self._search_by_query(search_query)

    def _search_by_query(self, query):
        self._wait_for_rate_limit()
        params = {
            'query': query,
            'display': 10,
            'start': 1,
            'sort': 'comment'
        }
        response = self.session.get(self.base_url, params=params, timeout=10)
        if response.status_code == 401:
            return None
        elif response.status_code == 429:
            time.sleep(1)
            return None
        elif response.status_code != 200:
            return None
        data = response.json()
        if not data.get('items'):
            return None
        for item in data['items']:
            telephone = item.get('telephone', '').strip()
            title = self._strip_html(item.get('title', '').strip())
            address = item.get('address', '').strip()
            if telephone:
                return {
                    'title': title,
                    'telephone': telephone,
                    'address': address,
                    'category': item.get('category', ''),
                    'search_query': query
                }
        return None

    def _strip_html(self, text):
        # 모든 HTML 태그 제거
        return re.sub('<.*?>', '', unescape(text))

    def _wait_for_rate_limit(self):
        current_time = time.time()
        time_since_last_call = current_time - self.last_call_time
        if time_since_last_call < self.min_interval:
            time.sleep(self.min_interval - time_since_last_call)
        self.last_call_time = time.time()

    def test_api_key(self):
        result = self._search_by_query("강남역 맛집")
        return bool(result)

# 사용 예시
# api = NaverAPI(client_id, client_secret)
# info = api.find_contact_info("부산 해운대구 중동")
# if info:
#     print(info['title'], info['telephone'])