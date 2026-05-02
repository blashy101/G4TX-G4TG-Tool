# G4TX-G4TG-Tool

Extracts/Repacks .g4tx/.g4tg textures from PS4 versions of Yo-Kai Watch 4++ and Yōkai Wotchi Jam: Yōkai Gakuen Y N to no Sōgū (Y School Heroes).

This tool handles all the GNF steps in memory so you just deal with the .g4tx/.g4tg files.

Implements deswizzling and dimension calculation logic from https://gitgud.io/veiledmerc/freegnm 

When editing .DDS texture file, re-export it using the same compression format (BC7/BC3/BC1), without changing resolution or mipmaps! 

__________________________________________________________________________________________________________________________________________________________

Usage: 

python ykps4tool.py extract filename.g4tx

python ykps4tool.py validate filename.g4tx (scans current directory and compares DDS files to ones in original file to ensure compliance)

python ykps4tool.py import filename.g4tx

python ykps4tool.py batch_extract (scans current/subdirectories and exports DDS files from them)

python ykps4tool.py batch_import (the opposite of batch_extraction) 
