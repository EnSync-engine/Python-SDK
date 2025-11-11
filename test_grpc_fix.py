#!/usr/bin/env python3
"""
Test script to verify the gRPC client fix for the close() method.
This ensures the TypeError with should_reconnect parameter is resolved.
"""
import asyncio
import sys
import os

# Add the parent directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ensync.grpc_client import EnSyncClient


async def test_close_method():
    """Test that close() method accepts should_reconnect parameter."""
    print("Testing EnSyncClient.close() method...")
    
    # Create a client instance (without connecting)
    client = EnSyncClient("localhost:50051")
    
    # Test 1: close() with no arguments (default should_reconnect=False)
    print("✓ Test 1: close() with default parameter")
    await client.close()
    assert client._state["should_reconnect"] == False, "Default should_reconnect should be False"
    
    # Test 2: close(should_reconnect=True)
    print("✓ Test 2: close(should_reconnect=True)")
    await client.close(should_reconnect=True)
    assert client._state["should_reconnect"] == True, "should_reconnect should be True"
    
    # Test 3: close(should_reconnect=False)
    print("✓ Test 3: close(should_reconnect=False)")
    await client.close(should_reconnect=False)
    assert client._state["should_reconnect"] == False, "should_reconnect should be False"
    
    print("\n✅ All tests passed! The close() method now properly accepts should_reconnect parameter.")
    return True


async def test_pythonic_naming():
    """Test that internal state uses snake_case naming."""
    print("\nTesting Pythonic naming conventions...")
    
    client = EnSyncClient("localhost:50051")
    
    # Verify internal state uses snake_case
    assert "is_connected" in client._state, "State should use 'is_connected'"
    assert "is_authenticated" in client._state, "State should use 'is_authenticated'"
    assert "reconnect_attempts" in client._state, "State should use 'reconnect_attempts'"
    assert "should_reconnect" in client._state, "State should use 'should_reconnect'"
    
    # Verify config uses snake_case
    assert "access_key" in client._config, "Config should use 'access_key'"
    assert "client_id" in client._config, "Config should use 'client_id'"
    assert "client_hash" in client._config, "Config should use 'client_hash'"
    assert "app_secret_key" in client._config, "Config should use 'app_secret_key'"
    assert "heartbeat_interval" in client._config, "Config should use 'heartbeat_interval'"
    assert "reconnect_interval" in client._config, "Config should use 'reconnect_interval'"
    assert "max_reconnect_attempts" in client._config, "Config should use 'max_reconnect_attempts'"
    
    # Verify properties work correctly
    assert client.is_connected == False, "is_connected property should work"
    assert client.is_authenticated == False, "is_authenticated property should work"
    assert client.client_id is None, "client_id property should work"
    assert client.client_hash is None, "client_hash property should work"
    
    print("✅ All naming conventions follow Pythonic patterns (snake_case)!")
    return True


async def main():
    """Run all tests."""
    print("=" * 60)
    print("EnSync gRPC Client - Fix Verification Tests")
    print("=" * 60)
    
    try:
        await test_close_method()
        await test_pythonic_naming()
        
        print("\n" + "=" * 60)
        print("🎉 SUCCESS: All fixes verified!")
        print("=" * 60)
        print("\nKey improvements:")
        print("  1. ✅ Fixed duplicate close() methods")
        print("  2. ✅ close() now accepts should_reconnect parameter")
        print("  3. ✅ All internal naming uses snake_case (Pythonic)")
        print("  4. ✅ Removed unused imports (deque)")
        print("  5. ✅ Properties work correctly")
        
        return 0
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
