# # save as check_devices.py and run it
# import pyaudio
# p = pyaudio.PyAudio()
# for i in range(p.get_device_count()):
#     d = p.get_device_info_by_index(i)
#     if d['maxInputChannels'] > 0:
#         print(f"Index {i}: {d['name']}")
# p.terminate()


# check_devices.py
# import pyaudio
# p = pyaudio.PyAudio()

# wasapi_host = None
# for i in range(p.get_host_api_count()):
#     api = p.get_host_api_info_by_index(i)
#     print(f"API {i}: {api['name']}")
#     if 'WASAPI' in api['name']:
#         wasapi_host = i

# print("\n--- Input devices ---")
# for i in range(p.get_device_count()):
#     d = p.get_device_info_by_index(i)
#     if d['maxInputChannels'] > 0:
#         print(f"  Index {i} | API {d['hostApi']} | {d['name']}")

# p.terminate()



# # scan_wasapi.py
# import sounddevice as sd
# print(sd.query_devices())



# list_voices.py
from elevenlabs.client import ElevenLabs
import os
from dotenv import load_dotenv
load_dotenv()

client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))
for v in client.voices.get_all().voices:
    print(f"{v.name:20} {v.voice_id}")