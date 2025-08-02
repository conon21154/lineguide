# utils/excel_handler.py
# 새로운 엑셀 구조에 맞춘 처리기

import pandas as pd

class ExcelHandler:
    """새로운 엑셀 구조로 연락처 데이터 처리하는 클래스"""
    
    def __init__(self):
        print("📁 새로운 구조의 Excel 처리기가 준비되었어요!")
    
    def load_addresses(self, file_path):
        """
        새로운 엑셀 구조에서 주소들을 읽어오는 함수
        컬럼: 주소 | 구 | 동 | 번지 | (추가정보)
        """
        try:
            print(f"📖 새로운 구조의 주소 파일을 읽는 중: {file_path}")
            
            # Excel 파일 읽기 (헤더 포함)
            df = pd.read_excel(file_path)
            print(f"✅ 파일 읽기 성공! 총 {len(df)}행")
            
            # 컬럼명 확인
            print(f"📋 컬럼명들: {list(df.columns)}")
            
            # 데이터 구조 분석
            address_data = []
            
            for i, row in df.iterrows():
                try:
                    # 각 컬럼에서 데이터 추출
                    city = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
                    district = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
                    dong = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ""
                    street_num = str(row.iloc[3]).strip() if pd.notna(row.iloc[3]) else ""
                    
                    # 추가 정보 (5번째 컬럼이 있으면)
                    additional_info = ""
                    if len(row) > 4 and pd.notna(row.iloc[4]):
                        additional_info = str(row.iloc[4]).strip()
                    
                    # 완전한 주소 조합
                    if city and district and dong:
                        # 기본 주소 형태: "부산광역시 동래구 온천동 871-95"
                        full_address = f"{city} {district} {dong}"
                        if street_num:
                            full_address += f" {street_num}"
                        
                        # 빈 주소 제외
                        if full_address.strip():
                            address_data.append({
                                'id': len(address_data) + 1,
                                'city': city,
                                'district': district,
                                'dong': dong,
                                'street_number': street_num,
                                'additional_info': additional_info,
                                'address': full_address.strip(),
                                'status': '대기중',
                                'place_name': None,
                                'phone': None,
                                'category': None,
                                'error': None
                            })
                            
                except Exception as e:
                    print(f"   ⚠️ {i+2}행 처리 중 오류: {e}")
                    continue
            
            print(f"🏠 총 {len(address_data)}개의 주소를 조합했어요!")
            
            # 처음 3개 주소 미리보기
            print(f"📋 주소 미리보기:")
            for i, addr in enumerate(address_data[:3]):
                print(f"   {i+1}. {addr['address']}")
                if addr['additional_info']:
                    print(f"      추가정보: {addr['additional_info']}")
            
            if len(address_data) > 3:
                print(f"   ... 외 {len(address_data) - 3}개 더")
            
            return address_data
            
        except Exception as e:
            print(f"❌ 파일 읽기 실패: {e}")
            raise Exception(f"Excel 파일을 읽을 수 없어요: {e}")
    
    def save_results(self, address_data, file_path):
        """
        연락처 검색 결과를 Excel 파일로 저장 (새 구조 포함)
        """
        try:
            print(f"💾 연락처 결과 저장 중: {file_path}")
            
            # 결과 데이터 준비
            results = []
            for item in address_data:
                results.append({
                    '순번': item['id'],
                    '시도': item.get('city', ''),
                    '구': item.get('district', ''),
                    '동': item.get('dong', ''),
                    '번지': item.get('street_number', ''),
                    '전체주소': item['address'],
                    '추가정보': item.get('additional_info', ''),
                    '상태': item['status'],
                    '업체명': item['place_name'] if item['place_name'] else '',
                    '전화번호': item['phone'] if item['phone'] else '',
                    '카테고리': item['category'] if item['category'] else '',
                    '오류내용': item['error'] if item['error'] else ''
                })
            
            # DataFrame으로 만들고 저장
            df = pd.DataFrame(results)
            
            # Excel 파일로 저장 (컬럼 너비 조정)
            with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='연락처_검색_결과', index=False)
                
                # 워크시트 가져오기
                worksheet = writer.sheets['연락처_검색_결과']
                
                # 컬럼 너비 조정
                column_widths = {
                    'A': 8,   # 순번
                    'B': 12,  # 시도
                    'C': 12,  # 구
                    'D': 15,  # 동
                    'E': 15,  # 번지
                    'F': 35,  # 전체주소
                    'G': 25,  # 추가정보
                    'H': 10,  # 상태
                    'I': 20,  # 업체명
                    'J': 15,  # 전화번호
                    'K': 20,  # 카테고리
                    'L': 25   # 오류내용
                }
                
                for column, width in column_widths.items():
                    worksheet.column_dimensions[column].width = width
            
            print(f"✅ 연락처 결과 저장 완료!")
            
        except Exception as e:
            print(f"❌ 저장 실패: {e}")
            raise Exception(f"결과를 저장할 수 없어요: {e}")

# 테스트 함수
def test_new_excel_structure():
    """새로운 엑셀 구조 테스트"""
    print("🧪 새로운 엑셀 구조 처리 테스트!")
    
    handler = ExcelHandler()
    
    # 테스트 파일이 있다고 가정
    try:
        test_file = "nms연락처 업로드 테스트.xlsx"
        address_data = handler.load_addresses(test_file)
        
        print(f"\n📊 처리 결과:")
        print(f"   총 주소 수: {len(address_data)}")
        
        for addr in address_data[:3]:
            print(f"   • {addr['address']}")
            if addr['additional_info']:
                print(f"     추가정보: {addr['additional_info']}")
        
    except Exception as e:
        print(f"❌ 테스트 실패: {e}")

if __name__ == "__main__":
    test_new_excel_structure()