import streamlit as st
import pandas as pd
import io
import base64

# 페이지 설정 (모바일 최적화)
st.set_page_config(
    page_title="📱 RU 검색",
    page_icon="📱",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 모바일 최적화 CSS
st.markdown("""
<style>
    /* 모바일 최적화 스타일 */
    @media (max-width: 768px) {
        .main-header {
            padding: 1rem !important;
            margin-bottom: 1rem !important;
        }
        
        .main-header h1 {
            font-size: 1.5rem !important;
        }
        
        .main-header p {
            font-size: 0.9rem !important;
        }
        
        .upload-area {
            padding: 2rem 1rem !important;
        }
        
        .search-box {
            padding: 1rem !important;
        }
        
        .result-card {
            padding: 1rem !important;
            margin-bottom: 0.5rem !important;
        }
        
        .detail-grid {
            grid-template-columns: 1fr !important;
            gap: 0.5rem !important;
        }
        
        .detail-item {
            padding: 0.5rem !important;
        }
        
        .filter-buttons {
            display: flex !important;
            overflow-x: auto !important;
            gap: 0.5rem !important;
            padding: 0.5rem 0 !important;
        }
        
        .filter-btn {
            white-space: nowrap !important;
            flex-shrink: 0 !important;
            padding: 0.5rem 1rem !important;
            font-size: 0.8rem !important;
        }
    }
    
    /* 기본 스타일 */
    .main-header {
        background: linear-gradient(45deg, #4158D0 0%, #C850C0 46%, #FFCC70 100%);
        padding: 1.5rem;
        border-radius: 15px;
        margin-bottom: 1.5rem;
        text-align: center;
        color: white;
    }
    
    .upload-area {
        border: 2px dashed #cbd5e1;
        border-radius: 15px;
        padding: 2rem;
        text-align: center;
        background: #f8fafc;
        transition: all 0.3s ease;
        margin-bottom: 1rem;
    }
    
    .upload-area:hover {
        border-color: #667eea;
        background: #f1f5f9;
    }
    
    .search-box {
        background: white;
        padding: 1rem;
        border-radius: 15px;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        margin-bottom: 1rem;
    }
    
    .result-card {
        background: white;
        border: 1px solid #e0e6ed;
        border-radius: 12px;
        padding: 1rem;
        margin-bottom: 0.75rem;
        transition: all 0.3s ease;
    }
    
    .result-card:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        border-color: #667eea;
    }
    
    .detail-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 0.75rem;
        margin-top: 0.75rem;
    }
    
    .detail-item {
        background: #f8fafc;
        padding: 0.5rem;
        border-radius: 8px;
        border-left: 3px solid #667eea;
    }
    
    .detail-label {
        font-size: 0.7rem;
        color: #64748b;
        text-transform: uppercase;
        font-weight: 600;
        margin-bottom: 0.25rem;
    }
    
    .detail-value {
        font-size: 0.8rem;
        color: #334155;
        font-weight: 500;
        word-break: break-all;
    }
    
    .filter-buttons {
        display: flex;
        gap: 0.5rem;
        margin-bottom: 1rem;
        flex-wrap: wrap;
    }
    
    .filter-btn {
        background: white;
        border: 2px solid #e0e6ed;
        border-radius: 20px;
        padding: 0.5rem 1rem;
        cursor: pointer;
        transition: all 0.3s ease;
        font-size: 0.8rem;
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
        padding: 0.75rem;
        margin-bottom: 1rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
        font-size: 0.8rem;
    }
    
    .mobile-actions {
        display: flex;
        gap: 0.5rem;
        margin-bottom: 1rem;
    }
    
    .mobile-actions button {
        flex: 1;
        padding: 0.5rem;
        font-size: 0.8rem;
    }
    
    /* 터치 최적화 */
    button, .upload-area {
        min-height: 44px;
        touch-action: manipulation;
    }
    
    /* 스크롤 최적화 */
    .results-container {
        max-height: 70vh;
        overflow-y: auto;
        -webkit-overflow-scrolling: touch;
    }
    
    /* 로딩 스피너 */
    .loading {
        text-align: center;
        padding: 2rem;
        color: #64748b;
    }
    
    .loading-spinner {
        width: 30px;
        height: 30px;
        border: 3px solid #f3f4f6;
        border-top: 3px solid #667eea;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        margin: 0 auto 1rem;
    }
    
    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
</style>
""", unsafe_allow_html=True)

# 메인 헤더 (모바일 최적화)
st.markdown("""
<div class="main-header">
    <h1>📱 RU 검색</h1>
    <p>회선선번장 정보를 빠르게 찾아보세요</p>
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
        <h3>📁 엑셀 파일 업로드</h3>
        <p>터치하여 파일 선택</p>
    </div>
    """, unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader(
        "파일 선택",
        type=['xlsx', 'xls'],
        label_visibility="collapsed"
    )
    
    if uploaded_file is not None:
        try:
            with st.spinner("파일을 분석하는 중..."):
                df = pd.read_excel(uploaded_file)
                st.session_state.data = df
                st.session_state.filtered_data = df
                st.success(f"✅ {uploaded_file.name} 로드 완료!")
                st.rerun()
        except Exception as e:
            st.error(f"❌ 파일 읽기 실패: {str(e)}")

# 검색 섹션
if st.session_state.data is not None:
    # 파일 정보 표시 (모바일 최적화)
    st.markdown(f"""
    <div class="file-info">
        <span>📋</span>
        <div>
            <strong>{uploaded_file.name if 'uploaded_file' in locals() else '파일'}</strong><br>
            <span>{len(st.session_state.data):,}개 데이터</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # 모바일 액션 버튼
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 새 파일", type="secondary", use_container_width=True):
            st.session_state.data = None
            st.session_state.filtered_data = None
            st.rerun()
    
    with col2:
        if st.button("📥 다운로드", type="secondary", use_container_width=True):
            csv = st.session_state.filtered_data.to_csv(index=False, encoding='cp949')
            st.download_button(
                "CSV 다운로드",
                csv,
                file_name=f"RU_검색결과_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )
    
    # 검색 및 필터링 (모바일 최적화)
    st.markdown('<div class="search-box">', unsafe_allow_html=True)
    
    # 검색어 입력 (모바일 키보드 최적화)
    search_query = st.text_input(
        "🔍 검색어",
        placeholder="RU명, DU명 등으로 검색",
        label_visibility="collapsed"
    )
    
    # 필터 버튼 (모바일 터치 최적화)
    st.markdown('<div class="filter-buttons">', unsafe_allow_html=True)
    
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        if st.button("전체", key="filter_all", type="primary" if st.session_state.current_filter == 'all' else "secondary", use_container_width=True):
            st.session_state.current_filter = 'all'
            st.rerun()
    with col2:
        if st.button("RU명", key="filter_ru", type="primary" if st.session_state.current_filter == 'RU_NAME' else "secondary", use_container_width=True):
            st.session_state.current_filter = 'RU_NAME'
            st.rerun()
    with col3:
        if st.button("DU명", key="filter_du", type="primary" if st.session_state.current_filter == 'DU_NAME' else "secondary", use_container_width=True):
            st.session_state.current_filter = 'DU_NAME'
            st.rerun()
    with col4:
        if st.button("MUX", key="filter_mux", type="primary" if st.session_state.current_filter == 'MUX' else "secondary", use_container_width=True):
            st.session_state.current_filter = 'MUX'
            st.rerun()
    with col5:
        if st.button("채널", key="filter_ch", type="primary" if st.session_state.current_filter == 'CH' else "secondary", use_container_width=True):
            st.session_state.current_filter = 'CH'
            st.rerun()
    
    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 데이터 필터링
    if search_query:
        if st.session_state.current_filter == 'all':
            mask = st.session_state.data.astype(str).apply(
                lambda x: x.str.contains(search_query, case=False, na=False)
            ).any(axis=1)
        else:
            if st.session_state.current_filter in st.session_state.data.columns:
                mask = st.session_state.data[st.session_state.current_filter].astype(str).str.contains(
                    search_query, case=False, na=False
                )
            else:
                mask = pd.Series([True] * len(st.session_state.data))
        
        st.session_state.filtered_data = st.session_state.data[mask]
    else:
        st.session_state.filtered_data = st.session_state.data
    
    # 결과 개수 표시 (모바일 최적화)
    total_count = len(st.session_state.data)
    filtered_count = len(st.session_state.filtered_data)
    st.info(f"📊 {total_count:,}개 중 {filtered_count:,}개")
    
    # 결과 표시 (모바일 최적화)
    if filtered_count == 0:
        st.markdown("""
        <div style="text-align: center; padding: 2rem; color: #64748b;">
            <h3>🔍</h3>
            <p>검색 결과가 없습니다</p>
            <p style="font-size: 0.8rem;">다른 검색어를 시도해보세요</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        # 최대 30개만 표시 (모바일 성능 최적화)
        display_data = st.session_state.filtered_data.head(30)
        
        st.markdown('<div class="results-container">', unsafe_allow_html=True)
        
        for idx, row in display_data.iterrows():
            st.markdown(f"""
            <div class="result-card">
                <h4 style="margin-bottom: 0.5rem; color: #1e293b;">{row.get('RU_NAME', 'N/A')}</h4>
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
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        if filtered_count > 30:
            st.warning("⚠️ 처음 30개만 표시됩니다. 더 구체적으로 검색해보세요.")

# 모바일 최적화 사이드바 (접을 수 있음)
with st.sidebar:
    st.markdown("## 📖 사용법")
    st.markdown("""
    1. **파일 업로드**: 엑셀 파일 선택
    2. **검색**: 검색어 입력
    3. **필터**: 버튼으로 검색 범위 선택
    4. **결과**: 카드로 확인
    5. **다운로드**: CSV로 저장
    """)
    
    st.markdown("## 📋 주요 컬럼")
    st.markdown("""
    - **RU_NAME**: RU 이름
    - **RU_ID**: RU ID  
    - **MUX**: MUX 정보
    - **CH**: 채널 정보
    - **DU_NAME**: DU 이름
    - **CARD**: 카드 정보
    - **PORT**: 포트 정보
    """)
    
    st.markdown("## 📱 모바일 최적화")
    st.markdown("""
    - 터치 친화적 UI
    - 빠른 검색
    - 스크롤 최적화
    - 반응형 디자인
    """) 