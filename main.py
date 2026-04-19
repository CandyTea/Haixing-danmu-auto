import json
import random
import string
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
import tkinter as tk
from tkinter import scrolledtext, ttk
from urllib.parse import parse_qs, urlparse

import requests

APP_TITLE = "自动弹幕工具"
APP_SIZE = "980x900"
APP_MINSIZE = (900, 760)
DEFAULT_SEND_URL = "https://www.qlwshi.com/qiutx-news/app/chat/commonFilter/send"
DEFAULT_DEVICE_ID = ""
DEFAULT_ROOM_ID = ""
DEFAULT_CHATROOM_ID = ""
DEFAULT_USER_ID = ""
DEFAULT_NICKNAME = ""
DEFAULT_MESSAGE = ""
CONFIG_PATH = Path(__file__).with_name("config.json")


@dataclass
class AppConfig:
    url: str = DEFAULT_SEND_URL
    live_page_url: str = ""
    auth: str = ""
    cookie: str = ""
    sign: str = ""
    device_id: str = DEFAULT_DEVICE_ID
    user_id: str = DEFAULT_USER_ID
    nickname: str = DEFAULT_NICKNAME
    chatroom_id: str = DEFAULT_CHATROOM_ID
    room_id: str = DEFAULT_ROOM_ID
    message: str = DEFAULT_MESSAGE
    send_mode: str = "single"
    long_text: str = ""
    segment_length: int = 5
    loop_segments: bool = True
    use_random_suffix: bool = True
    use_invisible_chars: bool = False
    rate: float = 0.5


