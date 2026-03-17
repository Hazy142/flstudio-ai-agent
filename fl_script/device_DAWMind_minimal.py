# name=DAWMind Minimal Test
#
# Minimal test script to verify FL Studio detects the device.
# If this shows up in MIDI Settings > Controller type as
# "DAWMind Minimal Test (user)" then FL Studio script loading works.

def OnInit():
    print("[DAWMind Minimal] Script loaded successfully!")
    print("[DAWMind Minimal] If you see this, FL Studio found the script.")

def OnDeInit():
    print("[DAWMind Minimal] Script unloaded.")

def OnIdle():
    pass
