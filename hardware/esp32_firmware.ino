/*
  WashMate AI - ESP32 Relay Controller
  This code runs on the ESP32 microcontroller.
  It receives ON/OFF commands from the Python backend over WiFi
  and controls the relay that switches power to the washing machine.
*/

#include <WiFi.h>
#include <WebServer.h>
#include <ArduinoJson.h>

// ── CHANGE THESE ──────────────────────────────────────
const char* WIFI_SSID     = "YourHostelWiFi";
const char* WIFI_PASSWORD = "YourWiFiPassword";
const int   MACHINE_ID    = 1;
// ──────────────────────────────────────────────────────

const int RELAY_PIN = 26;
WebServer server(80);
bool relayState = false;

void setRelay(bool on) {
  relayState = on;
  digitalWrite(RELAY_PIN, on ? LOW : HIGH);
}

void handleRelayControl() {
  if (server.method() != HTTP_POST) {
    server.send(405, "text/plain", "Method Not Allowed");
    return;
  }
  String body = server.arg("plain");
  StaticJsonDocument<128> doc;
  deserializeJson(doc, body);
  String state = doc["state"].as<String>();
  if (state == "ON") {
    setRelay(true);
    server.send(200, "application/json", "{\"relay\":\"ON\",\"ok\":true}");
  } else {
    setRelay(false);
    server.send(200, "application/json", "{\"relay\":\"OFF\",\"ok\":true}");
  }
}

void handleStatus() {
  String json = "{\"machine_id\":" + String(MACHINE_ID) +
                ",\"relay_on\":" + String(relayState ? "true" : "false") + "}";
  server.send(200, "application/json", json);
}

void setup() {
  Serial.begin(115200);
  pinMode(RELAY_PIN, OUTPUT);
  setRelay(false);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nConnected! IP: " + WiFi.localIP().toString());
  Serial.println(">>> Copy this IP into backend/main.py RELAY_IPS <<<");
  server.on("/relay",  HTTP_POST, handleRelayControl);
  server.on("/status", HTTP_GET,  handleStatus);
  server.begin();
}

void loop() {
  server.handleClient();
}
