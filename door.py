import cv2
import time
import threading
import queue
import speech_recognition as sr
import mediapipe as mp
import ctypes  # For Windows Message Box
import subprocess # For external TTS

# ================= CONFIGURATION =================
# Thresholds
FACE_WIDTH_THRESHOLD = 0.15  # Face must be at least 15% of screen width to be "meaningful"
CLOSE_DISTANCE_THRESHOLD = 0.25 # Face > 25% of width means "Close/Intimate"
COOLDOWN_SECONDS = 30  # Don't bother the same person for 30 seconds

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

def log_visitor_firebase(name, purpose):
    """Log visitor details to Firestore"""
    if db is None: return
    
    try:
        doc_ref = db.collection("visitors").document()
        doc_ref.set({
            "name": name,
            "purpose": purpose,
            "timestamp": firestore.SERVER_TIMESTAMP,
            "date_str": time.strftime("%Y-%m-%d %H:%M:%S")
        })
        print(f"✅ Logged to Firebase: {name}")
    except Exception as e:
        print(f"❌ Failed to log to Firebase: {e}")

# ================= WORKER THREAD FOR VOICE =================
class VoiceAssistant(threading.Thread):
    def __init__(self, command_queue, response_queue):
        super().__init__()
        self.command_queue = command_queue
        self.response_queue = response_queue
        self.daemon = True  # Kill thread when main program exits
        self.r = None

    def run(self):
        try:
            self.r = sr.Recognizer()
            # Tuning for better hearing
            self.r.pause_threshold = 1.2 # Allow 1.2s pause before ending phrase (default 0.8)
            self.r.energy_threshold = 300 # Lower starting threshold for sensitivity
            self.r.dynamic_energy_threshold = True 
        except Exception as e:
            print(f"Error initializing speech engine: {e}")
            return
        
        while True:
            try:
                task = self.command_queue.get()
                if task is None: break  # Poison pill
                
                action, data = task
                
                if action == "SPEAK":
                    try:
                        # Use external process for TTS to ensure stability and avoid COM issues
                        # creationflags=0x08000000 hides the console window on Windows
                        subprocess.call(["python", "speak.py", data], creationflags=0x08000000)
                    except Exception as e:
                        print(f"Error Speaking: {e}")
                
                elif action == "LISTEN":
                    print("🎤 Listening...")
                    with sr.Microphone() as source:
                        # Shorten ambient adjustment to feel more responsive, 
                        # but keep it to adapt to room noise.
                        self.r.adjust_for_ambient_noise(source, duration=0.5) 
                        try:
                            # increased phrase_time_limit to allow longer answers
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

