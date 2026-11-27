"""RoboMaster EP: pair with a shared Wi-Fi network using a QR code.

Based on DJI's examples/01_robot/05_sta_conn_helper.py.
This script generates network credentials locally and waits for the robot.
"""
from getpass import getpass
from pathlib import Path
import tempfile

from MyQR import myqr
from PIL import Image
from robomaster import conn


def main():
    print("EP 小车扫码配网：请先让电脑连接准备给小车使用的热点或路由器。")
    ssid = input("请输入该 Wi-Fi 的名称（区分大小写）：").strip()
    if not ssid:
        print("Wi-Fi 名称不能为空。")
        return 1
    password = getpass("请输入 Wi-Fi 密码（输入时不显示）：")
    helper = conn.ConnectionHelper()
    data = helper.build_qrcode_string(ssid=ssid, password=password)
    temp_root = Path(r"D:\RoboMaster\temp")
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ep-pair-", dir=str(temp_root)) as folder:
        myqr.run(words=data, save_name="qrcode.png", save_dir=folder)
        print("请将小车切到组网模式，按扫码连接键，再让小车摄像头扫描电脑上的二维码。")
        print("正在等待连接，最长约 6 分钟；可按 Ctrl+C 取消。")
        with Image.open(Path(folder) / "qrcode.png") as picture:
            picture.show()
        if helper.wait_for_connection():
            print("Connected! 小车已加入该网络。接下来运行 02_sta_check.py。")
            return 0
        print("连接未完成。请检查 Wi-Fi 名称、密码、组网模式及电脑是否在同一网络。")
        return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n已取消配网。")
        raise SystemExit(130)
