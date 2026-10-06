"""Chạy giao diện sa bàn (autopark/ui/app.py):

    python run_app.py [đường_dẫn_kịch_bản.json] [--max-cusps N] [--warn-cusps N] [--vehicle-config TỆP_XE]

Nghiệm thu (02/10/2026): xe configs/vehicle_nghiem_thu.json, tối đa 0,10 m/s (N-V1 ĐỀ XUẤT – CHỜ CHỐT):

    python run_app.py scenarios\\sa_ban_3x2_hai_hop.json --vehicle-config configs\\vehicle_nghiem_thu.json
"""
import sys

from autopark.ui.app import main

if __name__ == "__main__":
    sys.exit(main(sys.argv))
