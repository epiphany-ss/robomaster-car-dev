"""Connect to EP in STA mode and query its firmware version; no motion commands."""
import argparse
from contextlib import suppress

from robomaster import config, robot


def main():
    parser = argparse.ArgumentParser(description="EP 组网连接测试：读取固件版本，不发送运动指令。")
    parser.add_argument("--sn", help="同一网络有多台 EP 时，用 SN 指定小车。")
    parser.add_argument("--local-ip", help="多网卡识别错误时，指定电脑连接热点的 IPv4。")
    args = parser.parse_args()
    if args.local_ip:
        config.LOCAL_IP_STR = args.local_ip
    ep = robot.Robot()
    try:
        print("正在通过 STA 组网模式连接 EP……")
        if not ep.initialize(conn_type="sta", proto_type="udp", sn=args.sn):
            raise RuntimeError("初始化失败")
        version = ep.get_version()
        if not version:
            raise RuntimeError("未收到小车的版本信息")
        print("连接成功！Robot version:", version)
        return 0
    except Exception as error:
        print("连接测试未通过：", error)
        print("请检查电脑和小车是否在同一网络；多网卡时可用 --local-ip 指定电脑的 WLAN IPv4。")
        return 1
    finally:
        with suppress(Exception):
            ep.close()


if __name__ == "__main__":
    raise SystemExit(main())
