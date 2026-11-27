"""Local, hold-to-drive control window for RoboMaster EP.

Uses the installed DJI SDK. Direction signs follow DJI's 03_speed.py example.
Opening the window never connects to a robot or sends a motion command.
"""
import ipaddress
import logging
from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk


ZERO = (0.0, 0.0, 0.0)
DIRECTIONS = {
    "forward": (1, 0, 0), "back": (-1, 0, 0),
    "left": (0, -1, 0), "right": (0, 1, 0),
    "turn_left": (0, 0, -1), "turn_right": (0, 0, 1),
}
NAMES = {"forward": "前进", "back": "后退", "left": "左移",
         "right": "右移", "turn_left": "左转", "turn_right": "右转"}


class MotionIntent:
    """An expiring command; only the GUI thread can renew a held button."""
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._velocity = ZERO
        self._expires = 0.0

    def press(self, direction, speed, turn_speed):
        dx, dy, dz = DIRECTIONS[direction]
        speed = max(0.05, min(0.40, float(speed)))
        turn_speed = max(10.0, min(60.0, float(turn_speed)))
        with self._lock:
            self._velocity = (dx * speed, dy * speed, dz * turn_speed)
            self._expires = self._clock() + 0.25

    def renew(self):
        with self._lock:
            if self._velocity != ZERO:
                self._expires = self._clock() + 0.25

    def stop(self):
        with self._lock:
            self._velocity = ZERO
            self._expires = 0.0

    def velocity(self):
        with self._lock:
            return self._velocity if self._clock() < self._expires else ZERO


class RobotController:
    """Serializes SDK calls in one worker; GUI access stays on the Tk thread."""
    def __init__(self, robot_factory=None):
        self.intent = MotionIntent()
        self.events = queue.Queue()
        self.commands = queue.Queue()
        self.shutdown = threading.Event()
        self.done = threading.Event()
        self.robot_factory = robot_factory
        self._robot = None
        self._last_sent = None
        self._last_probe = 0.0
        self.thread = threading.Thread(target=self._run, daemon=True,
                                       name="EP-control-worker")
        self.thread.start()

    def connect(self, mode, serial="", local_ip=""):
        self.intent.stop()
        self.commands.put(("connect", (mode, serial, local_ip)))

    def disconnect(self):
        self.intent.stop()
        self.commands.put(("disconnect", None))

    def quit(self):
        self.intent.stop()
        self.shutdown.set()
        self.commands.put(("quit", None))

    def _close_robot(self):
        self.intent.stop()
        device, self._robot = self._robot, None
        self._last_sent = None
        if device is not None:
            try:
                device.chassis.drive_speed(x=0, y=0, z=0)
                timer = getattr(device.chassis, "_auto_timer", None)
                if timer is not None:
                    timer.cancel()
            except Exception:
                logging.exception("Stop command during disconnect failed")
            try:
                device.close()
            except Exception:
                logging.exception("Closing SDK connection failed")

    def _connect_robot(self, mode, serial, local_ip):
        self._close_robot()
        device = None
        try:
            if self.robot_factory is None:
                from robomaster import config, robot
                config.LOCAL_IP_STR = local_ip or None
                device = robot.Robot()
            else:
                device = self.robot_factory()
            if not device.initialize(conn_type=mode, proto_type="udp", sn=serial or None):
                raise RuntimeError("未能建立连接，请确认电脑与小车的联网方式。")
            self._robot = device
            version = device.get_version()
            if not version:
                raise RuntimeError("没有收到小车的版本信息。")
            if self.shutdown.is_set():
                self._close_robot()
                return
            self._last_probe = time.monotonic()
            self.events.put(("connected", str(version)))
        except Exception as error:
            logging.exception("Connection failed")
            if self._robot is None and device is not None:
                self._robot = device
            self._close_robot()
            if not self.shutdown.is_set():
                self.events.put(("error", str(error)))

    def _run(self):
        try:
            while not self.shutdown.is_set():
                try:
                    command, payload = self.commands.get(timeout=0.06)
                except queue.Empty:
                    command, payload = None, None
                if self.shutdown.is_set() or command == "quit":
                    break
                if command == "connect":
                    self._connect_robot(*payload)
                elif command == "disconnect":
                    self._close_robot()
                    self.events.put(("disconnected", "已断开连接"))
                if self._robot is None or self.shutdown.is_set():
                    continue
                try:
                    if time.monotonic() - self._last_probe > 1.0:
                        if not self._robot.get_version():
                            raise RuntimeError("与小车的通信已中断，已尝试发送停止指令。")
                        self._last_probe = time.monotonic()
                    velocity = self.intent.velocity()
                    if velocity != ZERO or self._last_sent != ZERO:
                        # This SDK's speed message is PUSH/no-ACK. Its public
                        # wrapper returns False even after sending successfully.
                        # Query messages above provide the connection health check.
                        self._robot.chassis.drive_speed(
                            x=velocity[0], y=velocity[1], z=velocity[2], timeout=0.4)
                        self._last_sent = velocity
                        if velocity == ZERO:
                            self.events.put(("stopped", "已发送停止指令"))
                except Exception as error:
                    logging.exception("Robot communication failed")
                    self._close_robot()
                    self.events.put(("error", str(error)))
        finally:
            self._close_robot()
            self.done.set()


