import time
import serial
import threading
import sqlite3
import glob
from mask_system import MaskAccessSystem, Config

DB_PATH = "tags.db"
DB_LOCK = threading.Lock()
ERROR_LOG_PATH = "tags_erro.txt"

def init_db():
    with DB_LOCK, sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                tag TEXT UNIQUE NOT NULL
            );
        """)
        conn.commit()

def create_tag(nome: str, tag: str):
    with DB_LOCK, sqlite3.connect(DB_PATH) as conn:
        try:
            conn.execute("INSERT INTO tags (nome, tag) VALUES (?, ?)", (nome, tag))
            conn.commit()
            print(f"[CRUD] Tag '{tag}' cadastrada para '{nome}'.")
        except sqlite3.IntegrityError:
            print(f"[CRUD] Erro: Tag '{tag}' já existe.")

def list_tags():
    with DB_LOCK, sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("SELECT id, nome, tag FROM tags ORDER BY id")
        rows = cur.fetchall()
    if not rows:
        print("[CRUD] Nenhuma tag cadastrada.")
    else:
        print("[CRUD] Tags cadastradas:")
        for row in rows:
            print(f"  {row[0]:>3}: {row[2]} → {row[1]}")

def update_tag(old_tag: str, new_tag: str = None, new_nome: str = None):
    with DB_LOCK, sqlite3.connect(DB_PATH) as conn:
        if new_tag:
            conn.execute("UPDATE tags SET tag = ? WHERE tag = ?", (new_tag, old_tag))
            print(f"[CRUD] Tag '{old_tag}' alterada para '{new_tag}'.")
        if new_nome:
            conn.execute("UPDATE tags SET nome = ? WHERE tag = ?", (new_nome, old_tag))
            print(f"[CRUD] Nome da tag '{old_tag}' atualizado para '{new_nome}'.")
        conn.commit()

def delete_tag(tag: str):
    with DB_LOCK, sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("DELETE FROM tags WHERE tag = ?", (tag,))
        conn.commit()
    if cur.rowcount:
        print(f"[CRUD] Tag '{tag}' removida.")
    else:
        print(f"[CRUD] Tag '{tag}' não encontrada.")

def crud_menu():
    menu = """
[CRUD] Menu de Tags:
  c — Create (cadastrar)
  l — List   (listar)
  u — Update (alterar)
  d — Delete (remover)
  x — Exit   (sair do menu)
"""
    print(menu)
    while True:
        cmd = input("[CRUD] Escolha uma opção (c/l/u/d/x): ").strip().lower()
        if cmd == 'c':
            nome = input("  [CRUD] Nome: ").strip()
            tag  = input("  [CRUD] Tag  : ").strip().upper()
            create_tag(nome, tag)
        elif cmd == 'l':
            list_tags()
        elif cmd == 'u':
            old = input("  [CRUD] Tag atual: ").strip().upper()
            choice = input("    Alterar (n)ome ou (t)ag? ").strip().lower()
            if choice == 'n':
                novo = input("    Novo nome: ").strip()
                update_tag(old_tag=old, new_nome=novo)
            elif choice == 't':
                novo = input("    Nova tag : ").strip().upper()
                update_tag(old_tag=old, new_tag=novo)
            else:
                print("    [CRUD] Opção inválida.")
        elif cmd == 'd':
            tag  = input("  [CRUD] Tag a remover: ").strip().upper()
            delete_tag(tag)
        elif cmd == 'x':
            print("[CRUD] Saindo do menu.")
            break
        else:
            print("[CRUD] Opção inválida.")


def tag_autorizada(tag: str):
    with DB_LOCK, sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("SELECT nome FROM tags WHERE tag = ?", (tag,))
        return cur.fetchone()

class Arduino:
    def __init__(self, baud=9600):
        porta = self._detectar_porta()
        if not porta:
            raise RuntimeError("Arduino não encontrado em /dev/ttyUSB* ou /dev/ttyACM*")
        print(f"[Arduino] Conectado em {porta}")
        self.ser = serial.Serial(porta, baud, timeout=1)
        time.sleep(2)

    def _detectar_porta(self):
        for p in glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"):
            try:
                s = serial.Serial(p, 9600, timeout=1)
                s.close()
                return p
            except:
                pass
        return None

    def ler_tag(self):
        if self.ser.in_waiting:
            linha = self.ser.readline().decode(errors='ignore').strip()
            if linha.startswith("TAG:"):
                return linha[4:].strip().upper()
        return None

    def liberar_acesso(self):
        self.ser.write(b"ACESSO:OK\n")

    def negar_acesso(self):
        self.ser.write(b"ACESSO:NEGADO\n")


def log_tag_erro(tag: str):
    with open(ERROR_LOG_PATH, "a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - TAG não cadastrada: {tag}\n")
    print(f"[LOG] TAG '{tag}' registrada no arquivo de erros.")

def main():
    print("Iniciando sistema de acesso...")
    init_db()
    # inicia thread de CRUD em background
    threading.Thread(target=crud_menu, daemon=True).start()

    arduino = Arduino()
    cfg = Config(
        api_key="iLrZkatUZLBk7QqnYC8s",
        project="cover-2",
        version="10",
        headless=True
    )

    try:
        while True:
            tag = arduino.ler_tag()
            if not tag:
                time.sleep(0.1)
                continue

            print(f"TAG detectada: {tag}")
            pessoa = tag_autorizada(tag)
            if not pessoa:
                print("TAG não cadastrada.")
                log_tag_erro(tag)  # Registra a TAG no arquivo de erros
                arduino.negar_acesso()
                time.sleep(1)
                continue

            print(f"Autorizada: {pessoa[0]}. Iniciando detecção de máscara...")
            arduino.ser.write(b"LCD:Aproxime o rosto\n")  # Exibe no LCD
            time.sleep(1)  # Pequeno delay para exibir antes de iniciar
            detector = MaskAccessSystem(cfg)
            det_thr = threading.Thread(target=detector.start, daemon=True)
            det_thr.start()

            deadline = time.time() + 10
            while time.time() < deadline:
                if detector.access_granted:
                    print("Máscara detectada: acesso liberado.")
                    arduino.liberar_acesso()
                    break
                time.sleep(0.2)
            else:
                print("Nenhuma máscara detectada: acesso negado.")
                arduino.negar_acesso()

            detector.running = False
            det_thr.join(timeout=1)
            time.sleep(1)

            print("Pronto para próxima TAG.\n")
            time.sleep(1)

    except KeyboardInterrupt:
        print("Encerrando sistema...")

if __name__ == "__main__":
    main()
