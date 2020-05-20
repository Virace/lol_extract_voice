Ravioli Game Tools v2.10
Copyright (c) 2007-2017 Stefan Mayr

"Ravioli - The good stuff is inside"


Contents of this file
---------------------

1) Overview
2) System requirements
3) Features
4) Supported formats
5) Related tools 
6) The "Ravioli Generic Directory File" (*.rgd) format
7) License
8) History


1) Overview
-----------

The Ravioli Game Tools are a set of programs to explore, analyze and extract files from
various game resource files.

* Ravioli Explorer: View and extract the contents of archives.
* Ravioli Extractor: Automate extractions from archives.
* Ravioli Scanner: Helps analyzing unknown file formats.


2) System requirements
----------------------

* Windows 7 with SP1 and update KB2758857, Windows 8.1 or higher
  KB2758857 for 32-bit systems: https://www.microsoft.com/en-us/download/details.aspx?id=35903
  KB2758857 for 64-bit systems: https://www.microsoft.com/en-us/download/details.aspx?id=35936
* .NET Framework 4.5.1 (https://www.microsoft.com/en-us/download/details.aspx?id=40779)


3) Features
-----------

Ravioli Explorer:
* Browse and extract the contents of archives
* View text files and images, listen to sound files.
* View only specific file types using the file list filter
* View directory structure hierarchically or flat
* View the file list as details or thumbnails
* Convert images to standard formats like jpg, bmp or png
* Convert sounds to standard formats like wav or ogg
* Use drag and drop to open archives or extract files
* Open either single archives or all available resources of a game
* Scan unknown files for known resources like images and sounds

Ravioli Extractor:
* Extract multiple archives in one go
* Perform automated extractions
* Convert images to standard formats like jpg, bmp or png
* Convert sounds to standard formats like wav or ogg
* Scan unknown files for known resources like images and sounds
* Available as GUI and command-line version

Ravioli Scanner:
* Scan files of any type for known resources like images and sounds
* Extract the files found during a scan
* Combine extracted files back into one file
* View the exact locations of all the files found
* View the contents of unknown file parts
* View scanning statistics
* Save and load scanning results
* Available as GUI and command-line version


4) Supported formats
--------------------

Supported archive formats:

Name                          Extensions        Example games
-------------------------------------------------------------------------------------------------
Absolute Magic Resource File  .res              Evasive Maneuvers, Tubes, Catch, If You Can!
Arnie Goes 4 Gold GFX File    .gfx              Arnie Goes 4 Gold
Arnie Goes 4 Gold SFX File    .sfx              Arnie Goes 4 Gold
Audiosurf CGR File            .cgr              Audiosurf
BloodRayne POD File           .pod              BloodRayne 2
Brix BRX File                 .brx              Brix
Doom WAD (IWAD) File          .wad              Doom, Doom 2, Duke Nukem 3D
Dreamfall PAK File            .pak              Dreamfall
Elite Dangerous OVL File      .ovl              Elite Dangerous
FAB File                      .fab              Zumba Fitness Rush (Xbox 360),
                                                Zumba Fitness Core (Xbox 360)
FMOD Sample Bank (FSB3)       .fsb, .fsb3       BioShock
FMOD Sample Bank (FSB4)       .fsb, .fsb4       Zumba Fitness (Xbox 360), Star Trek Online
Her Interactive CIF File      .cif              Nancy Drew
Her Interactive CIF Tree      .dat, .cal        Nancy Drew
Her Interactive HIS File      .his              Nancy Drew
In The Groove PCK File        .pck              In The Groove
Jack Orlando PAK File         .pak, .pa2        Jack Orlando
League of Legends RAF File    .raf              League of Legends
League of Legends WAD File    .wad              League of Legends
League of Legends WPK File    .wpk              League of Legends
LithTech Resource File        .rez              Blood 2, No One Lives Forever
Minecraft PCK File            .pck              Minecraft (Xbox 360, PlayStation 3, Wii U)
Psychonauts PKG File          .pkg              Psychonauts
Quake PAK File                .pak              Quake, Quake 2, Half-Life, Counter-Strike
Quake WAD (WAD2/WAD3) File    .wad              Quake, Quake 2, Half-Life, Counter-Strike
Ravioli Generic Directory File   .rgd           N/A
Ravioli Scan Results File     .rsr              N/A
Reverge Package File          .gfs              Skullgirls
Saints Row 3/4 BNK_PC (VWSB) File    .bnk_pc    Saints Row: The Third, Saints Row IV
Saints Row 3/4 BNK_PC (WWISE) File   .bnk_pc    Saints Row: The Third, Saints Row IV
Saints Row 3/4 STR2_PC File         .str2_pc    Saints Row: The Third, Saints Row IV
Saints Row 3/4 VPP_PC (SB) File      .vpp_pc    Saints Row: The Third, Saints Row IV
Saints Row 3/4 VPP_PC File           .vpp_pc    Saints Row: The Third, Saints Row IV
Shockwave Flash File          .swf              Lots of online games
Snocka Watten SND File        .snd              Snocka Watten
Snocka Watten WBM File        .wbm              Snocka Watten
Star Trek Online HOGG File    .hogg             Star Trek Online
Stargunner DLT File           .dlt              Stargunner
Steam Game Cache File         .gcf              Half-Life 2, Portal
Steam No Cache File           .ncf              Poker Superstars II
STTNG IMG File                .img              Star Trek: The Next Generation - A Final Unity
Summer Athletics PAK File     .pak              Summer Athletics
Telltale AUD File             .aud              Sam & Max Season 1
The Longest Journey BBB File  .bbb              The Longest Journey
The Longest Journey OVS File  .ovs              The Longest Journey
The Longest Journey SSS File  .sss              The Longest Journey
The Longest Journey TM File   .tm               The Longest Journey
The Longest Journey XARC File .xarc             The Longest Journey
Tomb Raider Big File          .000              Tomb Raider: Legend, Anniversary, Underworld
Valve Pak                     .vpk              Left 4 Dead, Alien Swarm, Half-Life 2, Portal
Wwise Package File            .pck              Sleeping Dogs, Dishonored,
                                                Zumba Fitness Rush (Xbox 360),
                                                Zumba Fitness Core (Xbox 360),
Wwise Sound Bank              .bnk              Sleeping Dogs, World of Tanks,
                                                Kinect Adventures (Xbox 360),
                                                Zumba Fitness Rush (Xbox 360),
                                                Zumba Fitness Core (Xbox 360)
WWTBAM AWF File               .awf              Who Wants To Be A Millionaire, Wer wird Millionär
XACT3 Sound Bank              .xsb              Dance Evolution/Masters (Xbox 360)
XACT3 Wave Bank               .xwb              Dance Evolution/Masters (Xbox 360)
ZIP File                      .zip, .pak, .pk3, Far Cry, Quake 3, Star Trek: Voyager - Elite Force,
                              .pk4, .crf        System Shock 2

