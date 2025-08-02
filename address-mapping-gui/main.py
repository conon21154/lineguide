# main.py
# 연락처 매핑 프로그램의 시작점!

import tkinter as tk
from tkinter import messagebox
import sys

try:
    from gui.contact_window import ContactMappingApp
except ImportError as e:
    print(f"❌ 필요한 파일을 찾을 수 없어요: {e}")
    print("📁 파일 구조를 확인해주세요!")
    sys.exit(1)

def main():
    """메인 함수"""
    try:
        print("📞 연락처 매핑 프로그램을 시작해요!")
        
        # 메인 윈도우 생성
        root = tk.Tk()
        app = ContactMappingApp(root)
        
        print("✅ 연락처 매핑 GUI 준비 완료!")
        
        # 프로그램 실행
        root.mainloop()
        
    except Exception as e:
        print(f"❌ 프로그램 실행 중 오류: {e}")
        messagebox.showerror("오류", f"프로그램 실행 실패:\n{str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()