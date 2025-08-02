# gui/contact_window.py
# 연락처 검색 전용 GUI

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import os
import sys
from datetime import datetime

# 부모 폴더를 Python 경로에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from utils.excel_handler import ExcelHandler
from utils.kakao_api import KakaoAPI

class ContactMappingApp:
    """연락처 매핑 애플리케이션"""
    
    def __init__(self, root):
        self.root = root
        self.setup_window()
        self.setup_variables()
        self.setup_ui()
        
        # 필요한 객체들
        self.excel_handler = ExcelHandler()
        self.kakao_api = None
        self.address_data = []
        self.is_processing = False
        
        print("🚀 연락처 매핑 GUI가 준비되었어요!")
    
    def setup_window(self):
        """윈도우 기본 설정"""
        self.root.title("📞 연락처 매핑 시스템")
        self.root.geometry("900x650")
        
        # 윈도우 중앙 배치
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (900 // 2)
        y = (self.root.winfo_screenheight() // 2) - (650 // 2)
        self.root.geometry(f"900x650+{x}+{y}")
    
    def setup_variables(self):
        """변수들 초기화"""
        self.api_key_var = tk.StringVar()
        self.file_path_var = tk.StringVar()
        self.total_count_var = tk.StringVar(value="0")
        self.success_count_var = tk.StringVar(value="0")
        self.error_count_var = tk.StringVar(value="0")
        self.progress_var = tk.IntVar()
    
    def setup_ui(self):
        """화면 구성"""
        # 메인 프레임
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill="both", expand=True)
        
        # 제목
        title_label = ttk.Label(main_frame, text="📞 연락처 매핑 시스템", 
                               font=("맑은 고딕", 18, "bold"))
        title_label.pack(pady=(0, 10))
        
        subtitle_label = ttk.Label(main_frame, text="주소 → 업체명 + 전화번호 변환", 
                                  font=("맑은 고딕", 10))
        subtitle_label.pack(pady=(0, 20))
        
        # 좌우 분할
        paned = ttk.PanedWindow(main_frame, orient="horizontal")
        paned.pack(fill="both", expand=True)
        
        # 왼쪽 제어판
        self.setup_control_panel(paned)
        
        # 오른쪽 결과 패널
        self.setup_result_panel(paned)
    
    def setup_control_panel(self, parent):
        """왼쪽 제어판 설정"""
        control_frame = ttk.Frame(parent, padding="10")
        parent.add(control_frame, weight=1)
        
        # 1. 파일 선택 섹션
        file_section = ttk.LabelFrame(control_frame, text="📁 Excel 파일 선택", padding="10")
        file_section.pack(fill="x", pady=(0, 10))
        
        ttk.Entry(file_section, textvariable=self.file_path_var, state="readonly").pack(fill="x", pady=(0, 5))
        ttk.Button(file_section, text="파일 선택", command=self.select_file).pack()
        
        # 2. API 키 섹션
        api_section = ttk.LabelFrame(control_frame, text="🔑 카카오 API 키", padding="10")
        api_section.pack(fill="x", pady=(0, 10))
        
        ttk.Label(api_section, text="⚠️ 카카오 개발자센터에서 REST API 키 발급", 
                 foreground="orange").pack(pady=(0, 5))
        ttk.Entry(api_section, textvariable=self.api_key_var, show="*").pack(fill="x", pady=(0, 5))
        ttk.Button(api_section, text="API 연결", command=self.connect_api).pack()
        
        # 3. 통계 섹션
        stats_section = ttk.LabelFrame(control_frame, text="📊 처리 현황", padding="10")
        stats_section.pack(fill="x", pady=(0, 10))
        
        stats_frame = ttk.Frame(stats_section)
        stats_frame.pack(fill="x")
        
        ttk.Label(stats_frame, text="총 주소:").grid(row=0, column=0, sticky="w")
        ttk.Label(stats_frame, textvariable=self.total_count_var, font=("맑은 고딕", 10, "bold")).grid(row=0, column=1, sticky="e")
        
        ttk.Label(stats_frame, text="성공:").grid(row=1, column=0, sticky="w")
        ttk.Label(stats_frame, textvariable=self.success_count_var, foreground="green").grid(row=1, column=1, sticky="e")
        
        ttk.Label(stats_frame, text="실패:").grid(row=2, column=0, sticky="w")
        ttk.Label(stats_frame, textvariable=self.error_count_var, foreground="red").grid(row=2, column=1, sticky="e")
        
        stats_frame.columnconfigure(1, weight=1)
        
        # 4. 진행률 섹션
        progress_section = ttk.LabelFrame(control_frame, text="⏳ 진행률", padding="10")
        progress_section.pack(fill="x", pady=(0, 10))
        
        self.progress_bar = ttk.Progressbar(progress_section, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill="x", pady=(0, 5))
        
        self.progress_label = ttk.Label(progress_section, text="파일을 선택해주세요")
        self.progress_label.pack()
        
        # 5. 실행 버튼
        action_section = ttk.LabelFrame(control_frame, text="🚀 실행", padding="10")
        action_section.pack(fill="x")
        
        self.start_btn = ttk.Button(action_section, text="연락처 매핑 시작", 
                                   command=self.start_mapping, state="disabled")
        self.start_btn.pack(fill="x", pady=(0, 5))
        
        self.download_btn = ttk.Button(action_section, text="결과 다운로드", 
                                      command=self.download_results, state="disabled")
        self.download_btn.pack(fill="x")
    
    def setup_result_panel(self, parent):
        """오른쪽 결과 패널 설정"""
        result_frame = ttk.Frame(parent, padding="10")
        parent.add(result_frame, weight=2)
        
        # 노트북 (탭)
        notebook = ttk.Notebook(result_frame)
        notebook.pack(fill="both", expand=True)
        
        # 결과 탭
        result_tab = ttk.Frame(notebook)
        notebook.add(result_tab, text="📞 연락처 결과")
        
        # 결과 트리뷰
        result_frame_inner = ttk.Frame(result_tab)
        result_frame_inner.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 트리뷰 스크롤바
        tree_scroll = ttk.Scrollbar(result_frame_inner)
        tree_scroll.pack(side="right", fill="y")
        
        # 트리뷰
        self.result_tree = ttk.Treeview(result_frame_inner, yscrollcommand=tree_scroll.set,
                                       columns=("순번", "주소", "업체명", "전화번호", "상태"), show="headings")
        tree_scroll.config(command=self.result_tree.yview)
        
        # 컬럼 설정
        self.result_tree.heading("순번", text="순번")
        self.result_tree.heading("주소", text="주소")
        self.result_tree.heading("업체명", text="업체명")
        self.result_tree.heading("전화번호", text="전화번호")
        self.result_tree.heading("상태", text="상태")
        
        self.result_tree.column("순번", width=50, anchor="center")
        self.result_tree.column("주소", width=200, anchor="w")
        self.result_tree.column("업체명", width=150, anchor="w")
        self.result_tree.column("전화번호", width=120, anchor="center")
        self.result_tree.column("상태", width=70, anchor="center")
        
        self.result_tree.pack(fill="both", expand=True)
        
        # 로그 탭
        log_tab = ttk.Frame(notebook)
        notebook.add(log_tab, text="📝 로그")
        
        self.log_text = scrolledtext.ScrolledText(log_tab, font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 초기 메시지
        self.add_log("📞 연락처 매핑 시스템이 준비되었어요!")
        self.add_log("📋 사용 순서:")
        self.add_log("1. Excel 파일 선택 (A열에 주소)")
        self.add_log("2. 카카오 REST API 키 입력")
        self.add_log("3. API 연결")
        self.add_log("4. 연락처 매핑 시작")
        self.add_log("5. 결과 다운로드")
    
    def add_log(self, message):
        """로그 메시지 추가"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"
        self.log_text.insert(tk.END, log_message)
        self.log_text.see(tk.END)
        self.root.update_idletasks()
    
    def select_file(self):
        """Excel 파일 선택"""
        file_path = filedialog.askopenfilename(
            title="Excel 파일 선택",
            filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")]
        )
        
        if file_path:
            self.file_path_var.set(file_path)
            try:
                self.address_data = self.excel_handler.load_addresses(file_path)
                self.total_count_var.set(str(len(self.address_data)))
                self.progress_label.config(text=f"{len(self.address_data)}개 주소 로드 완료")
                
                self.add_log(f"✅ {len(self.address_data)}개 주소를 로드했어요!")
                
                # 처음 3개 주소 미리보기
                for i, addr in enumerate(self.address_data[:3]):
                    self.add_log(f"   {i+1}. {addr['address']}")
                
                if len(self.address_data) > 3:
                    self.add_log(f"   ... 외 {len(self.address_data) - 3}개 더")
                
                self.update_button_states()
                
            except Exception as e:
                messagebox.showerror("오류", str(e))
                self.add_log(f"❌ 파일 로드 실패: {e}")
    
    def connect_api(self):
        """카카오 API 연결"""
        api_key = self.api_key_var.get().strip()
        
        if not api_key:
            messagebox.showwarning("경고", "API 키를 입력해주세요!")
            return
        
        try:
            self.kakao_api = KakaoAPI(api_key)
            
            # API 키 테스트
            if self.kakao_api.test_api_key():
                self.add_log("✅ 카카오 API 연결 성공!")
                messagebox.showinfo("성공", "카카오 API 연결이 완료되었어요! 👍")
                self.update_button_states()
            else:
                self.add_log("❌ API 키 테스트 실패")
                messagebox.showerror("실패", "API 키를 확인해주세요!")
                
        except Exception as e:
            self.add_log(f"❌ API 연결 실패: {e}")
            messagebox.showerror("오류", str(e))
    
    def start_mapping(self):
        """연락처 매핑 시작"""
        if self.is_processing:
            return
        
        if not self.kakao_api or not self.address_data:
            messagebox.showwarning("경고", "파일과 API를 먼저 준비해주세요!")
            return
        
        self.is_processing = True
        self.update_button_states()
        
        # 결과 초기화
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)
        
        # 통계 초기화
        self.success_count_var.set("0")
        self.error_count_var.set("0")
        self.progress_var.set(0)
        
        self.add_log("🚀 연락처 매핑을 시작해요!")
        
        # 별도 스레드에서 처리
        threading.Thread(target=self.process_addresses, daemon=True).start()
    
    def process_addresses(self):
        """주소 처리 (백그라운드)"""
        total = len(self.address_data)
        success = 0
        error = 0
        
        for i, addr_data in enumerate(self.address_data):
            try:
                # 연락처 검색
                contact_info = self.kakao_api.find_contact_info(addr_data['address'])
                
                addr_data['place_name'] = contact_info['place_name']
                addr_data['phone'] = contact_info['phone']
                addr_data['category'] = contact_info.get('category', '')
                addr_data['status'] = '성공'
                success += 1
                
                # UI 업데이트
                self.root.after(0, self.update_result_success, 
                               addr_data['id'], addr_data['address'], 
                               contact_info['place_name'], contact_info['phone'])
                
                self.root.after(0, self.add_log, 
                               f"✅ {i+1}/{total}: {contact_info['place_name']} - {contact_info['phone']}")
                
            except Exception as e:
                addr_data['status'] = '실패'
                addr_data['error'] = str(e)
                error += 1
                
                # UI 업데이트
                self.root.after(0, self.update_result_error, 
                               addr_data['id'], addr_data['address'], str(e))
                
                self.root.after(0, self.add_log, 
                               f"❌ {i+1}/{total}: {addr_data['address'][:25]}... - {e}")
            
            # 진행률 업데이트
            progress = int(((i + 1) / total) * 100)
            self.root.after(0, self.update_progress, i + 1, success, error, progress)
            
            # API 제한 (0.15초 대기)
            import time
            time.sleep(0.15)
        
        # 완료
        self.root.after(0, self.mapping_completed, success, error)
    
    def update_result_success(self, addr_id, address, place_name, phone):
        """성공 결과 업데이트"""
        self.result_tree.insert("", "end", values=(
            addr_id, 
            address[:30] + "..." if len(address) > 30 else address,
            place_name,
            phone,
            "✅ 성공"
        ), tags=("success",))
        
        self.result_tree.tag_configure("success", foreground="green")
        
        # 마지막 항목으로 스크롤
        children = self.result_tree.get_children()
        if children:
            self.result_tree.see(children[-1])
    
    def update_result_error(self, addr_id, address, error):
        """실패 결과 업데이트"""
        self.result_tree.insert("", "end", values=(
            addr_id,
            address[:30] + "..." if len(address) > 30 else address,
            "-",
            "-",
            "❌ 실패"
        ), tags=("error",))
        
        self.result_tree.tag_configure("error", foreground="red")
        
        # 마지막 항목으로 스크롤
        children = self.result_tree.get_children()
        if children:
            self.result_tree.see(children[-1])
    
    def update_progress(self, processed, success, error, progress):
        """진행률 업데이트"""
        self.success_count_var.set(str(success))
        self.error_count_var.set(str(error))
        self.progress_var.set(progress)
        self.progress_label.config(text=f"{processed} / {len(self.address_data)} ({progress}%)")
    
    def mapping_completed(self, success, error):
        """매핑 완료"""
        self.is_processing = False
        self.update_button_states()
        
        self.add_log(f"🎉 연락처 매핑 완료! 성공: {success}개, 실패: {error}개")
        messagebox.showinfo("완료", f"연락처 매핑 완료!\n성공: {success}개\n실패: {error}개")
    
    def download_results(self):
        """결과 다운로드"""
        if not self.address_data:
            messagebox.showwarning("경고", "다운로드할 데이터가 없어요!")
            return
        
        file_path = filedialog.asksaveasfilename(
            title="결과 저장",
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")],
            initialvalue=f"연락처_매핑_결과_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )
        
        if file_path:
            try:
                self.excel_handler.save_results(self.address_data, file_path)
                self.add_log(f"💾 결과 저장 완료: {file_path}")
                messagebox.showinfo("완료", "결과가 저장되었어요! 👍")
                
            except Exception as e:
                messagebox.showerror("오류", str(e))
                self.add_log(f"❌ 저장 실패: {e}")
    
    def update_button_states(self):
        """버튼 상태 업데이트"""
        has_file = bool(self.address_data)
        has_api = self.kakao_api is not None
        
        if has_file and has_api and not self.is_processing:
            self.start_btn.config(state="normal")
        else:
            self.start_btn.config(state="disabled")
        
        processed_data = [addr for addr in self.address_data if addr.get('status') and addr['status'] != '대기중']
        if processed_data and not self.is_processing:
            self.download_btn.config(state="normal")
        else:
            self.download_btn.config(state="disabled")