#ifndef PayloadDir
  #define PayloadDir "..\release\windows-portable\NEXA"
#endif
#ifndef ReleaseDir
  #define ReleaseDir "..\release"
#endif

[Setup]
AppId={{74FD409A-E081-427D-BEEA-FA1935B02724}
AppName=NEXA
AppVersion=1.7.1
AppPublisher=NXS MEDIA
DefaultDirName={localappdata}\Programs\NEXA
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#ReleaseDir}
OutputBaseFilename=NEXA-Setup
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\assets\branding\nexa-icon.ico
UninstallDisplayIcon={app}\NEXA.exe
CloseApplications=yes
SetupLogging=yes

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Excludes: ".env,installation-check.json,logs\*,config\settings.yaml"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#PayloadDir}\.env"; DestDir: "{app}"; Flags: onlyifdoesntexist

[Icons]
Name: "{userdesktop}\NEXA"; Filename: "{app}\NEXA.exe"; WorkingDir: "{app}"
Name: "{userprograms}\NEXA"; Filename: "{app}\NEXA.exe"; WorkingDir: "{app}"

[Run]
Filename: "{app}\NEXA.exe"; Description: "Launch NEXA"; Flags: nowait postinstall skipifsilent
