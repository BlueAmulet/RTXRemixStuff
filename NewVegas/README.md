# Fallout New Vegas related RTX Stuff

## Contents
**rtx.conf:**  
Minimal RTX Remix config to get started with, sky and interface textures marked  
**NewVegas RTX Mesh Patches.zip:**  
Mesh patches to fix issues with Remix  
**usdagen.py:**  
Parses through a textures folder and generates corresponding roughness maps and a USDA

**texhashes.txt:**  
A mapping of texture hashes and texture paths from the game's two Texture archives, likely missing DLC

## Recommended Mods
[NewVegasRTXHelper](https://github.com/BlueAmulet/NewVegasRTXHelper/releases/latest)  
NVSE plugin to send lighting information and disable features that cause issues with Remix  
[Fallout Alpha Rendering Tweaks](https://www.nexusmods.com/newvegas/mods/80316) by Wall_SoGB  
Fixes some rendering bugs, notably "Alpha blending carrying over into meshes that don't have it enabled"

## Bad Textures
07252F80D34A9D78 textures\interface\interfaceshared0.dds Causes rasterization in conversations
