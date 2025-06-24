## Sistema de Acesso RFID + Máscara

**Descrição:** Leitura de TAG RFID e verificação de máscara, liberando acesso via servo e exibindo status no LCD.

**Componentes:**

* Arduino Uno, RC522 e tags RFID
* Raspberry Pi 4 e câmera
* Servo SG90, LCD 16×2, jumpers e protoboard

**Arquitetura:**
Arduino ⇄ Serial ⇄ Raspberry Pi → Roboflow API → Arduino

**Instalação rápida:**

1. Clone o projeto
2. Carregue o sketch no Arduino.
3. No Pi: `sudo apt update && sudo apt install python3-opencv python3-requests`
4. Ajuste `API_KEY` no script Python.

**Uso:**

1. Inicie o script Python no Raspberry Pi.
2. Aproxime a TAG; o sistema detecta máscara e mostra “Liberado”/“Negado” no LCD.
