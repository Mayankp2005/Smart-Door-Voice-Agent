# Smart Door Voice Agent with Camera & Voice

An AI-powered Smart Door Security System that leverages facial detection, voice interaction, and cloud integration to secure your premises. The system consists of a Python-based edge device (acting as the physical door guard) and an Android application for remote homeowner control.

## 🌟 Features
* **Facial Detection:** Utilizes OpenCV and Mediapipe to accurately detect when a visitor approaches the door.
* **Interactive Voice Agent:** Uses `speech_recognition` to listen to the visitor's name and purpose, and responds with a realistic voice via the ElevenLabs API (with fallback to Google TTS / local TTS).
* **Live Video Streaming:** Hosts a lightweight Flask server to stream a live camera feed to the homeowner's network.
* **Cloud-Synced Remote Control:** Integrates with Firebase Firestore. When a visitor arrives, their information is pushed to the cloud in real-time, allowing the homeowner to approve or deny entry directly from the Android app.
* **Smart Polling:** The Edge device intelligently waits for the homeowner's decision via the Android app before granting or denying access to the visitor.

---

## 🏗️ Architecture

The project is split into two primary components:

### 1. Backend (Python Edge Device)
Located in the `Backend/` folder. This component acts as the brains at the door. 
- Listens to the camera feed and triggers when a face is detected.
- Asks for visitor details and pushes the payload to the `visitors` collection in Firestore.
- Awaits an `APPROVED` or `DENIED` status change from the cloud.

### 2. Android App (Remote Control)
Located in the `AndroidApp/` folder. This Kotlin-based Android application allows the homeowner to:
- See a list of pending visitors and their purpose of visit.
- Approve or deny entry remotely.
- Remotely toggle the Smart Door Agent on or off.

---

## 🚀 Getting Started

### Prerequisites
- Python 3.8+
- Android Studio
- A Firebase Project (with Firestore enabled)
- Camera & Microphone connected to the edge device

### 1. Setting up Firebase
1. Create a Firebase project and initialize Firestore.
2. Generate a Service Account Key from Firebase Project Settings -> Service Accounts.
3. Save the downloaded JSON file as `serviceAccountKey.json` inside the `Backend/` folder.
4. Add your `google-services.json` to the `AndroidApp/app/` folder for the Android application to connect.

### 2. Running the Edge Device (Python)
Navigate to the `Backend` directory and install the required packages:

```bash
cd Backend
pip install -r requirements.txt # Or install packages manually (opencv-python, mediapipe, firebase-admin, etc.)
```
Run the agent:
```bash
python door.py
```
*(The camera will turn on, and the Flask video stream will be available at `http://localhost:5000/video_feed`)*

### 3. Running the Android App
1. Open the `AndroidApp/` folder in **Android Studio**.
2. Sync the Gradle files.
3. Build and run the app on an Android Emulator or a physical device.

---

## 🛠️ Built With
* **Python** - Core logic for the edge device
* **Kotlin** - Android application
* **OpenCV & Mediapipe** - Computer vision and facial detection
* **SpeechRecognition & ElevenLabs/gTTS** - Voice interaction
* **Firebase Firestore** - Real-time cloud database
* **Flask** - Video streaming server

---
*Created as an academic project demonstrating the integration of Edge AI and Cloud Services.*
