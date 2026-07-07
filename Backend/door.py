import cv2
import time
import threading
import queue
import speech_recognition as sr
import mediapipe as mp
import ctypes
import subprocess
from flask import Flask, Response

# ================= FIREBASE INIT =================
import firebase_admin
from firebase_admin import credentials, firestore

db = None
try:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("✅ Firebase Connected Successfully!")
except Exception as e:
    print(f"⚠️ Firebase Init Failed: {e}")
    print("Visitors will NOT be logged to the cloud until 'serviceAccountKey.json' is fixed.")

# ================= CONFIGURATION =================
FACE_WIDTH_THRESHOLD = 0.15
CLOSE_DISTANCE_THRESHOLD = 0.25
COOLDOWN_SECONDS = 30

# Global flags for threads
agent_active = True
latest_frame = None
frame_lock = threading.Lock()

# Flask App for Video Streaming
app = Flask(__name__)

def generate_frames():
    global latest_frame
    while True:
        with frame_lock:
            if latest_frame is None:
                continue
            
            # Encode frame to JPEG
            ret, buffer = cv2.imencode('.jpg', latest_frame)
            frame = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

def start_flask_server():
    # Run Flask on all interfaces so phone can connect
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

# ================= PREVIOUS THREAD LOGIC (UNCHANGED MOSTLY) =================
class VoiceAssistant(threading.Thread):
    def __init__(self, command_queue, response_queue):
        super().__init__()
        self.command_queue = command_queue
        self.response_queue = response_queue
        self.daemon = True
        self.r = None

    def run(self):
        try:
            self.r = sr.Recognizer()
            self.r.pause_threshold = 1.2
            self.r.energy_threshold = 300
            self.r.dynamic_energy_threshold = True 
        except Exception as e:
            print(f"Error initializing speech engine: {e}")
            return
        
        while True:
            try:
                task = self.command_queue.get()
                if task is None: break
                
                action, data = task
                
                if action == "SPEAK":
                    try:
                        subprocess.call(["python", "speak.py", data], creationflags=0x08000000)
                    except Exception as e:
                        print(f"Error Speaking: {e}")
                
                elif action == "LISTEN":
                    print("🎤 Listening...")
                    with sr.Microphone() as source:
                        self.r.adjust_for_ambient_noise(source, duration=0.5)
                        try:
                            audio = self.r.listen(source, timeout=5, phrase_time_limit=10)
                            text = self.r.recognize_google(audio)
                            self.response_queue.put(text)
                        except sr.WaitTimeoutError:
                            self.response_queue.put(None)
                        except sr.UnknownValueError:
                            self.response_queue.put(None)
                        except Exception as e:
                            print(f"Error listening: {e}")
                            self.response_queue.put(None)
                            
                self.command_queue.task_done()
            except Exception as e:
                print(f"Voice Thread Error: {e}")

# ================= LISTENER FOR REMOTE SWITCH =================
def listen_for_agent_switch():
    global agent_active
    if db is None: return

    def on_snapshot(doc_snapshot, changes, read_time):
        global agent_active
        for doc in doc_snapshot:
            data = doc.to_dict()
            if data and "agent_active" in data:
                new_state = data["agent_active"]
                if agent_active != new_state:
                    agent_active = new_state
                    print(f"\n🔄 Remote Command: Agent {'ACTIVATED' if agent_active else 'PAUSED'}")

    doc_ref = db.collection("config").document("settings")
    # Ensure doc exists
    if not doc_ref.get().exists:
        doc_ref.set({"agent_active": True})
        
    doc_ref.on_snapshot(on_snapshot)