# ================= MAIN AGENT CLASS =================
class DoorAgent:
    def __init__(self):
        # Queues for threading
        self.cmd_q = queue.Queue()
        self.resp_q = queue.Queue()
        
        # Start Voice Thread
        self.voice_thread = VoiceAssistant(self.cmd_q, self.resp_q)
        self.voice_thread.start()

        # Mediapipe Face Detection
        self.mp_face = mp.solutions.face_detection
        self.face_detector = self.mp_face.FaceDetection(model_selection=0, min_detection_confidence=0.6)

        # State Variables
        self.state = "IDLE"  # IDLE, INTERACTING, DECIDING, COOLDOWN, WAIT_FOR_EXIT
        self.last_interaction_time = 0
        self.no_face_timestamp = 0
        self.current_visitor = {"name": None, "purpose": None}
        self.cap = cv2.VideoCapture(0)

    def speak(self, text):
        self.cmd_q.put(("SPEAK", text))

    def listen_sync(self):
        """Request listening and wait for response (blocking only logic, not video)"""
        self.cmd_q.put(("LISTEN", None))
        return self.resp_q.get() # This blocks the LOGIC flow, but we handle logic in a way that doesn't freeze video

    def process_interaction(self):
        """Run interaction logic in a specialized way so we don't block the main loop entirely"""
        # Note: This simple approach might still block if called directly in main loop.
        # Ideally, we used a state machine.
        pass

    def run(self):
        self.speak("Smart Security System Activated")
        
        while True:
            ret, frame = self.cap.read()
            if not ret: break

            h, w, c = frame.shape
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.face_detector.process(rgb_frame)

            closest_face_ratio = 0
            
            if results.detections:
                for detection in results.detections:
                    bboxC = detection.location_data.relative_bounding_box
                    ih, iw, _ = frame.shape
                    x, y, fw, fh = int(bboxC.xmin * iw), int(bboxC.ymin * ih), int(bboxC.width * iw), int(bboxC.height * ih)
                    
                    # Draw Box
                    color = (0, 255, 0)
                    if self.state == "INTERACTING": color = (0, 255, 255)
                    if self.state == "COOLDOWN": color = (0, 0, 255)
                    cv2.rectangle(frame, (x, y), (x + fw, y + fh), color, 2)
                    
                    # Calculate size ratio (how close they are)
                    face_ratio = fw / iw
                    closest_face_ratio = max(closest_face_ratio, face_ratio)

            # === LOGIC STATE MACHINE ===
            
            # TRIGGER CONDITION
            if self.state == "IDLE":
                if closest_face_ratio > CLOSE_DISTANCE_THRESHOLD:
                    # Check Cooldown
                    time_since_last = time.time() - self.last_interaction_time
                    if time_since_last > COOLDOWN_SECONDS:
                        print(f"Target Acquired (Ratio: {closest_face_ratio:.2f})")
                        self.state = "INTERACTING"
                        threading.Thread(target=self.interaction_flow).start()
                    else:
                        # Visual feedback for cooldown
                        cv2.putText(frame, "Cooldown Active", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)
            
            elif self.state == "WAIT_FOR_EXIT":
                # Check if person is still there
                if closest_face_ratio < FACE_WIDTH_THRESHOLD:
                    # Person is GONE
                    if self.no_face_timestamp == 0:
                        self.no_face_timestamp = time.time()
                    
                    # If gone for more than 3 seconds, reset
                    if time.time() - self.no_face_timestamp > 3:
                        print("Visitor has left. Resetting...")
                        self.state = "IDLE"
                        self.no_face_timestamp = 0
                        self.current_visitor = {"name": None, "purpose": None} # Clear helper data
                else:
                    # Person is still here
                    self.no_face_timestamp = 0 # Reset timer if they come back/stay
                    # Visual feedback
                    cv2.putText(frame, "Monitoring Visitor...", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,255), 2)
                
            # Visual Status
            cv2.putText(frame, f"State: {self.state}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.imshow("Smart AI Guard", frame)

            if cv2.waitKey(1) & 0xFF == 27:
                break

        self.cap.release()
        cv2.destroyAllWindows()
        self.cmd_q.put(None) # Kill voice thread

    def ask_owner_permission(self, name, purpose):
        """
        Pop up a Windows MessageBox to ask the owner for permission.
        Returns True if 'Yes' is clicked, False if 'No'.
        """
        # ctypes.windll.user32.MessageBoxW parameters:
        # hWnd: 0 (no owner window)
        # lpText: Content of the message box
        # lpCaption: Title of the message box
        # uType: 4 (MB_YESNO) | 0x00000030 (MB_ICONWARNING) | 0x00010000 (MB_SETFOREGROUND)
        
        MB_YESNO = 4
        MB_ICONQUESTION = 0x20
        MB_TOPMOST = 0x40000 # Make sure it appears on top
        
        result = ctypes.windll.user32.MessageBoxW(
            0, 
            f"Visitor: {name}\nPurpose: {purpose}\n\nDo you want to authorize entry?", 
            "Smart Door Access Control", 
            MB_YESNO | MB_ICONQUESTION | MB_TOPMOST
        )
        
        # IDYES = 6, IDNO = 7
        return result == 6

    def interaction_flow(self):
        """The blocking/linear interaction script running in a separate thread"""
        try:
            self.speak("Hello. Please tell me your name.")
            name = self.listen_sync()
            
            if not name:
                self.speak("I didn't hear you. One more time.")
                name = self.listen_sync()
            
            if name:
                self.current_visitor["name"] = name
                self.speak(f"Hello. What is your purpose?")
                purpose = self.listen_sync()
                
                if not purpose:
                    self.speak("I didn't catch that. Please state your purpose again.")
                    purpose = self.listen_sync()
                
                self.current_visitor["purpose"] = purpose
                
                print(f"\n🚨 VISITOR: {name} | PURPOSE: {purpose}")
                
                # Log to Firebase
                log_visitor_firebase(name, purpose)

                self.speak("Please wait while I verify with the owner.")
                
                # Ask Owner for Permission via Popup
                authorized = self.ask_owner_permission(name, purpose)
                
                if authorized:
                    self.speak("Entry authorized. Welcome.")
                    # TODO: Add door unlock logic here if hardware connected
                else:
                    self.speak("Entry denied. Please leave.")
                
            else:
                self.speak("No response. Closing session.")

        except Exception as e:
            print(f"Interaction Error: {e}")
        finally:
            self.state = "WAIT_FOR_EXIT"
            self.last_interaction_time = time.time()

if __name__ == "__main__":
    agent = DoorAgent()
    agent.run()
