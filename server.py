import socket
import threading
import json
import sqlite3
import hashlib

HOST = "0.0.0.0"
PORT = 5555

clients = []
users = {}

db = sqlite3.connect("chat.db", check_same_thread=False)
cursor = db.cursor()
db.commit()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT,
    sender TEXT,
    receiver TEXT,
    text TEXT,
    image TEXT
)
""")

db.commit()
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()
def broadcast(data, sender_conn=None):
    message = json.dumps(data) + "\n"
    print(message)

    for client in clients:
        try:
            client.send(message.encode("utf-8"))
        except:
            clients.remove(client)

def send_all_users():
    cursor.execute("SELECT username FROM users")
    rows = cursor.fetchall()

    all_users = []

    for row in rows:
        username = row[0]
        all_users.append({
            "name": username,
            "online": username in users.values()
        })


    broadcast({
        "type": "users",
        "users": all_users
    })

def send_users_list():
    print(users)
    user_list = list(users.values())

    data = {
        "type": "users",
        "users": user_list
    }

    broadcast(data)
def handle_client(conn):
    buffer = ""

    try:
        while True:
            data = conn.recv(8192).decode("utf-8")
            print(data)
            if not data:
                break

            buffer += data
            while "\n" in buffer:
                message_str, buffer = buffer.split("\n", 1)
                try:
                    message = json.loads(message_str)
                    print(message)
                except:
                    continue

                msg_type = message.get("type")
                print(message)
                print(msg_type)


            # ==================REGISTER===========================  
                if msg_type == "register":
                    user = message.get("user")
                    pw = hash_password(message.get("pass"))
                    try:
                        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (user, pw))
                        db.commit()
                        conn.send((json.dumps({"type": "auth_res", "subtype": "register","status": "success", "info": "Registered"}) + "\n").encode())
                    except sqlite3.IntegrityError:
                        conn.send((json.dumps({"type": "auth_res","subtype": "register", "status": "fail", "info": "User exists"}) + "\n").encode())

                # ==================LOGIN===========================         
                elif msg_type == "login":
                    username = message.get("user")
                    pw = hash_password(message.get("pass"))
                # отправка последних 50 сообщений общего чата
                    cursor.execute("SELECT * FROM users WHERE username=? AND password=?", (username, pw))

                    rows = cursor.fetchall()
                    if username in users.values():
                        conn.send((json.dumps({"type": "auth_res","subtype": "login", "status": "fail", "info": "You login"}) + "\n").encode())
                    elif rows and rows[0][2] == pw:
                        users[conn] = username
                        conn.send((json.dumps({"type": "auth_res","subtype": "login", "status": "success", "info": "Logged in"}) + "\n").encode())
                        # После логина отправляем историю и список юзеров
                        send_history_after_login(conn)
                        send_all_users()
                    else:
                        conn.send((json.dumps({"type": "auth_res","subtype": "login", "status": "fail", "info": "Wrong pass"}) + "\n").encode())


                # ============MESSAGE===========================
                elif msg_type == "message":
                    print("М ERROR")
                    print(message)
                    # 💌 DM
                    if message.get("subtype") == "dm":
                        to_user = message.get("to")
                        from_user = users.get(conn, "Unknown")
                        cursor.execute(
        "INSERT INTO messages (type, sender, receiver, text) VALUES (?, ?, ?, ?)",
        ("dm", from_user, to_user, message.get("text"))
    )
                        db.commit()
                        send_to_user(to_user, {
                            "type": "message",
                            "subtype": "dm",
                            "from": from_user,
                            "text": message.get("text")
                        })

                        # отправляем обратно отправителю тоже
                        conn.send((json.dumps({
                            "type": "message",
                            "subtype": "dm",
                            "from": from_user,
                            "to": to_user,
                            "text": message.get("text")
                        }) + "\n").encode("utf-8"))
                    else:
                        username = users.get(conn, "Unknown")
                        cursor.execute(
        "INSERT INTO messages (type, sender, receiver, text) VALUES (?, ?, ?, ?)",
        ("chat", username, None, message.get("text"))
    )
                        db.commit()
                        broadcast({
                            "type": "message",
                            "subtype": "chat",
                            "user": username,
                            "text": message.get("text")
                            })
                elif msg_type == "image":
                    from_user = users.get(conn, "Unknown")

                    if message.get("subtype") == "dm":
                        to_user = message.get("to")
                        cursor.execute(
                            "INSERT INTO messages (type, sender, receiver, image) VALUES (?, ?, ?, ?)",
                            ("dm", from_user, to_user, message.get("image"))
                        )
                        print(message.get("image"))
                        send_to_user(to_user, {
                            "type": "image",
                            "from": from_user,
                            "image": message.get("image")
                        })

                        conn.send((json.dumps({
                            "type": "image",
                            "from": from_user,
                            "to": to_user,
                            "image": message.get("image")
                        }) + "\n").encode("utf-8"))

                    else:
                        broadcast({
                            "type": "image",
                            "from": from_user,
                            "image": message.get("image")
                        })
                elif msg_type == "get_history":
                    user1 = users.get(conn)
                    user2 = message.get("with")

                    cursor.execute("""
                            SELECT sender, receiver, text, image, type FROM messages
                            WHERE type='dm' AND (
                                (sender=? AND receiver=?)
                                OR
                                (sender=? AND receiver=?)
                            )
                            ORDER BY id ASC
                            LIMIT 50
                        """, (user1, user2, user2, user1))

                    rows = cursor.fetchall()

                    for sender, receiver, text, image, msg_type in rows:
                        if msg_type == "dm":
                            if image:
                                conn.send((json.dumps({
                                    "type": "image",
                                    "from": sender,
                                    "to": receiver,
                                    "image": image
                                }) + "\n").encode("utf-8"))
                            else:
                                conn.send((json.dumps({
                                    "type": "message",
                                    "subtype": "dm",
                                    "from": sender,
                                    "to": receiver,
                                    "text": text
                                }) + "\n").encode("utf-8"))


                elif msg_type == "logout":
                    username = users.get(conn, "Unknown")

                    broadcast({
                        "type": "message",
                        "subtype": "system",
                        "text": f"{username} вышел из чата"
                    })
                    send_users_list() 
                    break

    except Exception as e:
        print("ERROR:", e)

    finally:
        print("fin")
        if conn in clients:
            clients.remove(conn)

        if conn in users:
            del users[conn]
        send_all_users()
        conn.close()

def send_history_after_login(conn):
    """Отправляет последние 50 сообщений общего чата конкретному соединению"""
    cursor.execute(
        "SELECT sender, text FROM messages WHERE type='chat' ORDER BY id DESC LIMIT 50"
    )
    rows = cursor.fetchall()
    for sender, text in reversed(rows):
        conn.send((json.dumps({
            "type": "message",
            "subtype": "chat",
            "user": sender,
            "text": text
        }) + "\n").encode("utf-8"))
def send_to_user(username, data):
    message = (json.dumps(data) + "\n").encode("utf-8")

    for conn, name in users.items():
        if name == username:
            try:
                conn.send(message)
            except:
                pass

def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen()

    print(f"Сервер запущен на {HOST}:{PORT}")

    while True:
        conn, addr = server.accept()
        print(f"Подключился: {addr}")

        clients.append(conn)

        thread = threading.Thread(target=handle_client, args=(conn,))
        thread.start()


if __name__ == "__main__":
    start_server()