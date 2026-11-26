"""Chạy giao diện thao tác gần (mặc định: cua 90 độ trong lối hẹp):

    python run_app.py [đường_dẫn_kịch_bản.json] [--max-cusps N] [--warn-cusps N] [--vehicle-config TỆP_XE]

    python run_app.py scenarios/thao_tac_cua_hep.json
    python run_app.py scenarios/thao_tac_lui_vao_khe.json
"""
import sys

from autopark.ui.app import main

if __name__ == "__main__":
    sys.exit(main(sys.argv))
