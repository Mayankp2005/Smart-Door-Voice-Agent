import sys
import os
import pyttsx3
import pygame
from dotenv import load_dotenv
from elevenlabs import ElevenLabs, save # Updated import for v1.0+
from elevenlabs.client import ElevenLabs
from gtts import gTTS

# Load Environment Variables
load_dotenv()
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

def speak_local(text):
    """Fallback to local TTS (pyttsx3)"""
    try:
        engine = pyttsx3.init()
        # Indian voice selection logic
        voices = engine.getProperty('voices')
        target_voice_id = None
        for voice in voices:
            if "India" in voice.name or "Hindi" in voice.name or "Ravi" in voice.name or "Heera" in voice.name or "Kalpana" in voice.name or "en-IN" in voice.id:
                target_voice_id = voice.id
                break
        
        if target_voice_id:
            engine.setProperty('voice', target_voice_id)
        
        engine.setProperty("rate", 160)
        engine.say(text)
        engine.runAndWait()
    except Exception as e:
        print(f"Local TTS Error: {e}")

def speak_elevenlabs(text):
    """Use ElevenLabs API"""
    try:
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        
        # 1. Choose Voice
        # We can try to find a specific Indian voice if we knew the ID, 
        # but for now we'll list and pick one, or default to a good one.
        # "Fin" is a popular male voice, "Rachel" female. 
        # Let's see if we can find one with "Indian" in the name/accent
        
        selected_voice_id = "21m00Tcm4TlvDq8ikWAM" # Default Rachel (US)
        
        try:
            voices = client.voices.get_all()
            for voice in voices.voices:
                # Basic check for "Indian" in labels/name
                # Note: Labels might be a dict or object depending on version
                labels = getattr(voice, 'labels', {})
                if labels and isinstance(labels, dict):
                     if "accent" in labels and "indian" in labels["accent"].lower():
                         selected_voice_id = voice.voice_id
                         print(f"[ElevenLabs] Using Indian Voice: {voice.name}")
                         break
                if "ndian" in voice.name: # name check fallback
                     selected_voice_id = voice.voice_id
                     print(f"[ElevenLabs] Using Voice by name: {voice.name}")
                     break
        except Exception as e:
            print(f"[ElevenLabs] Voice list error: {e}. Using default.")

        # 2. Generate Audio
        audio = client.generate(
            text=text,
            voice=selected_voice_id,
            model="eleven_monolingual_v1"
        )
        
        # 3. Save & Play
        temp_file = "temp_speech.mp3"
        save(audio, temp_file)
        
        pygame.mixer.init()
        pygame.mixer.music.load(temp_file)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        
        pygame.mixer.quit()
        os.remove(temp_file)
        
    except Exception as e:
        print(f"[ElevenLabs] Error: {e}. Falling back to local.")
        speak_local(text)



def speak_gtts(text):
    """Use Google Text-to-Speech (gTTS) for Indian accent"""
    try:
        # tld='co.in' gives the Indian accent
        tts = gTTS(text=text, lang='en', tld='co.in')
        
        temp_file = "temp_gtts.mp3"
        tts.save(temp_file)
        
        pygame.mixer.init()
        pygame.mixer.music.load(temp_file)
        pygame.mixer.music.play()
        
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
            
        pygame.mixer.quit()
        # Small delay to ensure file is released before deletion
        try:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        except Exception:
            pass 

    except Exception as e:
        print(f"gTTS Error: {e}. Falling back to local.")
        speak_local(text)

def speak(text):
    if ELEVENLABS_API_KEY and ELEVENLABS_API_KEY.strip() != "your_api_key_here":
        speak_elevenlabs(text)
    else:
        # Prioritize gTTS for Indian accent over local pyttsx3
        speak_gtts(text)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
        speak(text)
