#include <WiFi.h>
#include <PubSubClient.h>

// ─── WIFI ───────────────────────────────────────────────────
const char* ssid     = "Enter ssid";
const char* password = "Enter password";

// ─── MQTT ───────────────────────────────────────────────────
const char* mqtt_server = "192.168.116.30";
const int   mqtt_port   = 1884;

// 🔥 CHANGE THIS FOR EACH BUS
const char* BUS_ID = "BUS_02";

// Topic per bus
String topic;

// ─── GPS ROUTE (SIMULATION) ─────────────────────────────────
struct GPS {
    float lat;
    float lon;
};

GPS route[] = {
    {26.192880, 91.700321},
    {26.193410, 91.700955},
    {26.194020, 91.701600},
    {26.192345, 91.699876},
    {26.192880, 91.700321}
};

int routeSize = sizeof(route) / sizeof(route[0]);
int indexPos  = 0;

// ─── CLIENT ─────────────────────────────────────────────────
WiFiClient wifiClient;
PubSubClient client(wifiClient);

// ─── WIFI CONNECT ───────────────────────────────────────────
void connectWiFi() {
    WiFi.begin(ssid, password);
    Serial.print("📶 Connecting");

    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }

    Serial.println("\n✅ WiFi Connected!");
    Serial.println(WiFi.localIP());
}

// ─── MQTT RECONNECT ─────────────────────────────────────────
void reconnect() {
    while (!client.connected()) {
        Serial.print("🔌 Connecting MQTT...");

        if (client.connect(BUS_ID)) {
            Serial.println(" ✅ Connected!");
        } else {
            Serial.print(" ❌ Failed, rc=");
            Serial.println(client.state());
            delay(3000);
        }
    }
}

// ─── SETUP ──────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);

    connectWiFi();

    topic = "smartbus/" + String(BUS_ID) + "/location";

    client.setServer(mqtt_server, mqtt_port);
}

// ─── LOOP ───────────────────────────────────────────────────
void loop() {
    if (WiFi.status() != WL_CONNECTED) connectWiFi();
    if (!client.connected()) reconnect();

    client.loop();

    char payload[256];

    snprintf(payload, sizeof(payload),
             "{\"bus_id\":\"%s\",\"lat\":%.6f,\"lon\":%.6f,\"time\":%lu}",
             BUS_ID,
             route[indexPos].lat,
             route[indexPos].lon,
             millis() / 1000);

    client.publish(topic.c_str(), payload);

    Serial.println(payload);

    indexPos = (indexPos + 1) % routeSize;

    delay(2000);
}