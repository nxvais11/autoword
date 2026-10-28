#ifndef AppVersion
#define AppVersion "0.9.0"
#endif
[Setup]
AppId={{31A7AF6F-723A-447F-A665-B099CF45A775}
AppName=AutoWord
AppVersion={#AppVersion}
AppPublisher=AutoWord
DefaultDirName={localappdata}\Programs\AutoWord
DefaultGroupName=AutoWord
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=AutoWord-Setup
SetupIconFile=..\CondominioFacil\autoword.ico
UninstallDisplayIcon={app}\AutoWord.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
AppMutex=Local\CondominioFacil
CloseApplications=no
RestartApplications=no
[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
[Files]
Source: "..\dist\windows\AutoWord\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{userdesktop}\AutoWord"; Filename: "{app}\AutoWord.exe"; WorkingDir: "{app}"
Name: "{group}\AutoWord"; Filename: "{app}\AutoWord.exe"; WorkingDir: "{app}"
[Run]
Filename: "{app}\AutoWord.exe"; Description: "Abrir AutoWord"; Flags: nowait postinstall skipifsilent
Filename: "{app}\AutoWord.exe"; Flags: nowait; Check: IsAutomaticUpdate
[Code]
function IsAutomaticUpdate: Boolean;
begin
  Result := ExpandConstant('{param:AUTOWORDUPDATE|0}') <> '0';
end;
