import sys
import websockets

print(f"Python Executable: {sys.executable}")
print("\nSys Path:")
for p in sys.path:
    print(p)

print(f"\nWebsockets module location: {websockets.__file__}")
