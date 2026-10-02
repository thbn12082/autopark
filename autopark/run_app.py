"""Chạy giao diện sa bàn: python run_app.py [đường_dẫn_kịch_bản.json] [--max-cusps N] [--warn-cusps N] (autopark/ui/app.py)"""
import sys

from autopark.ui.app import main

if __name__ == "__main__":
    sys.exit(main(sys.argv))
