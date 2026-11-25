#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{7E1D6C2B-5A43-4E9B-9C3F-2B8A61D0E5A4}
AppName=RutaSegura
AppVersion={#AppVersion}
DefaultDirName={autopf}\RutaSegura
DefaultGroupName=RutaSegura
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputBaseFilename=RutaSegura-{#AppVersion}-instalador
UninstallDisplayIcon={app}\RutaSegura.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "..\dist\RutaSegura\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\RutaSegura"; Filename: "{app}\RutaSegura.exe"
Name: "{autodesktop}\RutaSegura"; Filename: "{app}\RutaSegura.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\RutaSegura.exe"; Description: "Abrir RutaSegura"; Flags: nowait postinstall skipifsilent
