"""Envio de mensagens e leitura de comandos do Telegram."""
import requests


class Telegram:
    def __init__(self, token, chat_id):
        self.token, self.chat_id = token, str(chat_id)
        self.offset = None

    def send(self, text):
        import config as C
        if C.ROBOT_NAME != "Robô" and not text.startswith("🤖"):
            text = f"[{C.ROBOT_NAME}] " + text
        print("[TG]", text.replace("\n", " | "), flush=True)
        if not self.token or not self.chat_id:
            return
        try:
            requests.post(f"https://api.telegram.org/bot{self.token}/sendMessage",
                          json={"chat_id": self.chat_id, "text": text, "disable_web_page_preview": True}, timeout=15)
        except requests.RequestException as e:
            print("Telegram falhou:", e, flush=True)

    def commands(self):
        """Retorna comandos novos enviados pelo dono do robô (ignora outros chats)."""
        if not self.token:
            return []
        try:
            p = {"timeout": 0}
            if self.offset is not None:
                p["offset"] = self.offset
            r = requests.get(f"https://api.telegram.org/bot{self.token}/getUpdates", params=p, timeout=15).json()
        except (requests.RequestException, ValueError):
            return []
        out = []
        for u in r.get("result", []):
            self.offset = u["update_id"] + 1
            m = u.get("message") or {}
            if str(m.get("chat", {}).get("id")) == self.chat_id and m.get("text"):
                out.append(m["text"].strip().split()[0].split("@")[0].lower())
        return out
