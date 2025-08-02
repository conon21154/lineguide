@echo off
echo ========================================
echo    📱 RU 검색 모바일 앱 실행
echo ========================================
echo.
echo 모바일에서 접속할 수 있도록 설정합니다...
echo.

REM 포트 확인
netstat -an | findstr :8501 > nul
if %errorlevel% == 0 (
    echo ⚠️  포트 8501이 이미 사용 중입니다.
    echo 다른 포트로 실행합니다...
    set PORT=8502
) else (
    set PORT=8501
)

echo.
echo 🚀 모바일 앱을 시작합니다...
echo 📱 접속 주소: http://localhost:%PORT%
echo 🌐 네트워크 접속: http://%COMPUTERNAME%:%PORT%
echo.

REM 모바일 앱 실행
streamlit run ru_search_mobile.py --server.address 0.0.0.0 --server.port %PORT%

pause 