class ControlWindow:
    def __init__(self, root, controller=None):
        self.root = root
        self.controller = controller or RobotController()
        self.connected = False
        self.busy = False
        self.closing = False
        self.held = None
        self.motion_buttons = []
        self.mode = tk.StringVar(value="组网 STA（与小车连接同一 Wi-Fi）")
        self.local_ip = tk.StringVar()
        self.serial = tk.StringVar()
        self.status = tk.StringVar(value="未连接 · 先完成小车配网，再点击连接")
        self.motion = tk.StringVar(value="未连接 · 运动按钮暂不可用")
        self.speed = tk.DoubleVar(value=0.15)
        self.turn_speed = tk.DoubleVar(value=20)
        self.speed_text = tk.StringVar(value="0.15 m/s")
        self.turn_text = tk.StringVar(value="20 °/s")
        self._build()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.bind_all("<ButtonRelease-1>", self.release, add="+")
        root.bind_all("<Escape>", self.release, add="+")
        root.bind_all("<space>", self._space_stop, add="+")
        root.bind("<FocusOut>", self._focus_lost, add="+")
        root.after(60, self.poll)

    def _build(self):
        root = self.root
        root.title("EP 小车运动控制")
        root.geometry("720x750")
        root.minsize(650, 710)
        root.configure(bg="#edf2f7")
        root.option_add("*Font", ("Microsoft YaHei UI", 10))
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background="#edf2f7")
        style.configure("TLabel", background="#edf2f7", foreground="#243349")
        style.configure("TButton", padding=(15, 8))
        style.configure("TCombobox", padding=6)
        header = tk.Frame(root, bg="#15334e", padx=26, pady=18)
        header.pack(fill="x")
        tk.Label(header, text="EP 小车运动控制", font=("Microsoft YaHei UI", 22, "bold"),
                 bg="#15334e", fg="white").pack(anchor="w")
        tk.Label(header, text="按住方向按钮运动 · 松开停止 · 空格 / Esc 停止",
                 bg="#15334e", fg="#c8deec").pack(anchor="w", pady=(6, 0))
        content = ttk.Frame(root, padding=(24, 15))
        content.pack(fill="both", expand=True)
        connection = ttk.Frame(content)
        connection.pack(fill="x")
        ttk.Label(connection, text="连接方式").grid(row=0, column=0, sticky="w", pady=5)
        self.mode_box = ttk.Combobox(connection, textvariable=self.mode, state="readonly",
                                    values=("组网 STA（与小车连接同一 Wi-Fi）",
                                            "直连 AP（电脑连接小车 Wi-Fi）"), width=35)
        self.mode_box.grid(row=0, column=1, padx=10, sticky="ew")
        self.connect_button = ttk.Button(connection, text="连接小车", command=self.toggle_connection)
        self.connect_button.grid(row=0, column=2, sticky="e")
        connection.columnconfigure(1, weight=1)
        self.state_label = tk.Label(content, textvariable=self.status, anchor="w",
                                    bg="#e2eaf1", fg="#334b63", padx=12, pady=9,
                                    wraplength=620, justify="left")
        self.state_label.pack(fill="x", pady=(10, 7))
        details = ttk.Frame(content)
        details.pack(fill="x", pady=(0, 6))
        ttk.Label(details, text="电脑 Wi-Fi IP（可留空）").grid(row=0, column=0, sticky="w")
        self.ip_entry = ttk.Entry(details, textvariable=self.local_ip, width=17)
        self.ip_entry.grid(row=0, column=1, padx=(7, 15))
        ttk.Label(details, text="小车 SN（可留空）").grid(row=0, column=2)
        self.sn_entry = ttk.Entry(details, textvariable=self.serial, width=18)
        self.sn_entry.grid(row=0, column=3, padx=(7, 0))
        ttk.Separator(content).pack(fill="x", pady=10)
        grid = ttk.Frame(content)
        grid.pack(fill="both", expand=True)
        for index in range(3):
            grid.columnconfigure(index, weight=1, uniform="motion")
            grid.rowconfigure(index, weight=1, uniform="motion")
        for label, direction, row, column in (
                ("↶  左转", "turn_left", 0, 0), ("↑  前进", "forward", 0, 1),
                ("右转  ↷", "turn_right", 0, 2), ("←  左移", "left", 1, 0),
                ("右移  →", "right", 1, 2), ("↓  后退", "back", 2, 1)):
            button = tk.Button(grid, text=label, state="disabled", font=("Microsoft YaHei UI", 15, "bold"),
                               bg="#dce9f3", fg="#173d5c", disabledforeground="#8293a2",
                               activebackground="#b9d7ec", relief="flat", cursor="hand2")
            button.grid(row=row, column=column, padx=5, pady=5, sticky="nsew")
            button.bind("<ButtonPress-1>", lambda event, d=direction: self.press(d))
            button.bind("<Leave>", self.release)
            self.motion_buttons.append(button)
        tk.Button(grid, text="■  停止", command=self.release, font=("Microsoft YaHei UI", 17, "bold"),
                  bg="#bf3241", fg="white", activebackground="#9c2431", activeforeground="white",
                  relief="flat", cursor="hand2").grid(row=1, column=1, padx=5, pady=5, sticky="nsew")
        ttk.Label(grid, text="以车头朝向为准", anchor="center").grid(row=2, column=0, sticky="nsew")
        ttk.Label(grid, text="按住才运动", anchor="center").grid(row=2, column=2, sticky="nsew")
        tk.Label(content, textvariable=self.motion, bg="#edf2f7", fg="#1b5c83",
                 font=("Microsoft YaHei UI", 12, "bold")).pack(pady=(8, 4))
        speeds = ttk.Frame(content)
        speeds.pack(fill="x")
        speeds.columnconfigure(1, weight=1)
        ttk.Label(speeds, text="平移速度").grid(row=0, column=0, sticky="w")
        ttk.Scale(speeds, from_=0.05, to=0.40, variable=self.speed,
                  command=self.speed_changed).grid(row=0, column=1, sticky="ew", padx=12)
        ttk.Label(speeds, textvariable=self.speed_text, width=10).grid(row=0, column=2)
        ttk.Label(speeds, text="转向速度").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Scale(speeds, from_=10, to=60, variable=self.turn_speed,
                  command=self.speed_changed).grid(row=1, column=1, sticky="ew", padx=12)
        ttk.Label(speeds, textvariable=self.turn_text, width=10).grid(row=1, column=2)
        ttk.Label(content, text="尚未配网？先运行同目录中的 01_扫码配网.cmd。",
                  foreground="#60758a").pack(anchor="w", pady=(8, 0))

    def speed_changed(self, _value=None):
        self.speed_text.set("{:.2f} m/s".format(self.speed.get()))
        self.turn_text.set("{:.0f} °/s".format(self.turn_speed.get()))

    def _set_connection_state(self, connected, busy=False):
        self.connected, self.busy = connected, busy
        for button in self.motion_buttons:
            button.configure(state="normal" if connected and not busy else "disabled")
        self.mode_box.configure(state="disabled" if connected or busy else "readonly")
        for entry in (self.ip_entry, self.sn_entry):
            entry.configure(state="disabled" if connected or busy else "normal")
        self.connect_button.configure(state="disabled" if busy else "normal",
                                      text="断开连接" if connected else "连接小车")

    def toggle_connection(self):
        self.release()
        if self.closing or self.busy:
            return
        if self.connected:
            self.status.set("正在停止并断开连接……")
            self._set_connection_state(False, True)
            self.controller.disconnect()
            return
        address = self.local_ip.get().strip()
        if address:
            try:
                ipaddress.IPv4Address(address)
            except ValueError:
                self.status.set("电脑 Wi-Fi IP 格式不正确；也可以留空自动选择。")
                return
        self._set_connection_state(False, True)
        self.status.set("正在连接小车，请稍候……")
        mode = "sta" if self.mode.get().startswith("组网") else "ap"
        self.controller.connect(mode, self.serial.get().strip(), address)

    def press(self, direction):
        if not self.connected or self.busy or self.closing:
            return
        self.held = direction
        self.controller.intent.press(direction, self.speed.get(), self.turn_speed.get())
        self.motion.set("正在" + NAMES[direction] + " · 松开按钮停止")

    def release(self, _event=None):
        self.held = None
        self.controller.intent.stop()
        self.motion.set("停止请求已提交" if self.connected else "未连接 · 运动按钮暂不可用")

    def _space_stop(self, event):
        if not isinstance(event.widget, (tk.Entry, ttk.Entry, ttk.Combobox)):
            self.release()
            return "break"

    def _focus_lost(self, _event=None):
        self.root.after_idle(self._check_focus)

    def _check_focus(self):
        # A ttk combobox popdown is a Tcl-created widget, so focus_displayof()
        # can raise KeyError when Tkinter tries to map it to a Python widget.
        focus_path = self.root.tk.call("focus", "-displayof", self.root._w)
        if not self.closing and not focus_path:
            self.release()

    def poll(self):
        if self.closing:
            if self.controller.done.is_set():
                self.root.destroy()
            else:
                self.root.after(60, self.poll)
            return
        while True:
            try:
                event, value = self.controller.events.get_nowait()
            except queue.Empty:
                break
            if event == "stopped":
                if self.connected and not self.held:
                    self.motion.set(value)
                continue
            self.release()
            if event == "connected":
                self._set_connection_state(True)
                self.status.set("已连接 · 固件版本 " + value)
                self.state_label.configure(bg="#dff0e7", fg="#226345")
                self.motion.set("尚未发送运动指令 · 可以按住方向按钮")
            else:
                self._set_connection_state(False)
                self.status.set(("连接未完成：" if event == "error" else "") + value)
                self.state_label.configure(bg="#f6e6df" if event == "error" else "#e2eaf1", fg="#684437")
        if self.held and self.connected:
            self.controller.intent.renew()
        self.root.after(60, self.poll)

    def on_close(self):
        if self.closing:
            return
        self.release()
        self.closing = True
        self._set_connection_state(False, True)
        self.status.set("正在发送停止指令并退出……")
        self.controller.quit()


def main():
    logs = Path(r"D:\RoboMaster\logs")
    logs.mkdir(parents=True, exist_ok=True)
    stream = open(logs / "motion-control.log", "a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream
    logging.basicConfig(filename=str(logs / "motion-control.log"), level=logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s")
    root = tk.Tk()
    ControlWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
