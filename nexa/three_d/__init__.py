"""Tạo và tương tác với mô hình 3D (docs/three_d.md).

Luồng: văn bản/giọng nói → planner (Gemini hoặc bộ phân tích local) → ModelSpec → JobManager chạy nền
→ CAD tham số cục bộ hoặc dịch vụ cloud (Tripo/Meshy) → kiểm tra hình học → render 6 góc → chấm điểm
→ GLB + assembly manifest trong cache → viewer Qt Quick 3D (xoay/tách/lắp bằng cử chỉ, giọng nói).
"""
