import streamlit as st
import pandas as pd
import io
import base64

# 페이지 설정
st.set_page_config(
    page_title="📡 회선선번장 검색",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# CSS 스타일
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(45deg, #4158D0 0%, #C850C0 46%, #FFCC70 100%);
        padding: 2rem;
        border-radius: 15px;
        margin-bottom: 2rem;
        text-align: center;
        color: white;
    }
    
    .upload-area {
        border: 2px dashed #cbd5e1;
        border-radius: 15px;
        padding: 3rem;
        text-align: center;
        background: #f8fafc;
        transition: all 0.3s ease;
    }
    
    .upload-area:hover {
        border-color: #667eea;
        background: #f1f5f9;
    }
    
    .search-box {
        background: white;
        padding: 1.5rem;
        border-radius: 15px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        margin-bottom: 1rem;
    }
    
    .result-card {
        background: white;
        border: 1px solid #e0e6ed;
        border-radius: 15px;
        padding: 1.5rem;
        margin-bottom: 1rem;
        transition: all 0.3s ease;
    }
    
    .result-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 25px rgba(0,0,0,0.1);
        border-color: #667eea;
    }
    
    .detail-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 1rem;
        margin-top: 1rem;
    }
    
    .detail-item {
        background: #f8fafc;
        padding: 0.75rem;
        border-radius: 8px;
        border-left: 3px solid #667eea;
    }
    
    .detail-label {
        font-size: 0.75rem;
        color: #64748b;
        text-transform: uppercase;
        font-weight: 600;
        margin-bottom: 0.25rem;
    }
    
    .detail-value {
        font-size: 0.875rem;
        color: #334155;
        font-weight: 500;
    }
    
    .filter-btn {
        background: white;
        border: 2px solid #e0e6ed;
        border-radius: 25px;
        padding: 0.5rem 1rem;
        margin: 0.25rem;
        cursor: pointer;
        transition: all 0.3s ease;
    }
    
    .filter-btn.active {
        background: #667eea;
        color: white;
        border-color: #667eea;
    }
    
    .file-info {
        background: #e0f2fe;
        border: 1px solid #0891b2;
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 1rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

# 메인 헤더
st.markdown("""
<div class="main-header">
    <h1>📡 회선선번장 검색</h1>
    <p>엑셀 파일을 업로드하고 RU 정보를 빠르게 찾아보세요</p>
</div>
""", unsafe_allow_html=True)

# 세션 상태 초기화
if 'data' not in st.session_state:
    st.session_state.data = None
if 'filtered_data' not in st.session_state:
    st.session_state.filtered_data = None
if 'current_filter' not in st.session_state:
    st.session_state.current_filter = 'all'

# 파일 업로드 섹션
if st.session_state.data is None:
    st.markdown("""
    <div class="upload-area">
        <h2>📁 엑셀 파일을 업로드하세요</h2>
        <p>클릭하거나 파일을 드래그해서 업로드</p>
    </div>
    """, unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader(
        "엑셀 파일 선택",
        type=['xlsx', 'xls'],
        label_visibility="collapsed"
    )
    
    if uploaded_file is not None:
        try:
            # 파일 읽기
            df = pd.read_excel(uploaded_file)
            st.session_state.data = df
            st.session_state.filtered_data = df
            st.success(f"✅ {uploaded_file.name} 파일이 성공적으로 로드되었습니다!")
            st.rerun()
        except Exception as e:
            st.error(f"❌ 파일 읽기 실패: {str(e)}")

# 검색 섹션
if st.session_state.data is not None:
    # 파일 정보 표시
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        st.markdown(f"""
        <div class="file-info">
            <span>📋</span>
            <div>
                <strong>{uploaded_file.name if 'uploaded_file' in locals() else '파일'}</strong><br>
                <span>{len(st.session_state.data):,}개 데이터 로드됨</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        if st.button("🔄 새 파일 업로드", type="secondary"):
            st.session_state.data = None
            st.session_state.filtered_data = None
            st.rerun()
    
    with col3:
        if st.button("📥 데이터 다운로드", type="secondary"):
            csv = st.session_state.filtered_data.to_csv(index=False, encoding='cp949')
            st.download_button(
                "CSV 다운로드",
                csv,
                file_name=f"RU_검색결과_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
    
    # 검색 및 필터링
    st.markdown('<div class="search-box">', unsafe_allow_html=True)
    
    # 검색어 입력
    search_query = st.text_input(
        "🔍 검색",
        placeholder="RU_NAME으로 검색하세요 (예: 복산동, 온천동 등)",
        label_visibility="collapsed"
    )
    
    # 필터 버튼
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        if st.button("전체", key="filter_all", type="primary" if st.session_state.current_filter == 'all' else "secondary"):
            st.session_state.current_filter = 'all'
            st.rerun()
    with col2:
        if st.button("RU명", key="filter_ru", type="primary" if st.session_state.current_filter == 'RU_NAME' else "secondary"):
            st.session_state.current_filter = 'RU_NAME'
            st.rerun()
    with col3:
        if st.button("DU명", key="filter_du", type="primary" if st.session_state.current_filter == 'DU_NAME' else "secondary"):
            st.session_state.current_filter = 'DU_NAME'
            st.rerun()
    with col4:
        if st.button("MUX", key="filter_mux", type="primary" if st.session_state.current_filter == 'MUX' else "secondary"):
            st.session_state.current_filter = 'MUX'
            st.rerun()
    with col5:
        if st.button("채널", key="filter_ch", type="primary" if st.session_state.current_filter == 'CH' else "secondary"):
            st.session_state.current_filter = 'CH'
            st.rerun()
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 데이터 필터링
    if search_query:
        if st.session_state.current_filter == 'all':
            # 모든 컬럼에서 검색
            mask = st.session_state.data.astype(str).apply(
                lambda x: x.str.contains(search_query, case=False, na=False)
            ).any(axis=1)
        else:
            # 특정 컬럼에서 검색
            if st.session_state.current_filter in st.session_state.data.columns:
                mask = st.session_state.data[st.session_state.current_filter].astype(str).str.contains(
                    search_query, case=False, na=False
                )
            else:
                mask = pd.Series([True] * len(st.session_state.data))
        
        st.session_state.filtered_data = st.session_state.data[mask]
    else:
        st.session_state.filtered_data = st.session_state.data
    
    # 결과 개수 표시
    total_count = len(st.session_state.data)
    filtered_count = len(st.session_state.filtered_data)
    st.info(f"📊 총 {total_count:,}개 중 {filtered_count:,}개 결과")
    
    # 결과 표시
    if filtered_count == 0:
        st.markdown("""
        <div style="text-align: center; padding: 3rem; color: #64748b;">
            <h2>🔍</h2>
            <h3>검색 결과가 없습니다</h3>
            <p>다른 검색어를 시도해보세요</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        # 최대 50개만 표시
        display_data = st.session_state.filtered_data.head(50)
        
        for idx, row in display_data.iterrows():
            st.markdown(f"""
            <div class="result-card">
                <h3>{row.get('RU_NAME', 'N/A')}</h3>
                <div class="detail-grid">
                    <div class="detail-item">
                        <div class="detail-label">RU ID</div>
                        <div class="detail-value">{row.get('RU_ID', 'N/A')}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">MUX</div>
                        <div class="detail-value">{row.get('MUX', 'N/A')}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">채널</div>
                        <div class="detail-value">{row.get('CH', 'N/A')}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">DU ID</div>
                        <div class="detail-value">{row.get('DU_ID', 'N/A')}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">DU NAME</div>
                        <div class="detail-value">{row.get('DU_NAME', 'N/A')}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">카드</div>
                        <div class="detail-value">{row.get('CARD', 'N/A')}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">포트</div>
                        <div class="detail-value">{row.get('PORT', 'N/A')}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">시리얼</div>
                        <div class="detail-value">{row.get('serial', 'N/A')}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        if filtered_count > 50:
            st.warning("⚠️ 처음 50개 결과만 표시됩니다. 더 구체적인 검색어를 사용해보세요.")

# 사이드바에 사용법 안내
with st.sidebar:
    st.markdown("## 📖 사용법")
    st.markdown("""
    1. **파일 업로드**: 엑셀 파일(.xlsx, .xls)을 업로드하세요
    2. **검색**: RU_NAME, DU_NAME, MUX 등으로 검색하세요
    3. **필터링**: 특정 필드만 검색하려면 필터 버튼을 사용하세요
    4. **결과 확인**: 검색 결과를 카드 형태로 확인하세요
    5. **다운로드**: 검색 결과를 CSV로 다운로드할 수 있습니다
    """)
    
    st.markdown("## 📋 지원 컬럼")
    st.markdown("""
    - **RU_NAME**: RU 이름
    - **RU_ID**: RU ID
    - **MUX**: MUX 정보
    - **CH**: 채널 정보
    - **DU_ID**: DU ID
    - **DU_NAME**: DU 이름
    - **CARD**: 카드 정보
    - **PORT**: 포트 정보
    - **serial**: 시리얼 번호
    """)
    
    st.markdown("## 🔧 개발 정보")
    st.markdown("""
    - **개발**: KT 통신장비 관리 시스템
    - **버전**: 1.0.0
    - **지원**: 엑셀 파일(.xlsx, .xls)
    """) 