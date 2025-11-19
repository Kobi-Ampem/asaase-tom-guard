# Architecture Overview
(Short description of system components and data flow)
- Raspberry Pi 4: main compute + camera + sensors + dashboard client
- Camera: Pi HQ camera captures images
- Motor drivers: TB6612 control motors
- Sensors: DHT22, soil moisture, LDR, ultrasonic
- Storage: microSD for logs and models
- Dashboard: Streamlit app for remote monitoring/control