"""Mở AutoPark: một cửa sổ chung cho mọi công cụ (đỗ xe, quan sát Pi, hiệu chuẩn, dữ liệu).

    python run_app.py [--page do_xe|ket_noi_xe|lai_tay|quan_sat_pi|noi_tham|ngoai_tham|bo_camera|gan_nhan|tren_cao]
                      [--scenario scenarios/thao_tac_cua_hep.json] [--host IP_PI]
"""
import sys

from autopark.ui.shell import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
