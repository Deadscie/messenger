from PIL import Image, ImageTk
import io
import base64
import tkinter as tk
import tkinter.ttk as ttk
from tkinter import filedialog
from tkinter import scrolledtext, messagebox
import socket
import threading
import json
import base64


HOST = "127.0.0.1"
PORT = 5555


class MessengerUI:
    def __init__(self, root):
        self.current_chat = "global"   # текущий чат
        self.chat_history = {}         # {user: [messages]}
        self.auth_win = None 
        self.unread_counts = {}
        self.unread_tabs = set()
        self.private_tabs = {}
        self.active_dm = None
        self.root = root
        self.root.title("Mini Messenger")
        self.root.geometry("1000x600")

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        self.username = ""

        self.build_menu()
        self.build_ui()
        self.ask_name()



        


    # ---------- CONNECT ----------
    def connect(self,username):
        try:
            self.socket.connect((HOST, PORT))
            threading.Thread(target=self.receive, daemon=True).start()
        except Exception as e:
                    pass

        self.username = username

    # ---------- NAME ----------
    def ask_name(self):
            self.auth_win = tk.Toplevel(self.root)
            self.auth_win.title("Вход")
            self.auth_win.geometry("300x200")
            self.temp_username = ''

            tk.Label(self.auth_win, text="Логин").pack(pady=5)
            u_entry = tk.Entry(self.auth_win)
            u_entry.pack()

            tk.Label(self.auth_win, text="Пароль").pack(pady=5)
            p_entry = tk.Entry(self.auth_win, show="*")
            p_entry.pack()

            def send_auth(mode):
                user = u_entry.get().strip()
                password = p_entry.get().strip()
                if not user or not password:
                    messagebox.showwarning("Внимание", "Заполните все поля")
                    return
                
                # Временно сохраняем введенное имя, чтобы использовать его после успеха
                self.temp_username = user 
                self.connect(user)
                
                data = {"type": mode, "user": user, "pass": password}
                self.socket.send((json.dumps(data) + "\n").encode("utf-8"))

            tk.Button(self.auth_win, text="Войти", command=lambda: send_auth("login")).pack(pady=5)
            tk.Button(self.auth_win, text="Регистрация", command=lambda: send_auth("register")).pack()



    # ---------- SEND ----------
    def send(self):
        text = self.msg_entry.get().strip()
        if not text:
            return

        current_tab = self.current_chat

        # 0 = общий чат
        if current_tab == "global":
            data = {
                "type": "message",
                "subtype": "chat",
                "text": text
            }
        else:
            print(list(self.private_tabs.keys()))
            username = current_tab

            data = {
                "type": "message",
                "subtype": "dm",
                "to": username,
                "text": text
            }

        self.socket.send((json.dumps(data) + "\n").encode("utf-8"))
        self.msg_entry.delete(0, tk.END)

    # ---------- RECEIVE ----------
    def receive(self):
        buffer = ""

        while True:
            data = self.socket.recv(8192).decode("utf-8")
            if not data:
                break

            buffer += data

            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)

                msg = json.loads(line)
                self.root.after(0, self.show, msg)
    def update_users(self, users):
        self.all_users = users
        self.users_list.delete(0, tk.END)
        # пользователи
        for i, user in enumerate(users):
            name = user["name"]
            online = user["online"]

            count = self.unread_counts.get(name, 0)

            display = name

            if count > 0:
                display = f"* {name} ({count})"

            self.users_list.insert(tk.END, display)

            # 🎨 цвет
            if online:
                self.users_list.itemconfig(i, fg="#00ff41")
            else:
                self.users_list.itemconfig(i, fg="#555555")
    # ---------- SHOW ----------
    def show(self, msg):
        print(msg)
        msg_type = msg.get("type")

        if msg_type == "image":
            if msg.get("from") == self.username:
                chat_user = msg.get("to")
                text = f"Вы:\n"
            else:
                chat_user = msg.get("from")
                text = f"{chat_user}:\n"
                self.notify_user(chat_user)
            img_data = base64.b64decode(msg.get("image"))
            image = Image.open(io.BytesIO(img_data))

            image.thumbnail((200, 200))  # уменьшаем

            photo = ImageTk.PhotoImage(image)
            chat = self.current_chat if self.current_chat != "global" else "global"     
            if self.current_chat == chat_user:
                self.chat_box.config(state="normal")
                self.chat_box.insert(tk.END, text)
                self.chat_box.image_create(tk.END, image=photo)
                self.chat_box.insert(tk.END, "\n")
                self.chat_box.config(state="disabled")
                self.chat_box.yview(tk.END)



            if chat not in self.chat_history:
                self.chat_history[chat] = []

            self.chat_history[chat].append(("image", img_data))
            self.chat_box.config(state="normal")


            # ❗ важно сохранить ссылку
            if not hasattr(self, "images"):
                self.images = []
            self.images.append(photo)

            return
        # -------- USERS --------
        if msg_type == "users":
            self.update_users(msg.get("users", []))
            return

        # -------- AUTH --------
        if msg_type == "auth_res":
            if msg.get("status") == "success":
                if msg.get("subtype") == "login":
                    self.username = self.temp_username
                    self.root.title(f"Mini Messenger - {self.username}")
                    self.auth_win.destroy()
            else:
                messagebox.showerror("Ошибка", msg.get("info"))
            return

        subtype = msg.get("subtype")

        # -------- DM --------
        if subtype == "dm" and msg_type != "image":
            if msg.get("from") == self.username:
                chat_user = msg.get("to")
                text = f"Вы: {msg.get('text')}\n"
            else:
                chat_user = msg.get("from")
                text = f"{chat_user}: {msg.get('text')}\n"
                self.notify_user(chat_user)

            # сохраняем историю
            if chat_user not in self.chat_history:
                self.chat_history[chat_user] = []

            self.chat_history[chat_user].append(text)

            # если открыт этот чат — показываем
            if self.current_chat == chat_user:
                self.chat_box.config(state="normal")
                self.chat_box.insert(tk.END, text)
                self.chat_box.config(state="disabled")
                self.chat_box.yview(tk.END)

            return

        # -------- ОБЩИЙ ЧАТ --------
        if subtype == "chat":
            text = f"{msg.get('user')}: {msg.get('text')}\n"

            if "global" not in self.chat_history:
                self.chat_history["global"] = []
        
            self.chat_history["global"].append(text)
            if self.current_chat == "global":
                self.chat_box.config(state="normal")
                self.chat_box.insert(tk.END, text)
                self.chat_box.config(state="disabled")
                self.chat_box.yview(tk.END)

            return

        # -------- SYSTEM --------
        if subtype == "system":
            text = f"[SYSTEM] {msg.get('text')}\n"

            self.chat_box.config(state="normal")
            self.chat_box.insert(tk.END, text)
            self.chat_box.config(state="disabled")
            self.chat_box.yview(tk.END)
    '''def notify_global(self):
        if self.current_chat != "global":
            self.global_unread += 1

            # обновляем первый элемент списка (Общий чат)
            self.users_list.delete(0)
            self.users_list.insert(0, f"* Общий чат ({self.global_unread})")'''
    def notify_user(self, username):
        if self.current_chat != username:
            self.unread_counts[username] = self.unread_counts.get(username, 0) + 1
            self.update_users(self.all_users)


    def on_tab_change(self, event):
        index = self.notebook.index(self.notebook.select())

        # общий чат
        if index == 0:
            self.global_unread = 0
            self.notebook.tab(0, text="Общий чат")
            return

        username = list(self.private_tabs.keys())[index - 1]

        if username in self.unread_counts:
            self.unread_counts[username] = 0
            self.notebook.tab(index, text=username)
            self.chat_name = tk.Label(self.notebook,text=username)
            self.chat_name.pack(padx=10, pady=10)

    def create_private_tab(self, username):
        if username in self.private_tabs:
            return self.private_tabs[username]

        frame = tk.Frame(self.notebook)

        chat_box = scrolledtext.ScrolledText(frame, state="disabled")
        chat_box.pack(fill=tk.BOTH, expand=1, padx=5, pady=5)

        self.notebook.add(frame, text=username)

        self.private_tabs[username] = chat_box

        return chat_box
    
    def send_image(self):
        print("SI")
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg")])
        if not path:
            print("Return")
            return

        with open(path, "rb") as f:
            img_data = base64.b64encode(f.read()).decode("utf-8")

        data = {
            "type": "image",
            "to": self.current_chat if self.current_chat != "global" else None,
            "subtype": "dm" if self.current_chat != "global" else "chat",
            "image": img_data
        }
        print(data)
        self.socket.send((json.dumps(data) + "\n").encode("utf-8"))

    def open_dm(self, event):
        selection = self.users_list.curselection()
        if not selection:
            return

        raw = self.users_list.get(selection[0])

        # если есть [ON] или значки — убираем
        username = raw.split(" ", 1)[-1]
        username = username.split(" ", 1)[0]

        if username == self.username or username == self.current_chat:
            return
        self.unread_counts[username] = 0
        self.update_users(self.all_users)
        self.current_chat = username
        self.chat_name.config(text=username)
        # очистка окна
        self.chat_box.config(state="normal")
        self.chat_box.delete(1.0, tk.END)

        self.chat_box.config(state="disabled")

        # запрос истории с сервера
        self.socket.send((json.dumps({
            "type": "get_history",
            "with": username
        }) + "\n").encode("utf-8"))

    # ---------- MENU ----------
    def build_menu(self):
        menu = tk.Menu(self.root, bg="#0b0f0b", fg="#00ff9c", tearoff=0)

        file_menu = tk.Menu(menu, tearoff=0, bg="#0b0f0b", fg="#00ff9c")
        file_menu.add_command(label="ВЫХОД", command=self.exit_app)

        menu.add_cascade(label="ФАЙЛ", menu=file_menu)

        self.root.config(menu=menu)

    # ---------- MAIN UI ----------
    def build_ui(self):
        BG = "#1b1f1b"
        PANEL = "#232823"
        BORDER = "#3a423a"
        TEXT = "#cfd6cf"
        SELECT = "#2f3a2f"

        main = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg=BG, sashwidth=4)
        main.pack(fill=tk.BOTH, expand=1, padx=8, pady=8)

        # ---------- LEFT PANEL ----------
        left_wrap = tk.Frame(main, bg=PANEL, highlightbackground=BORDER, highlightthickness=2)
        main.add(left_wrap)
        main.paneconfig(left_wrap, minsize=320)  

        self.left_frame = tk.Frame(left_wrap, bg=PANEL)
        self.left_frame.pack(fill=tk.BOTH, expand=1, padx=8, pady=8)

        tk.Label(
            self.left_frame,
            text="Контакты",
            bg=PANEL,
            fg=TEXT,
            font=("Arial", 12, "bold")
        ).pack(anchor="w", padx=8, pady=(5, 10))

        btn_global = tk.Button(
            self.left_frame,
            text="Общий канал",
            bg="#2e352e",
            fg=TEXT,
            relief=tk.FLAT,
            height=2,
            command=self.open_global
        )
        btn_global.pack(padx=8, pady=(0, 10), fill=tk.X)

        # ----- рамка под список -----
        list_wrap = tk.Frame(
            self.left_frame,
            bg=BG,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        list_wrap.pack(fill=tk.BOTH, expand=1, padx=5, pady=5)

        # ----- LISTBOX (крупный) -----
        self.users_list = tk.Listbox(
            list_wrap,
            bg=BG,
            fg=TEXT,
            selectbackground=SELECT,
            selectforeground=TEXT,
            highlightthickness=0,
            relief=tk.FLAT,
            font=("Arial", 12),
            activestyle="none"
        )
        self.users_list.pack(fill=tk.BOTH, expand=1, padx=10, pady=10)
        self.users_list.bind("<Double-Button-1>", self.open_dm)

        # ---------- RIGHT PANEL ----------
        right_wrap = tk.Frame(main, bg=PANEL, highlightbackground=BORDER, highlightthickness=2)
        main.add(right_wrap)

        self.right_frame = tk.Frame(right_wrap, bg=PANEL)
        self.right_frame.pack(fill=tk.BOTH, expand=1, padx=8, pady=8)

        self.chat_name = tk.Label(
            self.right_frame,
            text="Канал",
            bg=PANEL,
            fg=TEXT,
            font=("Arial", 12, "bold")
        )
        self.chat_name.pack(anchor="w", padx=5, pady=5)

        # ----- рамка чата -----
        chat_wrap = tk.Frame(
            self.right_frame,
            bg=BG,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        chat_wrap.pack(fill=tk.BOTH, expand=1, padx=5, pady=5)

        self.chat_box = scrolledtext.ScrolledText(
            chat_wrap,
            state="disabled",
            wrap=tk.WORD,
            bg=BG,
            fg=TEXT,
            insertbackground=TEXT,
            borderwidth=0,
            font=("Arial", 11)
        )
        self.chat_box.pack(fill=tk.BOTH, expand=1)

        # ---------- INPUT ----------
        bottom = tk.Frame(self.right_frame, bg=PANEL)
        bottom.pack(fill=tk.X, padx=5, pady=5)

        self.msg_entry = tk.Entry(
            bottom,
            bg=BG,
            fg=TEXT,
            insertbackground=TEXT,
            relief=tk.FLAT,
            font=("Arial", 11)
        )
        self.msg_entry.pack(side=tk.LEFT, fill=tk.X, expand=1, padx=(0, 5))

        send_btn = tk.Button(
            bottom,
            text=">",
            bg="#2e352e",
            fg=TEXT,
            relief=tk.FLAT,
            command=self.send
        )
        send_btn.pack(side=tk.RIGHT)

        img_btn = tk.Button(
            bottom,
            text="IMG",
            bg="#2e352e",
            fg=TEXT,
            relief=tk.FLAT,
            command=self.send_image
        )
        img_btn.pack(side=tk.RIGHT)

        self.msg_entry.bind("<Return>", lambda e: self.send())

        # ----- делаем строки выше (как карточки) -----
        self.root.after(100, self._style_listbox)


    def _style_listbox(self):
        try:
            for i in range(self.users_list.size()):
                self.users_list.itemconfig(i, {'padx': 5, 'pady': 6})
        except:
            pass
    def open_global(self):
        self.current_chat = "global"
        self.chat_name.config(text="Общий чат")
        self.chat_box.config(state="normal")
        self.chat_box.delete(1.0, tk.END)

        if "global" in self.chat_history:
            for msg in self.chat_history["global"]:
                if msg[0] == "text":
                    self.chat_box.insert(tk.END, msg[1])
                elif msg[0] == "image":
                    img_data = base64.b64decode(msg[1])
                    image = Image.open(io.BytesIO(img_data))
                    image.thumbnail((200, 200))
                    photo = ImageTk.PhotoImage(image)

                    self.chat_box.image_create(tk.END, image=photo)
                    self.chat_box.insert(tk.END, "\n")

                    self.images.append(photo)
                    
                    self.chat_box.config(state="disabled")
    # ---------- EXIT ----------
    def exit_app(self):
        try:
            self.socket.close()
        except:
            pass
        self.root.destroy()

# RUN
if __name__ == "__main__":
    root = tk.Tk()
    app = MessengerUI(root)
    root.mainloop()