#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <Servo.h>

// Declaração do objeto LCD e Servo
LiquidCrystal_I2C lcd(0x27, 16, 2);  // Verifique se o endereço I2C é mesmo 0x27
Servo portaServo;

void setup() {
  Serial.begin(9600);
  lcd.init();
  lcd.backlight();
  portaServo.attach(3);
  portaServo.write(0);
  lcd.setCursor(0, 0);
  lcd.print("Aguardando TAG");  // Mensagem padrão inicial
  Serial.println("Sistema iniciado. Aguardando comandos...");
}

void loop() {
  if (Serial.available()) {
    String comando = Serial.readStringUntil('\n');
    comando.trim();
    Serial.println("Comando recebido: " + comando);  // Depuração: exibe o comando recebido

    if (comando.startsWith("LCD:")) {
      lcd.clear();
      lcd.setCursor(0, 0);
      lcd.print(comando.substring(4));
      Serial.println("Mensagem exibida no LCD: " + comando.substring(4));  // Depuração
    }
    else if (comando == "ACESSO:OK") {
      lcd.clear();
      lcd.setCursor(0, 0);
      lcd.print("Porta Liberada");
      portaServo.write(90);
      Serial.println("Porta liberada.");  // Depuração
      delay(3000);
      portaServo.write(0);
      lcd.clear();
      lcd.setCursor(0, 0);
      lcd.print("Aguardando TAG");  // Retorna à mensagem padrão
    }
    else if (comando == "ACESSO:NEGADO") {
      lcd.clear();
      lcd.setCursor(0, 0);
      lcd.print("Acesso Negado");
      portaServo.write(0);
      Serial.println("Acesso negado.");  // Depuração
      delay(3000);
      lcd.clear();
      lcd.setCursor(0, 0);
      lcd.print("Aguardando TAG");  // Retorna à mensagem padrão
    }
  }
}
