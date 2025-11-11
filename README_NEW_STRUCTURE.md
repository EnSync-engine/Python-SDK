# EnSync Python SDK - New Multi-Package Structure

The EnSync Python SDK has been restructured into three separate pip packages for better modularity and lighter installations.

## 📦 Package Structure

```
python-sdk/
├── ensync-core/              # Core utilities package
│   ├── ensync_core/
│   │   ├── __init__.py
│   │   ├── ecc_crypto.py    # Encryption/decryption utilities
│   │   └── error.py         # Error handling
│   ├── setup.py
│   ├── README.md
│   └── MANIFEST.in
│
├── ensync-sdk/               # gRPC client package (main SDK)
│   ├── ensync_grpc/
│   │   ├── __init__.py
│   │   ├── grpc_client.py   # gRPC client implementation
│   │   ├── ensync_pb2.py    # Protocol buffers
│   │   └── ensync_pb2_grpc.py
│   ├── tests/
│   │   ├── example_publisher.py
│   │   └── example_subscriber.py
│   ├── setup.py
│   ├── README.md
│   └── MANIFEST.in
│
└── ensync-sdk-ws/         # WebSocket client package
    ├── ensync_sdk_ws/
    │   ├── __init__.py
    │   └── websocket.py     # WebSocket client implementation
    ├── tests/
    │   ├── example_publisher.py
    │   └── example_subscriber.py
    ├── setup.py
    ├── README.md
    └── MANIFEST.in
```

## 🚀 Installation

### For gRPC (Recommended for Production)

```bash
pip install ensync-sdk
```

This automatically installs `ensync-core` as a dependency.

### For WebSocket

```bash
pip install ensync-sdk-ws
```

This automatically installs `ensync-core` as a dependency.

## 📝 Usage

### gRPC Client

```python
from ensync_sdk import EnSyncEngine

# Initialize and create client
engine = EnSyncEngine("node.ensync.cloud")
client = await engine.create_client("your-app-key")

# Publish event
await client.publish("event/name", ["recipient-id"], {"data": "value"})

# Subscribe to events
subscription = await client.subscribe("event/name")
subscription.on(lambda event: print(event))
```

### WebSocket Client

```python
from ensync_sdk_ws import EnSyncEngine

# Initialize and create client
engine = EnSyncEngine("wss://node.ensync.cloud")
client = await engine.create_client("your-app-key")

# Publish event
await client.publish("event/name", ["recipient-id"], {"data": "value"})

# Subscribe to events
subscription = await client.subscribe("event/name")
subscription.on(lambda event: print(event))
```

## 🔧 Development

### Building Packages Locally

```bash
# Build ensync-core
cd ensync-core
python setup.py sdist bdist_wheel

# Build ensync-sdk
cd ensync-sdk
python setup.py sdist bdist_wheel

# Build ensync-sdk-ws
cd ensync-sdk-ws
python setup.py sdist bdist_wheel
```

### Installing in Development Mode

```bash
pip install -e ensync-core/
pip install -e ensync-sdk/
pip install -e ensync-sdk-ws/
```

### Running Tests

```bash
# Test gRPC client
cd ensync-sdk/tests
python example_publisher.py
python example_subscriber.py

# Test WebSocket client
cd ensync-sdk-ws/tests
python example_publisher.py
python example_subscriber.py
```

## 📤 Publishing to PyPI

Use the provided deployment script:

```bash
./deploy-all.sh
```

This will deploy all three packages in the correct order (core → sdk → websocket).

**Important**: `ensync-core` must be published first since the other packages depend on it.

## 📚 Documentation

- **PACKAGES.md** - Detailed package overview
- **MIGRATION_GUIDE.md** - Guide for migrating from old `ensync-sdk`
- **deploy-all.sh** - Automated deployment script

## 🎯 Benefits of This Structure

1. **Modular Installation** - Install only what you need
2. **Smaller Package Size** - No unnecessary dependencies
3. **Independent Versioning** - Update packages separately
4. **Clear Separation** - Better code organization
5. **Easier Maintenance** - Changes isolated to specific packages

## 📦 Package Dependencies

```
ensync-sdk
└── ensync-core
    └── pynacl>=1.5.0

ensync-sdk-ws
└── ensync-core
    └── pynacl>=1.5.0
```

## 🔄 Migration from Old Structure

If you were using the old `ensync-sdk` (v0.3.x) package:

1. For gRPC users: `pip install --upgrade ensync-sdk` (imports stay the same!)
2. For WebSocket users: Uninstall old package and install `ensync-sdk-ws`
3. See MIGRATION_GUIDE.md for details

## 📋 Package Versions

- **ensync-core**: 0.1.0
- **ensync-sdk**: 0.4.0
- **ensync-sdk-ws**: 0.4.0

## 🆘 Support

- GitHub: https://github.com/EnSync-engine/Python-SDK
- Documentation: https://ensync.cloud
- Email: info@ensync.io