Credits:
* Dreamfall PAK File: File list for determining the file names by Deniz Özmen
  (http://oezmen.eu/gameresources/).
* Stargunner DLT File: Decompression routines based on code written by Adam Nielsen
  (http://www.shikadi.net/moddingwiki/DLT_Format).
* League of Legends WAD File: Uses Zstandard.Net by Bernhard Pichler
  (https://github.com/bp74/Zstandard.Net).


Included game viewers:

Name
---------------------------------------------------------
Alien Swarm
Angry Birds
Audiosurf
BloodRayne 2
Counter-Strike: Source
Dance Dance Revolution
Dance Evolution/Masters (Xbox 360)
Dreamfall
Emergency 4
Half-Life
Half-Life 2
Half-Life 2: Episode One
Half-Life 2: Episode Two
Half-Life: Blue Shift
Half-Life: Counter-Strike
Half-Life: Opposing Force
Half-Life: Source
In The Groove
League of Legends
Nancy Drew #14: Danger By Design
Nancy Drew #15: The Creature of Kapu Cave
Nancy Drew #16: The White Wolf of Icicle Creek
Nancy Drew #17: Legend of the Crystal Skull
Nancy Drew #18: The Phantom of Venice
Nancy Drew #19: The Haunting of Castle Malloy
Nancy Drew #20: Ransom of the Seven Ships
Nancy Drew #21: Warnings at Waverly Academy
Nancy Drew #22: Trail of the Twister
No One Lives Forever
No One Lives Forever 2
Portal
Portal 2
Saints Row IV
Saints Row IV: Inauguration Station
Saints Row: The Third
Saints Row: The Third - Initiation Station
Skullgirls
Star Trek Online
Star Trek: Elite Force II
Star Trek: Voyager - Elite Force
Stargunner
Summer Athletics
System Shock 2
Team Fortress 2
The Longest Journey
Tomb Raider: Anniversary
Tomb Raider: Legend
Tomb Raider: Underworld
Zumba Fitness (Xbox 360)
Zumba Fitness Core (Xbox 360)
Zumba Fitness Rush (Xbox 360)


Supported image formats:

Name                          Extensions         Operations
------------------------------------------------------------
Absolute Magic GFX File       .gfx               Load
DirectDraw Surface            .dds               Load
Graphics Interchange Format   .gif               Load, Save
JPEG/JFIF Compliant           .jpg, .jpeg, .jpe, Load, Save
                              .jfif, .jif
LithTech Texture              .dtx               Load
Portable Network Graphics     .png               Load, Save
Star Trek Online WTEX Texture .wtex              Load
The Longest Journey XMG File  .xmg               Load
Truevision Targa              .tga               Load
Valve Texture File            .vtf               Load
Windows Bitmap                .bmp, .dib         Load, Save
ZSoft Paintbrush              .pcx               Load

Credits:
* DirectDraw Surface: Code based on the Paint.NET DDS Plugin (http://www.getpaint.net/) by Dean Ashton (http://www.dmashton.co.uk/).
  Uses Squish (http://code.google.com/p/libsquish/) by Simon Brown (http://sjbrown.co.uk/)
* Valve Texture File: Uses VTFLib (http://www.nemesis.thewavelength.net/index.php?p=41)
  by Neil Jedrzejewski (http://www.wunderboy.org/) and Ryan Gregg (http://nemesis.thewavelength.net/).


Supported sound formats:

Name                          Extensions         Operations
-----------------------------------------------------------------------------------------
Absolute Magic SFX File       .sfx               Load, Export (to Wave)
MPEG Layer 3 Audio            .mp3               Load, Export (to MPEG Layer 3 Audio, Wave)
Ogg Vorbis                    .ogg               Load, Export (to Ogg Vorbis, Wave)
Wave                          .wav               Load, Export (to Wave)
Wwise Encoded Media           .wem               Load, Export (to Ogg Vorbis, Wave)


Credits:
* MPEG Layer 3 Audio/Ogg Vorbis/Wave:
  Uses the FMOD Sound System (http://www.fmod.org/products/fmodex.html),
  copyright © Firelight Technologies Pty, Ltd. (http://www.fmod.org/), 1994-2010.
* Wwise Encoded Media:
  Uses ww2ogg (http://hcs64.com/vgm_ripping.html) by Adam Gashlin (http://hcs64.com).
  Uses revorb (http://www.hydrogenaudio.org/forums/index.php?showtopic=64328)
  by Jiri Hruska.
  Uses wwise_ima_adpcm (https://bitbucket.org/zabb65/payday-2-modding-information/downloads)
  by Zwagoth Klaar (https://bitbucket.org/zabb65/)


File types supported by the scanner:

Name                          Extensions
-----------------------------------------------
  Image
DirectDraw Surface            .dds
Graphics Interchange Format   .gif
JPEG 2000                     .jp2
JPEG/JFIF Compliant           .jpg
Portable Network Graphics     .png
Truevision Targa              .tga
Windows Bitmap                .bmp

  Audio
MPEG Layer 1 Audio            .mp1
MPEG Layer 2 Audio            .mp2
MPEG Layer 3 Audio            .mp3
MPEG-4 Audio                  .m4a
Ogg Vorbis                    .ogg
Wave                          .wav
Windows Media Audio           .wma
Wwise Encoded Media           .wem
XMA                           .xma

  Video
Audio Video Interleave        .avi
Bink                          .bik
MPEG-4 Video                  .mp4
Ogg Theora                    .ogv
QuickTime                     .mov
Windows Media Video           .wmv

  Containers
Advanced Systems Format       .asf
FMOD Event File               .fev
FMOD Sample Bank (FSB4)       .fsb
ISO Base Media File           .isom
MPEG-4 File                   .mp4
Ogg File (generic)            .ogx
RAR File                      .rar
Resource Interchange File Format   .riff
Shockwave Flash File          .swf
ZIP File                      .zip


5) Related tools
----------------

Use the RAD Video Tools (http://www.radgametools.com/bnkdown.htm) to view Bink videos
(*.bik) that are used by many games.

To convert XMA files (*.xma) to Wave files (*.wav), the ToWav Music Converter
(http://www.ctpax-x.ru/index.php?goto=files&show=24) can be used. Not all XMA files can
be readily converted and a preliminary transformation may be required.


6) The "Ravioli Generic Directory File" (*.rgd) format
------------------------------------------------------

This is an XML-based file format that can be written by external applications to create
a directory structure for archives that can be read by the Ravioli Game Tools.
This works for simple items where the content can be extracted without modifications
(no decompression or decryption).

Every directory entry is described by Name, Offset and Length.

The file structure is as follows:

<!-- The XML file should be saved as UTF-8 if possible -->
<!-- If it's not UTF-8, change the encoding attribute appropriately -->
<?xml version="1.0" encoding="utf-8"?>
<GenericDirectory>
  <!-- Absolute or relative name of referenced archive file -->
  <!-- e.g. "Archive.dat" or "C:\Files\Archive.dat" -->
  <FileName>Archive.dat</FileName>
  <!-- Size of referenced archive file -->
  <FileSize>718837760</FileSize>
  <Entries>
    <!-- Name: File name relative to root of the directory -->
    <!-- e.g. "File1.dat" or "Dir1\File1.dat" -->
    <!-- Offset: Entry offset, signed 64-bit integer, zero-based, decimal -->
    <!-- Length: Entry length, signed 64-bit integer, decimal -->
    <DirectoryEntry Name="File0001.dat" Offset="0" Length="2658984" />
    <DirectoryEntry Name="File0002.dat" Offset="2658985" Length="654987" />
    <!-- Other directory entries go here -->
  </Entries>
</GenericDirectory>


7) License
----------

You can use this software free of charge.

You are allowed to redistribute the unmodified distribution package, as long as 
you don't charge anything for it.

You use this software at your own risk. The author is not responsible for any 
loss or damage resulting from the use of this software.


8) History
----------

Version 2.10
------------

General changes:

* The prerequisites to run Ravioli Game Tools have changed:
  - The .NET Framework 4.5.1 or higher is now required.
  - The minimum supported operating system is now Windows 7 with SP1 and update KB2758857.
  - The Visual C++ 2005 SP1 Runtime is no longer needed.


Framework changes:

* Added support for hybrid sound formats. The reported file type stays the same, while the actual
  sound format can vary between different files, similar to containers. This changes how the file
  type can be handled, for example the formats in which a sound can be converted to.

* When converting sounds, it is now possible to specify multiple sound formats to convert to. If a
  sound plug-in does not support converting a loaded sound to a target sound format, conversion to
  the next target sound format in the list is attempted.

* The CompressedItemsArchive class now allows specification of an alternate data file for
  extraction and a compression type for every item.

* Improved handling of nested archives for game viewers in AbstractorArchive class.

* The GenericArchive class now allows overriding the whole data extraction workflow implemented in
  the CopyData method. Overriding CopyData should be done with care and the only use case where
  this was required so far was to switch the input stream on the fly.


Ravioli Explorer application changes:

* Added an extraction option "Fallback sound format". If conversion of a sound to a specified
  target sound format is not supported, the application attempts to convert to the specified
  fallback format.

* Fixed a problem with sorting the file list by size if there are files with unknown size.

* Added a cache that improves performance for navigating the directory tree of large archives
  (more than 100000 files).


Ravioli Extractor application changes:

* Added an extraction option "Fallback sound format" (command line: /fallbacksoundformat or /fsf).
  If conversion of a sound to a specified target sound format is not supported, the application
  attempts to convert to the specified fallback format.


Changes in file format support:

* Added archive format: League of Legends WPK File (*.wpk)
  - Usually contains files of type "Wwise Encoded Media" (*.wem).

* Added archive format: League of Legends WAD File (*.wad)
  - This format does not contain file names, only numeric identifiers.
  - Files with the same identifiers would have the same file names. The file extensions are
    determined from the content.
  - Files with unidentified content are assigned the file extension ".dat".
  - Format versions 2 and 3 are supported.

* Added archive format: League of Legends RAF File (*.raf)
  - The uncompressed sizes of the files in this format are not known.

* Added game viewer: League of Legends
  - All versions of plug-in assets and file archives are combined in ascending order. Files in
    newer versions replace existing older files.

* Added archive format: Minecraft PCK File (*.pck)
 - Metadata is presented as text files (*.txt) along with the original items, encoded as UTF-8.
 - Tested with files from PlayStation 3, Wii U and Xbox 360 versions.

* Updated image format: DirectDraw Surface (*.dds)
  - Added a workaround to allow loading of DDS files created by older versions of ImageMagick
    (before version 6.3.9-3), as these versions produce DDS files with malformed headers.
  - The DDS scanner was also updated to be able to detect such malformed DDS files.

* Added sound format: Wwise Encoded Media (*.wem)
  - This is the official name and file extension for Wwise sounds.
  - Replaces existing Wwise sound formats (Wwise PCM/ADPCM/Vorbis, *.wwise_p/a/v).
  - To convert sound from this format into the best possible target format, set "Ogg Vorbis" as
    target format and "Wave" as fallback format. Conversion to Wave is always possible.
  - The Wwise scanner was also updated to detect the new format.

* Updated archive format: Elite Dangerous OVL File (*.ovl)
 - Fixed reading audio banks.
 - Improved error message for unsupported resource types.


Version 2.9
-----------

General changes:

* Beginning with this version, there is the official possibility for other software developers to
  write their own plug-ins for the Ravioli Game Tools. This is made possible using a separate
  Software Development Kit (SDK) download, called the "Ravioli SDK", which contains interface
  libraries, documentation and sample code.
  
  Experience in .NET programming, preferably in the C# language, is required. Using an appropriate
  development environment, like Microsoft Visual Studio, is highly recommended.
  
  The first version of the SDK supports only development of new archive plug-ins. Other Ravioli
  extension points are not officially supported until documented in the Ravioli SDK.


Framework changes:

* Added support for nested archives in Game Viewers in a generic way. Only one nesting level
  is supported.
  
* Added the possibility to specify multiple archive types for a file in Game Viewers. Only the
  plug-in for which the archive type is valid loads the file. An error occurs if the file is not
  valid for any of the specified types.

* The ArchiveBase class now implements a new set of operations to support opening an archive from
  a stream and not directly from a file, for example when using nested archives in a Game Viewer.
  This is an automatic opt-in for all archives based on ArchiveBase, but the individual archive
  implementations must still be written correctly to make this actually work.

* Added an archive base class CompressedArchive that supports archives whose items are compressed.

* Extended the sound player interface ISoundPlayer2 to also return the duration of a sound.


Ravioli Explorer application changes:

* The status bar in the preview and view windows now show also the duration of a sound.

* Fixed a crash that can occur when a potential long-running operation (opening an archive,
  for example) is already completed before the "Please wait" dialog is shown.

* If an image or sound conversion fails, the affected file is no longer extracted automatically
  without conversion.


Ravioli Extractor application changes:

* If an image or sound conversion fails, the affected file is no longer extracted automatically
  without conversion.


Ravioli Scanner application changes:

* Fixed a crash that can occur when a potential long-running operation (extracting, for example)
  is already completed before the "Please wait" dialog is shown.

* Improved the "Combine" function: The dialog to confirm enlarging a file that is smaller than the
  original file now contains a "Yes to all" button to enlarge all further files automatically
  without asking again.


Added support for archive, sound and image files:

* Archive types of the Saints Row series
  - Saints Row 3/4 BNK_PC (VWSB) File (*.bnk_pc)
  - Saints Row 3/4 BNK_PC (WWISE) File (*.bnk_pc)
  - Saints Row 3/4 STR2_PC File (*.str2_pc)
  - Saints Row 3/4 VPP_PC (SB) File (*.vpp_pc)
  - Saints Row 3/4 VPP_PC File (*.vpp_pc)

* Reverge Package File (*.gfs)
  - Used by games like Skullgirls.

* Elite Dangerous OVL File (*.ovl)

* FMOD Sample Bank (FSB3) (*.fsb, *.fsb3)
  - Used by games like BioShock.
  - This is a backport of the FSB4 format with the data structures updated to match the FSB3 format.
  - Only the file extraction from BioShock files has been tested. Sound playing and conversion
    should work in the same way as with FSB4.

* Wwise ADPCM (*.wwise_a)
  - Can be played and converted to Wave files within the application.
  - Conversion happens via the external tool "wwise_ima_adpcm" (v1.15).
  - Tested with files from World of Tanks and Mass Effect 2.
  - The official file extension for all Wwise formats is WEM (Wwise Encoded Media), but this
    is not used here to be able to distinguish the Wwise formats easier.

* Wwise PCM (*.wwise_p)
  - Can be played and converted to Wave files within the application.
  - Tested with files from Elite Dangerous.
  - The official file extension for all Wwise formats is WEM (Wwise Encoded Media), but this
    is not used here to be able to distinguish the Wwise formats easier.


Updated support for archive, sound and image files:

* Star Trek Online HOGG File (*.hogg)
  - Renamed from "STO HOGG File"
  - Fixed errors when opening files of this type.

* Star Trek Online WTEX Texture (*.wtex)
  - Renamed from "STO WTEX Texture".

* Tomb Raider Big File (*.000)
  - Improved file type recognition so that the program does no longer attempt to open
    arbitrary *.000 files.

* Wave (*.wav), MPEG Layer 3 Audio (*.mp3), Ogg Vorbis (*.ogg)
  - Updated to support reading the duration of a sound.

 * Wwise Vorbis (*.wwise_v)
   - Updated to use the file extension .wwise_v instead of .wwise. 
   - Updated to support reading the duration of a sound.
   - Updated ww2ogg to version 0.24 to support more file format variants.
   - Improved RevorbWrapper.
   - The official file extension for all Wwise formats is WEM (Wwise Encoded Media), but this
     is not used here to be able to distinguish the Wwise formats easier.

* Wwise Package File (*.PCK)
  - Renamed from "Wwise PCK File".
  - Updated to support PCK files of the game "Dishonored".

* FMOD Sample Bank (FSB4) (*.fsb, *.fsb4)
  - Updated to support 8-bit encoded raw PCM sounds.

  
Added new game viewers:

* Saints Row series
  - Saints Row: The Third
  - Saints Row: The Third - Initiation Station
  - Saints Row IV
  - Saints Row IV: Inauguration Station

  Nested sound files (*_media.bnk_pc) are loaded automatically. Nested texture files (*.str2_pc)
  are not loaded at all because the high number of small files make the loading process very long
  and navigation in the Explorer very slow.

* Skullgirls


Updated the following game viewers:

* Tomb Raider Legend, Anniversary and Underworld
  - Fixed loading errors when opening the viewer.

* Half-Life
  - Fixed loading errors because of the no longer existing "gldrv" directory in Steam versions.
 

Version 2.8
-----------

Framework changes:

* Scanning plug-ins are now loaded dynamically.
* If a conversion between two sound formats is not supported, the error message that is
  generated while extracting a file now contains the names of the formats involved.
  

Ravioli Explorer application changes:

* Fixed highlighting of installed games in the "Open Game" dialog on Windows 7.

* Added support for files in archives where the size is unknown at load time.
  The following behavior happens now for such files:
  - In the file list in details view, a question mark (?) is shown in the "Size" column.
  - The total size in the status bar at the bottom of the screen shows the known size plus
    a question mark to indicate that the total size is not exact (ex. "120 MB +?").
  - When previewing a file and the size of the file is found to be larger than the
    internal preview size limit while reading its contents, the content is discarded and
    the preview is skipped.

* Changed the default size of the "View" window to be the same as the "View" window in
  the "Ravioli Scanner" application.


Added support for archive, sound and image files:

* STO HOGG File (*.hogg) (Star Trek Online)
  - The main archive format for "Star Trek Online".

* STO WTEX Texture (*.wtex)
  - These textures are found inside STO HOGG files (*.hogg).
  - Multiple format versions of WTEX textures exist. Only the one format that uses
    DXT compression is supported.

* Wwise Vorbis (*.wwise)
  - Can be played and converted to Ogg Vorbis within the application.
  - Conversion happens via the external tools "ww2ogg" (v0.20) and "revorb" (v0.2).
  - The use of external tools requires writing the files to disk for any operation. This
    may cause delays for large files.
  - The files can be encoded in different variants, depending on the Wwise version used.
    To find the correct variant, multiple attempts to convert the sound may be required,
    and this may cause delays for large files.
  - Tested using files from Saints Row: The Third, Mass Effect 2 and Sleeping Dogs.


Updated support for archive, sound and image files:

* DirectDraw Surface (*.dds)
  - Added support for DDS alpha format (A8).

* Valve Pak (*.vpk)
  - Renamed from "Valve Pack File".
  - Updated to support format version 2.
  - Fixed failing to extract files if the VPK file name contains multiple underscores.

* Wwise Sound Bank (*.bnk) and Wwise PCK File (*.pck)
  - Wwise Vorbis files are now given a separate file extension (*.wwise) to distinguish
    them clearly from standard Wave files (*.wav).
  - Added a way to distinguish PC and Xbox 360 variants automatically. This is not 100
    percent fail-safe but worked for all files it was tested with. Tested using files
    from Sleeping Dogs and Zumba Fitness Core (Xbox 360).
  
* FMOD Sample Bank (FSB4) (*.fsb, *.fsb4)
  - Renamed from "FSB4 Sound Bank".
  - Added support for Raw PCM and MPEG (MP2/MP3) formats.
  - Raw PCM sounds are converted to standalone Wave files (*.wav).
  - MP2/MP3 sounds (incl. streaming sounds) are converted to standalone files (*.mp2/*.mp3).

* Ogg Vorbis (*.ogg)
  - Allows exporting the sound in its own format, just copies the source data.

* MPEG Layer 3 Audio (*.mp3)
  - Allows exporting the sound in its own format, just copies the source data.


Added new game viewers:

* Star Trek Online
  - The sounds in the FSB files (*.fsb) cannot be listened to directly.
  - Not all texture formats are supported. In WTEX files (*.wtex), only one texture
    format is supported and HTEX files (*.htex) are not supported at all.

* Team Fortress 2
  - Only the SteamPipe version is supported, older GCF-based versions are not.

* Angry Birds


Updated the following game viewers:

* Updated the following game viewers to work with the new formats used by the SteamPipe
  content distribution system:
  - Half-Life
  - Half-Life: Counter-Strike
  - Half-Life: Opposing Force
  - Half-Life: Blue Shift
  - Half-Life: Source
  - Counter-Strike: Source
  - Half-Life 2
  - Half-Life 2: Episode One
  - Half-Life 2: Episode Two
  - Portal
  - Portal 2

  For the games "Half-Life", "Half-Life: Counter-Strike", "Half-Life: Opposing Force" and
  "Half-Life: Blue Shift", files for the optional "Half-Life High Definition Pack" are
  also loaded if they exist (in "valve_hd", "gearbox_hd" and "bshift_hd" subdirectories).

  For the game "Half-Life: Source", files for the optional "Half-Life High Definition
  Pack" are also loaded if they exist (in "hl1_hd" subdirectory).


Added scanning support for the following file types:

* FMOD Sample Bank (FSB4) (*.fsb)
  - Container format for audio files.
  - Supports little-endian variant, this is used on both PC and Xbox 360.

* FMOD Event File (*.fev)
  - This file type does not contain any multimedia content but is used together with
    FSB files.

* Wwise Vorbis (*.wwise)
  - Supports little-endian (PC) and big-endian (Xbox 360) variants.


Updated scanning support for the following file types:

* Added support for APEv2 tags in MPEG audio files (*.mp1/*.mp2/*.mp3)
  - If the tag is detected, it is saved along with the audio data.
  - The tag must be present after the audio data and must have a header.


Version 2.7
-----------

Framework changes:

* All components have been upgraded to .NET Framework 4.0. The .NET Framework 4.0 or
  higher is now required to use the Ravioli Game Tools.

* Added support for archives that need to be completely decompressed before the
  individual files in it - which are not further encoded or encrypted - can be accessed
  ("generic compressed archive").

* The available sound export formats are now dynamically enumerated from the plug-ins.
  Previously, this list was hard coded.


Ravioli Explorer application changes:

* Sound export now works while a sound is playing. The sound stops playing, the export is
  performed, and playing resumes afterwards (the last only if the sound player supports
  seeking, which all currently included players do).

* File extensions shown in the filter list are now sorted alphabetically.


Ravioli Extractor application changes:

* The extraction process can now be stopped properly while a file is being scanned.

* Small user interface adaptions.


Ravioli Scanner application changes:

* In the list of detected files, it is now possible to navigate to the previous or next
  item of a specific media type, allowing to jump from one unknown item to the next, for
  example.

* Scanning can now be performed within a specific range of a file only. A new option "Ask
  For Scan Range" can be enabled to have the application ask for a range when starting a
  scan. In the command-line version, ranges can be specified using the new parameter
  "/range".

* The restriction, that the whole file must have been scanned completely before the
  "Combine" function can be used, has been removed.


Added support for archive, sound and image files:

* FAB File (*.fab)
  - Supports big-endian (Xbox 360) variant.
  - Tested with Zumba Fitness Rush (Xbox 360) and Zumba Fitness Core (Xbox 360).


Updated support for archive, sound and image files:

* DirectDraw Surface (*.dds):
  - Added support for DDS luminance format (L8).
  - Fixed memory errors (stack imbalance) that occurred while decompressing DXT textures.

* Ogg Vorbis (*.ogg)/MPEG Layer 3 Audio (*.mp3)/Wave (*.wav):
  - Added exporting to Wave (*.wav) format.
    Converting Wave to Wave is just a roundtrip and doesn't actually convert anything.

* Wwise Sound Bank (*.bnk)
  - Added support for the PC version of this format, tested with Sleeping Dogs.
  - The implementation cannot distinguish between the PC and Xbox 360 versions.
    You have to specify the file type when opening such files.
  
* Wwise PCK File (*.pck)
  - Renamed from "PCK (AKPK) File".
  - Added a way to distinguish PC and Xbox 360 variants automatically. This is not 100
    percent fail-safe but worked for all files it was tested with.
  - Added support for sound banks within PCK files. Previously, PCK files containing
    sound banks could be opened, but the sound banks were ignored. If no other files
    besides sound banks were present, the PCK file appeared to be empty.
  - Added support for multi-language content. Every language is shown as a directory.
    Language-independent content is also put into its own directory (typically "sfx").

* Valve Texture File (*.vtf)
  - Updated for improved VTF support (VTFLib 1.3.1 -> 1.3.2)


Added new game viewers:

* Zumba Fitness Rush (Xbox 360)

* Zumba Fitness Core (Xbox 360)


Updated scanning support for the following file types:

* JPEG/JFIF Compliant (*.jpg):
  - JPEG images starting with a comment can now be detected.


Version 2.6
-----------

Framework changes:

* It is now possible to convert sound formats from inside the tools, similar to
  the existing functionality to convert images.

  The major difference between sound and image conversion is, that the image conversion
  is a generic solution and the sound conversion is not. You can convert any recognized
  image format to any supported target format, while for the sound conversion the
  sound player that supports the source format is also responsible for exporting the
  sound data to the target format. 

  If a sound player does not support exporting at all or does not support exporting to
  the specified target sound format, warnings are generated during extraction and the
  affected files are extracted without any conversion.
  
* Reduced the number of progress messages when scanning a file. This enhances the scanning
  performance if many items are found in a file.


Ravioli Explorer application changes:

* Updated to support sound format conversions.
  Sound conversions are possible in 3 places in the application:
  - When extracting files from an archive using the "Extract" function.
    In the extraction dialog, a target sound format can now be specified to which all
    recognized sounds should be converted during an extraction.
  - When listening to a sound in the preview area.
    The "Save" button in the preview area is now enabled if a sound is loaded that can be
    exported to a different format. When using the Save button, always the preferred
    export format (as defined by the sound player implementation) is preselected in the
    save dialog.
  - When listening to a sound using the "View" function.
    This works in the same way as in the preview area.
    
* The user can now choose, whenever an unknown file type is encountered, whether he or
  she wants to
  - scan the file for known resources
  - always scan unknown files
  - skip scanning the file
  - never perform scans on unknown files
  Previously, the user could only scan the file or skip scanning the file. The options
  for unknown files can be changed at any time in the options menu.
  
* When a file is opened in an external application while a sound is playing in the
  preview area, the sound is stopped.


Ravioli Extractor application changes:

* Updated user interface and command-line version to support sound format conversions.
  It is now possible to specify a target sound format to which all recognized sounds
  should be converted during an extraction.
  
* Added the possibility to scan unknown files.
  The extraction is now on par with the extraction of the Ravioli Explorer. If you can
  open a file and extract it with the Ravioli Explorer, the Ravioli Extractor will be
  able to extract it as well.
  
  Scanning of unknown files does not happen by default and must be enabled. In the user
  interface there is a new option "Allow scanning of unknown files", and in the command-
  line version there is a new parameter "/allowscanning" to enable this feature.


Ravioli Scanner application changes:

* Fixed a crash when trying to scan a file with a size of 0 bytes.

* The viewer now shows the first and last 32 KB of a file if a file is larger than 64 KB.
  Previously just the first 64 KB of a file were shown in this case.

* The scanner now verifies that a detector returns only file types that it also declares.


Changes in support for archive, sound and image files:

* Added decompression support for content in Stargunner DLT files.
  Decompression routines based on code written by Adam Nielsen
  (http://www.shikadi.net/moddingwiki/DLT_Format).

* Added support for decoding 16-color PCX images.

* Added a game viewer for Portal 2.
  Supports also the files that are part of the DLCs "Peer Review" and
  "Perpetual Testing Initiative".

* Added ".fsb4" file extension to the "FSB4 Sound Bank" archive type
  (previously only ".fsb").

* Fixed an error in the "FSB4 Sound Bank" type where in some files more bytes than available
  were read for a directory entry.

* Added a game viewer for Stargunner.

* Complete rewrite of LithTech Texture (*.dtx) support to remove dependencies to native
  libraries that are only available as 32-bit versions.
  The following image formats are supported:
  - 8-bit indexed
  - 32-bit true color, with the following compression types:
    Uncompressed, DXT1, DXT3, DXT5

* Added support for Absolute Magic Resource File (*.res) archives
  (used by Evasive Maneuvers, Tubes and Catch, If You Can!).

* Added support for Absolute Magic GFX File (*.gfx) images
  (used by Evasive Maneuvers, Tubes and Catch, If You Can!).

* Added support for Absolute Magic SFX File (*.sfx) sounds
  (used by Evasive Maneuvers, Tubes and Catch, If You Can!).
  Supports exporting to Wave (*.wav) sound format.
  
* Fixed an out-of-memory situation in all sound players that occurred after attempting
  to play a few files in unsupported formats.

* Added support for PCK (AKPK) File (*.pck)
  - Supports PC and Xbox 360 variants.
  - Tested with Sleeping Dogs (PC) and Zumba Fitness Rush (Xbox 360).
  - The implementation cannot distinguish between the PC and Xbox 360 versions.
    You have to specify the file type when opening such files.


Added scanning support for the following file types:

* ISO Base Media File (*.isom)
  - This is the base format for several other file formats like MPEG-4 or JPEG 2000.
  - This file type is only reported if the derived file format is unknown.
  - Only files containing a "File Type" box are detected. Older versions of this format
    exist which did not require this box.

* MPEG-4 File (*.mp4)
  - This file type is reported for MPEG-4 files with neither an audio nor a video track.
  - One of the MPEG-4 brands ("mp41", "mp42") must be the major brand and one of the
    compatible brands in the ISO Base Media File.

* MPEG-4 Audio (*.m4a)
  - This file type is reported for MPEG-4 files having an audio track and no video track.
  - One of the MPEG-4 brands ("mp41", "mp42") must be the major brand and one of the
    compatible brands in the ISO Base Media File.

* MPEG-4 Video (*.mp4)
  - This file type is reported for MPEG-4 files having a video track.
  - One of the MPEG-4 brands ("mp41", "mp42") must be the major brand and one of the
    compatible brands in the ISO Base Media File.

* JPEG 2000 (*.jp2)
  - This file type is reported for JPEG 2000 images.
  - The JPEG 2000 brand ("jp2 ") must be the major brand and one of the compatible brands
    in the ISO Base Media File.

* QuickTime (*.mov)
  - This file type is reported for QuickTime movies.
  - The QuickTime brand ("qt  ") must be the major brand and one of the compatible brands
    in the ISO Base Media File.
    
* Bink (*.bik)
  - This file type is reported for Bink videos.
  
* RAR File (*.rar)
  - This file type is reported for RAR compressed files.
  - Supports older format versions without an "end of archive" header as well as
    newer versions with such a header.


Updated scanning support for the following file types:

* Wave (*.wav)
  - Made changes to detect if Wave files are padded correctly.

    If a Wave file is not correctly padded, it is not conforming to the specification
    and the correct end of the file might not be found. This in turn can cause other
    files in an archive not to be detected by the scanner. By detecting a missing
    padding, the correct end of the Wave file can be determined.

    The padding detection works only in certain situations, for example if Wave files
    are back-to-back in an archive or if an archive ends immediately after a Wave file.

    Files with missing padding are reported as broken but may play or convert without
    any issues if the player or converter processing these files can handle this
    situation.
    
    This change affects not only Wave files, but also other RIFF-based file formats
    like AVI, but it was done primarily for Wave files.


Version 2.5
-----------

Plug-in changes:

* Added support for opening CIFTREE.DAT files in Nancy Drew #14: Danger By Design
  and older.

* Added support for opening CAL files external to a CIF Tree in Nancy Drew games.

* Added a game viewer for Nancy Drew #14: Danger By Design

* Renamed "Theora" file type to "Ogg Theora".


Ravioli Scanner changes:

* Added a new function to recombine extracted files.
  This enables modification of items and putting them back together when finished.

  Using this function requires that all parts of the file, including all unknown parts,
  have been extracted before.

  Modified items must have the same size than the original items. If a modified item is
  smaller than the original item, the program can enlarge the file up to the original
  size automatically. If a modified item is larger, the program does not resize the file
  automatically and combining will not be allowed.

* Added a "Please wait" window shown for longer operations, such as extracting or
  combining. 

* Enhanced log output. If nothing was found at a specific position, but log outputs have
  been created by a detector, a separator is now inserted in the log.


Version 2.4
-----------

Added scanning support for the following file types:

* XMA (*.xma)
  - The native sound format of the Xbox 360 console.
  - Supports XMA v1 and XMA2 (format tags 0x165 and 0x166).
  - Supports little-endian (Windows) and big-endian (Xbox 360) variants.

* Windows Media Video (*.wmv)
  - A resource is reported as Windows Media Video if an ASF container is present with a WMV video stream and a WMA audio stream or just a WMV video stream without audio.
  - The following FourCC codes are used to detect whether a video stream is a WMV video stream:
    Windows Media Video FourCC codes
    * MPG4 = Microsoft MPEG-4 version 1
    * MP42 = Microsoft MPEG-4 version 2
    * MP43 = Microsoft MPEG-4 version 3
    * MP4S = Microsoft ISO MPEG-4 version 1
    * M4S2 = Microsoft ISO MPEG-4 version 1.1
    * WMV1 = Windows Media Video 7
    * MSS1 = Windows Media Screen 7
    * WMV2 = Windows Media Video 8
    * WMV3 = Windows Media Video 9
    * MSS2 = Windows Media Video 9 Screen
    * WMVP = Windows Media Video 9.1 Image
    * WVP2 = Windows Media Video 9.1 Image V2
    * WMVA = Windows Media Video 9 Advanced Profile
    * WVC1 = Windows Media Video 9 Advanced Profile

* Windows Media Audio (*.wma)
  - A resource is reported as Windows Media Audio if an ASF container is present with a WMA audio stream and no video stream.
  - The following format tags are used to detect whether an audio stream is a WMA audio stream:
    Windows Media Audio codec IDs / format tags
    * 0x161 = Windows Media Audio (v7-v9 Series)
    * 0x162 = Windows Media Audio 9 Professional (v9 Series)
    * 0x163 = Windows Media Audio 9 Lossless (v9 Series)

* Advanced Systems Format (*.asf)

* Resource Interchange File Format (*.riff)
  - Supports little-endian (Windows) and big-endian (Xbox 360) variants.


Updated scanning support for the following file types:

* Wave (*.wav)
  - Complete rewrite of implementation for improved detection.
  - Supports little-endian (Windows) and big-endian (Xbox 360) variants.

* Audio Video Interleave (*.avi)
  - Complete rewrite of implementation for improved detection.
  - Preserves JUNK chunks used for padding.
  - Supports OpenDML extended AVI (AVIX).


Added support for archives:

* XACT3 Wave Bank (*.xwb) (Dance Evolution/Masters (Xbox 360))
  - Supports little-endian (Windows) and big-endian (Xbox 360) variants.
  - Adds headers to PCM, ADPCM and XMA sounds, to make them playable standalone. These headers are always written in little-endian format. For XMA sounds, always XMA v1 headers are generated.
  - XACT3 Wave Banks do not contain the names of their sounds. These can only be stored externally, for example in an XACT3 Sound Bank.

* XACT3 Sound Bank (*.xsb)  (Dance Evolution/Masters (Xbox 360))
  - Supports little-endian (Windows) and big-endian (Xbox 360) variants.
  - XACT3 Sound Banks do not contain actual sounds, they only reference sounds in XACT3 Wave Banks.
  - XACT3 Sound Banks usually contain sound names, but they don't have to.

* Wwise Sound Bank (*.bnk) (Kinect Adventures (Xbox 360))
  - Supports big-endian (Xbox 360) variant.
  - Wwise Sound Banks do not contain the names of their sounds. These can only be stored externally, for example in a text file.

* FSB4 Sound Bank (*.fsb) (Zumba Fitness (Xbox 360))
  - Supports little-endian variant, this is also used on the Xbox 360.
  - Assumes that the sounds in the sound bank are always in XMA format and thus always generates an XMA (v1) header for all sounds.



Updated archive support:

* Fixed several archive plug-ins that extracted more bytes than requested if not all bytes of a file are required, for example to identify a file.

* Fixed endless loop when extracting from Ravioli Scan Results (*.rsr) files and the input stream ends unexpectedly.


Added new game viewers:

* Dance Evolution/Masters (Xbox 360)
  - Supports sounds and movies.

* Zumba Fitness (Xbox 360)
  - Supports audio and video files.


Application and framework changes:

* Added a new special archive type "Ravioli Generic Directory File" (*.rgd). This is an XML-based file format that can be written by external applications to create a directory structure for archives that can be read by the Ravioli Game Tools. This works for simple items where the content can be extracted without modifications (no compressed or encrypted items). Every directory entry is described by Name, Offset and Length.

The file structure is as follows:

<!-- The XML file should be saved as UTF-8 if possible -->
<!-- If it's not UTF-8, change the encoding attribute appropriately -->
<?xml version="1.0" encoding="utf-8"?>
<GenericDirectory>
  <!-- Absolute or relative name of referenced archive file -->
  <!-- e.g. "Archive.dat" or "C:\Files\Archive.dat" -->
  <FileName>Archive.dat</FileName>
  <!-- Size of referenced archive file -->
  <FileSize>718837760</FileSize>
  <Entries>
    <!-- Name: File name relative to root of the directory -->
    <!-- e.g. "File1.dat" or "Dir1\File1.dat" -->
    <!-- Offset: Entry offset, signed 64-bit integer, zero-based, decimal -->
    <!-- Length: Entry length, signed 64-bit integer, decimal -->
    <DirectoryEntry Name="File0001.dat" Offset="0" Length="2658984" />
    <DirectoryEntry Name="File0002.dat" Offset="2658985" Length="654987" />
    <!-- Other directory entries go here -->
  </Entries>
</GenericDirectory>

* Scanning framework
  - Scanning is now about 3 times (or 66%) faster than in the previous version due to improved buffering logic.
  - Detectors previously categorized as "Other" are now categorized as "Container".
  - Log output now contains a separator line after after every file found. Makes the log easier to read.
  - Fixed a crash of the scanner when a scanning plug-in incorrectly returns negative file lengths.

* Ravioli Explorer
  - The text viewer now replaces binary zeroes by spaces to make the text display better.

* Ravioli Scanner
  - The console version now expects the file name to be specified first and then optionally any actions or options. If no action is specified, the files found during the scan are listed.
  - The console version now shows scanning statistics in the order 1) Type, 2) Count, similar to the GUI version.
  - The GUI version now features type distribution statistics. These statistics show how many images, sounds, etc. were found in total in a file. There is also a chart that visualizes where these resources were found within the file.


Version 2.3
-----------

Plug-in changes: (without scanning plug-ins, follow below)

* Added support for the Shockwave Flash File (*.swf) (Used by lots of online games).
  The following assets can be extracted:
  - Sounds (does not convert formats, extracts content as it is)
  - Streaming sounds (does not convert formats, extracts content as it is)
  - Lossless bitmaps (8-bit indexed with RGB colors, 24-bit RGB, 8-bit indexed with RGBA colors, 32-bit RGBA; 15-bit RGB images are not supported) - exported as PNG
  - JPEG bitmaps (via shared JPEG tables, as standard JPEG bitmap or as JPEG bitmap with alpha channel; other extensions to the JPEG bitmap - like deblocking - are not supported)
  - PNG and GIF89a bitmaps
* Enhanced ZIP file support:
  - ZIP files can now be opened independent of file extension.
  - ZIP files that are appended to a stub executable can also be detected.
  - Fixed extracting files from ZIP files with a data descriptor.
* Added support for the Valve Pack File (*.vpk) (Used by Left 4 Dead and Alien Swarm)
* Updated VTF Support to support newer VTF format versions (VTFLib 1.2.7 -> 1.3.1)
* Added game viewer for Alien Swarm
* Added game viewer for Nancy Drew: #22 Trail of the Twister
* Renamed "Ogg Vorbis File" plug-in to "Ogg Vorbis"
* Renamed "Wave File" plug-in to "Wave"

Scanning plug-in changes:

* Added support for detecting Windows Bitmap (*.bmp) image files.
* Added support for detecting Shockwave Flash (*.swf) animation files.
* Added support for detecting Truevision Targa (*.tga) image files.
  - Supports TGA 1.0 and 2.0 images
  - Supports 16, 24, and 32-bit uncompressed and RLE compressed images
  - Indexed images are not supported
* Added support for detecting Audio Video Interleave (*.avi) video files.
* Added support for detecting ZIP compressed files (*.zip).
* Fixed missing 128 bytes on all detected DirectDraw Surface (*.dds) images.
* Fixed frame length calculation for MPEG-2/2.5 Layer 3 (*.mp3) audio.
* Renamed "Ogg (generic)" detector to "Ogg File (generic)".
* Renamed "Ogg Vorbis File" detector to "Ogg Vorbis".
* Renamed "Wave File" detector to "Wave".

Ravioli Explorer changes:

* Changed error message for unknown file types. Does not show a list of possible plug-ins that are available for a file extension any longer.
* Fixed loading and scanning progress windows not always centered within the main window.
* Renamed "Full Games" plug-in types to "Game Viewers"
* Fixed exception if opening an invalid scan results file.

Ravioli Scanner changes:

* Added option to create a scanning log (GUI version only).
* Application can now keep all scan results found so far when stopping a scan (GUI version only).
* Switched file types and count columns in the statistics tab (GUI version only).
* Added support for handling compressed and animated file types.


Version 2.2
-----------

New features:

* Added a new module that allows scanning of files for known resources like images and sounds.

The following file types can be detected:

* Image:
  - DirectDraw Surface (.dds)
  - Graphics Interchange Format (.gif)
  - JPEG/JFIF Compliant (.jpg)
  - Portable Network Graphics (.png)
* Audio:
  - MPEG Layer 1 Audio (.mp1)
  - MPEG Layer 2 Audio (.mp2)
  - MPEG Layer 3 Audio (.mp3)
  - Ogg Vorbis File (.ogg)
  - Wave File (.wav)
* Video:
  - Theora (.ogv)
* Other:
  - Ogg (generic) (.ogx)

The scanner is accessible in multiple ways:

* Via the Ravioli Explorer, if you just want to see what's inside. If opening a file and the file type is unknown, the Explorer offers to scan the file. The results of the scan can be viewed like the contents of other archives. Scanning is enabled by default and can be disabled in the options as well as the confirmation message shown before scanning.
* Via the Ravioli Scanner, if you want to find out more about the file format. The Ravioli Scanner is a new dedicated application for scanning and includes features to help analyzing file formats. See further below for more information about the Ravioli Scanner.
* Via the Ravioli Scanner Console, if you want to automate scanning. This is the command line version of the Ravioli Scanner.

Notes about the scanning process:

* The time it takes to scan a file depends on the file size and the number of items found.
* Detection works only if the content is not encrypted or encoded in any way.
* If a data block appears to be of a certain file type, but is found to no longer match the specification later on or is simply truncated, the text "broken" is appended to file names of such detected files.

Notes about MPEG audio detection:

* At least 10 frames of MPEG audio data are required in succession to accept MPEG audio data as such. This is to prevent false positives, but also means that small files with less than 10 frames will not be detected.
* Supports ID3v1, ID3v2, Lyrics3 and Lyrics3v2 tags. If any of these tags is found, it is saved along with the audio data.
* If there is a tag stored before the audio data, like ID3v2, the audio data must follow immediately after the end of the tag. The 10 frame audio data minimum also still applies here. 
* If there is a tag stored after the audio data, like ID3v1, and the audio data does not end exactly at the end of a frame, the tag contents might be truncated.

Features of the Ravioli Scanner:

* Scan files of any type for known resources like images and sounds
* Extract the files found during a scan
* View the exact locations of all the files found
* View the contents of unknown file parts
* View scanning statistics
* Save and load scanning results
* Available as GUI and console version

Changes to the Ravioli Explorer:

* Added access to the new scanning module for unknown files (see "New Features" above).
* Changed thumbnail spacing to 150x150 px in thumbnail view. This allows a few more thumbnails to be displayed, while still being able to display most file names without cutting them off.
* Temporary files are now created in subdirectories based on the process ID. Previously, only a directory for the archive name was created. Using the process ID ensures that multiple instances of the application do not conflict with each other.
* The last open archive is now closed properly when exiting the application.
* Changed the function "Open" to "Open File" to better differenciate it from the "Open Game" function.
* Fixed a crash when no game viewers are installed and the "Open Game" function is used.
* Size and position of the main application window and the viewer window are now saved and restored.
* In the preview and view window now only the toolbar buttons that apply to the shown file type are displayed (e.g. "Zoom in" for images or "Play" for sounds). Previously, the buttons that did not apply to the file type were just disabled, which took up unnecessary space.
* The default startup behaviour has been changed to do nothing. Previously, the "Open File" dialog was shown on startup. The option to change the startup behaviour is still available, where you can change to the old behaviour, if needed.

Plug-in changes:

* Changed Stargunner DLT File: Added file names, but actual content of the files in the archive * re still in an unknown compressed format.
* Added Jack Orlando PAK File: Supports also decoding of the music tracks and some of the sound effects. Tested only with the original version, not the director's cut.
* Added BloodRayne POD File: Might work for other Infernal Engine games as well if the format is the same.
* Added Ravioli Scan Results File: Contains saved scan results of the new Ravioli Scanner.
* Added Summer Athletics PAK File: File names for sound, speech and music are recovered partially. Graphics files are unnamed and in an unknown compressed format.
* Changed MP3 File: Renamed to "MPEG Layer 3 Audio" and plays now also on x64 systems. 
* Added Audiosurf CGR File: Decodes music downloaded from the web (Audiosurf Radio).
* Changed ZSoft Paintbrush:
  - Fixed loading error if no DPI settings are present in a file.
  - Image loading is now faster (removed unsafe code).
* Changed Ogg Vorbis File: Plays now also on x64 systems.
* Changed LithTech Texture: Image loading is now faster (removed unsafe code).
* Changed Wave File: Plays now both PCM and ADPCM files.

Game viewer changes:
* Added Emergency 4
* Added Summer Athletics
* Added System Shock 2: Assumes that all compressed resource files are in the game directory, does not look into any configuration file. If no compressed resource files are in the game dir, but instead in a subdirectory "res", then a modded installation is assumed and uncompressed resource files from the file system in the game dir are also loaded after the compressed ones. If compressed resource files also exist in a subdirectory "patch", they will always be loaded as the last step, regardless if modded or not.
* Added Audiosurf
* Added BloodRayne 2
* Added Portal (based on english version)


Version 2.1
-----------

Architecture changes:
* Added image format autodetection. Several image formats can now be detected by 
  file content and not only by file extension. The plug-ins that are installed 
  with this version recognize the following image formats: DDS, JPG, BMP, GIF, 
  PNG and VTF. 
* The integration of the "Full Game" viewers to display all available resources 
  of a specific game has been improved. The full game viewers are now 
  implemented as a separate plug-in type. 
* Improved plug-in detection code. 

Changes to the Ravioli Explorer:
* Added a new function "Open Game" to access the supported full game viewers. 
  You do no longer open a file to access a full game viewer. 
* Added handling of archive type ambiguities. If a file that is to be opened can 
  be handled by multiple plug-ins, a disambiguation dialog is shown where the 
  user can select the correct type. Previously, just the first matching type was 
  used, without informing the user. 
* Added support for the new image format autodetection mechanism. The functions 
  Preview, View, Thumbnails and Convert images on extraction have been adapted 
  appropriately. 
* Added a "Loading" message while opening an archive. 
* If the root directory of an archive is selected in the hierarchical view, the 
  extract function now defaults to extract all files instead of the current 
  directory. 
* If images are converted during extraction or are saved from within preview or 
  view functions and the source file is already in the destination format, the 
  conversion is now skipped and the file is just extracted normally. 
* The last directory used for saving images in preview or view functions is now 
  kept separately from the last extraction directory since their meaning is 
  different. 
* Improved the memory management for the file list. Both the flat view and the 
  thumbnail view now display their entries much faster than before. 
* Fixed the sort indicator in the header of the details view. 

Details about the new "Open Game" function:

This function is for viewing all available resources of a game instead of having 
to open single archive files. You do this by by clicking the "Open Game" button. 
Then the "Open Game" window displays a list of games for which a full game 
viewer is available. If you have one of the listed games installed, select it, 
specify its installation directory and click OK.

If an installation of a game is found in one of its default installation 
directories, the entry for the game is highlighted and you do not have to 
specify the installation directory. Please note that the list of default 
installation directories is not guaranteed to be complete. In most cases it will 
contain the retail version directory and/or one or more directories where it is 
available when installed via a digital distribution service, such as Steam.

Changes to the Ravioli Extractor:
* Added support for the new full game plug-ins by allowing also directory names 
  as input besides file names. 
* Added the possibility to explicitly specify the archive type to override the 
  default autodetection mechanism. 
* Added a "Loading" message while opening an archive. 
* Added handling of archive type ambiguities. If a file that is to be opened can 
  be handled by multiple plug-ins, an error message is shown and the achive type 
  must be explicitly specifed as parameter. Previously, just the first matching 
  type was used without informing the user. 
* Added support for the new image format autodetection mechanism. The function 
  "Convert image on extraction" has been adapted appropriately. 
* If images are converted during extraction and the source file is already in 
  the destination format, the conversion is now skipped and the file is just 
  extracted normally. 

Plug-in changes:

Action      Type          Name                                  Comments
-----------------------------------------------------------------------------------------------------------------------
Added       Archive       Her Interactive CIF File (*.cif)      Used by Nancy Drew games.
Added       Archive       Her Interactive CIF Tree (*.dat)      Used by Nancy Drew games.
Added       Archive       Tomb Raider Big File (*.000)          Used by Tomb Raider: Legend, Anniversary and Underworld.
Added       Archive       Stargunner DLT File (*.dlt)           Used by Stargunner.
Updated     Archive       Her Interactive HIS File (*.his)      Now supports also newer Nancy Drew games like
                                                                "Ransom of the Seven Ships".
Updated     Archive       ZIP File (*.zip, etc.)                Fixed opening ZIP files that have a data descriptor.
Updated     Archive       The Longest Journey TM File (*.tm)    Does not use mipmaps any longer.
Added       Image         Valve Texture File (*.vtf)            For viewing the materials of the Half-Life 2 series or
                                                                other Source Engine games using this format.
Updated     Image         Truevision Targa (*.tga)              Complete rewrite to fix various loading issues.
Updated     Image         LithTech Texture (*.dtx)              True Color DTX images are now returned as 32-bit images.
                                                                Previously the transparency has been ignored and only 
                                                                24-bit images were returned.
Removed     Image         Tagged Image File Format (*.tif)      It's no use supporting this format for games.
Updated     Sound         Wave File (*.wav)                     Fixed an issue that could lead to application crashes.
Added       Full Game     In The Groove                         Detects updates to version R2.
Added       Full Game     Nancy Drew: #15: The Creature of Kapu Cave
Added       Full Game     Nancy Drew: #16: The White Wolf of Icicle Creek
Added       Full Game     Nancy Drew: #17: Legend of the Crystal Skull
Added       Full Game     Nancy Drew: #18: The Phantom of Venice
Added       Full Game     Nancy Drew: #19: The Haunting of Castle Malloy
Added       Full Game     Nancy Drew: #20: Ransom of the Seven Ships
Added       Full Game     Nancy Drew: #21: Warnings at Waverly Academy
Added       Full Game     Half-Life 2
Added       Full Game     Half-Life 2: Episode One              The oldest GCFs, such as Source Engine GCFs, are loaded
                                                                first and updated files in newer GCFs replace older ones.
                                                                Tested against the english version of the Orange Box.
Added       Full Game     Half-Life 2: Episode Two              The oldest GCFs, such as Source Engine GCFs, are loaded
                                                                first and updated files in newer GCFs replace older ones.
                                                                Tested against the english version of the Orange Box.
Added       Full Game     No One Lives Forever                  Detects updates to versions from 1.001 to 1.004 as well
                                                                as the Game Of The Year Edition.
Added       Full Game     No One Lives Forever 2                Detects updates to version 1.3.
Added       Full Game     Star Trek: Elite Force II
Added       Full Game     Star Trek: Voyager - Elite Force
Added       Full Game     Half-Life                             Does not support viewing textures in the WAD files in
                                                                the Steam version of the game.
Added       Full Game     Half-Life: Counter-Strike             Does not support viewing textures in the WAD files in
                                                                the Steam version of the game.
Added       Full Game     Half-Life: Opposing Force             Does not support viewing textures in the WAD files in
                                                                the Steam version of the game.
Added       Full Game     Half-Life: Blue Shift                 Does not support viewing textures in the WAD files in
                                                                the Steam version of the game.
Added       Full Game     Half-Life: Source
Added       Full Game     Counter-Strike: Source
Added       Full Game     Tomb Raider: Legend
Added       Full Game     Tomb Raider: Anniversary
Added       Full Game     Tomb Raider: Underworld
Updated     Full Game     Dreamfall                             Does no longer display resources grouped by PAK file
                                                                if the file names are known. Only if the file name of an
                                                                entry is unknown, such entries continue to be displayed
                                                                in their own subdirectories.


Version 2.0
-----------

* The PCK Tools are now known as "Ravioli Game Tools". Respectively, the PCK 
  Explorer is now "Ravioli Explorer" and the PCK Extractor is the "Ravioli 
  Extractor". Ravioli - The good stuff is inside.
* Reorganized plug-ins
* New archive plug-ins:
  - Brix BRX file (*.brx) 
  - Arnie Goes 4 Gold GFX file (*.gfx) -> In a few images, not all colors are 
    correct. 
  - STTNG IMG File (*.img) 
  - Her Interactive HIS File (*.his) 
* Changed archive plug-ins:
  - Added jar extension to the ZIP file plugin. 
* New sound players:
  - MP3 File (*.mp3) -> Works on 32-bit systems only! 
  - Ogg Vorbis File (*.ogg) -> Works on 32-bit systems only! 
* Introduced new plug-ins that allow viewing and extracting all resource files 
  belonging to a game at once, instead of having to open every resource file one 
  by one. To view all resources of a game, specify its main game executable 
  (.exe) file when opening a file. The executable serves as a key file to 
  determine the game's install location. In some situations it may be required 
  to read data also from the executable to locate resources.

  This release includes the following plug-ins for viewing all resources at once 
  for the following games:
  - The Longest Journey 
  - Dreamfall 
  - Dance Dance Revolution 

  The "The Longest Journey" batch extractor that has been separately available 
  for download until now is now obsolete since all resources can now be 
  extracted using the new "The Longest Journey" plug-in.

  The "Dance Dance Revolution" plug-in requires the game CD in your CD-ROM drive 
  to view all the resources. Alternatively, can also copy original_data.bin from 
  the CD into the game directory if you want to.

* Added a file list for files in Dreamfall resource files. This list was 
  compiled by Deniz Özmen.
  The Dreamfall file list covers the following Dreamfall editions:
  - German version 
  - Limited Edition (LE) 
  - Web download version from www.dreamfall.com 
  - Ialian version patch v1.01 
  - French version patch v1.02 
  - French version patch v1.03 
  - American version patch v1.03 
* Changes to the Ravioli Explorer:
  - New features: 
    * A hierarchical view for directories. This makes it so much better to 
      browse through large archives, and it is also the default directory view 
      beginning with this version. You can switch between the flat view, which 
      has previously been the only view, and the new hierarchical view at any 
      time. 
    * Thumbnail display. When you view a directory that contains supported image 
      files, the files can be displayed as thumbnails now, instead of only 
      listing the files. Because generating the thumbnails can be time 
      consuming, displaying the thumbnails is turned off by default and can be 
      enabled in the options menu. 
    * File list sorting, now complete this time. Previously, you could click on 
      the columns of the file list to sort it. But there were no possibilites to 
      use the keyboard to set the sort order, and the setting was also not 
      saved. The sort settings are now saved properly and the sort order can 
      also be changed in the options menu now. 
    * View all files in an archive as text also, regardless of the perceived 
      type. 
    * Startup behaviour can now be changed, the default is to open a file as in 
      the previous versions. 
    * Added support for extracting files via drag and drop. 
  - Changes: 
    * Separated the sound preview options: You can now specify whether you want 
      to preview sounds at all and whether the sounds should automatically be 
      played when a supported sound file is selected. Previously, only the 
      second option was possible - you could only prevent the sound from being 
      played automatically but not prevent the loading of the file. 
    * Reorganized the extraction dialog with a few group boxes. 
    * The last archive directory is now properly remembered when passing an 
      archive on the command line or when using drag and drop to open a file. 
    * When viewing a text file now also the detected encoding is shown. 
    * Changed the encoding detection mechanism for viewing text files. If no 
      Unicode or UTF-8 byte order marks are detected, the system's default ANSI 
      code page is now used. Previously the default was to use UTF-8, which 
      worked fine with UTF-8 files without byte order marks, but broke several 
      other ANSI-encoded files. 


Version 1.2
-----------

* Included 32-bit C++ runtime that is required for certain parts of the 
  package. On 64-bit systems the C++ runtime must be installed separately. 
* It is now possible that warnings are issued during file extraction. 
  These do not stop the extraction but may be important enough to be 
  reported. The base extractor issues a warning when an image conversion 
  fails. Other warnings depend on archive plugin implementation. 
* New archive formats: 
  - The Longest Journey BBB File (bbb) 
  - The Longest Journey TM File (tm) 
  - Arnie Goes 4 Gold SFX File (sfx) 
  - Snocka Watten SND File (snd) 
  - Snocka Watten WBM File (wbm) 
* New image formats: 
  - ZSoft Paintbrush (pcx) 
* Most of the archive implementations now use code page 1252 (Windows) for 
  reading file names, alternative charsets such as ISO-8859-1 are used as 
  needed or if specified by the file format. 
* DDS (DirectDraw Surface) support enhanced: 
  - Upgraded image processing code. 
  - Viewing DDS files is now possible on 64-bit systems. 
* ZIP File support enhanced: 
  - Loading is now faster. 
  - If invalid timestamps are encountered, the current time is used 
    instead and a warning is issued. 
* DTX (LithTech Texture) images are now processed correctly in their 
  actual format. Previously all DTX files were processed as 32-bit images 
  regardless of the actual format. Note: Viewing DTX files is currently 
  not possible on 64-bit systems. 
* Changes in the PCK Explorer: 
  - New feature: Image zooming. For the preview window, there also a new 
    option to keep the zoom locked. 
  - New feature: Drag and Drop support. Can now open archives that are 
    dropped on an open application window. 
  - In the dialogs for opening archives the filter for all supported types 
    no longer contains the actual file extensions. This doesn't make sense 
    when there are many file extensions and it looks also funny on Windows 
    Vista. (This change is visible in the PCK Extractor too). 
  - Changed the text "All files" to "All files in archive" in the 
    extraction dialog to make the meaning clear. 
  - The file extension filter now treats extensions with different case as 
    the same extension 
  - When viewing an image, now also the color depth is shown. 
  - When viewing files with no specific support, it is shown whether it is 
    a text file or a binary file. 
  - File type names are now correctly displayed on 64-bit systems. 
  - Introduced an Options menu, moved existing settings to this one 
