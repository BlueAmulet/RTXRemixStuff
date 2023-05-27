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

## Ini Tweaks
In Fallout.ini, set the following options:  
**[General]**  
`bAlwaysActive=1` Prevents a hang if the game is not active for too long

**[Display]**  
`bDoSpecularPass=0` Stops bright normals from being shown

**[Controls]**  
`bBackground Keyboard=0` Fixes Alt-X not opening the Remix UI

## Recommended Mods
[NewVegasRTXHelper](https://github.com/BlueAmulet/NewVegasRTXHelper/releases/latest)  
NVSE plugin to send lighting information and disable features that cause issues with Remix  
[Fallout Alpha Rendering Tweaks](https://www.nexusmods.com/newvegas/mods/80316) by Wall_SoGB  
Fixes some rendering bugs, notably "Alpha blending carrying over into meshes that don't have it enabled"

## Bad Textures
07252F80D34A9D78 textures\interface\interfaceshared0.dds  
Causes rasterization in conversations, otherwise needed

6DFF94A205779F01 textures\interface\hud\air_meter.dds  
FB101AF6B2A6925C textures\interface\hud\hud_compass_alphamap.dds  
E4064D279B9053C7 textures\interface\faders\white.dds  
Causes rasterization in interiors

46469FCAC447E09B textures\effects\fxdustsmallgen01.dds  
Not drawn properly, and ghosts badly