class ConfigManager:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> AppConfig:
        if not self.path.exists():
            return AppConfig()

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return AppConfig()

        config = AppConfig()
        for field_name in asdict(config):
            if field_name in data:
                setattr(config, field_name, data[field_name])

        config.segment_length = max(int(config.segment_length or 1), 1)
        config.rate = round(max(float(config.rate or 0.1), 0.1) * 10) / 10
        if config.send_mode not in {"single", "split"}:
            config.send_mode = "single"
        return config

    def save(self, config: AppConfig) -> None:
        self.path.write_text(
            json.dumps(asdict(config), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


class DanmakuApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry(APP_SIZE)
        self.root.minsize(*APP_MINSIZE)

        self.config_manager = ConfigManager(CONFIG_PATH)
        self.segment_index = 0
        self.is_running = False

        self.url = tk.StringVar(value=DEFAULT_SEND_URL)
        self.live_page_url = tk.StringVar()
        self.auth_token = tk.StringVar()
        self.cookie = tk.StringVar()
        self.sign = tk.StringVar()
        self.device_id = tk.StringVar(value=DEFAULT_DEVICE_ID)
        self.room_id = tk.StringVar(value=DEFAULT_ROOM_ID)
        self.chatroom_id = tk.StringVar(value=DEFAULT_CHATROOM_ID)
        self.user_id = tk.StringVar(value=DEFAULT_USER_ID)
        self.nickname = tk.StringVar(value=DEFAULT_NICKNAME)
        self.message = tk.StringVar(value=DEFAULT_MESSAGE)
        self.send_mode = tk.StringVar(value="single")
        self.segment_length = tk.IntVar(value=5)
        self.loop_segments = tk.BooleanVar(value=True)
        self.use_random_suffix = tk.BooleanVar(value=True)
        self.use_invisible_chars = tk.BooleanVar(value=False)
        self.rate = tk.DoubleVar(value=0.5)

        self.create_widgets()
        self.load_config()
        self.update_send_mode_ui()

    def create_widgets(self) -> None:
        main_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_pane.pack(fill="both", expand=True, padx=10, pady=10)

        left_panel = ttk.Frame(main_pane)
        right_panel = ttk.Frame(main_pane)
        main_pane.add(left_panel, weight=3)
        main_pane.add(right_panel, weight=2)

        self.build_auth_section(left_panel)
        self.build_room_section(left_panel)
        self.build_message_section(left_panel)
        self.build_control_section(left_panel)
        self.build_log_section(right_panel)

    def build_auth_section(self, parent: ttk.Frame) -> None:
        frame_auth = ttk.LabelFrame(parent, text="认证参数")
        frame_auth.pack(fill="x", pady=(0, 8))
        frame_auth.columnconfigure(1, weight=1)

        ttk.Label(frame_auth, text="发送接口:").grid(row=0, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(frame_auth, textvariable=self.url).grid(row=0, column=1, sticky="ew", padx=6, pady=3)

        ttk.Label(frame_auth, text="Authorization:").grid(row=1, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(frame_auth, textvariable=self.auth_token).grid(row=1, column=1, sticky="ew", padx=6, pady=3)

        ttk.Label(frame_auth, text="Cookie:").grid(row=2, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(frame_auth, textvariable=self.cookie).grid(row=2, column=1, sticky="ew", padx=6, pady=3)

        ttk.Label(frame_auth, text="Sign:").grid(row=3, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(frame_auth, textvariable=self.sign).grid(row=3, column=1, sticky="ew", padx=6, pady=3)

        ttk.Label(frame_auth, text="说明:").grid(row=4, column=0, sticky="nw", padx=6, pady=3)
        ttk.Label(
            frame_auth,
            text="开源版本不会附带任何真实凭证，请从浏览器请求中自行复制 Authorization、Cookie、Sign、设备ID。",
            wraplength=520,
            justify="left",
        ).grid(row=4, column=1, sticky="w", padx=6, pady=3)

    def build_room_section(self, parent: ttk.Frame) -> None:
        frame_room = ttk.LabelFrame(parent, text="直播间参数")
        frame_room.pack(fill="x", pady=(0, 8))
        frame_room.columnconfigure(1, weight=1)

        ttk.Label(frame_room, text="直播间网址:").grid(row=0, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(frame_room, textvariable=self.live_page_url).grid(row=0, column=1, sticky="ew", padx=6, pady=3)
        ttk.Button(frame_room, text="解析网址", command=self.parse_live_url).grid(row=0, column=2, sticky="w", padx=6, pady=3)

        ttk.Label(frame_room, text="直播间 ID:").grid(row=1, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(frame_room, textvariable=self.room_id, width=24).grid(row=1, column=1, sticky="w", padx=6, pady=3)

        ttk.Label(frame_room, text="聊天室 ID:").grid(row=2, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(frame_room, textvariable=self.chatroom_id, width=24).grid(row=2, column=1, sticky="w", padx=6, pady=3)

        ttk.Label(frame_room, text="用户 ID:").grid(row=3, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(frame_room, textvariable=self.user_id, width=24).grid(row=3, column=1, sticky="w", padx=6, pady=3)

        ttk.Label(frame_room, text="昵称:").grid(row=4, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(frame_room, textvariable=self.nickname, width=24).grid(row=4, column=1, sticky="w", padx=6, pady=3)

        ttk.Label(frame_room, text="设备 ID:").grid(row=5, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(frame_room, textvariable=self.device_id).grid(row=5, column=1, sticky="ew", padx=6, pady=3)

    def build_message_section(self, parent: ttk.Frame) -> None:
        frame_message = ttk.LabelFrame(parent, text="弹幕内容")
        frame_message.pack(fill="both", expand=True, pady=(0, 8))
        frame_message.columnconfigure(1, weight=1)
        frame_message.rowconfigure(2, weight=1)

        mode_bar = ttk.Frame(frame_message)
        mode_bar.grid(row=0, column=0, columnspan=3, sticky="w", padx=6, pady=(6, 2))
        ttk.Label(mode_bar, text="发送模式:").pack(side="left")
        ttk.Radiobutton(mode_bar, text="单条弹幕", value="single", variable=self.send_mode, command=self.update_send_mode_ui).pack(side="left", padx=(8, 4))
        ttk.Radiobutton(mode_bar, text="长文本分割", value="split", variable=self.send_mode, command=self.update_send_mode_ui).pack(side="left", padx=4)

        self.single_message_frame = ttk.Frame(frame_message)
        self.single_message_frame.grid(row=1, column=0, columnspan=3, sticky="ew", padx=6, pady=4)
        self.single_message_frame.columnconfigure(1, weight=1)
        ttk.Label(self.single_message_frame, text="单条弹幕:").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=2)
        ttk.Entry(self.single_message_frame, textvariable=self.message).grid(row=0, column=1, sticky="ew", pady=2)

        self.split_message_frame = ttk.Frame(frame_message)
        self.split_message_frame.grid(row=2, column=0, columnspan=3, sticky="nsew", padx=6, pady=4)
        self.split_message_frame.columnconfigure(1, weight=1)
        self.split_message_frame.rowconfigure(0, weight=1)

        ttk.Label(self.split_message_frame, text="长文本:").grid(row=0, column=0, sticky="nw", padx=(0, 6), pady=2)
        self.long_text_area = scrolledtext.ScrolledText(self.split_message_frame, height=8, wrap=tk.WORD)
        self.long_text_area.grid(row=0, column=1, columnspan=2, sticky="nsew", pady=2)

        ttk.Label(self.split_message_frame, text="每段字数:").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=4)
        ttk.Entry(self.split_message_frame, textvariable=self.segment_length, width=10).grid(row=1, column=1, sticky="w", pady=4)
        ttk.Checkbutton(self.split_message_frame, text="分段发送完后循环", variable=self.loop_segments).grid(row=1, column=2, sticky="w", padx=(8, 0), pady=4)

        option_bar = ttk.Frame(frame_message)
        option_bar.grid(row=3, column=0, columnspan=3, sticky="w", padx=6, pady=(6, 8))
        ttk.Checkbutton(option_bar, text="插入不可见字符", variable=self.use_invisible_chars).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(option_bar, text="追加随机数字后缀", variable=self.use_random_suffix).pack(side="left")

    def build_control_section(self, parent: ttk.Frame) -> None:
        frame_ctrl = ttk.LabelFrame(parent, text="发送控制")
        frame_ctrl.pack(fill="x")

        ttk.Label(frame_ctrl, text="发送频率 (每秒几条):").grid(row=0, column=0, padx=6, pady=6)
        self.rate_scale = ttk.Scale(
            frame_ctrl,
            from_=0.1,
            to=5,
            variable=self.rate,
            orient="horizontal",
            length=220,
            command=self.on_rate_change,
        )
        self.rate_scale.grid(row=0, column=1, padx=6, pady=6)
        ttk.Label(frame_ctrl, textvariable=self.rate, width=6).grid(row=0, column=2, padx=6, pady=6)

        btn_frame = ttk.Frame(frame_ctrl)
        btn_frame.grid(row=0, column=3, padx=10, pady=6)
        self.btn_start = ttk.Button(btn_frame, text="开始执行", command=self.start_task)
        self.btn_start.pack(side="left", padx=6)
        self.btn_stop = ttk.Button(btn_frame, text="停止", command=self.stop_task, state="disabled")
        self.btn_stop.pack(side="left", padx=6)

    def build_log_section(self, parent: ttk.Frame) -> None:
        frame_log = ttk.LabelFrame(parent, text="请求 / 返回日志")
        frame_log.pack(fill="both", expand=True)
        frame_log.columnconfigure(0, weight=1)
        frame_log.rowconfigure(0, weight=1)

        self.log_area = scrolledtext.ScrolledText(frame_log, wrap=tk.NONE, font=("Consolas", 10))
        self.log_area.grid(row=0, column=0, sticky="nsew")

        log_scroll_y = ttk.Scrollbar(frame_log, orient="vertical", command=self.log_area.yview)
        log_scroll_y.grid(row=0, column=1, sticky="ns")
        log_scroll_x = ttk.Scrollbar(frame_log, orient="horizontal", command=self.log_area.xview)
        log_scroll_x.grid(row=1, column=0, sticky="ew")
        self.log_area.configure(yscrollcommand=log_scroll_y.set, xscrollcommand=log_scroll_x.set)

    def on_rate_change(self, value: str) -> None:
        rounded = round(float(value) * 10) / 10
        self.rate.set(rounded)

    def update_send_mode_ui(self) -> None:
        if self.send_mode.get() == "single":
            self.single_message_frame.grid()
            self.split_message_frame.grid_remove()
        else:
            self.single_message_frame.grid_remove()
            self.split_message_frame.grid()

    def parse_live_url(self) -> None:
        live_url = self.live_page_url.get().strip()
        if not live_url:
            self.log("请先输入直播间网址")
            return

        try:
            parsed = urlparse(live_url)
            query = parse_qs(parsed.query)
            room_id = query.get("roomId", [""])[0] or query.get("room_id", [""])[0]
            chatroom_id = query.get("chatRoomId", [""])[0] or query.get("chatroom_id", [""])[0]

            if not room_id:
                path = parsed.path.strip("/")
                if path.isdigit():
                    room_id = path
                elif path.startswith("live/"):
                    room_id = path.split("/", maxsplit=1)[1]

            if room_id:
                self.room_id.set(room_id)
            if chatroom_id:
                self.chatroom_id.set(chatroom_id)

            if room_id or chatroom_id:
                self.log(f"已从网址解析参数 | 房间ID: {room_id or '未找到'} | 聊天室ID: {chatroom_id or '未找到'}")
                if room_id and not chatroom_id:
                    self.log("当前网址只识别出房间ID；若发送失败，请手动补充聊天室 ID")
                self.save_config()
            else:
                self.log("网址里没有识别到房间参数，请手动补充聊天室 ID")
        except Exception as exc:
            self.log(f"解析网址失败: {exc}")

    @staticmethod
    def split_text_segments(text: str, segment_length: int) -> list[str]:
        cleaned = text.replace("\r", "").replace("\n", "")
        if not cleaned:
            return []
        return [cleaned[i:i + segment_length] for i in range(0, len(cleaned), segment_length)]

    def get_next_message(self):
        if self.send_mode.get() == "split":
            long_text = self.long_text_area.get("1.0", tk.END).strip()
            if not long_text:
                return None, None, None

            segment_length = max(self.segment_length.get(), 1)
            segments = self.split_text_segments(long_text, segment_length)
            if not segments:
                return None, None, None

            if self.segment_index >= len(segments):
                if self.loop_segments.get():
                    self.segment_index = 0
                else:
                    self.log("长文本已经全部发送完成")
                    self.stop_task()
                    return None, None, None

            current_index = self.segment_index
            self.segment_index += 1
            return segments[current_index], current_index + 1, len(segments)

        message = self.message.get().strip()
        return message, None, None

    @staticmethod
    def obfuscate_text(text: str) -> str:
        invisibles = ["\u200b", "\u200c", "\u200d", "\ufeff"]
        new_text = ""
        for char in text:
            new_text += char
            if random.random() > 0.5:
                for _ in range(random.randint(1, 3)):
                    new_text += random.choice(invisibles)
        return new_text

    def log(self, message: str) -> None:
        now = time.strftime("%H:%M:%S")
        self.log_area.insert(tk.END, f"[{now}] {message}\n")
        self.log_area.see(tk.END)

    def log_json(self, title: str, data) -> None:
        self.log(f"{title}:")
        pretty = json.dumps(data, ensure_ascii=False, indent=2)
        self.log_area.insert(tk.END, pretty + "\n")
        self.log_area.see(tk.END)

    def collect_config(self) -> AppConfig:
        return AppConfig(
            url=self.url.get().strip(),
            live_page_url=self.live_page_url.get().strip(),
            auth=self.auth_token.get().strip(),
            cookie=self.cookie.get().strip(),
            sign=self.sign.get().strip(),
            device_id=self.device_id.get().strip(),
            user_id=self.user_id.get().strip(),
            nickname=self.nickname.get().strip(),
            chatroom_id=self.chatroom_id.get().strip(),
            room_id=self.room_id.get().strip(),
            message=self.message.get(),
            send_mode=self.send_mode.get(),
            long_text=self.long_text_area.get("1.0", tk.END).strip(),
            segment_length=max(self.segment_length.get(), 1),
            loop_segments=self.loop_segments.get(),
            use_random_suffix=self.use_random_suffix.get(),
            use_invisible_chars=self.use_invisible_chars.get(),
            rate=round(max(self.rate.get(), 0.1) * 10) / 10,
        )

    def apply_config(self, config: AppConfig) -> None:
        self.url.set(config.url)
        self.live_page_url.set(config.live_page_url)
        self.auth_token.set(config.auth)
        self.cookie.set(config.cookie)
        self.sign.set(config.sign)
        self.device_id.set(config.device_id)
        self.chatroom_id.set(config.chatroom_id)
        self.room_id.set(config.room_id)
        self.user_id.set(config.user_id)
        self.nickname.set(config.nickname)
        self.message.set(config.message)
        self.send_mode.set(config.send_mode)
        self.long_text_area.delete("1.0", tk.END)
        self.long_text_area.insert("1.0", config.long_text)
        self.segment_length.set(config.segment_length)
        self.loop_segments.set(config.loop_segments)
        self.use_random_suffix.set(config.use_random_suffix)
        self.use_invisible_chars.set(config.use_invisible_chars)
        self.rate.set(config.rate)

    def save_config(self) -> None:
        self.config_manager.save(self.collect_config())

    def load_config(self) -> None:
        self.apply_config(self.config_manager.load())

    def start_task(self) -> None:
        self.segment_index = 0
        self.save_config()
        self.is_running = True
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        threading.Thread(target=self.worker, daemon=True).start()

    def stop_task(self) -> None:
        self.is_running = False
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")

    def build_headers(self, timestamp: str) -> dict[str, str]:
        return {
            "authorization": self.auth_token.get().strip(),
            "cookie": self.cookie.get().strip(),
            "sign": self.sign.get().strip(),
            "deviceid": self.device_id.get().strip(),
            "client-type": "web",
            "platform": "dq",
            "version": "1.8.9",
            "channel": "F0",
            "channelapp": "F0",
            "origin": "https://www.qlwshi.com",
            "referer": f"https://www.qlwshi.com/live/{self.room_id.get().strip()}",
            "content-type": "application/json; charset=UTF-8",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
            "r": "".join(random.choices(string.ascii_letters + string.digits, k=36)),
            "t": timestamp,
            "x-user-header": json.dumps({"uid": self.user_id.get().strip()}, ensure_ascii=False),
        }

    def build_payload(self, content: str, room_id: int, user_id: int) -> dict:
        return {
            "chatRoomId": self.chatroom_id.get().strip(),
            "clientSendContent": {
                "content": content,
                "type": 0,
                "identity": 0,
                "nickname": self.nickname.get().strip(),
            },
            "enumItem": "LIVE_CHAT_ROOM",
            "liveRoomId": room_id,
            "test": True,
            "type": 2,
            "userId": user_id,
        }

    def worker(self) -> None:
        count = 0
        while self.is_running:
            base_message, current_segment, total_segments = self.get_next_message()
            if not base_message:
                self.log("当前发送模式下没有可发送内容")
                self.stop_task()
                break

            msg_content = base_message
            if self.use_invisible_chars.get():
                msg_content = self.obfuscate_text(msg_content)
            if self.use_random_suffix.get():
                msg_content += f" {random.randint(10, 9999)}"

            try:
                room_id = int(self.room_id.get().strip())
                user_id = int(self.user_id.get().strip())
            except ValueError:
                self.log("房间 ID 或用户 ID 不是有效数字，请检查")
                self.stop_task()
                return

            timestamp = str(int(time.time() * 1000))
            headers = self.build_headers(timestamp)
            payload = self.build_payload(msg_content, room_id, user_id)

            try:
                response = requests.post(
                    f"{self.url.get().strip()}?t={timestamp}",
                    headers=headers,
                    json=payload,
                    timeout=5,
                )
                data = response.json()
                desc = data.get("data", {}).get("desc") or data.get("msg") or "未知状态"

                if current_segment is not None and total_segments is not None:
                    message_info = f"分段: {current_segment}/{total_segments} | 原文: {base_message}"
                else:
                    message_info = f"单条: {base_message}"

                self.log(f"HTTP状态: {response.status_code} | 返回描述: {desc} | {message_info}")
                self.log_json("请求头", headers)
                self.log_json("请求体", payload)
                self.log_json("完整响应", data)
                self.log("-" * 90)

                if response.status_code == 200 and data.get("code") == 200 and data.get("data", {}).get("success") is True:
                    count += 1
                    self.log(f"第{count}条 已通过服务端校验")
                else:
                    self.log("本次发送未通过服务端校验")
            except Exception as exc:
                self.log(f"异常: {exc}")

            time.sleep(1.0 / max(self.rate.get(), 0.1))


def main() -> None:
    root = tk.Tk()
    DanmakuApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
