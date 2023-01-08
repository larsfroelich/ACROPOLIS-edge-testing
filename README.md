# Tentacruel

Here, a management software for autonomous sensor networks is created.

The system is made of three parts: the sensors themselves, the server, and the dashboard.

The sensors communicate with the server via MQTT. The server stores the data in a database and provides a REST API for the dashboard.

## Main goals 🎯

1. The network and sensors are to function reliably and autonomously
1. The status of the sensors can be observed in real-time and remotely
1. The software on the sensors can be updated remotely
1. The software is reusable for other sensor networks without changes

## Practical usage 📦

This software is developed for the ACROPOLIS project. The goal of ACROPOLIS is to measure CO2 concentrations with very high precision in the city of Munich. The network spans 20 sensors.

## Structure 🔨

![](assets/schema.png)
