#ifndef PayloadDir
  #define PayloadDir "..\release\windows-portable\NEXA"
#endif
#ifndef ReleaseDir
  #define ReleaseDir "..\release"
#endif

[Setup]
AppId={code:InstallAppId}
UsePreviousLanguage=no
AppName=NEXA
AppVersion=1.7.2
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
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Excludes: ".env,installation-check.json,release-payload-check.json,logs\*,config\settings.yaml"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#PayloadDir}\.env"; DestDir: "{app}"; Flags: onlyifdoesntexist

[Icons]
Name: "{userdesktop}\NEXA"; Filename: "{app}\NEXA.exe"; WorkingDir: "{app}"; Check: not IsReleaseTest
Name: "{userprograms}\NEXA"; Filename: "{app}\NEXA.exe"; WorkingDir: "{app}"; Check: not IsReleaseTest

[Run]
Filename: "{app}\NEXA.exe"; Description: "Launch NEXA"; Flags: nowait postinstall skipifsilent

[Code]
// Test the exact distributable without replacing the developer's installed
// application registration or shortcuts. The public/default AppId is unchanged.
function IsReleaseTest: Boolean;
begin
  Result := ExpandConstant('{param:NEXA_TEST_INSTALL|0}') = '1';
end;

function InstallAppId(Param: String): String;
begin
  if IsReleaseTest then
    Result := '{5361D67D-364B-44D6-8C58-3A49C4909C26}'
  else
    Result := '{74FD409A-E081-427D-BEEA-FA1935B02724}';
end;