# ================= MAIN AGENT CLASS =================
class DoorAgent:
    def __init__(self):
        self.cmd_q = queue.Queue()
        self.resp_q = queue.Queue()
        self.voice_thread = VoiceAssistant(self.cmd_q, self.resp_q)
        self.voice_thread.start()

        self.mp_face = mp.solutions.face_detection
        self.face_detector = self.mp_face.FaceDetection(model_selection=0, min_detection_confidence=0.6)

        self.state = "IDLE"
        self.last_interaction_time = 0
        self.no_face_timestamp = 0
        self.current_visitor = {"name": None, "purpose": None}
        # Try to open camera with DirectShow (faster/more reliable on Windows)
        print("📷 Attempting to open camera (Index 0)...")
        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        
        if not self.cap.isOpened():
            print("⚠️ Camera Index 0 failed. Trying default backend...")
            self.cap = cv2.VideoCapture(0)

        if not self.cap.isOpened():
            print("❌ ERROR: Could not open camera! Check connection or permissions.")
        
        # Start Remote Listener
        listen_for_agent_switch()
        
        # Start Flask Server in background
        threading.Thread(target=start_flask_server, daemon=True).start()

    def speak(self, text):
        self.cmd_q.put(("SPEAK", text))

    def listen_sync(self):
        self.cmd_q.put(("LISTEN", None))
        return self.resp_q.get()

    def log_visitor_firebase(self, name, purpose):
        """Log visitor and return the document ID for tracking approval status"""
        if db is None: return None
        
        try:
            doc_ref = db.collection("visitors").document()
            doc_ref.set({
                "name": name,
                "purpose": purpose,
                "timestamp": firestore.SERVER_TIMESTAMP,
                "date_str": time.strftime("%Y-%m-%d %H:%M:%S"),
                "status": "PENDING"  # PENDING, APPROVED, DENIED
            })
            print(f"✅ Logged to Firebase: {name}")
            return doc_ref.id
        except Exception as e:
            print(f"❌ Failed to log: {e}")
            return None

    def wait_for_app_approval(self, doc_id):
        """Poll Firestore for status change"""
        if not doc_id: return False # Fallback if firebase failed
        
        print("⏳ Waiting for App Approval...")
        
        # Timeout after 60 seconds
        start_wait = time.time()
        
        while time.time() - start_wait < 60:
            doc = db.collection("visitors").document(doc_id).get()
            if doc.exists:
                status = doc.to_dict().get("status", "PENDING")
                if status == "APPROVED":
                    return True
                elif status == "DENIED":
                    return False
            
            time.sleep(1) 
        
        print("Time out waiting for app.")
        return False

    def run(self):
        self.speak("Smart Security System Activated")
        
        print("\n📷 Video Stream available at: http://<YOUR_IP>:5000/video_feed\n")
        
        global latest_frame
        
        while True:
            ret, frame = self.cap.read()
            if not ret: break

            # Update global frame for Flask
            with frame_lock:
                latest_frame = frame.copy()

            h, w, c = frame.shape
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Only process logic if Agent is ACTIVE
            if agent_active:
                results = self.face_detector.process(rgb_frame)
                closest_face_ratio = 0
                
                if results.detections:
                    for detection in results.detections:
                        bboxC = detection.location_data.relative_bounding_box
                        ih, iw, _ = frame.shape
                        x, y, fw, fh = int(bboxC.xmin * iw), int(bboxC.ymin * ih), int(bboxC.width * iw), int(bboxC.height * ih)
                        
                        color = (0, 255, 0)
                        if self.state == "INTERACTING": color = (0, 255, 255)
                        if self.state == "COOLDOWN": color = (0, 0, 255)
                        cv2.rectangle(frame, (x, y), (x + fw, y + fh), color, 2)
                        
                        face_ratio = fw / iw
                        closest_face_ratio = max(closest_face_ratio, face_ratio)

                # logic
                if self.state == "IDLE":
                    if closest_face_ratio > CLOSE_DISTANCE_THRESHOLD:
                        time_since_last = time.time() - self.last_interaction_time
                        if time_since_last > COOLDOWN_SECONDS:
                            print(f"Target Acquired")
                            self.state = "INTERACTING"
                            threading.Thread(target=self.interaction_flow).start()
                        else:
                            pass # Cooldown text removed
                
                elif self.state == "WAIT_FOR_EXIT":
                    if closest_face_ratio < FACE_WIDTH_THRESHOLD:
                        if self.no_face_timestamp == 0: self.no_face_timestamp = time.time()
                        if time.time() - self.no_face_timestamp > 3:
                            self.state = "IDLE"
                            self.no_face_timestamp = 0
                    else:
                        self.no_face_timestamp = 0
                        # Monitoring text removed

            else:
                # Agent Paused
                pass # Paused text removed

            # Local Display
            cv2.imshow("Smart AI Guard", frame)

            if cv2.waitKey(1) & 0xFF == 27:
                break

        self.cap.release()
        cv2.destroyAllWindows()
        self.cmd_q.put(None)

    def interaction_flow(self):
        try:
            self.speak("Hello. Please tell me your name.")
            name = self.listen_sync()
            
            if not name:
                self.speak("I didn't hear you. One more time.")
                name = self.listen_sync()
            
            if name:
                self.current_visitor["name"] = name
                self.speak(f"Hello {name}. What is your purpose?")
                purpose = self.listen_sync()
                
                if not purpose:
                    self.speak("Purpose?")
                    purpose = self.listen_sync()
                
                self.current_visitor["purpose"] = purpose
                print(f"\n🚨 VISITOR: {name} | PURPOSE: {purpose}")
                
                # Log to Firebase & Get ID
                doc_id = self.log_visitor_firebase(name, purpose)
                self.speak("Please wait while I verify with the owner.")
                
                # Wait for App Approval (Remote) OR Fallback to Pop-up (Local)
                authorized = False
                if db is not None:
                    authorized = self.wait_for_app_approval(doc_id)
                else:
                    authorized = self.ask_owner_permission(name, purpose) # Keep legacy backup
                
                if authorized:
                    self.speak("Entry authorized. Welcome.")
                else:
                    self.speak("Sorry.He is not available right now .")
                
            else:
                self.speak("No response. Closing session.")

        except Exception as e:
            print(f"Interaction Error: {e}")
        finally:
            self.state = "WAIT_FOR_EXIT"
            self.last_interaction_time = time.time()

    def ask_owner_permission(self, name, purpose):
        """Legacy local popup"""
        MB_YESNO = 4
        MB_ICONQUESTION = 0x20
        MB_TOPMOST = 0x40000 
        result = ctypes.windll.user32.MessageBoxW(0, f"Visitor: {name}\nPurpose: {purpose}\n\nApprove?", "Smart Door", MB_YESNO | MB_ICONQUESTION | MB_TOPMOST)
        return result == 6

if __name__ == "__main__":
    agent = DoorAgent()
    agent.run()
